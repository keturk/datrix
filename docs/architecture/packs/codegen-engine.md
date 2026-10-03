# Pack: Codegen Engine — Transpiler, genDSL, Stage Boundaries

**Read when:** you touch the transpiler (`StagePipeline`, `NameResolver`, `QueryExpander`, `LanguageTranspiler`, `TranspileContext`/`FileScope`/`TranspileResult`), genDSL output paths or escaping, `#{}` interpolation, or SQL literal quoting.
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

## genDSL Engine Hardening

[Decision 42](../architecture-overview.md#decision-42-gendsl-engine-hardening--output-path-containment-sanitized-path-attributes-one-escaping-home-and-the-interpolation-rule-adopted) — Adopted.

Every genDSL output path is validated at construction on both render sinks by one shared containment guard (rejects `..`, absolute, drive, UNC). Path attributes resolve only through sanitizing case forms; raw/`original`/plugin names are display-only. Cross-target literal escaping has one home, dialect encoding sits behind `SQLDialect.quote_literal`, and a dialect that cannot encode raises `GenerationError` instead of quote-doubling. DSL `#{}` interpolation flows only through the validated expression visitor (conformance test over every generator package, counted exemption baseline).
