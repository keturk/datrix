#!/usr/bin/env python3
r"""Content-level comparison of .generated vs .generated_saved.

Detects features in file content and produces a purpose-driven Markdown report:
feature matrix with counts, what each feature is for, one example path per side,
and a compact per-project summary. No exhaustive file listing.

Usage:
    python scripts/library/dev/compare_generated.py [--current .generated] [--saved .generated_saved] [--report path.md]

From repository root. Default report path: generated-comparison-report.md under datrix root.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

# Add library directory to sys.path
library_dir = Path(__file__).resolve().parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

from shared.venv import get_datrix_root

# Default path exclusions (dirs/files to skip when scanning)
EXCLUDE_DIRS = frozenset({
    ".results", ".ruff_cache", ".test_results", ".git", "__pycache__",
    ".pytest_cache", ".mypy_cache", "node_modules", ".venv",
})
EXCLUDE_FILE_SUFFIXES = frozenset({".pyc", ".pyo", ".egg-info"})

# Feature registry: id -> { "name", "patterns", "description" }
FEATURE_REGISTRY: list[dict[str, Any]] = [
    {"id": "config", "name": "Config (Pydantic Settings)", "patterns": ["BaseSettings", "pydantic_settings", "model_config"], "description": "Application settings loaded from environment (Pydantic Settings). Present in both; old had richer options (replica DB, JWT, secrets)."},
    {"id": "secrets", "name": "Secrets manager", "patterns": ["get_secret", "secrets_manager", "secrets_backend", "vault_addr", "_secrets_cache"], "description": "Loads secrets from Vault/AWS/azure/gcp/env at runtime so config can use get_secret(). Missing in new: generated config uses only plain env vars."},
    {"id": "main_app", "name": "Main app (FastAPI)", "patterns": ["FastAPI(", "create_app", "app = FastAPI"], "description": "FastAPI app entry point. Present in both; layout differs (app/main.py vs src/<pkg>/main.py)."},
    {"id": "health_endpoint", "name": "Health endpoint", "patterns": ["/health", "health_endpoint", "readiness", "liveness"], "description": "Aggregated /health (or readiness/liveness) for load balancers and orchestration. Present in both."},
    {"id": "auth", "name": "Auth (JWT/deps)", "patterns": ["HTTPBearer", "verify_token", "decode_jwt", "Depends", "auth"], "description": "JWT auth dependency for protected routes. Present in both."},
    {"id": "rdbms_connection", "name": "RDBMS connection", "patterns": ["create_async_engine", "AsyncEngine", "database_url"], "description": "Async SQLAlchemy engine creation from config. Present in both."},
    {"id": "rdbms_session", "name": "RDBMS session", "patterns": ["async_sessionmaker", "get_session", "AsyncSession"], "description": "Session factory and FastAPI dependency for DB access. Present in both."},
    {"id": "db_base", "name": "DB base (DeclarativeBase)", "patterns": ["DeclarativeBase", "Base.metadata"], "description": "SQLAlchemy declarative base for ORM models. Present in both."},
    {"id": "models", "name": "ORM models", "patterns": ["Column(", "relationship(", "__tablename__"], "description": "SQLAlchemy ORM entity models. Present in both."},
    {"id": "schemas", "name": "Pydantic schemas", "patterns": ["BaseModel"], "description": "Pydantic request/response schemas. Present in both (old also matched test schema files)."},
    {"id": "enums", "name": "Enums", "patterns": ["StrEnum", "class ", "Enum)"], "description": "Python enums for domain types. Present in both."},
    {"id": "routes", "name": "API routes", "patterns": ["APIRouter", "include_router", "@router.", "router.get", "router.post", "router.put", "router.delete"], "description": "REST API route definitions (FastAPI APIRouter). Present in both."},
    {"id": "entity_service", "name": "Entity service layer", "patterns": ["BaseEntityService", "entity_service", "get_", "create_", "update_", "delete_"], "description": "Service-layer CRUD for entities. Present in both."},
    {"id": "events", "name": "Domain events", "patterns": ["event_schemas", "publish_event", "EventPublisher", "event_handlers"], "description": "Domain event publishing and handlers. Present in both."},
    {"id": "pubsub", "name": "Pub/sub (Kafka/RabbitMQ)", "patterns": ["pubsub_connection", "pubsub_producer", "pubsub_consumer", "KafkaProducer", "aio-pika", "aiokafka"], "description": "Message broker client (Kafka or RabbitMQ) for pub/sub. Only in new: old used different event wiring; new generates explicit pubsub modules."},
    {"id": "cache", "name": "Cache (Redis/Memcached)", "patterns": ["redis", "aioredis", "cache_access", "memcached", "aiomcache"], "description": "Cache client (Redis/Memcached) for caching. In both; fewer projects in new (cache block not in all examples)."},
    {"id": "cqrs", "name": "CQRS", "patterns": ["CqrsBus", "CommandHandler", "QueryHandler", "projection", "cqrs_view"], "description": "CQRS command/query and projections. Only in new for projects that declare cqrs block."},
    {"id": "jobs", "name": "Background jobs", "patterns": ["APScheduler", "CronTrigger", "jobs_runner", "jobs_scheduler"], "description": "Scheduled background jobs (APScheduler). Only in new where jobs are declared."},
    {"id": "integrations_email", "name": "Email integration", "patterns": ["email_client", "send_email", "smtplib", "SMTP"], "description": "Email sending client. In both; fewer in new (integration block not in all examples)."},
    {"id": "integrations_sms", "name": "SMS integration", "patterns": ["sms_client", "send_sms", "twilio"], "description": "SMS sending client. In both; fewer in new."},
    {"id": "integrations_storage", "name": "Storage integration", "patterns": ["storage_client", "upload", "download", "boto3", "S3"], "description": "Object/blob storage client. In both; fewer in new."},
    {"id": "integrations_payment", "name": "Payment integration", "patterns": ["payment_client", "payment_provider"], "description": "Payment provider client. Only in new where payment integration is declared."},
    {"id": "resilience", "name": "Resilience (retry/circuit breaker)", "patterns": ["retry", "circuit_breaker", "resilient_client", "Tenacity"], "description": "Retry and circuit-breaker for outbound calls. Present in both."},
    {"id": "discovery", "name": "Service discovery", "patterns": ["service_discovery", "get_service_url", "discovery_", "consul", "kubernetes"], "description": "Service discovery (Consul/K8s/env) for calling other services. Present in both."},
    {"id": "observability_metrics", "name": "Metrics (Prometheus)", "patterns": ["Prometheus", "metrics_middleware", "/metrics"], "description": "Prometheus metrics endpoint and middleware. Missing in new: no generated metrics middleware."},
    {"id": "observability_tracing", "name": "Tracing (OpenTelemetry)", "patterns": ["opentelemetry", "tracing", "trace_id"], "description": "OpenTelemetry tracing. In both; fewer in new (observability profile)."},
    {"id": "observability_logging", "name": "Structured logging", "patterns": ["structlog", "structured_logger", "JSON logging"], "description": "Structured (e.g. JSON) logging. Missing in new: no generated structured logger."},
    {"id": "helpers_json", "name": "JSON helpers", "patterns": ["_json_helpers", "json_serialize"], "description": "JSON serialization helpers for events/schemas. Only in new (generated when needed)."},
    {"id": "helpers_validator", "name": "Validator helpers", "patterns": ["_validator_helpers"], "description": "Custom validation helpers. Only in new (generated when validation is used)."},
    {"id": "helpers_queue", "name": "Queue helpers", "patterns": ["_queue_helpers"], "description": "Queue/message decode helpers. Only in new (generated for pub/sub)."},
    {"id": "nosql", "name": "NoSQL (Mongo/document)", "patterns": ["nosql_client", "MongoClient", "document repository", "nosql_repository"], "description": "NoSQL client and repository. Only in new where nosql block is declared."},
    {"id": "docker_compose", "name": "Docker Compose", "patterns": ["docker-compose", "services:", "build:"], "description": "Docker Compose file for local/CI run. Present in both."},
    {"id": "dockerfile", "name": "Dockerfile", "patterns": ["FROM python", "Dockerfile"], "description": "Container build file. Present in both."},
    {"id": "tests", "name": "Tests (pytest/conftest)", "patterns": ["pytest", "conftest", "client", "fixture"], "description": "Pytest setup (conftest, fixtures). Present in both; layout differs (app/tests vs src/.../tests)."},
    {"id": "docs", "name": "Documentation", "patterns": ["api-reference", "architecture", "docs/"], "description": "Generated docs (api-reference, architecture). Missing in new: no generated docs folder."},
    {"id": "scripts", "name": "Scripts", "patterns": ["start.py", "stop.py", "run_tests.py", "scripts/dev", "scripts/init"], "description": "Dev/CI scripts: run test suite (run_tests.py), deployment smoke tests (deploy_test.py), local start/stop. Missing in new: no generated test-runner or deploy-test entrypoints."},
    {"id": "env_docs", "name": "ENV documentation", "patterns": ["ENV.md", ".env.example"], "description": "Environment variable documentation or .env.example. Present in both."},
]


def _normalize_project_key_saved_layout(relative_path: str, root: Path) -> str | None:
    """Normalize path under .generated_saved: first two segments, strip _docker/_k8s from second.

    Saved layout example: 01-tutorial/01-basic-entity_docker/... -> 01-tutorial/01-basic-entity
    """
    parts = Path(relative_path).parts
    if len(parts) < 2:
        return None
    first, second = parts[0], parts[1]
    second = second.removesuffix("_docker") if second.endswith("_docker") else second
    second = second.removesuffix("_k8s") if second.endswith("_k8s") else second
    return f"{first}/{second}"


def _normalize_project_key_current_layout(relative_path: str, root: Path) -> str | None:
    """Normalize path under .generated: path under python/docker/ -> first two segments.

    Current layout example: python/docker/01-tutorial/01-basic-entity/... -> 01-tutorial/01-basic-entity
    """
    normalized = relative_path.replace("\\", "/")
    if normalized.startswith("python/docker/"):
        rest = normalized[len("python/docker/"):]
    elif normalized.startswith("python\\docker\\"):
        rest = normalized.replace("\\", "/")[len("python/docker/"):]
    else:
        return None
    parts = rest.split("/")
    if len(parts) < 1:
        return None
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]}/{parts[1]}"


def _should_skip_path(path: Path, root: Path) -> bool:
    """Return True if path should be excluded from scanning."""
    rel = path.relative_to(root) if path.is_relative_to(root) else path
    parts = rel.parts
    for p in parts:
        if p in EXCLUDE_DIRS:
            return True
    if path.suffix in EXCLUDE_FILE_SUFFIXES:
        return True
    if path.name.startswith(".") and path.name not in (".env.example", ".env.template"):
        return True
    return False


def _is_likely_text(path: Path) -> bool:
    """Return True if file is likely text (by extension)."""
    text_ext = {".py", ".yml", ".yaml", ".json", ".md", ".txt", ".sh", ".toml", ".ini", ".env", ".example", ".template"}
    return path.suffix.lower() in text_ext or path.name.endswith(".env.example") or path.name.endswith(".env.template")


def _read_file_content(path: Path) -> str:
    """Read file as text; return empty string on error or binary."""
    try:
        raw = path.read_bytes()
        if b"\x00" in raw[:8192]:
            return ""
        return raw.decode("utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return ""


def _feature_matches_content(feature: dict[str, Any], content: str) -> bool:
    """Return True if any of the feature's patterns match content."""
    for p in feature["patterns"]:
        if p in content:
            return True
    return False


