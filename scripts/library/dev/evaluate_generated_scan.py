#!/usr/bin/env python3
"""Project-level mechanical scan for the /evaluate-generated skill (quick mode).

Performs the deterministic parts of the skill's Phases 1-4 — service
inventory from the parsed DSL, manifest aggregation, project infrastructure
existence checks, docker-compose service-entry cross-check, and the
critical-blocker / warning rollup — and emits the per-service deep-dive
prompt files from the skill's Phase 6 template.

The .dtrx source is parsed with the real pipeline (TreeSitterParser +
SemanticAnalyzer), never with regexes. Service directory naming reuses
``datrix_common.paths.ServicePaths`` — the same transform the generators use.

Usage:
  python scripts/library/dev/evaluate_generated_scan.py \
      --source examples/01-foundation/system.dtrx \
      --generated D:/datrix/.generated/python/docker-compose/local/01-foundation
  .\\scripts\\dev\\evaluate-generated-scan.ps1 -Source <system.dtrx> -Generated <dir>
"""

from __future__ import annotations

import argparse
import fnmatch
import io
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Configure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add library directory to sys.path to import from shared
library_dir = Path(__file__).resolve().parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

from shared.venv import get_datrix_root  # noqa: E402

datrix_root = get_datrix_root()
for _sub in ("datrix-common/src", "datrix-language/src"):
    _pkg_path = datrix_root / _sub
    if _pkg_path.exists() and str(_pkg_path) not in sys.path:
        sys.path.insert(0, str(_pkg_path))

import yaml  # noqa: E402
from datrix_common.config_resolution import (  # noqa: E402
    ConfigResolutionError,
    resolve_service_configs,
)
from datrix_common.datrix_model.containers import Application  # noqa: E402
from datrix_common.paths import ServicePaths  # noqa: E402
from datrix_common.semantic import SemanticAnalyzer  # noqa: E402
from datrix_language.parser import TreeSitterParser  # noqa: E402
from datrix_language.registration import register_all  # noqa: E402

logger = logging.getLogger(__name__)

# ── Constants ──

SCHEMA_VERSION = 1
EXIT_OK = 0
EXIT_USAGE = 2

SYSTEM_DTRX_FILENAME = "system.dtrx"
#: generate.ps1's default -ConfigProfile; config resolution needs one.
DEFAULT_CONFIG_PROFILE = "test"
MANIFEST_SUBDIR = ".datrix/manifests"
PROJECT_SCAN_FILENAME = "project-scan.json"
EVAL_SUBDIR = "eval"
TMP_SUBDIR = ".tmp"
MAX_REPORTED_PARSE_ERRORS = 5

#: Manifest entries not under a service directory are grouped under this key.
PROJECT_LEVEL_KEY = "_project"

#: Cache/VCS directories excluded from any filesystem scan.
IGNORED_DIR_NAMES = frozenset({
    "__pycache__",
    ".ruff_cache",
    ".pytest_cache",
    ".mypy_cache",
    ".git",
    "node_modules",
    ".venv",
})

# Language detection probes (skill Phase 2a).
PYTHON_PROBE_FILES: tuple[str, ...] = ("pyproject.toml", "requirements.txt")
TYPESCRIPT_PROBE_FILES: tuple[str, ...] = ("package.json", "tsconfig.json")
LANGUAGE_PYTHON = "Python"
LANGUAGE_TYPESCRIPT = "TypeScript"
LANGUAGE_UNKNOWN = "Unknown"

# Platform detection: docker-compose.yml presence first (skill Phase 2a),
# then known runtime segments of the generated output path as fallback.
PLATFORM_DOCKER = "Docker"
PLATFORM_AWS = "AWS"
PLATFORM_AZURE = "Azure"
PLATFORM_UNKNOWN = "Unknown"
AWS_PATH_SEGMENTS = frozenset({"aws", "ecs-fargate", "app-runner"})
AZURE_PATH_SEGMENTS = frozenset({"azure", "azure-container-apps", "azure-app-service"})
DOCKER_PATH_SEGMENTS = frozenset({"docker", "docker-compose", "local"})

