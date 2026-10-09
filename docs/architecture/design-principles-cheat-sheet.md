# Design Principles Cheat Sheet

**What Datrix is:** a **multi-language, multi-platform code generator** (`.dtrx` domain specs → production-ready applications) — NOT limited to Python/TypeScript, NOT limited to Docker/AWS/Azure. Read every principle through that lens: a fix for one language/platform must not break another, and designs must preserve the multi-language, multi-platform nature.

## Core Principles

1. **Fail Fast, Fail Loud** -- Errors at generation time, not runtime. Raise with context, never return None.
2. **Templates + Formatter** -- Jinja2 templates; after write, `LanguageHooks` run the language formatter (ruff for Python) or validation-only (`tsc --noEmit` for TypeScript) when `format_output` is on. No raw string concatenation.
3. **Exhaustive Type Mappings** -- Every type explicitly mapped per language. Unmapped = error. No defaults/fallbacks.
4. **Immutability — Build-Then-Sealed (Adopted)** -- The AST is mutable through parse/transform and semantic analysis; `analyze()` seals it via a recursive `__setattr__` guard on `Node`. Generators receive a sealed application; post-seal mutation raises.
5. **Single Responsibility** -- One clear purpose per package/module.
6. **Dependency Inversion** -- Depend on protocols, not concretions.
7. **Explicit Over Implicit** -- No magic. All parameters explicit. Builtin traits are opt-in.
8. **Domain extensions** -- `use extension <name>;` in `system.dtrx`. Packs own definitions (`DatrixExtension`); language generators own their per-language maps (`PYTHON_EXTENSION_MAPS`, …), merged by the shared `build_type_map`. Core stays lean; infra-heavy domain types move to packs.
9. **No backward compatibility in the DSL** -- One supported syntax path. When syntax changes, old forms are removed, not deprecated in parallel.
10. **Minimal reserved words** -- Modifiers (`server`, `unique`, `indexed`) are contextual: they appear only in modifier lists after `:` on fields (and similar positions), never as global keywords.
11. **Protocol dispatch over isinstance** -- `ExpressionVisitor` / `StatementVisitor` with `node.accept(visitor)` for AST operations; `CallTargetEmitter` + `dispatch_call()` for call targets. Do not grow `isinstance` ladders on expression nodes.
12. **Explicit data flow** -- Service-wide config is frozen (`TranspileContext`). Per-file sibling state uses fresh `FileScope` objects. Visits return `TranspileResult` (merge with `merge_artifacts`), never hidden mutation on the transpiler.
13. **Staged transpilation** -- Name resolution and query expansion are explicit Stages 1–2 (`StagePipeline`); each language emitter is Stage 3. Keep stage boundaries and side-tables (`ResolutionTable`).
14. **Construct-mapped platform realization** -- `.dtrx` = platform-agnostic logic; `.dcfg` = deployment target (runtime + provider + sizing); the generator maps each DSL block to the target's native primitive. Service shape derives from declared blocks, not a service-flavor selector. No silent ignore: unsupported combinations raise actionable errors. No defaults: every deployment choice is explicit in config.
15. **Credentials fail closed** -- A missing/empty credential never silently disables auth. The only valid state for secret-backed auth is "required and present": fail loud before constructing any unauthenticated client; unauthenticated operation is an explicit config declaration, never implied by an absent value. `.dtrx`/`.dcfg` carry only logical secret **handles**, never values or fallbacks; errors and logs name the logical secret and backend class, never the value.
16. **Shared layers ask, target plugins answer (Adopted)** -- No language/provider name in `datrix-common`/`datrix-codegen-common`/`datrix-cli` source; `dict[TargetId, policy]` or `if target == X:` in a shared layer is a defect. Target facts live with the target's plugin. Enforced by the I1 ratchet at zero (`check-import-boundaries.ps1 -CheckTargetLiterals`).
17. **A declared knob must be realized (Adopted)** -- A config field the system accepts is a promise: perturbing it must change the emitted artifact in a functional position, not just pass validation or land in a comment/docstring/log line. Every consumed field is proven by a perturb-and-diff check (`datrix_testing.conformance.config_realization`, run by each consuming package against its own pinned exemption baseline) or carries a reviewed, written exemption. A target that realizes a portable capability by no implementation records a `capability_gaps` row on its own declaration; it never declares the field unsupported.
18. **Purposeful mini-DSLs** -- Datrix's declarative layer is a family of small single-concern surfaces: ConfigDSL, SeedDSL, genDSL, RealizationDSL (typed platform-capability cells driving provisioning dispatch), EmitDSL (typed per-language emit-table rows validated against the closed builtin registry), and per-language declared dependency tables (feature + typed qualifier → package name and scope; versions stay in the dependency catalog). The authoring unit is a table cell or row, not text. Declarations are the *only* emission path for their concern — a parallel imperative path is a bypass to close; where the schema cannot express a routing decision it gains typed predicate columns. Compilation is closed (unknown reference = load-time error); text is earned (typed data by default, computation stays in Python). Never fold a new concern into an existing DSL because it happens to be declarative, and never open a new surface for a concern an existing declaration already owns (casing is served by `LanguageProfile.naming`'s casers — thread the declaration into shared algorithms, never author a second casing surface). A large duplicated family is often evidence a surface is under-used, not missing.

## DSL vs YAML Boundary

| Behavioral (DSL .dtrx) | Environmental (ConfigDSL .dcfg) |
|---|---|
| Cache TTL, rate limits, lifecycle hooks | Connection strings, ports, CPU/memory |
| Entity structure, validation rules | CORS origins, JWT secrets |
| Service version, topology | Job schedules, retry/timeout defaults |
| Computed fields, spec tests | Provider credentials, replica count |
| **`use extension`** (which packs are enabled) | (not used for extension enablement) |

## Standard Library (product rules)

Shipped `.dtrx` modules in `datrix-language` ([datrix-stdlib-reference.md](../../../datrix-language/docs/reference/datrix-stdlib-reference.md)) are part of the language distribution, not optional user packages.

- **Implicit availability** — Stdlib exports (`BaseEntity`, `Address`, …) resolve from global scope without `import`/`use`; qualified `datrix.*` names also work.
- **Lazy loading** — A stdlib module deserializes only when a reference forces it.
- **User-first shadowing** — User definitions win over stdlib; shadowing is intentional, not a warning. Use qualified names for the stdlib shape.
- **Concrete codegen** — Unlike mostly-abstract builtins, referenced stdlib entities, structs and functions become real generated artifacts.
- **Database-agnostic** — Builtin scalars only. Infrastructure-specific types (PostGIS/Timescale-style) belong in domain extensions.
- **Versions with `datrix-language`** — No separate stdlib semver.
- **Low bar for inclusion** — Patterns used by more than one real project are candidates.

## Code Generation Principles

- Generate **idiomatic** code per target language
- **No dead code** -- only generate what's used
- **Readable** output -- docstrings, type hints, clear names
- **Spec-level tests** -- `test("...") { }` blocks compile to real test cases (pytest / Jest)

## Full doc

- [design-principles.md](./design-principles.md)
