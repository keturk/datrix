#!/usr/bin/env python3
"""Service-level mechanical scan for the /evaluate-generated-service skill.

Performs the deterministic parts of the skill's Phases 1-3f and 4 for ONE
service: DSL feature inventory (via the real parser + serializer), manifest
subset and both-direction filesystem diff, directory-name convention check,
per-block / per-entity expected-artifact existence table (existence ONLY —
semantic verification stays with the model, skill Phase 3.5), dead-code
candidates (skill Phase 3f tables), environment-variable references
(Phase 4c), and Dockerfile / migrations existence.

Usage:
  python scripts/library/dev/evaluate_service_scan.py \
      --source examples/01-foundation/system.dtrx --service BookService \
      --generated D:/datrix/.generated/.../01-foundation/library_book_service
  .\\scripts\\dev\\evaluate-service-scan.ps1 -Source <dtrx> -Generated <service dir>
"""

from __future__ import annotations

import argparse
import io
import logging
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

# Configure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add library directory to sys.path to import from shared / dev
library_dir = Path(__file__).resolve().parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

from shared.venv import get_datrix_root  # noqa: E402

datrix_root = get_datrix_root()
for _sub in ("datrix-common/src", "datrix-language/src"):
    _pkg_path = datrix_root / _sub
    if _pkg_path.exists() and str(_pkg_path) not in sys.path:
        sys.path.insert(0, str(_pkg_path))

from datrix_common.builtins.value_struct_definitions import BUILTIN_VALUE_STRUCTS  # noqa: E402
from datrix_common.datrix_model.containers import Application, Service  # noqa: E402
from datrix_common.paths import ServicePaths  # noqa: E402
from datrix_common.utils.text import PolyString  # noqa: E402
from dev.evaluate_generated_scan import (  # noqa: E402
    DEFAULT_CONFIG_PROFILE,
    EVAL_SUBDIR,
    EXIT_OK,
    EXIT_USAGE,
    IGNORED_DIR_NAMES,
    MANIFEST_SUBDIR,
    SCHEMA_VERSION,
    TMP_SUBDIR,
    ManifestData,
    ScanInputError,
    configure_logging,
    load_json_object,
    load_manifests,
    local_timestamp,
    match_any_pattern,
    parse_application,
    write_json_file,
)
from shared.visualization.serializer import serialize_service  # noqa: E402

logger = logging.getLogger(__name__)

# ── Constants ──

