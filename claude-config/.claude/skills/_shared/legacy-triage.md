# Legacy Triage Workflow (no structured test output) — used by /troubleshoot-generated

### Phase 1L: Legacy Triage (when `index.json` does NOT exist)

**Goal:** Understand WHAT failed from raw logs. (This is the fallback for older test runs.)

**FIRST: script the parse.** Do not read raw pytest/deploy logs into context — run the triage script on each failing log and read its grouped report instead (read `datrix/scripts/dev/quick-reference.md` before invoking; a pre-tool hook enforces this):

```bash
powershell -File "d:/datrix/datrix/scripts/dev/triage-failures.ps1" "{log-path}" -Format pytest -OutputFile "D:\datrix\.test-output\legacy-triage.md"   # or -Format deploy
```

Fall back to the manual reads below only for detail the report lacks (Grep the specific log for the representative failure, don't read the whole file).

**For unit-tests failures:**
1. Read `unit-tests-summary.log` — identify which services failed and how many tests failed
2. For each failed service, triage `{service-name}-tests.log` (script above) — find exact test failures, assertion errors, import errors, collection errors

**For deploy-test failures:**
1. Read `deploy-test-summary.log` — identify overall status and which projects failed
2. Triage `deploy-test-output.log` (script above, `-Format deploy`) — find the specific failure point (build failure? health check timeout? test failure?)
3. For container issues, Grep `docker-logs/{container-name}.log` for error markers — application errors, startup failures, database connection issues

**What to look for:**
- `FAILED` / `ERROR` / `ERRORS` in pytest output
- `ImportError` / `ModuleNotFoundError` — wrong imports in generated code
- `TypeError` / `AttributeError` — wrong types or missing attributes in generated code
- `SyntaxError` — template rendering produced invalid syntax
- `sqlalchemy` errors — ORM model issues
- `pydantic` validation errors — schema issues
- Health check timeouts — service startup failures (check docker logs)
- Docker build failures — missing dependencies, Dockerfile issues
- `collection errors` — pytest could not even collect the tests (import failures)

**End-of-phase assessment:**
- Which services/containers failed
- What type of failure (build, startup, test, timeout)
- Key error messages
- How many distinct failures there appear to be

**If confident** in the failure summary (clear errors, obvious patterns) → proceed to Phase 2L (include brief status note).
**If NOT confident** (ambiguous logs, unclear failure mode, too many distinct failures) → **STOP and present summary, WAIT** for user direction.

---

### Phase 2L: Legacy Read the Failing Generated Code

**Goal:** Understand the generated code that's failing. Nothing more.

From the error messages identified in Phase 1L, read the generated file(s) that contain the bug:
- Error tracebacks point to file paths within the generated project
- Map the relative path to the full generated path under `.generated/`

**Key generated file locations within a project (Python):**
```
{service_dir}/
├── src/{python_package}/
│   ├── models/{block_name}/         # SQLAlchemy ORM models
│   ├── schemas/{block_name}/        # Pydantic schemas
│   ├── services/{block_name}/       # Service layer
│   ├── routes/{block_name}/         # FastAPI routes
│   ├── events/                      # Event handlers
│   ├── cqrs/                        # CQRS components
│   ├── cache/                       # Cache configuration
│   └── config/                      # App configuration
├── tests/
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

**Key generated file locations within a project (TypeScript):**
```
{service_dir}/
├── src/
│   ├── entities/                    # TypeORM entities
│   ├── dto/                         # Data transfer objects
│   ├── controllers/                 # NestJS controllers
│   ├── services/                    # NestJS services
│   ├── modules/                     # NestJS modules
│   ├── config/                      # Configuration files
│   ├── database/                    # Database configs
│   ├── nosql/                       # MongoDB configs
│   ├── pubsub/                      # Pub/sub configs
│   ├── observability/               # Tracing, logging
│   └── app.module.ts                # Root module
├── tests/
├── Dockerfile
├── docker-compose.yml
└── package.json
```

**End-of-phase assessment:**
- Which generated files contain the problem
- The specific code that's wrong (with line numbers)
- Your initial hypothesis about what's wrong

**If confident** in the hypothesis (clear bug, obvious mismatch) → proceed to Phase 3L (include brief status note).
**If NOT confident** (multiple possible causes, need user context on intent) → **STOP and present findings, WAIT** for user direction.

---

### Phase 3L: Legacy Trace Back to Codegen Source

**Goal:** Find the template/generator that produced the broken code.

#### 3a: Find the .dtrx Source File

The generated project path encodes the example location:
- Generated: `.generated/{language}/{platform}/{category}/{example}/`
- Source .dtrx: `datrix/examples/{category}/{example}/*.dtrx`

Read the .dtrx source to understand the entity/service definitions that drive code generation.

#### 3b: Identify the Generator and Template

Map the generated file type to its generator and template:

**Python targets:**

| Generated File Pattern | Generator Class | Template | Package |
|---|---|---|---|
| `models/{block}/*.py` | `EntityGenerator` | `entity_model.py.j2` | `datrix-codegen-python` |
| `schemas/{block}/*_schema.py` | `SchemaGenerator` | `entity_schema.py.j2` | `datrix-codegen-python` |
| `services/{block}/*_service.py` | `ServiceGenerator` | `entity_service.py.j2` | `datrix-codegen-python` |
| `routes/{block}/*_routes.py` | `EndpointGenerator` | `api_routes.py.j2` | `datrix-codegen-python` |
| `docker-compose.yml` | Docker generators | compose templates | `datrix-codegen-docker` |
| `Dockerfile` | Docker generators | dockerfile templates | `datrix-codegen-docker` |

**TypeScript targets:**

| Generated File Pattern | Generator/Template | Package |
|---|---|---|
| `src/entities/*.entity.ts` | Entity templates | `datrix-codegen-typescript` |
| `src/dto/*.dto.ts` | DTO templates | `datrix-codegen-typescript` |
| `src/config/*.ts` | Config templates | `datrix-codegen-typescript` |
| `src/database/*.ts` | Database config templates | `datrix-codegen-typescript` |
| `src/app.module.ts` | App module template | `datrix-codegen-typescript` |
| `docker-compose.yml` | Docker generators | `datrix-codegen-docker` |
| `Dockerfile` | Dockerfile templates | `datrix-codegen-docker` |

**Key source locations:**

- **Python templates:** `d:\datrix\datrix-codegen-python\src\datrix_codegen_python\templates\`
- **Python generators:** `d:\datrix\datrix-codegen-python\src\datrix_codegen_python\generators\`
- **TypeScript templates:** `d:\datrix\datrix-codegen-typescript\src\datrix_codegen_typescript\templates\`
- **TypeScript generators:** `d:\datrix\datrix-codegen-typescript\src\datrix_codegen_typescript\generators\`
- **Docker generators:** `d:\datrix\datrix-codegen-docker\src\datrix_codegen_docker\`
- **Path helpers:** `d:\datrix\datrix-common\src\datrix_common\paths.py`
- **Template engine:** `d:\datrix\datrix-common\src\datrix_common\rendering\`
- **Base generator:** `d:\datrix\datrix-common\src\datrix_common\generation\`

#### 3c: Read the Generator and Template

Read the generator class to understand:
- What context variables it passes to the template
- How it builds the context (field mappings, type resolution, path construction)
- What helper functions it calls

Read the Jinja2 template to understand:
- How the template uses the context variables
- Where the error in the generated output originates

#### 3d: Compare Generated Output vs Template

Side-by-side compare the generated code (broken) against the template logic to pinpoint exactly where the template or generator produces wrong output.

**End-of-phase assessment:**
- The specific template/generator code that causes the issue
- The causal chain from .dtrx → generator → template → broken output
- Your confidence level in the diagnosis

**If confident** in root cause (full causal chain traced, single clear origin) → proceed to Phase 4 (include brief status note). (Both structured and legacy workflows converge at Phase 4.)
**If NOT confident** (multiple possible origins, incomplete trace, need user input) → **STOP and present analysis, WAIT** for user direction.
