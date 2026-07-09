# Project Evaluation Report (Quick Mode)

**Project:** {system name}
**Date:** {YYYY-MM-DD HH:MM}
**Source:** `{SOURCE path}`
**Generated:** `{GENERATED path}`
**Language:** {Python/TypeScript}
**Platform:** {Docker/AWS/Azure}
**Generated At:** {timestamp from manifests}

---

## Executive Summary

**Project Readiness:** {READY / NOT READY -- {N} blockers}
**Services Defined:** {count}
**Services Generated:** {count}
**Services Missing:** {count}
**Critical Blockers:** {count}
**Warnings:** {count}

{2-3 sentence summary}

**Next Steps:** Run individual service evaluations using the generated prompt files in this directory. Use `/evaluate-generated-service` with each prompt file for deep semantic verification.

---

## Services Inventory

| Service Name | Source (.dtrx) | Generated Directory | Status |
|--------------|----------------|-------------------|--------|
| {service} | {path} | {dir} | PRESENT / MISSING |
| ... | ... | ... | ... |

**Total Services:** {count}
**Generated:** {count}
**Missing:** {count}

---

## System Configuration

| Config Type | Path | Present |
|-------------|------|---------|
| System config | {path} | Yes/No |
| Registry | {path} | Yes/No |
| Gateway | {path} | Yes/No |
| Observability | {path} | Yes/No |

### Detected Features

| Feature | Enabled |
|---------|---------|
| Multi-service (Gateway) | Yes/No |
| Service Registry | Yes/No |
| Metrics (Prometheus) | Yes/No |
| Visualization (Grafana) | Yes/No |
| Tracing (Jaeger) | Yes/No |
| Logging (Loki) | Yes/No |

---

## Manifests Summary

| Manifest | Files | Generated At |
|----------|-------|--------------|
| {language}.json | {count} | {timestamp} |
| docker.json | {count} | {timestamp} |
| component.json | {count} | {timestamp} |
| sql.json | {count} | {timestamp} |

---

## Project-Level Infrastructure

### Docker Compose

| Check | Status | Details |
|-------|--------|---------|
| docker-compose.yml exists | PASS/FAIL | |
| All services defined | PASS/FAIL | {missing services} |
| Gateway container | PASS/FAIL/N/A | |
| Prometheus container | PASS/FAIL/N/A | |
| Grafana container | PASS/FAIL/N/A | |
| Jaeger container | PASS/FAIL/N/A | |
| Loki container | PASS/FAIL/N/A | |

### Environment

| Check | Status | Details |
|-------|--------|---------|
| .env.example exists | PASS/FAIL | |

### Gateway Configuration (if multi-service)

| Check | Status | Details |
|-------|--------|---------|
| nginx.conf exists | PASS/FAIL | |

### Observability Configuration

| Check | Status | Details |
|-------|--------|---------|
| Prometheus config | PASS/FAIL/N/A | |
| Grafana dashboards | PASS/FAIL/N/A | |

---

## Critical Blockers

{Numbered list of project-level deployment blockers:}
1. **{Blocker}** -- {Why it blocks deployment}

If no blockers: "None identified at project level. See individual service evaluations for service-level issues."

---

## Warnings

{Numbered list of warnings:}
1. **{Warning}** -- {Impact}

If no warnings: "None identified at project level."

---

## Service Prompt Files

- [{service-1}.prompt.md]({EVAL_DIR}/service-{service-1}.prompt.md)
- [{service-2}.prompt.md]({EVAL_DIR}/service-{service-2}.prompt.md)
- ...
