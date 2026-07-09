---
model: claude-sonnet-4-6
---

# Evaluate Generated Code Skill (Quick Mode)

Perform a **fast, project-level evaluation** of a `.dtrx` application's generated output. This skill creates a timestamped evaluation directory, performs manifest-based completeness checking at the project level, and generates individual service evaluation prompts for deep-dive analysis.

**This skill is optimized for large projects** (10+ services). It performs quick checks and delegates deep semantic verification to the `/evaluate-generated-service` skill.

## When to Use

- User asks to "evaluate", "assess", or "check" generated output against its source
- User wants to know if a generated project is deployment-ready
- User asks "what's missing" from a generated project
- User wants a completeness comparison between DSL source and generated code
- User asks about deployment readiness or blockers for a generated project
- User asks about "dead code", "unnecessary code", or "extra/stale artifacts" in generated output
- User reports seeing platform-specific code (e.g., AWS files) when the target platform is different
- **New:** User wants to evaluate a large project (10+ services) quickly

## How to Invoke

Primary invocation with both paths:
```
/evaluate-generated

SOURCE: D:\datrix\datrix\examples\03-domains\ecommerce\system.dtrx
GENERATED: D:\datrix\.generated\python\docker-compose\local\03-domains\ecommerce
```

Alternative natural language:
```
"Evaluate generated output for the ecommerce project"
"Check deployment readiness of the ecommerce example"
"Compare ecommerce source against its generated code"
```

When only one path is given, the skill **must ask for the other**. Both SOURCE and GENERATED are required.

## What This Skill Does (Quick Mode)