def _extract_snippet(content: str, max_len: int = 80) -> str:
    """Return first non-empty line trimmed to max_len."""
    for line in content.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return s[:max_len] + ("..." if len(s) > max_len else "")
    return ""


def scan_tree(
    root: Path,
    is_old: bool,
) -> tuple[dict[str, dict[str, list[tuple[str, str, str]]]], dict[str, dict[str, set[str]]]]:
    """Scan root for features. Return (by_feature, by_project).

    by_feature: feature_id -> {"old"|"new": [(project_key, relative_path, snippet), ...]}
    by_project: project_key -> {"old"|"new": set of feature_ids}
    """
    by_feature: dict[str, dict[str, list[tuple[str, str, str]]]] = {
        f["id"]: {"old": [], "new": []} for f in FEATURE_REGISTRY
    }
    by_project: dict[str, dict[str, set[str]]] = {}

    key = "old" if is_old else "new"
    norm_fn = _normalize_project_key_saved_layout if is_old else _normalize_project_key_current_layout

    try:
        all_files = list(root.rglob("*"))
    except OSError:
        return by_feature, by_project

    for path in all_files:
        if not path.is_file():
            continue
        if _should_skip_path(path, root):
            continue
        if not _is_likely_text(path):
            continue
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        rel_str = rel.as_posix()
        project_key = norm_fn(rel_str, root)
        if not project_key:
            continue
        content = _read_file_content(path)
        if not content:
            continue

        snippet = _extract_snippet(content)
        if project_key not in by_project:
            by_project[project_key] = {"old": set(), "new": set()}
        for feat in FEATURE_REGISTRY:
            if _feature_matches_content(feat, content):
                by_feature[feat["id"]][key].append((project_key, rel_str, snippet))
                by_project[project_key][key].add(feat["id"])

    return by_feature, by_project