# Project-level infrastructure files (skill Phase 3).
DOCKER_COMPOSE_FILENAME = "docker-compose.yml"
INFRA_CHECKS: tuple[tuple[str, str], ...] = (
    ("docker_compose", DOCKER_COMPOSE_FILENAME),
    ("env_example", ".env.example"),
    ("nginx_conf", "config/nginx/nginx.conf"),
    ("prometheus_config", "config/prometheus/prometheus.yml"),
    ("grafana_dir", "config/grafana"),
)

GATEWAY_TOKENS: tuple[str, ...] = ("nginx", "gateway")
OBSERVABILITY_TOKENS: tuple[str, ...] = ("prometheus", "grafana", "jaeger", "loki")
#: Observability container token -> infra check key whose config must exist.
OBSERVABILITY_CONFIG_KEYS: tuple[tuple[str, str], ...] = (
    ("prometheus", "prometheus_config"),
    ("grafana", "grafana_dir"),
)

# Per-service deep-dive prompt (skill Phase 6a content template).
PROMPT_FILENAME_TEMPLATE = "service-{name}.prompt.md"
PROMPT_TEMPLATE = """# Service Evaluation Prompt

**Service:** {service_name}
**Project:** {system_name}
**Evaluation Session:** {eval_dir}

---

## Instructions

This prompt file was generated by `/evaluate-generated` (quick mode). Invoke \
`/evaluate-generated-service` per its own SKILL.md, passing:

```
PROMPT_FILE: {prompt_path}
```

---

## Service Context

**Service Name:** {service_name}
**Qualified Name:** {qualified_name}
**Source .dtrx:** `{service_dtrx}`
**Generated Directory:** `{generated_dir}`
**Project Source:** `{system_dtrx}`
**Language:** {language}
**Platform:** {platform}

---

## Project-Level Context

**System Name:** {system_name}
**Total Services:** {total_services}
**Gateway Enabled:** {gateway_enabled}
**Observability Enabled:** {observability_enabled}

---

## Quick Scan Results (from project-level evaluation)

**Service Directory Exists:** {dir_exists}
**Files in Manifests:** {manifest_file_count} (approximate, filtered by service name pattern)

---

## Evaluation Scope

Full scope per `/evaluate-generated-service`'s own SKILL.md (DSL analysis, \
generated-output scan, cross-reference, semantic verification, dead-code \
detection, deployment readiness assessment, report generation in \
`{report_path}`).

---

## Expected Output

**Report Path:** `{report_path}`

The report should include:
- Service DSL analysis (entities, blocks, APIs)
- Generated output analysis (files, manifests)
- Completeness verification (missing items)
- Semantic correctness issues (transpilation bugs)
- Dead code detection (unused modules, dependencies)
- Deployment readiness assessment
- Generator-side fixes needed

---

## Notes

- This is part of a project-wide evaluation session
- Project-level quick scan: `{scan_path}`
- Other service prompts available in `{eval_dir}`
"""


class ScanInputError(Exception):
    """Raised for missing or unreadable required input (maps to exit code 2)."""


# ── Shared data structures ──


@dataclass(frozen=True)
class ServiceRecord:
    """Naming facts for one DSL service, via the generators' own transform."""

    qualified_name: str
    simple_name: str
    kebab_name: str
    service_dir: str
    compose_name: str
    dtrx_path: str


@dataclass(frozen=True)
class ManifestData:
    """Summary of one .datrix/manifests/<target>.json file."""

    target: str
    path: Path
    generated_at: str
    files: tuple[str, ...]
    user_files: tuple[str, ...]
    append_only_files: tuple[str, ...]

    @property
    def all_tracked(self) -> tuple[str, ...]:
        """Every path the manifest claims, including scaffolding."""
        return self.files + self.user_files + self.append_only_files


# ── Shared helpers (also imported by evaluate_service_scan.py) ──