1. **Creates timestamped evaluation directory:** `D:\datrix\eval\{YYYY-MM-DD-HHMMSS}-{project-slug}\`
2. **Quick project-level analysis:**
   - Reads `system.dtrx` to identify all services
   - Reads system-level configs (registry, gateway, observability)
   - Reads manifests (doesn't scan all generated files)
   - Verifies project-level infrastructure (docker-compose, .env, nginx, prometheus, grafana)
   - Identifies missing services or major structural issues
3. **Generates project-level report:** Quick overview of completeness and deployment readiness
4. **Generates service evaluation prompts:** One prompt file per service for deep-dive analysis using `/evaluate-generated-service`

**For deep semantic verification of individual services**, run the generated prompt files using `/evaluate-generated-service`.

## Documentation Quick Reference

For complete documentation index with "When to use" guidance, see [doc_index.md](../../../../../datrix/docs/doc_index.md).

**Essential reads (MANDATORY before starting):**
- [ai-agent-rules.md](../../../../../datrix-common/docs/contributing/ai-agent-rules.md) → Core rules, STOP AND THINK principle
- [architecture-overview.md](../../../../../datrix/docs/architecture/architecture-overview.md) → System architecture
- [design-principles.md](../../../../../datrix/docs/architecture/design-principles.md) → Design philosophy

**Quick refs:**
- [architecture-cheat-sheet.md](../../../../../datrix/docs/architecture/architecture-cheat-sheet.md)
- [design-principles-cheat-sheet.md](../../../../../datrix/docs/architecture/design-principles-cheat-sheet.md)

### Project Structure
Read `d:\datrix\{package-name}\.project-structure.md`. Regenerate if missing: `powershell -File "d:/datrix/datrix/scripts/dev/project-structure.ps1" {package-name}`.

## Inputs

1. **SOURCE** -- Path to `system.dtrx` file (the root DSL file that may include other .dtrx files)
2. **GENERATED** -- Path to the generated output directory (the root containing service dirs, docker-compose.yml, etc.)

## Workflow -- Quick Mode (Phased)

---

### Phase 0: Setup Evaluation Directory

**Goal:** Create timestamped directory for this evaluation session.

1. Generate timestamp: `{YYYY-MM-DD-HHMMSS}` (e.g., `2026-05-11-143022`)
2. Extract project slug from SOURCE path or system.dtrx system name (e.g., `ecommerce`, `inventory`)
3. Create directory: `D:\datrix\eval\{timestamp}-{project-slug}\`
4. Set this as the **evaluation directory** for all output files

**End-of-phase output:** Evaluation directory created and confirmed.

---

### Phase 1: Quick Source Analysis

**Goal:** Identify all services and system-level configuration without deep-diving into each service's DSL.

#### 1a: Read system.dtrx

1. Read `system.dtrx` from SOURCE path
2. Identify system name and version
3. Identify all `include` statements (these are service .dtrx files)
4. Extract service names from include paths (e.g., `"product-service.dtrx"` → `product-service`)
5. Identify system config references:
   - System config path (e.g., `config/system.dcfg`)
   - Registry config path
   - Gateway config path (if multi-service)
   - Observability config path

#### 1b: Read System-Level Configs (Optional)

Read system-level YAML configs to understand project-wide features:
- System config: platform (Docker/AWS/Azure), environment settings
- Registry: service registry configuration
- Gateway: NGINX routing, JWT auth, rate limiting
- Observability: metrics, tracing, logging, visualization

**DO NOT** read individual service .dtrx files or their config YAMLs in this phase. Just catalog that they exist.

#### 1c: Create Service Inventory

Build a table of services:

| Service Name | .dtrx File Path | Expected Generated Dir |
|--------------|----------------|----------------------|
| product-service | {SOURCE_DIR}/product-service.dtrx | {GENERATED}/ecommerce_product_service |
| order-service | {SOURCE_DIR}/order-service.dtrx | {GENERATED}/ecommerce_order_service |
| ... | ... | ... |

**End-of-phase output:** Service inventory table with SOURCE and GENERATED paths for each service.

**If confident** -- proceed to Phase 2.
**If NOT confident** (can't parse system.dtrx, missing includes) -- **STOP and report.**

---

### Phase 2: Quick Generated Output Analysis

**Goal:** Verify services exist and read manifests (don't scan all files).

#### 2a: Auto-detect Language and Platform

Determine the target language and platform from the generated output:

- **Python:** Look for `pyproject.toml`, `requirements.txt` in service dirs
- **TypeScript:** Look for `package.json`, `tsconfig.json` in service dirs
- **Docker:** Look for `docker-compose.yml` at project root

#### 2b: Read Manifests

Read all JSON files under `{GENERATED}/.datrix/manifests/`:
- `python.json` or `typescript.json` -- language-specific generated files
- `docker.json` -- Docker-specific generated files
- `component.json` -- platform-agnostic component files
- `sql.json` -- SQL DDL files

Each manifest has: `{ "target": "...", "generated_at": "...", "files": [...], "user_files": [...] }`

Extract:
- Generation timestamp
- Total file count per manifest
- List of services that have files in each manifest

#### 2c: Verify Service Directories Exist

For each service in the service inventory (from Phase 1), check if the expected generated directory exists:

| Service Name | Expected Dir | Exists? |
|--------------|-------------|---------|
| product-service | ecommerce_product_service | Yes/No |
| order-service | ecommerce_order_service | Yes/No |
| ... | ... | ... |

Flag any services defined in `system.dtrx` that have no corresponding generated directory.

**DO NOT** scan the contents of service directories in detail. Just verify they exist.

**End-of-phase output:** Service existence table, manifest summary, generation timestamp.

---

### Phase 3: Quick Project-Level Infrastructure Check

**Goal:** Verify project-level deployment infrastructure exists.

#### 3a: Docker Compose Verification

Check if `docker-compose.yml` exists at `{GENERATED}/docker-compose.yml`.

If it exists, read it and verify:
- [ ] All services from service inventory have a corresponding service entry
- [ ] Infrastructure containers exist (based on system config):
  - Gateway (nginx) if multi-service
  - Prometheus if observability.metrics enabled
  - Grafana if observability.visualization enabled
  - Jaeger if observability.tracing enabled
  - Loki if observability.logging enabled

**DO NOT** verify service-level infrastructure (databases, cache, brokers) in this phase. That's for `/evaluate-generated-service`.

#### 3b: Environment Variables

Check if `.env.example` exists at `{GENERATED}/.env.example`.

If it exists, note its presence. **DO NOT** verify individual service environment variables.

#### 3c: Gateway Configuration (if multi-service)

If gateway config is defined in system.dtrx:
- [ ] Check if `{GENERATED}/config/nginx/nginx.conf` exists
- Note its presence (detailed verification in service evaluations)

#### 3d: Observability Configuration

If observability is configured:
- [ ] Check if `{GENERATED}/config/prometheus/prometheus.yml` exists (if metrics enabled)
- [ ] Check if `{GENERATED}/config/grafana/` exists (if visualization enabled)
- Note presence (detailed verification later if needed)

**End-of-phase output:** Project-level infrastructure checklist with PASS/FAIL/N/A for each item.

---

### Phase 4: Quick Deployment Readiness Assessment

**Goal:** Identify project-level deployment blockers.

#### 4a: Critical Blockers

Flag if ANY of these are true:
- [ ] docker-compose.yml missing (for Docker platform)
- [ ] No services generated (all service directories missing)
- [ ] Manifest files missing or empty
- [ ] System config errors (if critical configs can't be read)

#### 4b: Warnings

Flag if ANY of these are true:
- [ ] .env.example missing
- [ ] Some services from system.dtrx have no generated directory
- [ ] Gateway config missing (for multi-service projects)
- [ ] Observability configs missing (if observability enabled)

**End-of-phase output:** List of critical blockers and warnings.

---

### Phase 5: Generate Project-Level Quick Report

**Goal:** Write a quick project overview report.

#### 5a: Report Filename

```
{EVAL_DIR}/project-evaluation-quick.md
```

Where `{EVAL_DIR}` is the timestamped evaluation directory created in Phase 0.

#### 5b: Report Template

Load `references/quick-report-template.md` (relative to this skill) when writing the report.

---

### Phase 6: Generate Service Evaluation Prompts

**Goal:** Create one prompt file per service for deep-dive evaluation.

#### 6a: Prompt File Format

For each service in the service inventory, create a prompt file:

**Filename:** `{EVAL_DIR}/service-{service-name}.prompt.md`

**Content Template:**

```markdown
# Service Evaluation Prompt

