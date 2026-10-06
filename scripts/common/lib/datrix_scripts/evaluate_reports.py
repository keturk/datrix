"""The report text the evaluation scans can write themselves, from their own JSON.

``render_project_quick_report`` is the whole /evaluate-generated quick report: every section of it is
a fact the project scan already computed, so the skill reviews it instead of writing it.
``render_service_mechanical`` is the mechanical half of an /evaluate-generated-service report -- the
manifest subset, the expected-artifact checks, the dead-code candidates, dependencies, environment
variables, Dockerfile and migrations -- which the skill carries into its report and builds its
judgment sections (semantic correctness, root causes, fixes) on.

Both are pure functions of the scan payload: no model, no filesystem access.
"""

from __future__ import annotations

PRESENT = "PRESENT"
MISSING = "MISSING"
PASS = "PASS"
FAIL = "FAIL"
NOT_APPLICABLE = "N/A"
NONE_TEXT = "none"
MAX_LISTED = 10
QUICK_REPORT_FILENAME = "project-evaluation-quick.md"
SERVICE_MECHANICAL_TEMPLATE = "service-{name}-mechanical.md"
OBSERVABILITY_CONTAINERS = ("prometheus", "grafana", "jaeger", "loki")
GATEWAY_CONTAINERS = ("nginx", "gateway")


def _str(value: object) -> str:
    return "" if value is None else str(value)


def _list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _dict(value: object) -> dict[str, object]:
    return {str(k): v for k, v in value.items()} if isinstance(value, dict) else {}


def _flag(value: object) -> str:
    return PASS if value else FAIL


def _yes(value: object) -> str:
    return "Yes" if value else "No"


def _listed(items: list[object]) -> str:
    shown = ", ".join(f"`{_str(i)}`" for i in items[:MAX_LISTED])
    more = f" (+{len(items) - MAX_LISTED} more)" if len(items) > MAX_LISTED else ""
    return (shown + more) if items else NONE_TEXT


def _numbered(items: list[object], empty: str) -> list[str]:
    return [f"{n}. {_str(item)}" for n, item in enumerate(items, start=1)] or [empty]


def _summary(payload: dict[str, object]) -> str:
    blockers = _list(payload.get("critical_blockers"))
    warnings = _list(payload.get("warnings"))
    total = int(_str(payload.get("service_count")) or 0)
    generated = int(_str(payload.get("generated_service_count")) or 0)
    state = "is not ready to deploy" if blockers else "has no project-level deployment blocker"
    first = (f"{_str(payload.get('system_name'))} defines {total} service(s), of which {generated} were generated; "
             f"the project {state}.")
    second = (f" The first blocker: {_str(blockers[0])}." if blockers else
              f" {len(warnings)} warning(s) need a look." if warnings else " The scan raised no warning.")
    return first + second + " Service-level correctness is judged per service from the prompt files below."


def _infra_rows(payload: dict[str, object]) -> list[str]:
    compose = _dict(payload.get("docker_compose"))
    containers = _dict(compose.get("infra_containers"))
    exists = bool(compose.get("exists"))
    missing = _list(compose.get("missing_service_entries"))
    rows = ["| Check | Status | Details |", "|-------|--------|---------|",
            f"| docker-compose.yml exists | {_flag(exists)} | `{_str(compose.get('path'))}` |",
            f"| All services defined | {_flag(exists and not missing) if exists else NOT_APPLICABLE} | "
            f"{_listed(missing) if missing else ''} |"]
    gateway = any(containers.get(token) for token in GATEWAY_CONTAINERS)
    rows.append(f"| Gateway container | {(PASS if gateway else NOT_APPLICABLE) if exists else NOT_APPLICABLE} | |")
    for token in OBSERVABILITY_CONTAINERS:
        status = (PASS if containers.get(token) else NOT_APPLICABLE) if exists else NOT_APPLICABLE
        rows.append(f"| {token.capitalize()} container | {status} | |")
    return rows


def _infra_file(infra: dict[str, object], key: str) -> tuple[bool, str]:
    entry = _dict(infra.get(key))
    return bool(entry.get("exists")), _str(entry.get("path"))


