# Service Evaluation Report

**Service:** {qualified service name}
**Date:** {YYYY-MM-DD HH:MM}
**Source:** `{source .dtrx path}`
**Generated:** `{generated service directory path}`
**Language:** {Python/TypeScript}
**Generated At:** {timestamp from manifests}

---

## Executive Summary

**Service Readiness:** {READY / NOT READY -- {N} blockers}
**Completeness Score:** {X}/{Y} expected artifacts generated ({percentage}%)
**Deployment Blockers:** {count}
**Warnings:** {count}
**Dead Code Items:** {count}
**Semantic Issues:** {count} ({critical}/{major}/{minor})

{2-3 sentence summary of findings}

---

## Service DSL Analysis

### Service Configuration

| Config Type | Path | Present |
|-------------|------|---------|
| Service config | {path} | Yes/No |
| Registration | {path} | Yes/No |
| Resilience | {path} | Yes/No |
| Discovery | {count} dependencies | Yes/No |

### Blocks Defined

| Block Type | Block Name | Config Path | Feature Count |
|------------|------------|-------------|---------------|
| RDBMS | {name} | {path} | {entities count} |
| Cache | {name} | {path} | {definitions count} |
| PubSub | {name} | {path} | {topics/subs count} |
| REST API | {name} | {basePath} | {endpoints count} |
| GraphQL | {name} | {basePath} | {types/queries/mutations count} |
| Jobs | {name} | {path} | {jobs count} |
| Storage | {name} | {path} | - |
| NoSQL | {name} | {path} | {documents count} |
| CQRS | {name} | - | {views/commands/queries count} |

### Entity Summary (per RDBMS block)

| Block | Entity | Abstract | Fields | Relationships | Computed Fields | Lifecycle Hooks | Validations |
|-------|--------|----------|--------|---------------|----------------|----------------|-------------|
| {block} | {entity} | Yes/No | {count} | {count} | {count} | {list} | {count} |

### API Summary

**REST API Endpoints:**
| API | Method | Path | Internal | Parameters | Return Type |
|-----|--------|------|----------|------------|-------------|
| {api} | {method} | {path} | Yes/No | {count} | {type} |

**GraphQL API:**
| API | Queries | Mutations | Subscriptions |
|-----|---------|-----------|---------------|
| {api} | {count} | {count} | {count} |

---

## Generated Output Analysis

### Manifest Summary

| Manifest | Files for This Service | Files on Disk | Missing |
|----------|----------------------|---------------|---------|
| {language}.json | {count} | {count} | {count} |
| sql.json | {count} | {count} | {count} |

### Service Files Verification

| Category | Expected | Found | Missing | Status |
|----------|----------|-------|---------|--------|
| ORM Models / Entities | {N} | {N} | {list or "none"} | PASS/FAIL |
| Schemas / DTOs | {N} | {N} | {list or "none"} | PASS/FAIL |
| Services | {N} | {N} | {list or "none"} | PASS/FAIL |
| Routes / Controllers | {N} | {N} | {list or "none"} | PASS/FAIL |
| Migrations | {N} | {N} | {list or "none"} | PASS/FAIL |
| Cache modules | {N} | {N} | {list or "none"} | PASS/FAIL |
| PubSub modules | {N} | {N} | {list or "none"} | PASS/FAIL |
| Jobs modules | {N} | {N} | {list or "none"} | PASS/FAIL |
| NoSQL modules | {N} | {N} | {list or "none"} | PASS/FAIL |
| Storage modules | {N} | {N} | {list or "none"} | PASS/FAIL |
| Enum files | {N} | {N} | {list or "none"} | PASS/FAIL |
| Tests | {present/absent} | | | PASS/FAIL |
| Dockerfile | {present/absent} | | | PASS/FAIL |
| Requirements | {present/absent} | | | PASS/FAIL |

---

## Missing or Incomplete Items

### Critical (Deployment Blockers)

{Numbered list of items that MUST be present for deployment:}
1. **{What is missing}** -- {Which block/entity} -- {Why it blocks deployment}

### Warnings (Non-blocking but Notable)

{Numbered list of items that are expected but not strictly required:}
1. **{What is missing}** -- {Which block/entity} -- {Impact if absent}

### Observations

{Items that are notable but not necessarily problems:}
- {Observation about generated structure}

---

## Semantic Correctness Issues

Generated code that does NOT correctly implement the DSL semantics.