def configure_logging(debug: bool) -> None:
    """Configure root logging; DEBUG when --debug was passed."""
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def local_timestamp() -> str:
    """ISO local timestamp for the generated_at field."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json_object(path: Path) -> dict[str, object]:
    """Load a JSON file that must contain a top-level object."""
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScanInputError(
            f"File {path} is not valid JSON ({exc}). Expected a JSON object; "
            "regenerate the project to rewrite it."
        ) from exc
    if not isinstance(raw, dict):
        raise ScanInputError(
            f"File {path} does not contain a JSON object (got {type(raw).__name__}). "
            "Expected the manifest schema written by datrix_common.generation.manifest."
        )
    return {str(key): value for key, value in raw.items()}


def _require_str(data: dict[str, object], key: str, context: str) -> str:
    """Read a required string field from a parsed JSON object."""
    value = data.get(key)
    if not isinstance(value, str):
        raise ScanInputError(
            f"{context}: required string field '{key}' is missing or not a string. "
            "Expected the manifest schema written by datrix_common.generation.manifest; "
            "regenerate the project."
        )
    return value


def _optional_str_tuple(data: dict[str, object], key: str, context: str) -> tuple[str, ...]:
    """Read an optional list-of-strings field from a parsed JSON object."""
    if key not in data:
        return ()
    value = data[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ScanInputError(
            f"{context}: field '{key}' must be a list of strings. "
            "Expected the manifest schema written by datrix_common.generation.manifest; "
            "regenerate the project."
        )
    return tuple(str(item) for item in value)


def write_json_file(path: Path, payload: dict[str, object]) -> None:
    """Write a JSON payload with stable formatting, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def parse_application(source_path: Path, profile: str = DEFAULT_CONFIG_PROFILE) -> Application:
    """Parse a .dtrx file with the real pipeline and return the validated app.

    Mirrors the CLI generation pipeline's front stages (and the sibling
    visualize.py): parse, resolve ConfigDSL for the given profile, then run
    semantic analysis.

    Raises:
        ScanInputError: If the source is missing, config resolution fails, or
            semantic analysis reports errors (the generated output could not
            have come from this source).
    """
    if source_path.is_dir():
        candidate = source_path / SYSTEM_DTRX_FILENAME
        if not candidate.exists():
            raise ScanInputError(
                f"No {SYSTEM_DTRX_FILENAME} found in directory {source_path}. "
                f"Pass the .dtrx file itself or a directory containing {SYSTEM_DTRX_FILENAME}."
            )
        source_path = candidate
    if not source_path.exists():
        raise ScanInputError(
            f"Source .dtrx not found: {source_path}. "
            "Pass an existing system.dtrx (or service .dtrx) path via --source."
        )
    register_all()
    parser = TreeSitterParser()
    ast = parser.parse_file(source_path)
    try:
        resolve_service_configs(ast, source_path.parent, profile)
    except ConfigResolutionError as exc:
        raise ScanInputError(
            f"Config resolution for {source_path} (profile '{profile}') failed: {exc}. "
            "Pass the profile the project was generated with via --profile "
            "(generate.ps1 default: test)."
        ) from exc
    result = SemanticAnalyzer().analyze(ast)
    if not result.is_valid:
        summary = "; ".join(str(err) for err in result.errors[:MAX_REPORTED_PARSE_ERRORS])
        raise ScanInputError(
            f"Semantic analysis of {source_path} failed with {len(result.errors)} error(s): "
            f"{summary}. Fix the DSL source (see syntax-checker.ps1) before scanning."
        )
    return result.app


def build_service_records(app: Application) -> list[ServiceRecord]:
    """Build the service inventory using ServicePaths (the generator transform)."""
    records: list[ServiceRecord] = []
    for name, service in app.services.items():
        paths = ServicePaths(str(name))
        dtrx_path = ""
        if service.location is not None and service.location.file_path is not None:
            dtrx_path = str(service.location.file_path)
        records.append(
            ServiceRecord(
                qualified_name=str(name),
                simple_name=paths.simple_name,
                kebab_name=paths.kebab_resource,
                service_dir=paths.service_dir,
                compose_name=paths.compose_service,
                dtrx_path=dtrx_path,
            )
        )
    return records


def resolve_system_name(app: Application) -> str:
    """System name from the DSL, falling back to the first service namespace."""
    if app.system is not None:
        return str(app.system.qualified_name)
    for name in app.services:
        parts = str(name).split(".")
        return parts[0] if len(parts) > 1 else str(name)
    raise ScanInputError(
        "The parsed application defines no system block and no services. "
        "Expected at least one 'service' declaration in the .dtrx source."
    )