def _merge_by_feature(
    by_feature_old: dict[str, dict[str, list[tuple[str, str, str]]]],
    by_feature_new: dict[str, dict[str, list[tuple[str, str, str]]]],
) -> dict[str, dict[str, list[tuple[str, str, str]]]]:
    """Merge old and new scan results into one by_feature structure."""
    merged: dict[str, dict[str, list[tuple[str, str, str]]]] = {}
    for f in FEATURE_REGISTRY:
        fid = f["id"]
        merged[fid] = {
            "old": by_feature_old.get(fid, {}).get("old", []),
            "new": by_feature_new.get(fid, {}).get("new", []),
        }
    return merged


def _merge_by_project(
    by_project_old: dict[str, dict[str, set[str]]],
    by_project_new: dict[str, dict[str, set[str]]],
) -> dict[str, dict[str, set[str]]]:
    """Merge old and new by_project; all project keys from both."""
    all_keys = set(by_project_old.keys()) | set(by_project_new.keys())
    merged: dict[str, dict[str, set[str]]] = {}
    for pk in sorted(all_keys):
        merged[pk] = {
            "old": by_project_old.get(pk, {}).get("old", set()),
            "new": by_project_new.get(pk, {}).get("new", set()),
        }
    return merged


def _count_files_excluding(root: Path) -> int:
    """Count files under root excluding EXCLUDE_DIRS and binary."""
    n = 0
    try:
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if _should_skip_path(p, root):
                continue
            if _is_likely_text(p):
                n += 1
    except OSError:
        pass
    return n


