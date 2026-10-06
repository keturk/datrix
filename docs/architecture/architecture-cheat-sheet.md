# Architecture Cheat Sheet

**This is the map, not the territory.** It holds what every task needs. Anything deeper lives in a **knowledge pack** (table below): open the pack for the area you are touching, and only that one. Not sure which? Ask: `powershell -File "d:/datrix/datrix/scripts/dev/ineedtoknow.ps1" "<your question>"` answers from the packs, the decision log and the agent rules with a file and line range to open (`dev\ineedtoknow.ps1` in `datrix/scripts/dev/quick-reference.md`).

**What Datrix is:** a **multi-language, multi-platform code generator** that turns `.dtrx` domain specifications into production-ready applications — NOT limited to Python/TypeScript, NOT limited to Docker/AWS/Azure. The shipped generator packages are the *current* targets, never the boundary. Two invariants follow: a fix for one language/platform must never break another (shared layers are imported by every generator — test every package the change reaches), and solutions live at the most language/platform-agnostic layer that can own them. Never write a doc, test, or script that assumes the shipped set is the whole set.

**Pipeline:** `.dtrx → Parser (datrix-language) → extension directives on AST → extension resolution → Semantic Analysis → Config Resolution → Application (sealed AST) → Generators`. No IR layer. `GenerationPipeline` (`datrix-cli/src/datrix_cli/pipeline/generation.py`) runs an ordered list of typed stages — see [pipeline-stages](./packs/pipeline-stages.md).

## Knowledge Packs — Read the One You Need

| If you are… | Read |
|---|---|
| Adding/changing a language, platform or frontend target; plugin entry points; capability declarations; identity/flavor/runtime validation; a package dependency edge or import boundary; a domain extension | [target-plugins](./packs/target-plugins.md) |
| Seeing two targets behave differently; touching `capability_gaps`, a parity gate, a portable config field, telemetry/diagnostics; a `datrix/scripts/gates/*/*-gate.ps1` is red | [parity-and-obligation](./packs/parity-and-obligation.md) |
| Moving, hoisting or deduplicating code; a duplicate-body / shared-vocabulary / manifest-import gate is red; deciding which package owns a module | [shared-layer-and-one-fact](./packs/shared-layer-and-one-fact.md) |
| Touching `auth(...)`, identity providers, guards, tenancy, `@crossTenant`, `@produces`, API keys, revocation | [auth](./packs/auth.md) |
| Touching Angular/Flutter or any client target, the client/UI contract, the `app` container, `UI0xx` diagnostics | [frontend-clients](./packs/frontend-clients.md) |
| Touching DSL doc comments, enum keywords or wire/stored values, `work { }`, `extern service`, or needing the grammar snapshot | [dsl-features](./packs/dsl-features.md) |
| Touching the transpiler, genDSL paths/escaping, `#{}` interpolation, SQL literal quoting | [codegen-engine](./packs/codegen-engine.md) |
| Touching generated-service startup, the secret backend, env vars, framework headers, problem types, gateways, observability | [runtime-and-deploy](./packs/runtime-and-deploy.md) |
| Touching schema snapshots, the migration ledger, `migrations { }`, migration adapters | [migrations](./packs/migrations.md) |
| Touching the LSP, keyword manifest, `datrix-vscode` | [language-server](./packs/language-server.md) |
| Touching the `agents` block, tools, model providers, `approval`, `replay` | [ai-agents](./packs/ai-agents.md) |
| Adding/reordering a pipeline stage; builtins/stdlib loading; "where in the run does X happen?" | [pipeline-stages](./packs/pipeline-stages.md) |
| Needing the *why* behind a rule | [architecture-overview](./architecture-overview.md) (numbered decision log; each pack links its decisions) |

## Packages

Eighteen core packages plus optional **datrix-extensions**. Dependencies point downward only.

| Package | Role |
|---------|------|
| datrix-common | Foundation: AST model, types, config resolution, plugin and deployment declarations. ZERO deps on other Datrix packages |
| datrix-semantic | `SemanticAnalyzer`, phase pipeline, validators, synthesis, auth-contract lowering. Depends on common only |
| datrix-migration | RDBMS migration machinery (snapshot, diff, policy, ledger, state store). Depends on common only |
| datrix-language | Tree-sitter parser, CST→AST transformers, stdlib `.dtrx` modules, language server. Depends on common, semantic |
| datrix-codegen-kernel | Target-neutral generation framework (`Generator`, template engine, discovery, type-mapping registry, shared route/runtime derivations, deploy-script machinery, GenDSL model, Seed, `sql_facts`). Depends on common, migration; loads no language-layer module |
| datrix-codegen-common | Language layer: transpiler, `LanguageProfile` + `SyntaxEmitters`, context builders, genDSL. Used by EVERY language generator |
| datrix-codegen-typescript-core | Shared TypeScript core (transpiler core, profile, type maps, naming/path facts, web-client mechanics). Library; used by the TS backend and every TS-emitting frontend |
| datrix-codegen-python / -typescript | Backend language generators (FastAPI / NestJS-Express) |
| datrix-codegen-sql / -component | SQL DDL; platform-agnostic artifacts (docs, config, scripts). Depend on the kernel, never on codegen-common |
| datrix-codegen-docker / -aws / -azure | Platform generators: Compose; CDK/CloudFormation; Bicep/ARM |
| datrix-codegen-angular / -flutter | Client targets (artifact-phase plugins, **not** languages); activate only when the app declares them |
| datrix-cli | CLI; discovers plugins via entry points |
| datrix-extensions | Optional domain packs (`datrix.extensions`) |
| datrix-testing | Shared test harness; a `dev` extra of every package, never a runtime dependency. The `pytest11` feature-tag plugin stays in common |