def load_manifests(generated_root: Path) -> list[ManifestData]:
    """Load every manifest under <generated>/.datrix/manifests/."""
    manifest_dir = generated_root / MANIFEST_SUBDIR
    if not manifest_dir.is_dir():
        return []
    manifests: list[ManifestData] = []
    for path in sorted(manifest_dir.glob("*.json")):
        data = load_json_object(path)
        context = f"Manifest {path}"
        manifests.append(
            ManifestData(
                target=_require_str(data, "target", context),
                path=path,
                generated_at=_require_str(data, "generated_at", context),
                files=_optional_str_tuple(data, "files", context),
                user_files=_optional_str_tuple(data, "user_files", context),
                append_only_files=_optional_str_tuple(data, "append_only_files", context),
            )
        )
    return manifests


def find_missing_manifest_files(manifest: ManifestData, generated_root: Path) -> list[str]:
    """Manifest-tracked files (excluding user scaffolding) absent on disk."""
    tracked = [*manifest.files, *manifest.append_only_files]
    return [entry for entry in tracked if not (generated_root / entry).exists()]


def find_absent_user_files(manifest: ManifestData, generated_root: Path) -> list[str]:
    """user_files absent on disk — informational only (overwrite=False scaffolding)."""
    return [entry for entry in manifest.user_files if not (generated_root / entry).exists()]


def match_any_pattern(rel_path_lower: str, patterns: tuple[str, ...]) -> bool:
    """True if the lowercase posix relative path matches any fnmatch pattern."""
    return any(fnmatch.fnmatch(rel_path_lower, pattern) for pattern in patterns)


# ── Project-scan specific helpers ──


def group_manifest_files_by_top_dir(manifests: list[ManifestData]) -> dict[str, int]:
    """Count manifest entries by their first path segment (project root = _project)."""
    counts: dict[str, int] = {}
    for manifest in manifests:
        for entry in manifest.all_tracked:
            top = entry.split("/", 1)[0] if "/" in entry else PROJECT_LEVEL_KEY
            counts[top] = counts.get(top, 0) + 1
    return counts


def detect_service_language(service_dir: Path) -> str:
    """Detect a single generated service's language via probe files."""
    if any((service_dir / probe).exists() for probe in PYTHON_PROBE_FILES):
        return LANGUAGE_PYTHON
    if any((service_dir / probe).exists() for probe in TYPESCRIPT_PROBE_FILES):
        return LANGUAGE_TYPESCRIPT
    return LANGUAGE_UNKNOWN


def detect_project_language(service_languages: list[str]) -> str:
    """Project language = first detected service language."""
    for language in service_languages:
        if language != LANGUAGE_UNKNOWN:
            return language
    return LANGUAGE_UNKNOWN


def detect_platform(generated_root: Path, compose_exists: bool) -> str:
    """Docker if a compose file exists, else infer from output path segments."""
    if compose_exists:
        return PLATFORM_DOCKER
    segments = {part.lower() for part in generated_root.parts}
    if segments & AWS_PATH_SEGMENTS:
        return PLATFORM_AWS
    if segments & AZURE_PATH_SEGMENTS:
        return PLATFORM_AZURE
    if segments & DOCKER_PATH_SEGMENTS:
        return PLATFORM_DOCKER
    return PLATFORM_UNKNOWN


def read_compose_services(compose_path: Path) -> list[str]:
    """Service entry names from a docker-compose.yml."""
    raw: object = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ScanInputError(
            f"{compose_path} is not a YAML mapping. Expected a docker-compose file "
            "with a top-level 'services:' mapping; regenerate the project."
        )
    services_obj = raw.get("services")
    if not isinstance(services_obj, dict):
        raise ScanInputError(
            f"{compose_path} has no 'services:' mapping. Expected a docker-compose "
            "file as written by the docker generator; regenerate the project."
        )
    return sorted(str(key) for key in services_obj)


