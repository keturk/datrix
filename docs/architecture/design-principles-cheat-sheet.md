# Design Principles Cheat Sheet

## Core Principles

1. **Fail Fast, Fail Loud** -- Errors at generation time, not runtime. Raise with context, never return None.
2. **Templates + Formatter** -- Jinja2 templates; after write, `LanguageHooks` run ruff / Prettier when `format_output` is on. No raw string concatenation.
3. **Exhaustive Type Mappings** -- Every type explicitly mapped per language. Unmapped = error. No defaults/fallbacks.
4. **Immutability** -- AST model is frozen (Pydantic v2). Generators are read-only.
5. **Single Responsibility** -- One clear purpose per package/module.
6. **Dependency Inversion** -- Depend on protocols, not concretions.
7. **Explicit Over Implicit** -- No magic. All parameters explicit. Builtin traits are opt-in.
8. **Domain extensions** -- `use extension <name>;` in `system.dtrx` (DSL). Packs own definitions (`DatrixExtension`); language generators own all per-language maps (`PYTHON_EXTENSION_MAPS` + `build_python_type_map`, etc.). Core stays lean; infra-heavy domain types move to packs.
9. **No backward compatibility in the DSL** -- One supported syntax path at a time. When syntax changes (for example removing `@` on types for server-managed fields), old forms are removed rather than deprecated in parallel.
10. **Minimal reserved words / contextual keywords** -- Modifiers such as `server`, `unique`, and `indexed` appear only in modifier lists after `:` on fields (and similar positions). They are not a separate global “keyword soup”; the grammar keeps reserved words tight and uses contextual positions for these identifiers.
11. **Protocol dispatch over isinstance** -- Use `ExpressionVisitor` / `StatementVisitor` and `node.accept(visitor)` for AST operations; use `CallTargetEmitter` + `dispatch_call()` for call targets. Do not grow `isinstance` ladders on expression nodes.
12. **Explicit data flow** -- Service-wide config is frozen (`TranspileContext`). Per-file sibling state uses fresh `FileScope` objects. Visit results return `TranspileResult` (merge with `merge_artifacts`) — not hidden mutation on the transpiler for imports/flags.
13. **Staged transpilation** -- Name resolution and query expansion run as explicit Stages 1–2 (`StagePipeline`); each language emitter is Stage 3. Keep stage boundaries and side-tables (`ResolutionTable`) instead of monolithic “do everything in one visit” growth.

## DSL vs YAML Boundary

| Behavioral (DSL .dtrx) | Environmental (YAML config/) |
|---|---|
| Cache TTL, rate limits, lifecycle hooks | Connection strings, ports, CPU/memory |
| Entity structure, validation rules | CORS origins, JWT secrets |
| Service version, topology | Job schedules, retry/timeout defaults |
| Computed fields, spec tests | Provider credentials, replica count |
| **`use extension`** (which domain packs are enabled) | (not used for extension enablement) |

## Standard library (product rules)

Shipped `.dtrx` modules in `datrix-language` (see [datrix-stdlib-reference.md](../../../datrix-language/docs/reference/datrix-stdlib-reference.md)) are part of the language distribution, not optional user packages.

- **Implicit availability** — Stdlib exports (`BaseEntity`, `Address`, `hashPassword`, …) resolve from global scope without `import` / `use` in user modules (same rules as the semantic pipeline; qualified `datrix.*` names still work when you need them).
- **Lazy loading** — Serialized stdlib module ASTs deserialize only when a reference forces it; unused stdlib modules incur no deserialization work.
- **User-first shadowing** — User definitions win over stdlib; use qualified names when you need the stdlib shape explicitly. Shadowing is intentional, not a warning surface.
- **Concrete codegen** — Unlike builtins (mostly abstract mappings into host languages), stdlib entities, structs, and functions become real generated artifacts (tables, classes, transpiled methods) when referenced.
- **Database-agnostic** — Stdlib uses builtin scalars only; no PostGIS/Timescale-style coupling. Infrastructure-specific types belong in **domain extensions**, not stdlib.
- **Versions with `datrix-language`** — No separate stdlib semver; upgrading the language package upgrades stdlib.
- **Low bar for inclusion** — Shared patterns used by more than one real project are candidates; lazy loading keeps unused modules cheap.

## Code Generation Principles

- Generate **idiomatic** code per target language
- **No dead code** -- only generate what's used
- **Readable** output -- docstrings, type hints, clear names
- **Spec-level tests** -- `test("...") { }` blocks compile to real test cases (pytest / Jest)

## Full doc

- [design-principles.md](./design-principles.md)