def render_project_quick_report(payload: dict[str, object]) -> str:
    """The /evaluate-generated quick report, entirely from ``project-scan.json``."""
    services = [_dict(s) for s in _list(payload.get("services"))]
    manifests = [_dict(m) for m in _list(payload.get("manifests"))]
    infra = _dict(payload.get("infra"))
    blockers = _list(payload.get("critical_blockers"))
    warnings = _list(payload.get("warnings"))
    stamps = sorted({_str(m.get("generated_at")) for m in manifests if m.get("generated_at")})
    readiness = f"NOT READY -- {len(blockers)} blocker(s)" if blockers else "READY"
    lines = [
        "# Project Evaluation Report (Quick Mode)", "",
        f"**Project:** {_str(payload.get('system_name'))}",
        f"**Date:** {_str(payload.get('generated_at'))}",
        f"**Source:** `{_str(payload.get('source'))}`",
        f"**Generated:** `{_str(payload.get('generated_root'))}`",
        f"**Language:** {_str(payload.get('language'))}",
        f"**Platform:** {_str(payload.get('platform'))}",
        f"**Generated At:** {', '.join(stamps) if stamps else 'no manifest timestamp'}",
        "", "---", "", "## Executive Summary", "",
        f"**Project Readiness:** {readiness}",
        f"**Services Defined:** {_str(payload.get('service_count'))}",
        f"**Services Generated:** {_str(payload.get('generated_service_count'))}",
        f"**Services Missing:** {_str(payload.get('missing_service_count'))}",
        f"**Critical Blockers:** {len(blockers)}",
        f"**Warnings:** {len(warnings)}", "", _summary(payload), "",
        "**Next Steps:** Run individual service evaluations using the generated prompt files in this "
        "directory. Use `/evaluate-generated-service` with each prompt file for deep semantic verification.",
        "", "---", "", "## Services Inventory", "",
        "| Service Name | Source (.dtrx) | Generated Directory | Status |",
        "|--------------|----------------|-------------------|--------|",
    ]
    lines += [f"| {_str(s.get('qualified_name'))} | `{_str(s.get('dtrx_path'))}` | `{_str(s.get('expected_dir'))}` | "
              f"{PRESENT if s.get('expected_dir_exists') else MISSING} |" for s in services]
    compose = _dict(payload.get("docker_compose"))
    containers = _dict(compose.get("infra_containers"))
    lines += [
        "", f"**Total Services:** {_str(payload.get('service_count'))}",
        f"**Generated:** {_str(payload.get('generated_service_count'))}",
        f"**Missing:** {_str(payload.get('missing_service_count'))}",
        "", "---", "", "## Detected Features", "", "| Feature | Enabled |", "|---------|---------|",
        f"| Multi-service (Gateway) | {_yes(payload.get('gateway_enabled'))} |",
    ]
    lines += [f"| {token.capitalize()} | {_yes(containers.get(token))} |" for token in OBSERVABILITY_CONTAINERS]
    lines += ["", "---", "", "## Manifests Summary", "", "| Manifest | Files | Missing on Disk | Generated At |",
              "|----------|-------|-----------------|--------------|"]
    lines += [f"| {_str(m.get('target'))}.json | {_str(m.get('file_count'))} | {len(_list(m.get('missing_on_disk')))} | "
              f"{_str(m.get('generated_at'))} |" for m in manifests] or ["| (no manifest) | 0 | 0 | |"]
    env_ok, env_path = _infra_file(infra, "env_example")
    nginx_ok, nginx_path = _infra_file(infra, "nginx_conf")
    prom_ok, prom_path = _infra_file(infra, "prometheus_config")
    graf_ok, graf_path = _infra_file(infra, "grafana_dir")
    multi = int(_str(payload.get("service_count")) or 0) > 1
    lines += ["", "---", "", "## Project-Level Infrastructure", "", "### Docker Compose", "", *_infra_rows(payload),
              "", "### Environment", "", "| Check | Status | Details |", "|-------|--------|---------|",
              f"| .env.example exists | {_flag(env_ok)} | `{env_path}` |",
              "", "### Gateway Configuration", "", "| Check | Status | Details |", "|-------|--------|---------|",
              f"| nginx.conf exists | {_flag(nginx_ok) if multi else NOT_APPLICABLE} | `{nginx_path}` |",
              "", "### Observability Configuration", "", "| Check | Status | Details |", "|-------|--------|---------|",
              f"| Prometheus config | {_flag(prom_ok) if containers.get('prometheus') else NOT_APPLICABLE} | `{prom_path}` |",
              f"| Grafana dashboards | {_flag(graf_ok) if containers.get('grafana') else NOT_APPLICABLE} | `{graf_path}` |",
              "", "---", "", "## Critical Blockers", "",
              *_numbered(blockers, "None identified at project level. See individual service evaluations for "
                                   "service-level issues."),
              "", "---", "", "## Warnings", "", *_numbered(warnings, "None identified at project level."),
              "", "---", "", "## Service Prompt Files", ""]
    lines += [f"- [{_str(p).replace(chr(92), '/').rsplit('/', 1)[-1]}]({_str(p)})"
              for p in _list(payload.get("prompt_files"))]
    return "\n".join(lines) + "\n"