**Service:** {service name}
**Project:** {system name}
**Evaluation Session:** {EVAL_DIR}

---

## Instructions

This prompt file was generated by `/evaluate-generated` (quick mode). Invoke `/evaluate-generated-service` per its own SKILL.md, passing:

```
PROMPT_FILE: {this file path}
```

---

## Service Context

**Service Name:** {service name}
**Qualified Name:** {namespace.ServiceName} (extract from .dtrx if available, otherwise TBD)
**Source .dtrx:** `{service .dtrx path}`
**Generated Directory:** `{generated service directory path}`
**Project Source:** `{system.dtrx path}`
**Language:** {Python/TypeScript}
**Platform:** {Docker/AWS/Azure}

---

## Project-Level Context

**System Name:** {system name}
**Total Services:** {count}
**Gateway Enabled:** {Yes/No}
**Observability Enabled:** {Yes/No}

---

## Quick Scan Results (from project-level evaluation)

**Service Directory Exists:** {Yes/No}
**Files in Manifests:** {count} (approximate, filtered by service name pattern)

---

## Evaluation Scope

Full scope per `/evaluate-generated-service`'s own SKILL.md (DSL analysis, generated-output scan, cross-reference, semantic verification, dead-code detection, deployment readiness assessment, report generation in `{EVAL_DIR}/service-{service-name}-evaluation.md`).

---

## Expected Output

**Report Path:** `{EVAL_DIR}/service-{service-name}-evaluation.md`

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
- Project-level quick report: `{EVAL_DIR}/project-evaluation-quick.md`
- Other service prompts available in `{EVAL_DIR}/`
```

#### 6b: Generate Prompt Files

For each service in the service inventory:
1. Determine service name (from .dtrx filename, e.g., `product-service.dtrx` → `product-service`)
2. Determine paths (source .dtrx, generated directory, system.dtrx)
3. Create prompt file using template above
4. Save to `{EVAL_DIR}/service-{service-name}.prompt.md`

**End-of-phase output:** One prompt file per service, saved in evaluation directory.

---

### Phase 7: Confirm Completion

Emit lean summary:

```
EVAL: {READY|NOT READY} — {N}/{M} services, {blockers} blockers, {warnings} warnings
Report: {EVAL_DIR}/project-evaluation-quick.md
Prompts: {N} files in {EVAL_DIR}/
```

Do NOT add "Next steps" or invocation examples — the user knows what to do.

---

## Anti-Patterns to Avoid

- **Do NOT read individual service .dtrx files** -- that's for `/evaluate-generated-service`
- **Do NOT scan generated service directories in detail** -- manifest-based only
- **Do NOT perform semantic verification** -- quick mode doesn't do that
- **Do NOT read all config YAMLs** -- only system-level configs
- **Do NOT verify entity completeness** -- service-level concern
- **Do NOT detect dead code at service level** -- service-level concern
- **NO workarounds** — don't steer around issues, don't paper over them; fix the root cause or STOP and report (CLAUDE.md rule)
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)

This skill is FAST and LIGHTWEIGHT. It creates the evaluation structure and delegates deep work to `/evaluate-generated-service`.

---

## CLI Quick Reference

```bash
# Parse system.dtrx to see structure
powershell -File "d:/datrix/datrix/scripts/dev/syntax-checker.ps1" "{system.dtrx}"
```

