# Design Principles Cheat Sheet

## Core Principles

1. **Fail Fast, Fail Loud** -- Errors at generation time, not runtime. Raise with context, never return None.
2. **Templates + Formatter** -- Jinja2 + ruff format (Python) / Prettier (TypeScript). No raw string concatenation.
3. **Exhaustive Type Mappings** -- Every type explicitly mapped per language. Unmapped = error. No defaults/fallbacks.
4. **Immutability** -- AST model is frozen (Pydantic v2). Generators are read-only.
5. **Single Responsibility** -- One clear purpose per package/module.
6. **Dependency Inversion** -- Depend on protocols, not concretions.
7. **Explicit Over Implicit** -- No magic. All parameters explicit. Builtin traits are opt-in.

## DSL vs YAML Boundary

| Behavioral (DSL .dtrx) | Environmental (YAML config/) |
|---|---|
| Cache TTL, rate limits, lifecycle hooks | Connection strings, ports, CPU/memory |
| Entity structure, validation rules | CORS origins, JWT secrets |
| Service version, topology | Job schedules, retry/timeout defaults |
| Computed fields, spec tests | Provider credentials, replica count |

## Code Generation Principles

- Generate **idiomatic** code per target language
- **No dead code** -- only generate what's used
- **Readable** output -- docstrings, type hints, clear names
- **Spec-level tests** -- `test("...") { }` blocks compile to real test cases (pytest / Jest)

## Full doc

- [design-principles.md](./design-principles.md)