def render_service_mechanical(payload: dict[str, object]) -> str:
    """The mechanical sections of a service evaluation, from ``service-<name>-scan.json``."""
    service = _dict(payload.get("service"))
    summary = _dict(payload.get("artifact_check_summary"))
    dead = _dict(payload.get("dead_code"))
    docker = _dict(payload.get("dockerfile"))
    migrations = _dict(payload.get("migrations"))
    env_vars = _dict(payload.get("env_var_references"))
    convention = "OK" if service.get("dir_convention_ok") else \
        f"MISMATCH (expected `{_str(service.get('expected_dir'))}`, found `{_str(service.get('actual_dir'))}`)"
    lines = [f"# Mechanical findings -- {_str(service.get('qualified_name'))}", "",
             f"From `{_str(payload.get('generated_dir'))}`, scanned {_str(payload.get('generated_at'))}. "
             "Carry these into the report; the judgment sections are yours.", "",
             f"**Directory convention:** {convention}",
             f"**Expected-artifact checks:** {_str(summary.get('pass'))} PASS / {_str(summary.get('fail'))} FAIL",
             f"**Files on disk:** {_str(payload.get('fs_file_count'))}; not tracked by any manifest: "
             f"{len(_list(payload.get('fs_not_in_manifest')))}", "",
             "## Manifest Summary", "", "| Manifest | Files for This Service | Missing on Disk |",
             "|----------|----------------------|-----------------|"]
    lines += [f"| {_str(r.get('target'))}.json | {_str(r.get('service_file_count'))} | "
              f"{_listed(_list(r.get('missing_on_disk')))} |" for r in map(_dict, _list(payload.get("manifest_subset")))]
    lines += ["", "## Expected-Artifact Checks", "", "| Scope | Check | Status | Matched |",
              "|-------|-------|--------|---------|"]
    lines += [f"| {_str(c.get('scope'))} | {_str(c.get('check'))} | {_str(c.get('status'))} | "
              f"{_listed(_list(c.get('matched')))} |" for c in map(_dict, _list(payload.get("artifact_checks")))]
    lines += ["", "## Dead-Code Candidates", "", "| Module Dir | Paths | Requires Block |", "|---|---|---|"]
    lines += [f"| {_str(d.get('dir_name'))} | {_listed(_list(d.get('paths')))} | {_str(d.get('requires_block'))} |"
              for d in map(_dict, _list(dead.get("unused_module_dirs")))] or ["| none | | |"]
    lines += ["", "| Orphaned Artifact | Category | Stem |", "|---|---|---|"]
    lines += [f"| `{_str(o.get('path'))}` | {_str(o.get('category'))} | {_str(o.get('stem'))} |"
              for o in map(_dict, _list(dead.get("orphaned_entity_artifacts")))] or ["| none | | |"]
    lines += ["", "| Suspect Dependency | Feature Not Declared |", "|---|---|"]
    lines += [f"| {_str(s.get('dependency'))} | {_str(s.get('unused_feature'))} |"
              for s in map(_dict, _list(dead.get("suspect_dependencies")))] or ["| none | |"]
    lines += ["", "## Deployment Facts", "", "| Check | Status | Details |", "|-------|--------|---------|",
              f"| Dockerfile present | {_flag(docker.get('exists'))} | {_listed(_list(docker.get('matches')))} |",
              f"| Migration dirs | {_flag(_list(migrations.get('migration_dirs')))} | "
              f"{_listed(_list(migrations.get('migration_dirs')))} |",
              f"| Migration revisions | {_str(migrations.get('revision_file_count'))} | "
              f"{_listed(_list(migrations.get('revision_files')))} |",
              "", f"**Declared dependencies ({len(_list(payload.get('dependencies')))}):** "
              f"{_listed(_list(payload.get('dependencies')))}",
              "", f"**Environment variables referenced** ({_str(payload.get('env_var_files_scanned'))} file(s) scanned):",
              ""]
    lines += [f"- `{name}`: {_listed(_list(files))}" for name, files in sorted(env_vars.items())] or ["- none"]
    return "\n".join(lines) + "\n"
