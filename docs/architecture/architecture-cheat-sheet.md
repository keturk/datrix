# Architecture Cheat Sheet

**What Datrix is:** a **multi-language, multi-platform code generator** that transforms `.dtrx` domain specifications into production-ready applications — NOT limited to Python/TypeScript, NOT limited to Docker/AWS/Azure. The shipped generator packages below are the *current* targets, never the boundary of the system. Two invariants follow: a fix for one language/platform must never break another (shared layers are consumed by every generator — test all consuming packages), and solutions must live at the most language/platform-agnostic layer that can own them.

Pipeline (user sources): `.dtrx -> Parser (datrix-language) -> extension directives on AST -> extension resolution (registry / TypeRegistry when invoked) -> Semantic Analysis -> Config Resolution -> Application (AST) -> Generators`

**Builtins and stdlib (language layer, before generators):** builtins ship as pre-parsed ASTs (traits, scalars, enums, and the four builtin domain exceptions in `builtins.dtrx`). Seven stdlib `.dtrx` modules ship as pre-parsed ASTs under `datrix-common/src/datrix_common/stdlib/` and stay lazy until semantic analysis needs them. User files still go through Tree-sitter parse + transformers into `Application`; stdlib symbols are registered as placeholders on the app scope and the owning stdlib module is deserialized on first reference during semantic analysis.

```
builtins        -> pre-parsed builtin ASTs
stdlib/*.dtrx   -> seven pre-parsed module ASTs (lazy-loaded)
user *.dtrx     -> TreeSitterParser + transformers -> Application
semantic analysis -> stdlib placeholders + lazy module injection -> continuing phases -> Generators
```

**Load order:** builtins → stdlib placeholder registration → user parse/transform → semantic analysis (lazy stdlib deserialization when a stdlib export is first resolved).

No IR layer. Parser produces `Application` directly. Named `GenerationPipeline.run` stages include: `parse` → `resolve_service_configs` → `analyze` → `resolve_infrastructure_configs` → `validate_deployment` → `apply_cli_overrides` → `normalize_service_memory_limits` → `discover_generators` / `discover_platforms` → `generate:{name}` (per generator) → file write → migrations (when configured) → language hooks + JSON format → `snapshot` (service filter and incremental merge sit between infra resolution and discovery when enabled). There is **no** `platform_validation` stage; cross-model and `(provider, DeploymentProvider)` realization checks run inside `resolve_infrastructure_configs` (the Stage 2 cross-model hook), and deployment-presence checks run in `validate_deployment`.

## Packages (14)

Optional **datrix-extensions** (domain packs, `datrix.extensions` entry points) plus thirteen core packages below.

| Package | Purpose |
|---------|---------|
| datrix-common | Foundation: AST model, types, semantic analysis, config resolution, generation framework. ZERO deps on other Datrix packages |
| datrix-language | Parser (Tree-sitter) + CST-to-AST transformers; shipped stdlib sources in `src/datrix_language/stdlib/` (eight `.dtrx` modules, pre-parsed at build time, lazy-loaded in analysis). Depends on datrix-common |
| datrix-codegen-common | Shared codegen intelligence: transpiler, `LanguageProfile` + `SyntaxEmitters`, context builders, genDSL. Consumed by EVERY language generator |
| datrix-codegen-component | Platform-agnostic artifacts (docs, config, scripts) |
| datrix-codegen-python | Python generation (FastAPI). Jinja2 + ruff format |
| datrix-codegen-typescript | TypeScript generation (NestJS/Express). Jinja2 (pre-formatted templates, no separate formatter) + `tsc --noEmit` compile validation |
| datrix-codegen-dotnet | .NET/ASP.NET Core generation (persistence, migrations, identity/auth, messaging, jobs, CQRS). Jinja2 + CSharpier |
| datrix-codegen-java | Java generation (Spring Boot 4.1 / Java 25). Jinja2 + google-java-format |
| datrix-codegen-sql | SQL DDL (PostgreSQL, MySQL) |
| datrix-codegen-docker | Docker/Compose generation. YAML builders |
| datrix-codegen-aws | AWS infrastructure (CDK/CloudFormation): VPC, ECS, RDS, ElastiCache, SNS/SQS, MSK (Kafka), DynamoDB, S3 |
| datrix-codegen-azure | Azure infrastructure (Bicep/ARM): App Service, Functions, Flexible Server, Cosmos DB, Service Bus, Event Hubs (Kafka), Redis, Blob, APIM, Front Door, AI Search |
| datrix-cli | CLI. Discovers generator plugins dynamically via entry points |
| datrix-extensions | Optional domain extension packs (`datrix.extensions`). Depends on datrix-common |