SERVICE_SCAN_FILENAME_TEMPLATE = "service-{name}-scan.json"
MAX_MATCH_PATHS = 10
MAX_TEXT_FILE_BYTES = 1_000_000
MAX_PROJECT_ROOT_ASCENT = 4
SOURCE_CODE_SUFFIXES = frozenset({".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".mts"})

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"

SQL_MANIFEST_TARGET = "sql"
DOCKERFILE_BASENAME = "dockerfile"
SRC_PREFIX = "src/"
SERVICE_FILE_SUFFIX = "_service"

#: Skill Phase 3f fixed table: generated module dir -> required DSL feature.
MODULE_DIR_TO_FEATURE: dict[str, str] = {
    "redis": "cache",
    "cache": "cache",
    "mq": "pubsub",
    "pubsub": "pubsub",
    "messaging": "pubsub",
    "jobs": "jobs",
    "store": "storage",
    "docdb": "nosql",
    "nosql": "nosql",
    "cqrs": "cqrs",
    "graphql": "graphql_api",
    "clients": "discovery",
}

#: Skill Phase 3f unused-dependency table: feature -> libraries implying it.
SUSPECT_DEPENDENCIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("rdbms", ("asyncpg", "aiomysql", "pg", "mysql2")),
    ("cache", ("redis", "aioredis", "ioredis")),
    ("pubsub", ("aiokafka", "aio-pika", "kafkajs", "amqplib")),
    ("storage", ("boto3", "minio", "@aws-sdk/client-s3")),
    ("nosql", ("motor", "pymongo", "mongodb")),
)

#: Infrastructure file stems that are never entity artifacts (Phase 3f orphans).
NON_ENTITY_STEMS = frozenset({
    "__init__",
    "base",
    "base_entity",
    "database",
    "session",
    "health",
    "connection",
    "index",
})
ENTITY_ARTIFACT_DIRS: tuple[str, ...] = ("models", "schemas", "services")

# Expected-artifact existence patterns, derived from skill Phase 3b tables.
# Placeholders: {bs}=block snake, {bk}=block kebab, {es}=entity snake.
RDBMS_BLOCK_CHECKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("database_connection", ("*/{bs}/connection.*", "*/database.*", "*/db/connection.*")),
    ("session_management", ("*/{bs}/session.*", "*/db/session.*", "*session*")),
    ("base_model", ("*/{bs}/base.*", "*/models/*base*")),
    ("health_check", ("*/{bs}/health.*", "*/{bs}/*health*")),
    ("migration_config", ("alembic-{bk}.ini", "*alembic*.ini", "*migrations*/env.*")),
    ("initial_migration", ("*migrations*{bk}*/versions/*", "*migrations*/versions/*")),
)
ENTITY_CHECKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("orm_model", ("*/models/{bs}/{es}.*", "*/models/{es}.*", "*/entities/{es}.*")),
    ("schema_dto", ("*/schemas/{bs}/{es}.*", "*/schemas/{es}.*", "*/dto*/{es}.*")),
    (
        "service_layer",
        ("*/services/{bs}/{es}_service.*", "*/services/{es}_service.*", "*/services/{es}.*"),
    ),
)
CACHE_CHECKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cache_module", ("*/redis/*", "*/cache/*", "*cache*")),
)
PUBSUB_CHECKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("broker_module", ("*/mq/*", "*/pubsub/*", "*/messaging/*")),
    ("producer", ("*producer*", "*publisher*")),
    ("consumer", ("*consumer*", "*subscriber*")),
    ("event_schemas", ("*event*",)),
)
REST_API_CHECKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("routes", ("*/routes/*", "*/controllers/*", "*/api/*")),
)
GRAPHQL_CHECKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("graphql_module", ("*/graphql/*",)),
)
JOBS_CHECKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("jobs_module", ("*/jobs/*",)),
    ("scheduler", ("*scheduler*",)),
    ("runner", ("*runner*", "*worker*")),
)
CQRS_CHECKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cqrs_module", ("*/cqrs/*",)),
    ("commands", ("*command*",)),
    ("queries", ("*quer*",)),
)
STORAGE_CHECKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("storage_module", ("*/store/*", "*/storage/*")),
)
# NoSQL blocks are named like RDBMS blocks; the generated layout nests under
# the block name (e.g. docdb/models/<doc>.py, docdb/repositories/...).
NOSQL_BLOCK_CHECKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("nosql_client", ("*/{bs}/client.*", "*/{bs}/connection.*", "*/docdb/client.*", "*/nosql/client.*")),
    ("nosql_health", ("*/{bs}/health.*",)),
)
NOSQL_DOCUMENT_CHECKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("document_model", ("*/{bs}/models/{es}.*", "*/models/{bs}/{es}.*", "*/{bs}/{es}.*")),
    ("document_repository", ("*/{bs}/repositories/{es}_repository.*", "*{es}_repositor*")),
)
#: Feature key -> block-level check table (applied when the feature is present).
SIMPLE_FEATURE_CHECKS: tuple[tuple[str, tuple[tuple[str, tuple[str, ...]], ...]], ...] = (
    ("cache", CACHE_CHECKS),
    ("pubsub", PUBSUB_CHECKS),
    ("rest_api", REST_API_CHECKS),
    ("graphql_api", GRAPHQL_CHECKS),
    ("jobs", JOBS_CHECKS),
    ("cqrs", CQRS_CHECKS),
    ("storage", STORAGE_CHECKS),
)

MIGRATION_CONTENT_PATTERNS: tuple[str, ...] = (
    "*migrations*/versions/*",
    "*/migrations/versions/*",
)