Full per-package dependency detail and the layering invariants: [target-plugins](./packs/target-plugins.md). Repo tooling keys off what is on disk (a `pyproject.toml`/`src/` joins venv install and scans; a test suite joins `test.ps1`), so nothing is re-listed by hand. Repo boundaries and placement: `.claude/rules/repo-boundaries.md`.

- **Not a package:** the **datrix** showcase repo (`D:\datrix\datrix`) holds docs/examples/scripts only — **no test suite**, no product or cross-package tests; repo-level validation is scripts under `datrix/scripts/gates/` (and the test-tooling gates under `datrix/scripts/test/`).
- **datrix-vscode** is TypeScript, not installable; its Node suite runs under `test.ps1` ([language-server](./packs/language-server.md)).

## Entity Access (CRITICAL)

Entities are **block-scoped**. Always iterate per-service, per-block; never flatten across services:
```python
for service in app.services.values():
    for rdbms_block in service.rdbms_blocks.values():
        for entity in rdbms_block.entities.values():
            generate(entity, service)
```

## Plugin Architecture

Entry-point groups: `datrix.generators`, `datrix.platforms`, `datrix.languages` (`LanguagePlugin` aggregate), `datrix.extensions` (`DatrixExtension`). Language generators subclass `LanguageGenerator` (10 abstract methods). Type mappings register with `TypeMappingRegistry.global_registry`. Details: [target-plugins](./packs/target-plugins.md).

## Standing Rules (apply to every change)

Each is held by an executable gate; the pack and decision named give the check.

1. **Shared layers ask, targets answer.** No language/provider name in shared packages; target facts live in the target's plugin declaration ([target-plugins](./packs/target-plugins.md)).
2. **Same source, same behaviour; only rendering differs.** A per-target behaviour difference is a defect; a missing capability is a counted `capability_gaps` row, never an exemption. Repo gates derive their target inventories from registration and read each target's generated artifacts through that target's own conformance probes (`LanguagePlugin.conformance_probes`, `PlatformPlugin.declared_conformance_probes()`), never naming a target; each gate's self-test proves it by scanning itself ([parity-and-obligation](./packs/parity-and-obligation.md)).
3. **One fact, one home.** A function with a shared home has one definition; a hoist removes every private copy ([shared-layer-and-one-fact](./packs/shared-layer-and-one-fact.md)).
4. **A declared knob must be realized,** and a declared surface is the only emission path for its concern.
5. **Open-world identifiers fail loud.** Providers, flavors, runtimes, targets are registry-validated, never closed enums.
6. **Zero-environment runtime; credentials fail closed;** a missing value is never defaulted ([runtime-and-deploy](./packs/runtime-and-deploy.md)).
7. **Every seam gets a set comparison in code** (producer vs consumer), landed as a validator or test.
8. **One import path per symbol;** no upward imports ([target-plugins](./packs/target-plugins.md)).
9. **Connection-bearing surfaces walk the realized or connected block set.** What a service connects to (cache clients, settings, connection keys, network reach, access grants) is derived from `realized_cache_blocks(service)` (its own blocks plus the shared ones it consumes through `uses`), never from the service's own block alone; every platform proves it supplied each key the connection surface declares (`require_cache_keys_supplied`). Held by `datrix/scripts/gates/realization/shared-cache-realization-gate.ps1`.

10. **One async-hosting decision.** Whether a service's consumers, queue workers and jobs run in its web app (`hosting = "inProcess"`) or in dedicated runtimes is answered once, by the kernel's `resolve_service_async_hosting`, and every platform and language realizes the answer from the kernel `InProcessHostingPlan`; a target never carries its own "supports in-process" flag. A host that suspends idle processes is refused, never silently degraded.

## Technology

Python 3.11+, Tree-sitter, Pydantic v2, Jinja2, ruff, pytest.

## Full Docs

- [architecture-overview.md](./architecture-overview.md) — decision log
- [datrix-stdlib-reference.md](../../../datrix-language/docs/reference/datrix-stdlib-reference.md)
- [code-generation.md](../../../datrix-common/docs/architecture/code-generation.md)
