# Pack: Generated Runtime and Deploy — Boot Path, Zero-Environment, Headers, Gateways, Observability

**Read when:** you touch what a generated service does at startup or on the wire: readiness probes, the secret backend, env-var handling, `.gitignore` of a generated project, framework HTTP headers, RFC 7807 problem types, gateway realizations, or observability providers.
**Not for:** migration state ([migrations.md](./migrations.md)) or auth semantics ([auth.md](./auth.md)).
**Core map:** [architecture-cheat-sheet.md](../architecture-cheat-sheet.md)

## Boot-Path Contracts

[Decision 45](../architecture-overview.md#decision-45-a-generated-service-must-be-able-to-reach-its-database--probe-transport-migration-readiness-and-chain-owned-schema-approved--implementation-in-progress) — Approved, implementation in progress.

A service that compiles is not a service that runs. Rules, each an executable comparison: a readiness probe exercises the transport its dependents connect over (`service_healthy` releases dependents on the probe's word); a probe command has one home and zero-consumer registries are deleted; every target's migration entrypoint waits for the database over a bounded retry (one shared attempt-count + delay) before any DDL; a migration failure reports the driver's diagnosis (credential-free URL); every type an emitted migration references is created by that same chain (`referenced − created` empty); a native type's name has one home per language and its labels one home for all (`enum_member_stored_literal`); schema DDL is never emitted outside the migration chain (no init-script DDL); an unrecognised migration operation kind raises; no service resolves a connection fact or credential from the process environment; a declared secret backend with no renderer raises rather than falling back to an environment reader. Migration specifics: [RDBMS Migration Decisions D39–D41](../rdbms-migration-decisions.md#boot-path-readiness-and-chain-owned-schema-d39d41).

## Zero-Environment Runtime

Every deployment-static value is baked at generation time; a running service consults no environment variable. Each language carries `LanguageCapabilityDeclaration.zero_environment_runtime` (regexes spelling an env read in its templates); a language not realizing it carries a counted `capability_gaps` row. `zero-environment-runtime-gate.ps1` censuses every language's templates (a realizing language fails on an unlisted/stale exemption in `zero-environment-runtime-baseline.json`; a gap-row language carries a decrease-only read count). A missing value is never defaulted.

## Untracked Project Artifacts

A generated `.gitignore` has two owners: the language's `service/gitignore.j2` (toolchain leftovers only) and the platform-declared `PlatformCapabilityDeclaration.untracked_project_artifacts` (pattern + reason; docker's `secrets/*/` and compose `.env`, Azure deploy transcripts), resolved by `capability_resolution.untracked_project_artifacts_for(provider, runtime)` and appended by the shared `DocGenerator` (`datrix_codegen_kernel.generation.project_ignore`). A language template never re-types a platform's secret layout.

## Framework HTTP Headers and Problem Types

Every header Datrix mints (trusted-caller token, rate-limit headers, inbound webhook secret, outbound delivery headers) has one home, `datrix_codegen_common.generation.http_headers` (`FRAMEWORK_HEADERS`; retired names under `RETIRED_HEADERS`); a language uses the exact registered name or constant and is obligated to realize every family. `framework-header-parity-gate.ps1` (exemptions in `framework-header-exemptions.json`, empty today; retired spellings have no exemption path). RFC 7807 `type` values are `urn:datrix:error:<slug>`, minted by `datrix_common.datrix_model.problem_types` (`FRAMEWORK_PROBLEM_TYPES`); `problem-type-parity-gate.ps1` holds every literal slug to the registry and every family to realized-or-counted-gap.

## Gateways and Observability

- **Declaration-driven gateways** (NGINX, Azure APIM, AWS API Gateway), emitted when the system declares `gateway { }`. All consume the one shared route enumeration (`datrix_codegen_kernel.generation.gateway_routes`), so the public surface (including nested sub-collection routes) and per-route edge credential policy cannot diverge. A GraphQL HTTP path is EXACT, the subscription path `<basePath>/subscriptions` is an upgrade route, and a path published by two gateway services fails generation. **Gateway-minted routes no backend serves are a declared family registry** (`GATEWAY_SYNTHESIZED_ROUTE_FAMILIES` → `gateway_synthesized_routes`: health-probe and OpenAPI discovery/spec families); registering a family reaches every target, and a platform's private route table never mints one.
- **Native-only observability per platform** — each target emits only its native providers (LOCAL: Prometheus/Jaeger/Loki/Grafana/Alertmanager + cAdvisor and alert rules; AWS: CloudWatch/X-Ray; Azure: Azure Monitor/App Insights). Each platform declares its set on `PlatformCapabilityDeclaration`; a generic validator rejects non-native providers (Decision 27). Export volume and diagnostics are separate portable axes ([parity-and-obligation.md](./parity-and-obligation.md)).
- Jobs run on a schedule or on demand through `dispatch Job();`, realized as a framework-owned queue and consumer: the semantic analyzer synthesizes one builtin queue and one builtin same-service consumer per dispatched job, so every registered language, engine and platform provisions it exactly as it does an author's self-consumed queue, and the consumer runs the job's own timeout/retry/dead-letter wrapper.
- Other shipped capabilities: background jobs (APScheduler), seed data, Elasticsearch, GraphQL DataLoaders, rate limiting (gateway + per-route Redis), RFC 7807 errors, inter-service HTTP auth, ArcGIS FeatureServer paged ingestion (`arcgisFeatureLayer` integration kind).