def build_infra_report(generated_root: Path) -> dict[str, dict[str, object]]:
    """Existence report for project-level infrastructure files (Phase 3)."""
    report: dict[str, dict[str, object]] = {}
    for key, rel_path in INFRA_CHECKS:
        full = generated_root / rel_path
        report[key] = {"path": str(full), "exists": full.exists()}
    return report


def infra_exists(infra: dict[str, dict[str, object]], key: str) -> bool:
    """Read the existence flag of one infra check entry."""
    return bool(infra[key]["exists"])


def build_compose_report(
    generated_root: Path,
    records: list[ServiceRecord],
    infra: dict[str, dict[str, object]],
) -> dict[str, object]:
    """Cross-check compose service entries against the DSL inventory (Phase 3a)."""
    compose_path = generated_root / DOCKER_COMPOSE_FILENAME
    if not infra_exists(infra, "docker_compose"):
        return {"exists": False, "path": str(compose_path)}
    compose_services = read_compose_services(compose_path)
    missing = [rec.compose_name for rec in records if rec.compose_name not in compose_services]
    infra_containers = {
        token: any(token in name for name in compose_services)
        for token in GATEWAY_TOKENS + OBSERVABILITY_TOKENS
    }
    return {
        "exists": True,
        "path": str(compose_path),
        "service_entries": compose_services,
        "missing_service_entries": missing,
        "infra_containers": infra_containers,
    }


def compose_has_container(compose_report: dict[str, object], token: str) -> bool:
    """True if the compose file declares a container whose name contains token."""
    containers = compose_report.get("infra_containers")
    if not isinstance(containers, dict):
        return False
    return bool(containers.get(token, False))


def compute_blockers(
    platform: str,
    infra: dict[str, dict[str, object]],
    records: list[ServiceRecord],
    existing_dirs: set[str],
    manifests: list[ManifestData],
) -> list[str]:
    """Critical deployment blockers per skill Phase 4a."""
    blockers: list[str] = []
    if platform == PLATFORM_DOCKER and not infra_exists(infra, "docker_compose"):
        blockers.append(
            f"docker-compose.yml missing at {infra['docker_compose']['path']} (Docker platform)"
        )
    if records and not existing_dirs:
        names = ", ".join(rec.service_dir for rec in records)
        blockers.append(f"No services generated: all expected service directories missing ({names})")
    if not manifests:
        blockers.append(f"No manifest files found under {MANIFEST_SUBDIR} — generation incomplete")
    elif all(not manifest.files for manifest in manifests):
        blockers.append("All manifests list zero generated files — generation incomplete")
    return blockers


def compute_warnings(
    infra: dict[str, dict[str, object]],
    records: list[ServiceRecord],
    existing_dirs: set[str],
    compose_report: dict[str, object],
) -> list[str]:
    """Warnings per skill Phase 4b."""
    warnings: list[str] = []
    if not infra_exists(infra, "env_example"):
        warnings.append(f".env.example missing at {infra['env_example']['path']}")
    missing_services = [rec.qualified_name for rec in records if rec.service_dir not in existing_dirs]
    if missing_services and len(missing_services) < len(records):
        warnings.append(
            f"{len(missing_services)} service(s) from the DSL have no generated directory: "
            + ", ".join(missing_services)
        )
    if len(records) > 1 and not infra_exists(infra, "nginx_conf"):
        warnings.append(
            f"Gateway config missing for multi-service project: {infra['nginx_conf']['path']}"
        )
    for token, config_key in OBSERVABILITY_CONFIG_KEYS:
        if compose_has_container(compose_report, token) and not infra_exists(infra, config_key):
            warnings.append(
                f"Observability enabled ({token} container in compose) but config missing: "
                f"{infra[config_key]['path']}"
            )
    return warnings