def _one_example_path(entries: list[tuple[str, str, str]]) -> str:
    """Return one example path from the list (first by project then path), or 'none'."""
    if not entries:
        return "none"
    # Prefer a path that looks like a main module (config, main, etc.) for readability
    for project, path, _ in entries:
        if "config" in path or "main" in path or path.endswith(".py"):
            return f"{project} — {path}"
    project, path, _ = entries[0]
    return f"{project} — {path}"


def write_report(
    report_path: Path,
    current_root: Path,
    saved_root: Path,
    by_feature: dict[str, dict[str, list[tuple[str, str, str]]]],
    by_project: dict[str, dict[str, set[str]]],
    file_count_current: int,
    file_count_saved: int,
) -> None:
    """Write purpose-driven Markdown report: summary, matrix, per-feature purpose + one example, compact per-project."""
    feature_order = [f["id"] for f in FEATURE_REGISTRY]
    feature_names = {f["id"]: f["name"] for f in FEATURE_REGISTRY}
    feature_descriptions = {f["id"]: f.get("description", "") for f in FEATURE_REGISTRY}

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Content-level comparison: .generated vs .generated_saved\n\n")
        f.write("Purpose-driven summary: what each capability is for, where it appears (counts + one example), and gaps.\n\n")

        # Executive summary
        f.write("## 1. Executive summary\n\n")
        f.write(f"- **Current (`.generated`):** `{current_root}` — text files scanned: **{file_count_current}**\n")
        f.write(f"- **Saved (`.generated_saved`):** `{saved_root}` — text files scanned: **{file_count_saved}**\n")
        projects_old = {pk for pk, d in by_project.items() if d["old"]}
        projects_new = {pk for pk, d in by_project.items() if d["new"]}
        f.write(f"- **Projects (normalized):** in old: **{len(projects_old)}**, in new: **{len(projects_new)}**\n\n")

        # Feature matrix
        f.write("## 2. Feature matrix\n\n")
        f.write("| Feature | In old (projects) | In new (projects) | Gap |\n")
        f.write("|---------|-------------------|--------------------|-----|\n")
        for fid in feature_order:
            old_list = by_feature[fid]["old"]
            new_list = by_feature[fid]["new"]
            old_projects = len({x[0] for x in old_list}) if old_list else 0
            new_projects = len({x[0] for x in new_list}) if new_list else 0
            if old_projects and new_projects:
                gap = "both"
            elif old_projects:
                gap = "only in old"
            elif new_projects:
                gap = "only in new"
            else:
                gap = "—"
            name = feature_names.get(fid, fid)
            f.write(f"| {name} | {old_projects} | {new_projects} | {gap} |\n")
        f.write("\n")

        # Per-feature summary: purpose, counts, one example each side, gap
        f.write("## 3. Per-feature summary (what it's for)\n\n")
        for fid in feature_order:
            name = feature_names.get(fid, fid)
            desc = feature_descriptions.get(fid, "")
            old_list = by_feature[fid]["old"]
            new_list = by_feature[fid]["new"]
            old_projects = len({x[0] for x in old_list}) if old_list else 0
            new_projects = len({x[0] for x in new_list}) if new_list else 0
            example_old = _one_example_path(old_list)
            example_new = _one_example_path(new_list)

            f.write(f"### {name}\n\n")
            if desc:
                f.write(f"**Purpose:** {desc}\n\n")
            f.write(f"- **In old:** {old_projects} projects. Example: `{example_old}`\n")
            f.write(f"- **In new:** {new_projects} projects. Example: `{example_new}`\n")
            if old_projects and not new_projects:
                f.write("- **Gap:** Missing in new.\n\n")
            elif new_projects and not old_projects:
                f.write("- **Gap:** Only in new.\n\n")
            else:
                f.write("- **Gap:** In both.\n\n")

        # Compact per-project: one table row per project with counts
        f.write("## 4. Per-project summary\n\n")
        f.write("Count of features only in old, only in new, or in both per project.\n\n")
        f.write("| Project | Only in old | Only in new | In both |\n")
        f.write("|---------|-------------|-------------|--------|\n")
        for project_key in sorted(by_project.keys()):
            d = by_project[project_key]
            old_feats = d["old"]
            new_feats = d["new"]
            only_old = old_feats - new_feats
            only_new = new_feats - old_feats
            both = old_feats & new_feats
            if not old_feats and not new_feats:
                continue
            f.write(f"| {project_key} | {len(only_old)} | {len(only_new)} | {len(both)} |\n")
        f.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Content-level comparison of .generated vs .generated_saved (purpose-driven report).",
    )
    parser.add_argument(
        "--current",
        type=str,
        default=".generated",
        help="Current generated root (default: .generated)",
    )
    parser.add_argument(
        "--saved",
        type=str,
        default=".generated_saved",
        help="Saved (old) generated root (default: .generated_saved)",
    )
    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Output Markdown report path (default: <datrix_root>/generated-comparison-report.md)",
    )
    args = parser.parse_args()

    try:
        datrix_root = get_datrix_root()
    except FileNotFoundError:
        print("ERROR: Could not find Datrix root directory", file=sys.stderr)
        return 1

    current_root = Path(args.current)
    saved_root = Path(args.saved)
    if not current_root.is_absolute():
        current_root = datrix_root / current_root
    if not saved_root.is_absolute():
        saved_root = datrix_root / saved_root

    if not current_root.is_dir():
        print(f"ERROR: Current root not found: {current_root}", file=sys.stderr)
        return 1
    if not saved_root.is_dir():
        print(f"ERROR: Saved root not found: {saved_root}", file=sys.stderr)
        return 1

    # Scan both trees
    by_feature_old, by_project_old = scan_tree(saved_root, is_old=True)
    by_feature_new, by_project_new = scan_tree(current_root, is_old=False)
    by_feature = _merge_by_feature(by_feature_old, by_feature_new)
    by_project = _merge_by_project(by_project_old, by_project_new)

    file_count_current = _count_files_excluding(current_root)
    file_count_saved = _count_files_excluding(saved_root)

    report_path = Path(args.report) if args.report else datrix_root / "generated-comparison-report.md"
    if not report_path.is_absolute():
        report_path = datrix_root / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_report(
        report_path,
        current_root,
        saved_root,
        by_feature,
        by_project,
        file_count_current,
        file_count_saved,
    )
    print(f"Report written: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