**datrix-codegen-dotnet is a real generator.** Increments 0-3 (conformance scaffold, transpiler core, entities/schemas, service scaffold & REST) landed first, producing a dotnet service that compiles and serves REST traffic. Increments 4-6 (persistence via EF Core, identity & auth with JWT/JWKS/gateway/trusted-caller/webhook/rate-limit/tenancy, messaging & workers covering pubsub/queue/CQRS/jobs) landed on top of that, full suite green (1347/0/0) with docker and cli generation unchanged and all G1-G8 conformance checks passing. dotnet now joins python, typescript, and java as a real generator, not a scaffold. **Migrations via FluentMigrator** shipped in two distinct steps, not one: the `DotnetFluentMigratorAdapter` itself landed first (renders real `[Migration(N)]` classes, all 8 `RdbmsMigrationAdapter` protocol members) but was unreachable from a real `datrix generate` run — no `migration` GenDSL domain, no registry wiring to `MigrationOrchestrator`, so `Migrations/*.cs` was never actually emitted in production; a follow-up closed that gap by declaring the `migration` domain and swapping `MigrationOrchestrator` into `datrix-codegen-dotnet`'s registry, mirroring python's/typescript's own wiring. Migration rendering is now both adapter-present AND pipeline-wired. Repo tooling keys off what is actually on disk — a package joins `test.ps1 -All`, `status-tests.ps1`, the venv install set, and the import-boundary/dead-code scans automatically as soon as it has a `pyproject.toml` / `src/` / `tests/`. Nothing needs to be re-listed by hand. Increment 7 (data & integrations — cache/nosql/storage/search/remote-config/secrets/email/sms/push/payment/crypto/discovery/resilience/CDN/extern + inter-service REST clients) and increment 8 (GraphQL/websockets/geo — dotnet's `CLAIMED_BUILTIN_GROUPS` now includes `GEO`, matching python/typescript/java) have **landed**. Increments 9-10 (test generation, package docs, serverless cloud wiring) have also **landed**: `TestSpecGenerator` renders xUnit specs from DSL `test(...)` blocks, `readme.md.j2` renders package docs, and the Lambda/Azure Functions/container serverless adapters wire cloud hosting. **Serverless handler realization is now complete on all three platforms** — job/subscription/endpoint/enqueue-consumer handlers each carry exactly one realization on LAMBDA, FUNCTIONS, and CONTAINER (a platform-agnostic handler class plus a thin per-platform adapter that translates the native trigger payload into it; CONTAINER alone emits no separate handler class, since its standalone entrypoints already carry the transpiled body inline). An unrecognized platform raises rather than silently emitting nothing. The **container-hosting platform** work (Azure Container Apps / ECS Fargate best-native targets) is separate and language-agnostic — it does not own dotnet's serverless authoring.

**Language count is not a constant.** Datrix targets many languages and platforms. Never write a doc, test, or script that assumes the currently-shipped set is the whole set.

**Not a package:** the **datrix** showcase repo (`D:\datrix\datrix`) holds only docs/examples/scripts — not installable, **no test suite**. Never put a `tests/` pytest suite, product tests, cross-package tests, or language/provider matrix tests in it. Datrix generates for **many languages and platforms** (not just Python/TypeScript, not just Docker/AWS/Azure); each `datrix-*` package tests only its own surface, and repo-level validation lives as scripts under `datrix/scripts/test/`.

## Entity Access (CRITICAL)

Entities are **block-scoped**, not flat. Always iterate per-service, per-block:
```python
for service in app.services.values():
    for rdbms_block in service.rdbms_blocks.values():
        for entity in rdbms_block.entities.values():
            generate(entity, service)
```
Never flatten entities across services.

## Plugin Architecture

Generators and extensions discovered via entry points: `datrix.generators`, `datrix.platforms`, `datrix.languages` (`LanguagePlugin` aggregate — folds the formerly-separate `datrix.language_hooks`/`datrix.language_runtime_spec` groups for Python/TypeScript), **`datrix.extensions`** (`DatrixExtension`).
Language generators subclass `LanguageGenerator` (10 abstract methods).
Type mappings registered with `TypeMappingRegistry.global_registry`.

## Multi-Target Plugin Architecture

Closes three closed-world defects (enum-based target identity, asymmetric language↔platform abstraction, hand-authored conformance). **Adopted** — all seven invariants hold today as executable gates:

| # | Invariant | Check |
|---|---|---|
| I1 | Zero target-name policy references in shared layers | `powershell -File "d:/datrix/datrix/scripts/dev/check-import-boundaries.ps1" -CheckTargetLiterals` — identifier-level lint ratchet over `datrix-common`/`datrix-codegen-common`/`datrix-cli` source, baseline empty (`datrix/scripts/config/target-literal-baseline.toml`) |
| I2 | Add-a-language = one package | Testkit fixture language plugin generates hello-world; `git status --porcelain` clean across framework repos (`datrix-codegen-common/tests/integration/testkit/test_closed_world_drill.py`) |
| I3 | Add-a-platform = one package | Same drill, fixture platform plugin |
| I4 | Drift is a red test in the drifting package | Kit self-consistency gate: declaration ↔ registration ↔ fixture output; mutation check fails that package's own suite (`test_mutation_check.py`) |
| I5 | No `(target → policy)` / `(target × target)` tables in shared layers | Subsumed by I1 — enums are gone |
| I6 | Language packages contain zero provider conditionals | `powershell -File "d:/datrix/datrix/scripts/dev/check-import-boundaries.ps1" -CheckProviderConditionals` — baseline empty (`datrix/scripts/config/provider-conditional-baseline.toml`). The same flag also runs a SEPARATE, hard-zero (no-baseline) check over the three SHARED packages (`datrix_common`/`datrix_codegen_common`/`datrix_cli`) — any hit fails outright, with no grandfathering mechanism. The one former offender, `EndpointOrchestrator`'s `ProviderId("local")` + docker-compose runtime comparison used to decide whether to inject the `test_auth` identity provider, is gone: the selected platform's own `PlatformCapabilityDeclaration.injected_test_identity_providers` answers this now (docker/local declares `("test_auth",)`; cloud platforms declare `()`), so the shared orchestrator asks the platform instead of naming one. |
| I7 | Import-boundary allowlist empty | `import-boundary-allowlist.toml` has zero entries |

