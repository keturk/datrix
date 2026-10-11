# Pack: Codegen Engine — Transpiler, DAL generator, Stage Boundaries

**Read when:** you touch the transpiler (`StagePipeline`, `NameResolver`, `QueryExpander`, `LanguageTranspiler`, `TranspileContext`/`FileScope`/`TranspileResult`), a backend generation domain or its `.dal` declaration, DAL generator output paths or escaping, `#{}` interpolation, or SQL literal quoting.
**Not for:** deciding what a target must realize ([parity-and-obligation.md](./parity-and-obligation.md)).
**Core map:** [architecture-cheat-sheet.md](../architecture-cheat-sheet.md)

## Transpiler Pipeline (per file)

```
Stage 1: NameResolver     -> ResolutionTable (id(ast_node) -> ResolutionInfo)
Stage 2: QueryExpander    -> updated table + query annotations
Stage 3: LanguageTranspiler (Python / TypeScript / …) -> TranspileResult (code + imports + flags)
```

`StagePipeline` in `datrix_codegen_common.transpiler` runs Stages 1–2 and configures the emitter; templates call the language transpiler for DSL bodies. Details: [code-generation.md](../../../../datrix-common/docs/architecture/code-generation.md), [datrix-common architecture](../../../../datrix-common/docs/architecture.md#transpiler-architecture-staged-pipeline).

| Category | Type | Lifetime |
|----------|------|----------|
| Config | `TranspileContext` | Per service; frozen |
| Per-file state | `FileScope` / language subclass | Fresh per emitted file; mutable |
| Upward artifacts | `TranspileResult` | Per visit; frozen |

**AST dispatch:** `ExpressionVisitor[T]` / `StatementVisitor[T]` + `node.accept()` for expressions/statements (as `TypeVisitor[T]` for types); `CallTargetEmitter` + `dispatch_call()` for call targets — see [datrix-common-api — Transpiler modules](../../../../datrix-common/docs/datrix-common-api.md#transpiler-modules).

## Declared Emission — Every Backend Domain Is a DAL generator Declaration

[Decision 59](../architecture-overview.md#decision-59-declared-emission-for-backend-generators--every-domain-a-declaration-items-not-emissions-adopted) — Adopted.

- **One shape.** A backend domain is `each <item-target> [where call <predicate>] { context <Type> from <builder>; <lang> <name> { template "<t>" => "<path>"; [when call <gate>;] } … }`, nested as the items nest. Its Python is only its context builders, gates and filters (plain functions bound by name from the iteration scope); the builder carries the preconditions and builds the shared typed context where the domain has one. No per-domain micro-generator, hooks class or orchestrator exists in a backend package (`datrix_codegen_common.testkit.gates.domain_machinery_census`, run in each backend's suite).
- **Items, not emissions.** A computed collection is an item-yielding `IterationTargetSpec` (`resolver_ref`); a resolver returns model items, never `GeneratedFile`s, and a `builder` file clause supplies `str`/`bytes` content only — the kernel refuses both shapes. A resolver must declare its return type, and one whose declared type names `GeneratedFile` (or a subclass, in any generic argument) is refused when it is loaded, before it ever runs (`iteration_targets.require_item_yielding_resolver`).
- **Paths are declared.** Static path templates over sanitizing path attributes; a domain's structural glob derives from them or from its committed `structural "<glob>";` line — never from a class attribute.
- **`.dal` resources.** Each target's definitions are `dgen/generator.dal`, loaded by `generator_definition_file`; no DAL generator source lives in a docstring.
- **`migration` is the sole F2 exemption.** Its compiled spec is swapped for `MigrationOrchestrator`'s (`build_sub_generator_specs`), which carries the compiled domain; its glob is the `structural=` argument of `@expand migration_domain(...)`, and its `builder` line binds to the fail-loud `migration_domain_builder`. The shared emission-path gate (`check_every_domain_declared_or_f2_exempt`) refuses any other domain carrying a `builder` line.

## Internal Documents — One Language, DAL

[Decision 60](../architecture-overview.md#decision-60-datrixs-internal-dsls-are-one-language-dal-parsed-by-lark-adopted) — Adopted.

Every internal declarative surface is a DAL document kind owning one decision family: `generator.dal` (generator definitions), `emit.dal` (builtin emit routing), `dependencies.dal` (per-language dependency tables), `realization.dal` (per-platform cell → plan builder and emitters). One strict-LALR Lark grammar (`datrix_codegen_kernel.dal`) gives every kind one syntax, lexical layer and error model; the registries rows validate against stay typed Python. No package constructs a table, row or cell outside its loader — the `datrix_testing.conformance.dal_authored_tables` gate pins each package at zero. Grammar and checks per kind: `datrix-codegen-kernel/docs/reference/dal.md`.

## DAL generator Engine Hardening

[Decision 42](../architecture-overview.md#decision-42-dal-generator-engine-hardening--output-path-containment-sanitized-path-attributes-one-escaping-home-and-the-interpolation-rule-adopted) — Adopted.

Every DAL generator output path is validated at construction on both render sinks by one shared containment guard (rejects `..`, absolute, drive, UNC). Path attributes resolve only through sanitizing case forms; raw/`original`/plugin names are display-only. Cross-target literal escaping has one home, dialect encoding sits behind `SQLDialect.quote_literal`, and a dialect that cannot encode raises `GenerationError` instead of quote-doubling. DSL `#{}` interpolation flows only through the validated expression visitor (conformance test over every generator package, counted exemption baseline).
