# Design Principles Cheat Sheet

## Core Principles

1. **Fail Fast, Fail Loud** -- Errors at generation time, not runtime. Raise with context, never return None.
2. **Templates + Formatter** -- Jinja2 + ruff format (Python) / Prettier (TypeScript). No raw string concatenation.
3. **Exhaustive Type Mappings** -- Every type explicitly mapped per language. Unmapped = error. No defaults/fallbacks.
4. **Immutability** -- AST model is frozen (Pydantic v2). Generators are read-only.
5. **Single Responsibility** -- One clear purpose per package/module.
6. **Dependency Inversion** -- Depend on protocols, not concretions.
7. **Explicit Over Implicit** -- No magic. All parameters explicit. Builtin traits are opt-in.
8. **Domain extensions** -- `use extension <name>;` in `system.dtrx` (DSL). Packs own definitions (`DatrixExtension`); language generators own all per-language maps (`PYTHON_EXTENSION_MAPS` + `build_python_type_map`, etc.). Core stays lean; infra-heavy domain types move to packs.
9. **No backward compatibility in the DSL** -- One supported syntax path at a time. When syntax changes (for example removing `@` on types for server-managed fields), old forms are removed rather than deprecated in parallel.
10. **Minimal reserved words / contextual keywords** -- Modifiers such as `server`, `unique`, and `indexed` appear only in modifier lists after `:` on fields (and similar positions). They are not a separate global “keyword soup”; the grammar keeps reserved words tight and uses contextual positions for these identifiers.

## DSL vs YAML Boundary

| Behavioral (DSL .dtrx) | Environmental (YAML config/) |
|---|---|
| Cache TTL, rate limits, lifecycle hooks | Connection strings, ports, CPU/memory |
| Entity structure, validation rules | CORS origins, JWT secrets |
| Service version, topology | Job schedules, retry/timeout defaults |
| Computed fields, spec tests | Provider credentials, replica count |
| **`use extension`** (which domain packs are enabled) | (not used for extension enablement) |

## Code Generation Principles

- Generate **idiomatic** code per target language
- **No dead code** -- only generate what's used
- **Readable** output -- docstrings, type hints, clear names
- **Spec-level tests** -- `test("...") { }` blocks compile to real test cases (pytest / Jest)

## Full doc

- [design-principles.md](./design-principles.md)