def render_prompt(
    record: ServiceRecord,
    eval_dir: Path,
    context: dict[str, str],
    dir_exists: bool,
    manifest_file_count: int,
) -> tuple[Path, str]:
    """Fill the Phase 6 prompt template for one service."""
    prompt_path = eval_dir / PROMPT_FILENAME_TEMPLATE.format(name=record.kebab_name)
    report_path = eval_dir / f"service-{record.kebab_name}-evaluation.md"
    generated_dir = Path(context["generated_root"]) / record.service_dir
    content = PROMPT_TEMPLATE.format(
        service_name=record.kebab_name,
        qualified_name=record.qualified_name,
        system_name=context["system_name"],
        eval_dir=str(eval_dir),
        prompt_path=str(prompt_path),
        service_dtrx=record.dtrx_path or "(not recorded in parsed model)",
        generated_dir=str(generated_dir),
        system_dtrx=context["source"],
        language=context["language"],
        platform=context["platform"],
        total_services=context["total_services"],
        gateway_enabled=context["gateway_enabled"],
        observability_enabled=context["observability_enabled"],
        dir_exists="Yes" if dir_exists else "No",
        manifest_file_count=manifest_file_count,
        report_path=str(report_path),
        scan_path=str(eval_dir / PROJECT_SCAN_FILENAME),
    )
    return prompt_path, content


def default_eval_dir(source_path: Path) -> Path:
    """Default evaluation output dir: <workspace>/.tmp/eval/<project-slug>/."""
    slug = source_path.parent.name
    return datrix_root / TMP_SUBDIR / EVAL_SUBDIR / slug


# ── Scan assembly ──


def _build_service_entries(
    records: list[ServiceRecord],
    generated_root: Path,
    top_dir_counts: dict[str, int],
    compose_report: dict[str, object],
) -> list[dict[str, object]]:
    """Per-service scan rows (existence, language, manifest counts, compose)."""
    compose_entries = compose_report.get("service_entries")
    compose_names = set(compose_entries) if isinstance(compose_entries, list) else set()
    entries: list[dict[str, object]] = []
    for record in records:
        service_path = generated_root / record.service_dir
        entries.append({
            "qualified_name": record.qualified_name,
            "simple_name": record.simple_name,
            "dtrx_path": record.dtrx_path,
            "expected_dir": record.service_dir,
            "expected_dir_exists": service_path.is_dir(),
            "language": detect_service_language(service_path),
            "compose_name": record.compose_name,
            "compose_entry_present": record.compose_name in compose_names,
            "manifest_file_count": top_dir_counts.get(record.service_dir, 0),
        })
    return entries


def _build_manifest_entries(
    manifests: list[ManifestData], generated_root: Path
) -> list[dict[str, object]]:
    """Per-manifest scan rows (counts + missing-on-disk cross-check, Phase 2b/3e)."""
    entries: list[dict[str, object]] = []
    for manifest in manifests:
        entries.append({
            "target": manifest.target,
            "path": str(manifest.path),
            "generated_at": manifest.generated_at,
            "file_count": len(manifest.files),
            "user_file_count": len(manifest.user_files),
            "append_only_count": len(manifest.append_only_files),
            "missing_on_disk": find_missing_manifest_files(manifest, generated_root),
            "user_files_absent": find_absent_user_files(manifest, generated_root),
        })
    return entries


def _write_prompt_files(
    records: list[ServiceRecord],
    eval_dir: Path,
    context: dict[str, str],
    service_entries: list[dict[str, object]],
) -> list[str]:
    """Write one Phase 6 prompt file per service; return written paths."""
    entry_by_name = {str(entry["qualified_name"]): entry for entry in service_entries}
    written: list[str] = []
    for record in records:
        entry = entry_by_name[record.qualified_name]
        prompt_path, content = render_prompt(
            record,
            eval_dir,
            context,
            dir_exists=bool(entry["expected_dir_exists"]),
            manifest_file_count=int(str(entry["manifest_file_count"])),
        )
        prompt_path.write_text(content, encoding="utf-8")
        written.append(str(prompt_path))
    return written


