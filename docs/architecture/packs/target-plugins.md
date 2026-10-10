# Pack: Target Plugins, Open-World Identity, Package Layering, Extensions

**Read when:** adding or changing a language/platform/frontend target, a plugin entry point, a capability declaration, identity-provider/flavor/runtime validation, a package dependency edge, an import boundary, or a domain extension.
**Not for:** what a generator emits (see the other packs) or per-target behaviour parity ([parity-and-obligation.md](./parity-and-obligation.md)).
**Core map:** [architecture-cheat-sheet.md](../architecture-cheat-sheet.md)

## Multi-Target Plugin Architecture

Open-world targets, derived conformance: [Decision 15](../architecture-overview.md#decision-15-multi-target-plugin-architecture--open-world-targets-derived-conformance-adopted) — Adopted.

| # | Invariant | Check |
|---|---|---|
| I1 | Zero target-name policy references in shared layers (the shared set is *derived*: every package registering none of the four entry-point groups) | `check-import-boundaries.ps1 -CheckTargetLiterals`; reasoned, decrease-only baseline `datrix/scripts/config/target-literal-baseline.toml` |
| I2 | Add-a-language = one package | `datrix-codegen-common/tests/integration/testkit/test_closed_world_drill.py` |
| I3 | Add-a-platform = one package | `datrix-testing/tests/integration/conformance/test_closed_world_drill.py` |
| I4 | Drift is a red test in the drifting package | Kit self-consistency gate + mutation check (`test_mutation_check.py`) |
| I5 | No `(target → policy)` / `(target × target)` tables in shared layers | Subsumed by I1 |
| I6 | Language packages contain zero provider conditionals; shared packages are held to a separate hard zero (no baseline) | `check-import-boundaries.ps1 -CheckProviderConditionals`; a package the derivation cannot classify aborts the scan naming it. The shared orchestrator asks the platform (`PlatformCapabilityDeclaration.injected_test_identity_providers`) rather than naming a provider |
| I7 | Import-boundary allowlist empty | `import-boundary-allowlist.toml` has zero entries |
| I8 | An identity provider type's rules (issuer, JWKS, audience, operator prerequisites) have exactly one owner — the package that integrates the provider — and no shared layer holds one; the shared identity tree is held at a hard zero (no baseline) | `check-import-boundaries.ps1 -CheckTargetLiterals` (the owned provider types are derived from the installed platform declarations; kinds `target_name_literal` and `identity_provider_member`); `datrix-common/tests/integration/identity/test_provider_type_ownership.py` (every realized type resolves to one owner); `identity_provider_type_rules` fails loud on an unowned or doubly-owned type |

(The check commands are `powershell -File "d:/datrix/datrix/scripts/scan/check-import-boundaries.ps1" <flag>`.)

## Open-World Identity, Flavors, Runtimes

[Decision 22](../architecture-overview.md#decision-22-open-world-identity-providers-and-infrastructure-flavors-adopted) — Adopted.

Identity provider types, the six infrastructure flavors (Rdbms/Cache/Pubsub/Queue/Nosql/Storage) and deployment runtimes are **open identifiers validated against the installed platform plugins** — no central capability matrix, no closed enums. Each platform declares its own column (identity `(provider type, feature)`, flavor cells, runtime support, identity write-back claim/encoding) in its `PlatformCapabilityDeclaration`. An unknown value fails loud, listing what the installed plugins declare. A platform declaring no write-back realization fails loud on write-back.

**Identity provider rules have one owner.** What a provider type's issuer, JWKS and audience are is a fact about the provider product, not the platform hosting it, so the rules live in the package that integrates the provider (docker → `zitadel`, aws → `cognito`, azure → `entra-id` / `entra-external-id`; `external` is built in) and are registered on that package's `PlatformCapabilityDeclaration.identity_provider_type_rules`. The `.dcfg` vocabulary is open-world the same way: `IdentityConfig.provider` names only the built-in `external` and `apiKey` types, and a contributed type's provider-specific block (its key and model, `source_block`) and whether Datrix hosts its issuer (`self_hosted`, which licenses `mode = self`) are the owner's rules too, checked at the identity-config load boundary. A platform that only realizes a type owns nothing. The shared planner asks the registry; the deploy-time identity context is an open map keyed by provider type and built by one reader from each platform's declared projection.

## Foundation Package Restructure

[Decision 50](../architecture-overview.md#decision-50-foundation-package-restructure--smaller-shared-packages-narrower-change-reach-adopted) — Adopted.

Change reach is computed per package, so the shared layers split into the packages in the core map. Invariants: no upward import from a lower layer, `TYPE_CHECKING` included (import-linter `layers` contract per package, zero ignored edges; manifest-import parity gate); importing the core loads no generation, migration or semantic code; the kernel loads no language-layer module; platforms, SQL and component never depend on the language layer; no frontend target depends on a backend language package; every shared package is covered by the shared-layer ratchets (derived set, an unclassified package fails the scan); **exactly one import path per symbol** (`check-import-boundaries.ps1 -CheckReexportFacades`, standing hard zero, no baseline). A module is placed by who uses it: the nearest package every consumer already depends on; a pure derivation over the model lives beside the model; a module holding a core fact beside an upper-layer one is split.

## Domain Extensions

- **DSL:** `use extension <name>;` inside `system { }` (stored on `app.extension_directives`).
- **Protocol `DatrixExtension`** (`datrix_common.plugin.extension`): properties `name`, `version`; methods `scalar_definitions()`, `builtin_objects()`, `value_struct_definitions()`, `db_extensions()`, `extra_dependencies()`, `template_dirs()`.
- **Discovery:** `PluginRegistry.discover_extensions()`; `load_declared_extensions(declared)`; `TypeRegistry.load_extensions(extensions)`; `declared_extension_names(app)` is passed into `LanguageGenerator` and resolvers.
- **Split ownership:** packs own definitions; each language/SQL owns its maps — `PYTHON_EXTENSION_MAPS` (`datrix_codegen_python.type_mappings`), `TS_EXTENSION_MAPS` (`datrix_codegen_typescript_core.type_mappings`), `SQL_EXTENSION_MAPS` (`datrix_codegen_kernel.sql_facts.type_mappings`) — merged into the core `*_TYPE_MAP` by the shared `datrix_codegen_kernel.generation.type_mapping_registry.build_type_map` (raises `ExtensionNotSupportedError` for a declared extension with no map). A new language ships its own `*_EXTENSION_MAPS` the same way.

Guides: [extensions-guide.md](../../../../datrix-extensions/docs/extensions-guide.md) · [datrix-common extensions](../../../../datrix-common/docs/extensions.md).