### Critical Issues (Causes Runtime Errors or Data Loss)

| Entity/Block | DSL Feature | DSL Source | Generated Code | Issue | Expected |
|--------------|-------------|------------|----------------|-------|----------|
| {Entity.field} | Computed field | {DSL code} | {Generated code} | {Issue} | {Expected code} |

### Major Issues (Incorrect Behavior, No Crash)

| Entity/Block | DSL Feature | DSL Source | Generated Code | Issue | Expected |
|--------------|-------------|------------|----------------|-------|----------|
| {Entity.validation} | Validation | {DSL code} | {Generated code} | {Issue} | {Expected code} |

### Minor Issues (Cosmetic or Optimization)

| Entity/Block | DSL Feature | DSL Source | Generated Code | Issue | Suggested Fix |
|--------------|-------------|------------|----------------|-------|---------------|
| {Entity.field} | Computed field | {DSL code} | {Generated code} | {Issue} | {Suggested fix} |

### How to Fix Semantic Issues (Transpiler-Side)

{For each semantic issue, trace back to the transpiler code that needs fixing:}

1. **[SEVERITY]** {Issue description}
   - **Transpiler:** `{TranspilerClass}` in `{file path}`
   - **Root cause:** {Why the transpilation is wrong}
   - **Suggested fix:** {What to change in the transpiler}

---

## Dead / Unnecessary Code

Generated artifacts that should NOT exist given the DSL source for this service.

### Unused Feature Modules

| Module Path | Expected DSL Block | Present in DSL? | Action |
|------------|-------------------|-----------------|--------|
| {path} | {block type} | No | Remove from generator |

### Orphaned Entity Artifacts

| Artifact | Expected Entity | Present in DSL? |
|----------|----------------|-----------------|
| {path} | {entity name} | No |

### Unused Dependencies

| Dependency | Feature It Supports | Feature Present? |
|-----------|--------------------|-----------------|
| {package name} | {feature} | No |

### How to Fix Dead Code (Generator-Side)

{For each dead code item, trace back to the generator:}

1. **[CATEGORY]** {What was generated unnecessarily}
   - **Generator:** `{GeneratorClass}` in `{file path}`
   - **Root cause:** {Why it was generated}
   - **Suggested fix:** {What to change in the generator}

---

## Service Deployment Readiness Checklist

### Container

| Check | Status | Details |
|-------|--------|---------|
| Dockerfile present | PASS/FAIL | |
| Multi-stage build | PASS/FAIL | |
| Non-root user | PASS/FAIL | |
| Port configuration | PASS/FAIL | |

### Database (if RDBMS blocks)

| Check | Status | Details |
|-------|--------|---------|
| Migration configs | PASS/FAIL | {per block} |
| Initial migrations | PASS/FAIL | {per block} |
| Database connection config | PASS/FAIL | |

### Environment

| Check | Status | Details |
|-------|--------|---------|
| Required vars documented | PASS/FAIL | {missing vars} |
| Database URLs | PASS/FAIL | |
| Secrets | PASS/FAIL | |

### Dependencies

| Check | Status | Details |
|-------|--------|---------|
| All required libraries | PASS/FAIL | {missing libs} |
| Database drivers | PASS/FAIL | |
| Cache libraries | PASS/FAIL | |
| Broker libraries | PASS/FAIL | |

---

## How to Fix (Generator-Side)

{Prioritized list of fixes needed in the generator code:}

1. **[CRITICAL]** {What is missing/broken}
   - **Generator:** `{GeneratorClass}` in `{file path}`
   - **Template:** `{template_name.j2}` in `{template path}`
   - **Root cause:** {Why the generator does not produce this artifact}
   - **Suggested fix:** {What to change}

2. **[WARNING]** {What is missing/broken}
   - **Generator:** ...
   - **Root cause:** ...
   - **Suggested fix:** ...

---

## Next Steps

{If tasks were generated:}
1. Review generated fix tasks in the package `.tasks/phase-{NN}/` directories (see "Generated Fix Tasks" section above)
2. Execute tasks: `/execute-tasks phase-{NN}` (or implement manually)
3. After fixes complete, regenerate this service: `powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" -Source "{source-dtrx}"`
4. Re-run this evaluation to verify all issues resolved
5. {Additional service-specific recommendations}

{If no tasks were generated (clean evaluation):}
1. Service is ready for deployment
2. {Additional service-specific recommendations if any}