Full decision log and phase plan: [Architecture Overview — Decision 15](./architecture-overview.md#decision-15-multi-target-plugin-architecture--open-world-targets-derived-conformance-adopted) | [datrix-common API — LanguagePlugin](../../../datrix-common/docs/datrix-common-api.md#languageplugin)

## Open-World Identity, Flavors, and Runtimes

Closes the last closed-world island the multi-target plugin migration left behind. Identity provider types, the six infrastructure flavors (Rdbms/Cache/Pubsub/Queue/Nosql/Storage), and deployment runtimes are **registry-validated open identifiers resolved against the installed platform plugin set** — no central capability matrix, no closed target/flavor/runtime enums. **Adopted**:

| # | Invariant | Detail |
|---|---|---|
| I1 | No central identity policy table | The former `CAPABILITY_MATRIX`/`_MATRIX_INDEX`/`_SET_FEATURES` and the hardcoded self-host-IdP-on-cloud special case are gone; one generic validator asks the selected platform plugin |
| I2 | No closed target/flavor/runtime enums remain | Identity provider type, deployment target, deployment runtime, and the six `*Flavor` value sets are open identifiers, not enums, in `datrix-common` |
| I3 | Each platform declares its own column | Identity `(provider type, feature)` support, flavor cells, and runtime support live in that platform's `PlatformCapabilityDeclaration` — never a shared table |
| I4 | Unknown values fail loud | An unrecognized identity provider type, flavor, or runtime raises, listing the installed plugins and what they declare |
| I5 | Behavior preserved for the shipped set | Existing identity/flavor/runtime combinations resolve identically — pure relocation of policy into declarations |
| I6 | Identity write-back realization is platform-declared | Subject claim, value encoding, and claim-name transform live on the platform plugin's `PlatformCapabilityDeclaration`; a platform declaring none fails loud on write-back; language packages carry zero provider names for identity write-back specifically, and any such name would be caught by the provider-conditional ratchet (`datrix/scripts/config/provider-conditional-baseline.toml`), held at the ratchet's empty baseline |

Full decision log: [Architecture Overview — Decision 22](./architecture-overview.md#decision-22-open-world-identity-providers-and-infrastructure-flavors-adopted).

## Cross-Target Parity Program

Establishes systematic parity enforcement across every registered language and platform generator, closing catalogued language-target and platform-target capability drift. **Decision 28 landed and passing:** `block-realization-parity-gate.ps1` (D1) is green across all 5 registered platforms with zero unexempted holes; `standing-conformance-gate.ps1` (D10) is green across all 8 committed specs. **Decision 30 landed:** the platform axis (aws/azure/docker) has a uniform pre-generation validation floor, zero catalogued capability holes, and its dead surfaces deleted and pinned by standing specs. **Decision 31 landed:** declared mini-DSL surfaces (EmitDSL typed predicate columns, shared test-generator plans, the closed seed pipeline, the emission-path gate, and queue/serverless block dispatch) replace the imperative bypasses that used to cause per-target drift, each held by a documented zero or a documented non-zero floor. Decision 29 remains approved, implementation in progress.

| # | Invariant | Enforcement mechanism |
|---|---|---|
| 1 | Every language-target/platform-target discrepancy class is a red check in the drifting package or a red repo-level gate, never a fact someone must notice | New per-axis parity gates alongside the existing domain-parity gate |
| 2 | Repo-level gates enumerate their target set from entry points at runtime, self-test their own non-vacuity every run, and refuse to pass with fewer than two targets | Each new gate copies the domain-parity gate's runtime-discovery + self-test shape |
| 3 | Gate inventories are derived from registration, never hand-authored lists | Corpus/drill/ratchet module lists replaced by entry-point derivation |
| 4 | A known hole is a typed, reviewed exemption entry with coordinates, a reason, and a pinned count — never silence; remediation removes the entry and decrements the count in the same change | Per-gate exemption JSON files under `datrix/scripts/config/` |
| 5 | A capability realized on one target is realized on the others or declared unsupported with a reason cell; genuine impossibilities become declarations | `supported=False`-with-reason cells replace silent gaps |
| 6 | Config surfaces no target consumes are deleted, not deprecated | Dead-surface removal + standing conformance specs |
| 7 | Per-target behavior is declared once rather than hand-written per target; a declared surface is the only emission path | Mini-DSL schema/plan-module extensions close imperative bypasses |

Full decision log: [Architecture Overview — Decision 28](./architecture-overview.md#decision-28-cross-target-parity-enforcement--derived-gates-and-declared-capability-holes-adopted) · [Decision 29](./architecture-overview.md#decision-29-language-target-capability-parity-to-the-reference-surface-approved--implementation-in-progress) · [Decision 30](./architecture-overview.md#decision-30-platform-target-validation-floor-and-realization-parity-adopted) · [Decision 31](./architecture-overview.md#decision-31-mini-dsl-consolidation--declared-surfaces-replace-imperative-bypasses-adopted)

## Portable Telemetry Volume, Platform Diagnostics, and Realization Conformance

Lifts telemetry export-volume control and platform-collected diagnostics out of individual targets into the portable layer, and adds the conformance machinery that makes a declared-but-never-realized knob impossible to ship. **Approved — implementation in progress: none of the models, gates, declarations, or exemption baselines below exist in the tree yet.**

| # | Invariant | Enforcement mechanism (planned) |
|---|---|---|
| 1 | Every OpenTelemetry signal has a portable export-volume field | Volume fields on the portable observability models — trace sampling rate (existing), a log export severity floor, and a metric export interval; a profile declaring each produces a functionally different artifact on every target that realizes it |
| 2 | Adopting the new fields changes no existing generated byte | Every new field defaults to today's effective behavior — no export floor, and each target's current metric cadence |
| 3 | No platform package defines its own retention or verbosity field | One portable `diagnostics { verbosity; retentionDays; dailyBudgetGb }` block on the shared platform-config base, projected by each platform onto its native mechanism; a scan finds zero surviving per-platform retention or log-selection declarations |
| 4 | A knob a target accepts is a knob it realizes | Per-package perturb/regenerate/diff conformance: Tier 1 catches a byte-identical (inert) field, Tier 2 catches a change confined to comments and strings (cosmetic-only) |
| 5 | A legitimately-inert field is a reviewed exemption with a pinned count, never silence | Package-owned exemption baseline, each entry carrying a written reason; the count is enforced against the entry list |
| 6 | The conformance gate proves its own non-vacuity every run | A known-realized knob must pass and a deliberately severed one must fail, checked before the real comparison |
| 7 | (provider × target) realization is one fact assembled from the registered target set | Each target declares its realized provider set across the five observability categories; the matrix is derived from the language and platform entry-point groups, never a hardcoded literal; declaring an unsupported pair is a loud validation error on every target |

Full decision log: [Architecture Overview — Decision 32](./architecture-overview.md#decision-32-portable-telemetry-volume-and-platform-diagnostics-contracts-with-realization-conformance).

## Codegen Shared-Layer Consolidation

Moves target-agnostic logic out of the language generator packages and into the layer that can own it, and removes the shared layer's own target-named surfaces. **Adopted** — both ratchets ship and pass, and all six invariants hold today as executable gates:

| # | Invariant | Check |
|---|---|---|
| 1 | Exactly one definition of each hoisted helper exists across the language packages | Duplicate-body scan reports zero exact-duplicate groups for the consolidated symbol set; the only surviving per-package definitions are pure pre-binding adapters (a single `return` delegating to the shared builder with this package's provider-language identifier and casing callable) |
| 2 | No language package redeclares a member set already declared in `datrix_codegen_common.enums` | `powershell -File "d:/datrix/datrix/scripts/dev/check-import-boundaries.ps1" -CheckSharedVocabulary` — baseline empty (`datrix/scripts/config/shared-vocabulary-baseline.toml`) |
| 3 | No type, field, or type alias in `datrix-codegen-common` carries a registered **language** name | `powershell -File "d:/datrix/datrix/scripts/dev/check-import-boundaries.ps1" -CheckSharedTargetNames` — baseline holds exactly **one** reviewed exemption, the scope-fenced `PYTHON_BASE_IMAGE_DIR` that `datrix-codegen-docker` consumes directly (`datrix/scripts/config/shared-target-name-baseline.toml`), down from 76 matched declarations. Complements I1, which matches a frozen name list rather than the identifier shape. Scoped to languages (not platforms — `local` collides with the English word) and to `datrix-codegen-common` (not `datrix-common`/`datrix-cli`, which hold platform config schemas and canonical-import API). `sql`/`nosql`-substring identifiers are **not** hits — `sql` is not a registered `datrix.languages` entry — and the ratchet's own self-test proves each as a non-match rather than baselining it |
| 4 | No package hand-rolls a service-body walk — `Service.iter_callable_bodies()` is the only enumeration | Zero private body-enumeration helpers survive; a `datrix-codegen-python` regression test proves a typed cross-service call inside a CQRS handler materializes its response module (observed red before the fix) |
| 5 | Every hoist is behavior-preserving | Each affected package's targeted suites pass unchanged |
| 6 | The scope fence holds — `datrix-codegen-sql` and `-component` stay out | Both packages' runtime dependencies still exclude `datrix-codegen-common` |

Both ratchets self-test their own non-vacuity as step 1 of every invocation, including a CLI mutation proof that plants a violation, sees the exact count delta, and sees the revert clear it.

Deliberately excluded: the thin delegating micro-generator classes (constructor arity and forwarded-kwarg variation would make a shared factory cost more than the boilerplate it removes).

Full decision log: [Architecture Overview — Decision 34](./architecture-overview.md#decision-34-codegen-shared-layer-consolidation--target-agnostic-logic-leaves-the-language-packages-adopted).

## One Fact, One Home — Residual Duplication and Standard-Library Adoption

Closes what the shared-layer consolidation above left behind: private copies of code that already has a shared home, a duplicate-detection scope gap, a parallel emission layer in one language package, and six hand-written topological sorts where the standard library has one. **Adopted** — all ten invariants hold today as executable gates.

| # | Invariant | Enforcement mechanism |
|---|---|---|
| 1 | A member set declared in two or more packages is a baseline entry with a written reason, never silence | New cross-package duplicate-vocabulary ratchet (decrease-only baseline + plant/observe/revert self-test). The enum-scoped `-CheckSharedVocabulary` ratchet is untouched at its hard zero — it enforces something stronger on a narrower surface |
| 2 | Code that has a shared home has exactly one definition | Per-symbol negative check that the private copy is gone, plus a positive test that the shared value drives behaviour — mandatory where the deleted copy had no test |
| 3 | A topological order survives the move to `graphlib` | Order test authored against the current code and observed green BEFORE the swap, asserting full sequences; a cycle then names its members instead of being inferred from a length comparison |
| 4 | A GraphQL reference cycle fails generation, never emits code that breaks at runtime | One shared sort; cycle fixture raises on every consuming target |
| 5 | A generator module is never reachable only from tests | Package-owned reachability check, pinned baseline, landed before the deletions it polices |
| 6 | Consolidation is behaviour-preserving unless declared otherwise | Duplicate-block count strictly drops per package (before/after) + byte-identical output; the one intended exception is re-blessed as a diff |
| 7 | One implementation per fact in the foundation, no new third-party dependency | Negative grep + a test proving the union of previously-divergent accepted inputs resolves through one path |
| 8 | A declared dependency is an imported dependency | Absent from the manifest; clean editable install succeeds; the test-only library moves to an extra named in that package's own `dev` list |
| 9 | An adapter cannot widen an orchestrator-owned policy set | Orchestrator validates every registered adapter and fails loud on a widening; both per-adapter sets survive |
| 10 | Parallel implementations are measured by a signal that survives divergence | `parallel-implementation-drift-gate.ps1 -Axis languages\|platforms` — one scanner, two runtime-derived target sets; platform axis compares packages, not registered names (name-sharing packages fold into one labelled entry, a no-op on the 1:1 language axis); each axis excludes the other axis's packages; two decrease-only count baselines, never shared (`datrix/scripts/config/parallel-implementation-drift-baseline.json`, `datrix/scripts/config/platform-implementation-drift-baseline.json`); zero unclassified groups |

**A duplicate a design REQUIRES is a reviewed baseline entry, not a merge** — per-platform capability declarations (Decision 22 I3), per-target realized-provider sets (Decision 32 invariant 7), and per-adapter expressible-operation sets are all near-identical *because* their governing decisions forbid a shared table. A container assembled entirely from a shared enum's members is consumption, not duplication, and is exempt from both vocabulary ratchets.

Full decision log: [Architecture Overview — Decision 36](./architecture-overview.md#decision-36-one-fact-one-home--residual-duplication-and-standard-library-adoption-adopted).

## Lowering the Declarative Floor on Both Axes

Decision 36 measures parallel implementations; this decision asks what would *remove* them, and shrinks the code that must be written once per language and once per platform toward its irreducible core. **Adopted:** all nine invariants hold today as executable gates.

| # | Invariant | Check |
|---|---|---|
| 1 | Every drifted group on **both** axes records not just whether the divergence is legitimate but whether it is **collapsible, and by what mechanism** | A `collapsibility.mechanism` field on every entry (or `none` plus a reason distinct from the legitimacy reason), so "what would remove this" is a query, not an investigation: `powershell -File "d:/datrix/datrix/scripts/test/collapsibility-classification-gate.ps1" -Axis languages\|platforms`, each axis holding its own unclassified-count ratchet |
| 2 | Classification completeness is checked, not commented | Each axis's entry count must equal that axis's live drifted count, verified alongside the drift gate — the requirement previously lived only as prose inside the classification file |
| 3 | A family already served by an existing declaration never gets a new surface | The casing family routes through the already-declared `LanguageProfile.naming` casers (`identifier_caser`, `type_name_caser`, `constant_caser`); a casing table would be a second home for a declaration that exists. The one new surface earned under F1 is the per-language dependency table — versions stay in the dependency catalog, so a row never carries one |
| 4 | Pure predicates over the sealed model live once in the shared layer, not once per platform | `datrix-codegen-common/src/datrix_codegen_common/generation/service_predicates.py`; where a predicate genuinely differs per platform, the difference becomes a **declared per-platform set read by one shared predicate** — never a per-platform copy of the algorithm |
| 5 | A hoist that does not move the ratchet did not remove a parallel implementation | Both drift baselines are decrease-only counts, and the decrease is pinned in the **same change** as the hoist that produced it |
| 6 | These are refactors, so their whole claim is that nothing changed | Behaviour preservation proven by **byte-identical generated output**, not a green suite alone; a deliberate behavioural change is re-blessed as a diff, never landed silently |
| 7 | A shared raise site is parameterized by the caller's own exception class, never forced onto a new declared-exception-type hook | `algorithms.declared_table_lookup`, `algorithms.entity_query_chain.transpile_where_comparison`, `transpiler.skeleton.nosql_dispatch.nosql_sort_direction`, `generation.raise_site_guards.reject_unrealizable_gateway_fields` all take the exception class as a parameter — python's own `ValueError` on the entity-query path is load-bearing, caught by its own chain-step fallback |
| 8 | No classification entry claims `status: intentional` while its own reason describes a capability or emission gap | The classification gate hard-rejects `mechanism: capability-gap-defect` + `status: intentional`; the five entries this was ever true for are fixed against a named reference target, not just reclassified to `tracked` |

**A mechanism label is a hypothesis about code, not a fact about it.** Roughly half the names once labelled collapsible-by-casing carried divergences beyond casing — an absent branch, a different return arity, a missing parameter — and reclassifying those to their real mechanism, before any hoist touched them, is what kept the eventual casing pass from silently dropping behaviour. Read the implementations before collapsing on a label. One name remains labelled collapsible-by-casing but unreached: `NamingProfile.structural_rule` is still populated as identity by every language, so a structural-rather-than-case-based convention (a leading-underscore private-field prefix, a directory's kebab-case convention) has no home in the profile as it stands, and inventing one needs a decision family to justify it, not a hoist.

Full decision log: [Architecture Overview — Decision 38](./architecture-overview.md#decision-38-lowering-the-declarative-floor-on-both-axes--collapsibility-classification-and-declared-dependency-tables-adopted).

## Transpiler pipeline (per file)

```
Stage 1: NameResolver     -> ResolutionTable (id(ast_node) -> ResolutionInfo)
Stage 2: QueryExpander    -> updated table + query annotations
Stage 3: LanguageTranspiler (Python / TypeScript / …) -> TranspileResult (code + imports + flags)
```

Orchestration: `StagePipeline` in **datrix-common** runs Stages 1–2 and configures the emitter; templates call the language transpiler for DSL bodies. Details: [code-generation.md](../../../datrix-common/docs/architecture/code-generation.md), [datrix-common architecture](../../../datrix-common/docs/architecture.md#transpiler-architecture-staged-pipeline).

| Category | Type | Lifetime |
|----------|------|----------|
| Config | `TranspileContext` | Per service; frozen |
| Per-file state | `FileScope` / language subclass | Fresh per emitted file; mutable |
| Upward artifacts | `TranspileResult` | Per visit; frozen |

## Domain extensions

- **DSL:** `use extension <name>;` inside `system { }` (stored on `app.extension_directives`).
- **Protocol `DatrixExtension` (eight surfaces):** properties `name`, `version`; methods `scalar_definitions()`, `builtin_objects()`, `value_struct_definitions()`, `db_extensions()`, `extra_dependencies()`, `template_dirs()` (`datrix_common.plugin.extension`).
- **Discovery:** `PluginRegistry.discover_extensions()`; load declared names: `load_declared_extensions(declared)`.
- **Types:** `TypeRegistry.load_extensions(extensions)` when callers register pack scalars.
- **Declared names in codegen:** `declared_extension_names(app)` → passed into `LanguageGenerator` / resolvers.
- **Python maps:** `PYTHON_EXTENSION_MAPS` + `build_python_type_map()` in `datrix_codegen_python.type_mappings` (raises `ExtensionNotSupportedError` if a declared extension has no Python map).
- **Every language + SQL package:** same split-ownership pattern, already shipped — `TS_EXTENSION_MAPS` (`datrix_codegen_typescript.type_mappings`), `SQL_EXTENSION_MAPS` (`datrix_codegen_sql.type_mappings`), `DOTNET_EXTENSION_MAPS` (`datrix_codegen_dotnet.type_mappings`), `JAVA_EXTENSION_MAPS` (`datrix_codegen_java.type_mappings`) each merge into their core `*_TYPE_MAP` via `build_type_map()`, mirroring `PYTHON_EXTENSION_MAPS` above. A new language package is expected to ship its own `*_EXTENSION_MAPS` module the same way.

Full guide: [extensions-guide.md](../../../datrix-extensions/docs/extensions-guide.md) · Core protocol: [datrix-common extensions](../../../datrix-common/docs/extensions.md).

## Extern Services

Contract-only declarations for external libraries/tools that Datrix does not generate. Consumed via `uses` (same as shared blocks and inter-service dependencies).

- **Container kinds:** `system`, `module`, `service`, `shared`, **`extern service`**
- **Extern service = contract only** — user builds and deploys the implementation
- **Allowed members:** `struct`, `enum`, `rest_api` (signature-only), `errors`, `auth`, `health`
- **No infrastructure blocks** (`rdbms`, `cache`, `pubsub`, etc.)
- **Config:** `deployment: container` (image + port, compose entries generated) or `deployment: external` (remote URL, no deployment artifacts)
- **Generated artifacts:** typed HTTP client, request/response models, error classes, contract validation (per consuming service)
- **AST:** `ExternService` in `datrix_common.datrix_model.extern_service`, registered on `Application.extern_services`
- **`uses` resolution order:** shared block → extern service → regular service

## RDBMS Migration Contract

Incremental, language-neutral, UUID-scoped. State lives under `{app_dir}/.datrix/rdbms-migrations/{rdbms_id}/`:
- `schema.json` — canonical schema snapshot (target-language/engine agnostic)
- `ledger.json` — ordered revision chain with database-agnostic canonical operations

Key rules:
- Every `RdbmsConfig` requires `id: UUID` in ConfigDSL
- Migration revisions are immutable once generated (append-only)
- Destructive changes are generation errors (no override)
- `RdbmsMigrationAdapter` protocol in `datrix-codegen-common` — Python/Alembic, TypeScript/MikroORM, SQL are adapters
- Shared-owned RDBMS migrations use `SharedPaths.rdbms_dir`, one apply unit per `rdbms_id`
- `GeneratedFile.retention = "append_only"` protects historical migration files from manifest cleanup

## Key Capabilities

- Background jobs (APScheduler), incremental RDBMS migrations (Alembic/MikroORM adapters), seed data
- Elasticsearch integration, inter-service HTTP auth (shared secret), JWT gateway
- GraphQL DataLoaders, rate limiting (gateway + per-route Redis), RFC 7807 errors
- Prometheus metrics, Grafana dashboards, cAdvisor, alert rules (the LOCAL/docker-native observability stack)
- **Native-only observability per platform** — each target emits only its native providers (LOCAL: Prometheus/Jaeger/Loki/Grafana/Alertmanager; AWS: CloudWatch/X-Ray; Azure: Azure Monitor/App Insights). Each platform declares its native set on `PlatformCapabilityDeclaration`; a generic validator rejects non-native providers at the platform boundary (see architecture-overview Decision 27; design principle 10)
- Export **volume** (trace sampling rate, log export floor, metric export interval) and platform-collected **diagnostics** (verbosity, retention, daily budget) are separate portable axes, orthogonal to the provider axis above — see Portable Telemetry Volume, Platform Diagnostics, and Realization Conformance above
- Declaration-driven gateway realizations (NGINX, Azure APIM, AWS API Gateway), emitted when the system declares `gateway { }`; all consume the same shared route enumeration (`datrix_common.generation.gateway_routes`), so the public surface — including relationship-derived nested sub-collection routes — and per-route JWT enforcement can never diverge between them. **Gateway-minted routes no backend serves are a declared family registry** (`GATEWAY_SYNTHESIZED_ROUTE_FAMILIES` → `gateway_synthesized_routes`, covering the health-probe and OpenAPI discovery/spec families): every realization consumes the registry rather than naming builders, so registering a family reaches every target at once. Minting one inside a single platform's private route table is what shipped health routes, and later the whole OpenAPI surface, on nginx alone. Per-service routing derived from auth contracts; upstreams, health aliases, CORS, rate limit zones
- ArcGIS FeatureServer paged ingestion (`arcgisFeatureLayer` integration kind): metadata-aware pagination, deterministic checksums, watermark optimization, archive/refresh modes

## DSL grammar snapshot (`.dtrx`)

High-level constructs the parser and transformers understand today. Full detail: [language-reference.md](../reference/language-reference.md) and [datrix-syntax-reference.md](../../../datrix-language/docs/reference/datrix-syntax-reference.md).

| Layer | Constructs |
|-------|------------|
| File structure | `include`, `from X import Y`, `system`, `module`, `service`, `extern service` |
| Declarations | `entity`, `abstract entity`, `trait`, `enum`, `struct`, `const`, `fn` |
| Field features | Types, optional (`?`), sized (`String(200)`), collections (`Array<T>`, `Map<K,V>`, `Set<T>`), modifiers (`: unique, indexed, immutable, server, …`), defaults (`= expr`). **Server-managed fields** use the **`server`** modifier (e.g. `UUID id : primaryKey, server = uuid();`) — there is **no** `@` prefix on field types. |
| Catalog types | Module- or service-level **`scalar Name : BaseType { constraints… }`** for constrained aliases on existing types |
| Errors | Module- or service-level **`exceptions { … }`** with `Name : status(N), message("…");` and optional structured fields |
| REST (unchanged) | Endpoint decorators such as **`@retry`**, **`@rateLimit`**, **`@cache`** remain **`@`-prefixed**; that is separate from field modifiers |

## Technology

Python 3.11+, Tree-sitter, Pydantic v2, Jinja2, ruff/CSharpier/google-java-format, pytest.

**AST dispatch:** `ExpressionVisitor[T]` / `StatementVisitor[T]` + `node.accept()` for expressions/statements (same pattern as `TypeVisitor[T]` for types); `CallTargetEmitter` + `dispatch_call()` for call targets — see [datrix-common-api — Transpiler modules](../../../datrix-common/docs/datrix-common-api.md#transpiler-modules).

## Full docs

- [architecture-overview.md](./architecture-overview.md)
- [datrix-stdlib-reference.md](../../../datrix-language/docs/reference/datrix-stdlib-reference.md) (stdlib module catalog)
- [code-generation.md](../../../datrix-common/docs/architecture/code-generation.md)
- [datrix-common-api.md — Transpiler modules](../../../datrix-common/docs/datrix-common-api.md#transpiler-modules)