# Env-var reference scan (skill Phase 4c): main + config files only.
ENV_VAR_FILE_PATTERNS: tuple[str, ...] = ("main.*", "*/main.*", "*/config/*", "*settings*")
ENV_VAR_REGEXES: tuple[re.Pattern[str], ...] = (
    re.compile(r"os\.environ\.get\(\s*[\"']([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"os\.environ\[\s*[\"']([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"os\.getenv\(\s*[\"']([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"process\.env\.([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"process\.env\[[\"']([A-Za-z_][A-Za-z0-9_]*)"),
)


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one expected-artifact existence check."""

    scope: str
    check: str
    patterns: tuple[str, ...]
    status: str
    matched: tuple[str, ...]
    total_matches: int

    def to_json(self) -> dict[str, object]:
        """JSON row for the scan payload."""
        return {
            "scope": self.scope,
            "check": self.check,
            "patterns": list(self.patterns),
            "status": self.status,
            "matched": list(self.matched),
            "total_matches": self.total_matches,
        }


# ── Input resolution ──


def select_service(app: Application, requested: str | None) -> Service:
    """Pick the target service from the parsed application."""
    available = ", ".join(str(name) for name in app.services)
    if requested:
        for name, service in app.services.items():
            paths = ServicePaths(str(name))
            if requested in (str(name), paths.simple_name, paths.kebab_resource):
                return service
        raise ScanInputError(
            f"Service '{requested}' not found in the parsed source. "
            f"Available services: {available}. Pass --service with one of these "
            "(qualified, simple, or kebab-case name)."
        )
    if len(app.services) == 1:
        return next(iter(app.services.values()))
    raise ScanInputError(
        f"The source defines {len(app.services)} services; pass --service to pick one of: "
        f"{available}."
    )


def resolve_project_root(generated_dir: Path, explicit: Path | None) -> Path:
    """Locate the generated project root that holds .datrix/manifests."""
    if explicit is not None:
        if not (explicit / MANIFEST_SUBDIR).is_dir():
            raise ScanInputError(
                f"--project-generated {explicit} contains no {MANIFEST_SUBDIR} directory. "
                "Pass the generated PROJECT root (the directory holding docker-compose.yml "
                "and .datrix/), not a service subdirectory."
            )
        return explicit
    current = generated_dir.parent
    for _ in range(MAX_PROJECT_ROOT_ASCENT):
        if (current / MANIFEST_SUBDIR).is_dir():
            return current
        if current.parent == current:
            break
        current = current.parent
    raise ScanInputError(
        f"Could not find {MANIFEST_SUBDIR} in any of the {MAX_PROJECT_ROOT_ASCENT} directories "
        f"above {generated_dir}. Pass --project-generated <generated project root> explicitly."
    )


# ── Filesystem index ──


def index_files(root: Path) -> list[str]:
    """Relative posix paths of all files under root, excluding cache dirs."""
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in IGNORED_DIR_NAMES for part in rel_parts):
            continue
        files.append("/".join(rel_parts))
    return files


# ── DSL inventory ──


def feature_presence(service: Service) -> dict[str, bool]:
    """Which DSL feature families this service actually declares."""
    return {
        "rdbms": bool(service.rdbms_blocks),
        "cache": service.cache_block is not None or bool(service.cache_blocks),
        "pubsub": bool(service.pubsub_blocks),
        "jobs": service.jobs_block is not None,
        "storage": bool(service.storage_blocks),
        "nosql": bool(service.nosql_blocks),
        "cqrs": service.cqrs_block is not None,
        "graphql_api": bool(service.graphql_apis),
        "rest_api": bool(service.rest_apis),
        "queues": service.queues_block is not None,
        "discovery": service.discovery is not None and bool(service.discovery.dependencies),
    }


def build_entity_details(service: Service) -> list[dict[str, object]]:
    """Per-entity supplements not covered by serialize_service (hooks etc.)."""
    details: list[dict[str, object]] = []
    for block_name, block in service.rdbms_blocks.items():
        for entity in block.entities.values():
            details.append({
                "block": str(block_name),
                "entity": str(entity.name),
                "is_abstract": entity.is_abstract,
                "computed_fields": [str(name) for name in entity.computed_fields],
                "lifecycle_hooks": {
                    hook_type: len(hooks) for hook_type, hooks in entity.lifecycle_hooks.items()
                },
                "validation_count": len(entity.validations),
            })
    return details


def build_dsl_inventory(service: Service) -> dict[str, object]:
    """Full DSL feature inventory via the shared serializer + supplements."""
    inventory = serialize_service(service)
    inventory["graphql_apis"] = [str(name) for name in service.graphql_apis]
    inventory["cache_block_names"] = [str(name) for name in service.cache_blocks]
    inventory["storage_block_names"] = [str(name) for name in service.storage_blocks]
    inventory["nosql_block_names"] = [str(name) for name in service.nosql_blocks]
    inventory["has_queues"] = service.queues_block is not None
    inventory["entity_details"] = build_entity_details(service)
    return inventory


def collect_concrete_entities(service: Service) -> list[tuple[str, str]]:
    """(block_name, entity_name) pairs for all non-abstract RDBMS entities."""
    pairs: list[tuple[str, str]] = []
    for block_name, block in service.rdbms_blocks.items():
        for entity in block.entities.values():
            if not entity.is_abstract:
                pairs.append((str(block_name), str(entity.name)))
    return pairs


def collect_nosql_documents(service: Service) -> list[tuple[str, str]]:
    """(block_name, document_name) pairs for all non-abstract NoSQL documents."""
    pairs: list[tuple[str, str]] = []
    for block_name, block in service.nosql_blocks.items():
        for entity in block.entities.values():
            if not entity.is_abstract:
                pairs.append((str(block_name), str(entity.name)))
    return pairs


def collect_struct_stems(app: Application) -> set[str]:
    """Snake-case names of every struct declared anywhere in the application.

    Generated request/response schemas legitimately come from structs that may
    be declared in shared modules or other services and imported — so orphan
    detection for the schemas/ directory suppresses all of them.
    """
    stems: set[str] = set()
    containers = [*app.services.values(), *app.modules.values(), *app.shared_blocks.values()]
    for container in containers:
        stems.update(PolyString(str(name)).snake for name in container.structs)
    # Builtin value structs (e.g. StorageRef) are always available in the
    # language without a DSL declaration; their schemas are never orphans.
    stems.update(PolyString(definition.canonical_name).snake for definition in BUILTIN_VALUE_STRUCTS)
    return stems


# ── Expected-artifact existence checks ──


def run_pattern_check(
    scope: str,
    check: str,
    patterns: tuple[str, ...],
    fs_index_lower: list[tuple[str, str]],
) -> CheckResult:
    """Evaluate one existence check over the (original, lowercase) path index."""
    matched = [rel for rel, rel_lower in fs_index_lower if match_any_pattern(rel_lower, patterns)]
    return CheckResult(
        scope=scope,
        check=check,
        patterns=patterns,
        status=STATUS_PASS if matched else STATUS_FAIL,
        matched=tuple(matched[:MAX_MATCH_PATHS]),
        total_matches=len(matched),
    )


def build_check_specs(service: Service, features: dict[str, bool]) -> list[tuple[str, str, tuple[str, ...]]]:
    """All (scope, check, patterns) specs for this service's declared features."""
    specs: list[tuple[str, str, tuple[str, ...]]] = []
    for block_name in service.rdbms_blocks:
        block_snake = PolyString(str(block_name)).snake
        block_kebab = PolyString(str(block_name)).kebab
        for check, patterns in RDBMS_BLOCK_CHECKS:
            formatted = tuple(p.format(bs=block_snake, bk=block_kebab) for p in patterns)
            specs.append((f"rdbms:{block_name}", check, formatted))
    for entity_block, entity_name in collect_concrete_entities(service):
        block_snake = PolyString(entity_block).snake
        entity_snake = PolyString(entity_name).snake
        for check, patterns in ENTITY_CHECKS:
            formatted = tuple(p.format(bs=block_snake, es=entity_snake) for p in patterns)
            specs.append((f"entity:{entity_name}", check, formatted))
    for nosql_name in service.nosql_blocks:
        block_snake = PolyString(str(nosql_name)).snake
        for check, patterns in NOSQL_BLOCK_CHECKS:
            formatted = tuple(p.format(bs=block_snake) for p in patterns)
            specs.append((f"nosql:{nosql_name}", check, formatted))
    for document_block, document_name in collect_nosql_documents(service):
        block_snake = PolyString(document_block).snake
        document_snake = PolyString(document_name).snake
        for check, patterns in NOSQL_DOCUMENT_CHECKS:
            formatted = tuple(p.format(bs=block_snake, es=document_snake) for p in patterns)
            specs.append((f"document:{document_name}", check, formatted))
    for feature, checks in SIMPLE_FEATURE_CHECKS:
        if not features[feature]:
            continue
        for check, patterns in checks:
            specs.append((f"block:{feature}", check, patterns))
    return specs


def check_migration_references(
    service_root: Path,
    fs_index: list[str],
    entities: list[tuple[str, str]],
) -> list[CheckResult]:
    """Skill Phase 3c: each concrete entity is referenced in a migration file."""
    migration_files = [
        rel for rel in fs_index if match_any_pattern(rel.lower(), MIGRATION_CONTENT_PATTERNS)
    ]
    texts: dict[str, str] = {}
    for rel in migration_files:
        path = service_root / rel
        if path.stat().st_size > MAX_TEXT_FILE_BYTES:
            continue
        texts[rel] = path.read_text(encoding="utf-8", errors="replace").lower()
    results: list[CheckResult] = []
    for _block_name, entity_name in entities:
        entity_snake = PolyString(entity_name).snake
        matched = tuple(rel for rel, text in texts.items() if entity_snake in text)
        results.append(
            CheckResult(
                scope=f"entity:{entity_name}",
                check="migration_reference",
                patterns=MIGRATION_CONTENT_PATTERNS,
                status=STATUS_PASS if matched else STATUS_FAIL,
                matched=matched[:MAX_MATCH_PATHS],
                total_matches=len(matched),
            )
        )
    return results


def check_sql_manifest(
    manifests: list[ManifestData],
    dir_prefixes: tuple[str, ...],
) -> CheckResult:
    """Skill Phase 3b (RDBMS): SQL DDL for this service is in the sql manifest."""
    matched: list[str] = []
    for manifest in manifests:
        if manifest.target != SQL_MANIFEST_TARGET:
            continue
        matched.extend(
            entry for entry in manifest.all_tracked
            if entry.split("/", 1)[0] in dir_prefixes
        )
    return CheckResult(
        scope="rdbms",
        check="sql_manifest_ddl",
        patterns=(f"{SQL_MANIFEST_TARGET}.json manifest entries under service dir",),
        status=STATUS_PASS if matched else STATUS_FAIL,
        matched=tuple(matched[:MAX_MATCH_PATHS]),
        total_matches=len(matched),
    )


# ── Manifest subset and diff ──


def manifest_service_subset(
    manifests: list[ManifestData],
    dir_prefixes: tuple[str, ...],
    project_root: Path,
) -> tuple[list[dict[str, object]], set[str]]:
    """Per-target manifest rows for this service + set of service-relative paths."""
    rows: list[dict[str, object]] = []
    service_relative: set[str] = set()
    for manifest in manifests:
        tracked = _entries_under(manifest.all_tracked, dir_prefixes)
        generated_only = _entries_under(manifest.files + manifest.append_only_files, dir_prefixes)
        missing = [entry for entry in generated_only if not (project_root / entry).exists()]
        for entry in tracked:
            service_relative.add(entry.split("/", 1)[1])
        rows.append({
            "target": manifest.target,
            "generated_at": manifest.generated_at,
            "service_file_count": len(tracked),
            "missing_on_disk": missing,
        })
    return rows, service_relative


def _entries_under(entries: tuple[str, ...], dir_prefixes: tuple[str, ...]) -> list[str]:
    """Manifest entries whose first path segment is one of the service dirs."""
    selected: list[str] = []
    for entry in entries:
        top, separator, rest = entry.partition("/")
        if separator and rest and top in dir_prefixes:
            selected.append(entry)
    return selected


# ── Dead-code candidates (skill Phase 3f) ──


def find_dead_module_dirs(fs_index: list[str], features: dict[str, bool]) -> list[dict[str, object]]:
    """Module dirs from the fixed Phase 3f table with no corresponding DSL block."""
    dirs_by_name: dict[str, set[str]] = {}
    for rel in fs_index:
        parts = rel.split("/")
        for depth, part in enumerate(parts[:-1]):
            if part in MODULE_DIR_TO_FEATURE:
                dirs_by_name.setdefault(part, set()).add("/".join(parts[: depth + 1]))
    candidates: list[dict[str, object]] = []
    for dir_name, dir_paths in sorted(dirs_by_name.items()):
        feature = MODULE_DIR_TO_FEATURE[dir_name]
        if features[feature]:
            continue
        candidates.append({
            "dir_name": dir_name,
            "paths": sorted(dir_paths),
            "requires_block": feature,
        })
    return candidates


def find_orphaned_entity_artifacts(
    fs_index: list[str],
    entity_stems: set[str],
    schema_stems: set[str],
) -> list[dict[str, str]]:
    """Entity-artifact files whose stem matches no DSL type (candidates only).

    models/ and services/ files are matched against this service's entity and
    document names; schemas/ files additionally against every struct declared
    in the application (request/response DTOs come from structs, possibly
    imported from shared modules).
    """
    scoped = [rel for rel in fs_index if rel.startswith(SRC_PREFIX)]
    if not scoped:
        scoped = fs_index
    orphans: list[dict[str, str]] = []
    for rel in scoped:
        parts = rel.split("/")
        category = next((d for d in ENTITY_ARTIFACT_DIRS if d in parts[:-1]), "")
        if not category:
            continue
        stem = Path(parts[-1]).stem.lower()
        if stem.endswith(SERVICE_FILE_SUFFIX):
            stem = stem[: -len(SERVICE_FILE_SUFFIX)]
        known = schema_stems if category == "schemas" else entity_stems
        if stem.startswith("_") or stem in NON_ENTITY_STEMS or stem in known:
            continue
        orphans.append({"path": rel, "category": category, "stem": stem})
    return orphans


# ── Dependency scan (skill Phase 3f / 4d) ──


def read_service_dependencies(service_root: Path) -> list[str]:
    """Declared dependency names from requirements.txt / pyproject / package.json."""
    deps: set[str] = set()
    _add_requirements_deps(service_root / "requirements.txt", deps)
    _add_pyproject_deps(service_root / "pyproject.toml", deps)
    _add_package_json_deps(service_root / "package.json", deps)
    return sorted(deps)


def _dependency_name(spec: str) -> str:
    """Package name from a requirement spec line (before any version/extras)."""
    return re.split(r"[<>=~!\[; ]", spec.strip(), maxsplit=1)[0].strip().lower()


def _add_requirements_deps(path: Path, deps: set[str]) -> None:
    """Collect dependency names from a requirements.txt file."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue
        name = _dependency_name(stripped)
        if name:
            deps.add(name)


def _add_pyproject_deps(path: Path, deps: set[str]) -> None:
    """Collect dependency names from [project].dependencies in pyproject.toml."""
    if not path.exists():
        return
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data.get("project")
    if not isinstance(project, dict):
        logger.debug("pyproject %s has no [project] table; skipping", path)
        return
    listed = project.get("dependencies")
    if not isinstance(listed, list):
        return
    for item in listed:
        if isinstance(item, str) and _dependency_name(item):
            deps.add(_dependency_name(item))


def _add_package_json_deps(path: Path, deps: set[str]) -> None:
    """Collect dependency names from package.json dependencies/devDependencies."""
    if not path.exists():
        return
    data = load_json_object(path)
    for key in ("dependencies", "devDependencies"):
        section = data.get(key)
        if not isinstance(section, dict):
            continue
        for name in section:
            deps.add(str(name).lower())


def find_suspect_dependencies(deps: list[str], features: dict[str, bool]) -> list[dict[str, str]]:
    """Dependencies implying a feature the DSL does not declare (Phase 3f table)."""
    dep_set = set(deps)
    suspects: list[dict[str, str]] = []
    for feature, libraries in SUSPECT_DEPENDENCIES:
        if features[feature]:
            continue
        for library in libraries:
            if library in dep_set:
                suspects.append({"dependency": library, "unused_feature": feature})
    return suspects


# ── Env vars, Dockerfile, migrations (skill Phase 4) ──


def _extract_env_vars(text: str) -> set[str]:
    """Environment variable names referenced in one source file's text."""
    names: set[str] = set()
    for regex in ENV_VAR_REGEXES:
        for match in regex.finditer(text):
            names.add(match.group(1))
    return names


def scan_env_var_references(
    service_root: Path, fs_index: list[str]
) -> tuple[dict[str, list[str]], int]:
    """Env-var references in main/config source files (skill Phase 4c).

    Returns (variable -> referencing files, number of files scanned). A zero
    variable count with a nonzero scanned count is a real result: generated
    services may read all configuration from a config store instead of the
    environment.
    """
    references: dict[str, set[str]] = {}
    files_scanned = 0
    for rel in fs_index:
        if Path(rel).suffix.lower() not in SOURCE_CODE_SUFFIXES:
            continue
        if not match_any_pattern(rel.lower(), ENV_VAR_FILE_PATTERNS):
            continue
        path = service_root / rel
        if path.stat().st_size > MAX_TEXT_FILE_BYTES:
            continue
        files_scanned += 1
        for name in _extract_env_vars(path.read_text(encoding="utf-8", errors="replace")):
            references.setdefault(name, set()).add(rel)
    return {name: sorted(files) for name, files in sorted(references.items())}, files_scanned


def check_dockerfile(fs_index: list[str]) -> dict[str, object]:
    """Dockerfile existence at the service root (skill Phase 4a)."""
    root_dockerfile = any(rel.lower() == DOCKERFILE_BASENAME for rel in fs_index)
    variants = [rel for rel in fs_index if DOCKERFILE_BASENAME in rel.lower()]
    return {"exists": root_dockerfile, "matches": variants[:MAX_MATCH_PATHS]}


def summarize_migrations(fs_index: list[str]) -> dict[str, object]:
    """Migration dirs and revision files present in the service (Phase 4b)."""
    migration_dirs = sorted({
        rel.split("/", 1)[0]
        for rel in fs_index
        if "/" in rel and rel.split("/", 1)[0].startswith("migrations")
    })
    revision_files = [
        rel
        for rel in fs_index
        if match_any_pattern(rel.lower(), MIGRATION_CONTENT_PATTERNS)
        and not rel.endswith("__init__.py")
    ]
    return {
        "migration_dirs": migration_dirs,
        "revision_file_count": len(revision_files),
        "revision_files": revision_files[:MAX_MATCH_PATHS],
    }


# ── Scan assembly ──


def _run_all_checks(
    service: Service,
    features: dict[str, bool],
    service_root: Path,
    fs_index: list[str],
    manifests: list[ManifestData],
    dir_prefixes: tuple[str, ...],
) -> list[CheckResult]:
    """Every expected-artifact existence check for this service."""
    fs_index_lower = [(rel, rel.lower()) for rel in fs_index]
    results = [
        run_pattern_check(scope, check, patterns, fs_index_lower)
        for scope, check, patterns in build_check_specs(service, features)
    ]
    entities = collect_concrete_entities(service)
    if features["rdbms"]:
        results.extend(check_migration_references(service_root, fs_index, entities))
        results.append(check_sql_manifest(manifests, dir_prefixes))
    return results


def run_service_scan(
    source: Path,
    service_name: str | None,
    generated_dir: Path,
    project_root_arg: Path | None,
    output_arg: Path | None,
    profile: str,
) -> int:
    """Execute the full service-level scan and write the JSON output."""
    app = parse_application(source, profile)
    service = select_service(app, service_name)
    paths = ServicePaths(str(service.name))
    project_root = resolve_project_root(generated_dir, project_root_arg)
    fs_index = index_files(generated_dir)
    features = feature_presence(service)
    manifests = load_manifests(project_root)

    actual_dir_name = generated_dir.name
    dir_prefixes = tuple(dict.fromkeys((actual_dir_name, paths.service_dir)))
    manifest_rows, manifest_relative = manifest_service_subset(manifests, dir_prefixes, project_root)
    not_in_manifest = sorted(set(fs_index) - manifest_relative)
    missing_on_disk_total = sum(len(list(row["missing_on_disk"])) for row in manifest_rows if isinstance(row["missing_on_disk"], list))

    check_results = _run_all_checks(service, features, generated_dir, fs_index, manifests, dir_prefixes)
    pass_count = sum(1 for result in check_results if result.status == STATUS_PASS)
    fail_count = len(check_results) - pass_count

    entity_stems = {
        PolyString(entity_name).snake for _block, entity_name in collect_concrete_entities(service)
    }
    entity_stems.update(
        PolyString(document_name).snake for _block, document_name in collect_nosql_documents(service)
    )
    schema_stems = entity_stems | collect_struct_stems(app)
    dead_dirs = find_dead_module_dirs(fs_index, features)
    orphans = find_orphaned_entity_artifacts(fs_index, entity_stems, schema_stems)
    dependencies = read_service_dependencies(generated_dir)
    suspect_deps = find_suspect_dependencies(dependencies, features)
    env_vars, env_files_scanned = scan_env_var_references(generated_dir, fs_index)

    output_path = output_arg if output_arg is not None else default_output_path(source, paths)
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": local_timestamp(),
        "source": str(source),
        "generated_dir": str(generated_dir),
        "project_generated": str(project_root),
        "config_profile": profile,
        "service": {
            "qualified_name": paths.qualified_name,
            "simple_name": paths.simple_name,
            "expected_dir": paths.service_dir,
            "actual_dir": actual_dir_name,
            "dir_convention_ok": actual_dir_name == paths.service_dir,
        },
        "features": features,
        "dsl": build_dsl_inventory(service),
        "manifest_subset": manifest_rows,
        "manifest_missing_on_disk_total": missing_on_disk_total,
        "fs_not_in_manifest": not_in_manifest,
        "fs_file_count": len(fs_index),
        "artifact_checks": [result.to_json() for result in check_results],
        "artifact_check_summary": {"pass": pass_count, "fail": fail_count},
        "dead_code": {
            "unused_module_dirs": dead_dirs,
            "orphaned_entity_artifacts": orphans,
            "suspect_dependencies": suspect_deps,
        },
        "dependencies": dependencies,
        "env_var_references": env_vars,
        "env_var_files_scanned": env_files_scanned,
        "dockerfile": check_dockerfile(fs_index),
        "migrations": summarize_migrations(fs_index),
    }
    write_json_file(output_path, payload)

    convention = "OK" if actual_dir_name == paths.service_dir else f"MISMATCH (expected {paths.service_dir})"
    manifest_total = sum(int(str(row["service_file_count"])) for row in manifest_rows)
    print(
        f"{paths.qualified_name}: dir {convention}; manifest files {manifest_total} "
        f"({missing_on_disk_total} missing on disk, {len(not_in_manifest)} untracked)"
    )
    print(
        f"checks: {pass_count} PASS / {fail_count} FAIL; dead-code dirs: {len(dead_dirs)}; "
        f"orphans: {len(orphans)}; suspect deps: {len(suspect_deps)}; env vars: {len(env_vars)}"
    )
    print(f"Details: {output_path}")
    return EXIT_OK


def default_output_path(source: Path, paths: ServicePaths) -> Path:
    """Default output: <workspace>/.tmp/eval/<project-slug>/service-<name>-scan.json."""
    slug = source.parent.name
    filename = SERVICE_SCAN_FILENAME_TEMPLATE.format(name=paths.kebab_resource)
    return datrix_root / TMP_SUBDIR / EVAL_SUBDIR / slug / filename


# ── CLI ──


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mechanical service-level scan for /evaluate-generated-service.",
    )
    parser.add_argument(
        "--source", required=True, help="Service .dtrx or system.dtrx (with --service)"
    )
    parser.add_argument(
        "--service", default=None, help="Service name (qualified, simple, or kebab-case)"
    )
    parser.add_argument("--generated", required=True, help="Generated SERVICE directory")
    parser.add_argument(
        "--project-generated",
        default=None,
        help="Generated PROJECT root (holds .datrix/manifests); auto-detected if omitted",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON path (default: <workspace>/.tmp/eval/<project>/service-<name>-scan.json)",
    )
    parser.add_argument(
        "--profile",
        default=DEFAULT_CONFIG_PROFILE,
        help="Config profile the project was generated with (default: test)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()


def _resolve_cli_path(value: str) -> Path:
    """Absolute path from a CLI argument, resolved against the current dir."""
    path = Path(value)
    return path if path.is_absolute() else (Path.cwd() / path).resolve()


def main() -> int:
    """Entry point for the service-level evaluation scan."""
    args = _parse_args()
    configure_logging(bool(args.debug))
    source = _resolve_cli_path(str(args.source))
    generated_dir = _resolve_cli_path(str(args.generated))
    project_root = _resolve_cli_path(str(args.project_generated)) if args.project_generated else None
    output_path = _resolve_cli_path(str(args.output)) if args.output else None
    service_name = str(args.service) if args.service else None
    try:
        if not generated_dir.is_dir():
            raise ScanInputError(
                f"Generated service directory not found: {generated_dir}. "
                "Pass the service-specific folder inside the generated project "
                "(e.g. <project>/library_book_service)."
            )
        logger.debug(
            "source=%s service=%s generated=%s project=%s",
            source, service_name, generated_dir, project_root,
        )
        return run_service_scan(
            source, service_name, generated_dir, project_root, output_path, str(args.profile)
        )
    except ScanInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