def run_project_scan(source: Path, generated_root: Path, eval_dir: Path, profile: str) -> int:
    """Execute the full project-level scan and write all outputs."""
    app = parse_application(source, profile)
    records = build_service_records(app)
    if not records:
        raise ScanInputError(
            f"No services found in {source}. Expected at least one 'service' "
            "declaration (directly or via include'd .dtrx files)."
        )
    system_name = resolve_system_name(app)
    manifests = load_manifests(generated_root)
    top_dir_counts = group_manifest_files_by_top_dir(manifests)
    infra = build_infra_report(generated_root)
    compose_report = build_compose_report(generated_root, records, infra)
    platform = detect_platform(generated_root, infra_exists(infra, "docker_compose"))
    service_entries = _build_service_entries(records, generated_root, top_dir_counts, compose_report)
    existing_dirs = {
        str(entry["expected_dir"]) for entry in service_entries if entry["expected_dir_exists"]
    }
    language = detect_project_language([str(entry["language"]) for entry in service_entries])
    gateway_enabled = infra_exists(infra, "nginx_conf") or any(
        compose_has_container(compose_report, token) for token in GATEWAY_TOKENS
    )
    observability_enabled = any(
        compose_has_container(compose_report, token) for token in OBSERVABILITY_TOKENS
    ) or infra_exists(infra, "prometheus_config") or infra_exists(infra, "grafana_dir")
    blockers = compute_blockers(platform, infra, records, existing_dirs, manifests)
    warnings = compute_warnings(infra, records, existing_dirs, compose_report)

    eval_dir.mkdir(parents=True, exist_ok=True)
    context = {
        "source": str(source),
        "generated_root": str(generated_root),
        "system_name": system_name,
        "language": language,
        "platform": platform,
        "total_services": str(len(records)),
        "gateway_enabled": "Yes" if gateway_enabled else "No",
        "observability_enabled": "Yes" if observability_enabled else "No",
    }
    prompt_files = _write_prompt_files(records, eval_dir, context, service_entries)

    scan_path = eval_dir / PROJECT_SCAN_FILENAME
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": local_timestamp(),
        "source": str(source),
        "generated_root": str(generated_root),
        "eval_dir": str(eval_dir),
        "config_profile": profile,
        "system_name": system_name,
        "language": language,
        "platform": platform,
        "service_count": len(records),
        "generated_service_count": len(existing_dirs),
        "missing_service_count": len(records) - len(existing_dirs),
        "services": service_entries,
        "manifests": _build_manifest_entries(manifests, generated_root),
        "manifest_files_by_top_dir": top_dir_counts,
        "infra": infra,
        "docker_compose": compose_report,
        "gateway_enabled": gateway_enabled,
        "observability_enabled": observability_enabled,
        "critical_blockers": blockers,
        "warnings": warnings,
        "prompt_files": prompt_files,
    }
    write_json_file(scan_path, payload)

    print(
        f"{len(records)} services: {len(existing_dirs)} generated, "
        f"{len(records) - len(existing_dirs)} missing; "
        f"blockers: {len(blockers)}, warnings: {len(warnings)}"
    )
    print(f"Prompts: {len(prompt_files)} file(s) in {eval_dir}")
    print(f"Details: {scan_path}")
    return EXIT_OK


# ── CLI ──


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mechanical project-level scan for /evaluate-generated (quick mode).",
    )
    parser.add_argument("--source", required=True, help="Path to the system.dtrx file")
    parser.add_argument("--generated", required=True, help="Generated project root directory")
    parser.add_argument(
        "--eval-dir",
        default=None,
        help="Evaluation output directory (default: <workspace>/.tmp/eval/<project-slug>/)",
    )
    parser.add_argument(
        "--profile",
        default=DEFAULT_CONFIG_PROFILE,
        help="Config profile the project was generated with (default: test)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()


def main() -> int:
    """Entry point for the project-level evaluation scan."""
    args = _parse_args()
    configure_logging(bool(args.debug))
    source = Path(str(args.source))
    if not source.is_absolute():
        source = (Path.cwd() / source).resolve()
    generated_root = Path(str(args.generated))
    if not generated_root.is_absolute():
        generated_root = (Path.cwd() / generated_root).resolve()
    try:
        if not generated_root.is_dir():
            raise ScanInputError(
                f"Generated project root not found: {generated_root}. "
                "Pass the directory produced by generate.ps1 (under D:/datrix/.generated/...)."
            )
        eval_dir = Path(str(args.eval_dir)) if args.eval_dir else default_eval_dir(source)
        logger.debug("source=%s generated=%s eval_dir=%s", source, generated_root, eval_dir)
        return run_project_scan(source, generated_root, eval_dir, str(args.profile))
    except ScanInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
