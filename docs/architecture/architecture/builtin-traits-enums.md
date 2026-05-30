# Builtin Traits & Enums Reference

> Part of the architecture documentation. See [../architecture-overview.md](../architecture-overview.md) for the full index.

---

## Builtin Traits and Enums

Datrix provides a catalog of **ten builtin traits** and **two builtin enums** that are always available in every service and module without user definition.

### Builtin Traits

| Trait | Fields | Purpose |
|-------|--------|---------|
| **Activatable** | `Boolean isActive`, `DateTime? activatedAt`, `DateTime? deactivatedAt` | Enable/disable entities |
| **Auditable** | `UUID createdBy`, `UUID? updatedBy` | Track who created/modified |
| **Publishable** | `DateTime? publishedAt`, `UUID? publishedBy`, `PublishStatus publishStatus` | Draft/publish workflow |
| **Schedulable** | `DateTime? scheduledFor`, `DateTime? executedAt`, `ScheduleStatus scheduleStatus` | Scheduled execution |
| **Sluggable** | `String(200) slug : unique` | URL-friendly slugs |
| **SoftDeletable** | `DateTime? deletedAt`, `UUID? deletedBy`, computed `isDeleted` | Soft deletion |
| **Taggable** | `Array<String> tags` | Tagging |
| **Tenantable** | `UUID tenantId : server, immutable, indexed` | Row-level tenant isolation |
| **Timestampable** | `DateTime createdAt`, `DateTime updatedAt` | Automatic timestamps |
| **Versionable** | `Int version` | Optimistic locking |

### Builtin Enums

| Enum | Values | Used By |
|------|--------|---------|
| **PublishStatus** | `Draft`, `Published`, `Archived` | Publishable trait |
| **ScheduleStatus** | `Pending`, `Scheduled`, `Executed`, `Cancelled` | Schedulable trait |

### Builtin Objects (Temporal)

| Object | Methods / Constants | Purpose |
|--------|---------------------|---------|
| **Timezone** | `Timezone.UTC`, `Timezone.of(identifier)` | Timezone specification for datetime operations. `UTC` is the only constant; `of()` accepts IANA identifiers (e.g., `"America/New_York"`). |

`Timezone` is used as a parameter to `DateTime.now()` and `DateTime.fromTimestamp()`. When omitted, both default to `Timezone.UTC`. There is no `Timezone.server()` — server-local time is an anti-pattern for generated code.

### Builtin Objects (Reference Data)

| Object | Methods | Purpose |
|--------|---------|---------|
| **Seed** | `Seed.countries()`, `Seed.subdivisions(String?)`, `Seed.currencies()`, `Seed.timezones()`, `Seed.languages()`, `Seed.mimeTypes()`, `Seed.httpStatusCodes()` | Framework-maintained reference datasets for seeding and runtime validation. |

`Seed` functions return `Array<Object>` and are usable in both `.dseed` seed declarations and `.dtrx` application code. In seed declarations, they populate reference tables (e.g., `Country from Seed.countries()`). In application code, they provide canonical datasets for runtime validation (e.g., checking a country code against `Seed.countries()`).

Canonical data lives in `datrix-common/src/datrix_common/builtins/data/` as JSON files (ISO 3166 countries, ISO 3166-2 subdivisions, ISO 4217 currencies, IANA timezones, ISO 639 languages). Data is loaded lazily on first access and updated with each Datrix release.

Each codegen package maps `Seed.*` calls to language-native implementations via its `BuiltinMethodMapper`. Generated services include an embedded helper module (`_seed_data.py` / `seed-data.ts`) containing frozen reference data loaded at import time — no runtime I/O.

Domain extension packs can register additional seed builtins via their `builtin_objects()` method on `DatrixExtension`, following the same pattern used by other extension builtins.

### How It Works

1. Builtin traits and enums are **defined in Datrix DSL** in `datrix-language/src/datrix_language/builtins/builtins.dtrx`. `datrix_language.builtins.loader` parses that file once (with `inject_builtins=False` to avoid recursion), caches the module, and returns **deep copies** for injection.
2. The CST→AST transformer **`_inject_builtins()`** merges those definitions into **every TypeContainer** (Service, Module) after the `Application` is built from user source and before reference resolution.
3. Injected trait/enum nodes are tagged with **`is_builtin = True`**. `datrix_common` still exposes **`BUILTIN_TRAIT_NAMES`**, **`BUILTIN_ENUM_NAMES`**, and **`ENUM_REQUIRED_BY_TRAIT`** for BLT001 and injection policy (so validators do not depend on `datrix-language`).
4. Users reference traits with `with TraitName` on entity declarations (e.g., `entity User extends BaseEntity with Tenantable`).
5. Traits are **opt-in** — no trait is automatically applied to entities.
6. User code **cannot redefine** builtin trait or enum names (BLT001 validator enforces this).
