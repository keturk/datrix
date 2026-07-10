# Codegen Consolidation: Migration & Testing Strategy

**Last Updated:** April 24, 2026

Migration plan for the codegen consolidation described in [codegen-consolidation.md](../../../datrix-common/docs/architecture/codegen-consolidation.md). Covers phase ordering, per-phase validation, rollback, and testing strategy.

---

## Phase Ordering

```
Phase 1: Smaller Wins
  |- 5.1 Feature detection consolidation
  |- 5.2 Entity import path extraction
  +- 5.3 Sample value function extraction

Phase 2: Type Mapping Registry
  |- 3.3.1 Create TypeMappingRegistry
  |- 3.3.2 Register in both packages
  +- 3.3.3 Add cross-language completeness test

Phase 3: Generator Orchestration Layer
  |- 2.2.2 Extract language_helpers.py
  |- 2.2.1 Create LanguageGenerator base class
  |- Migrate Python plugin.py
  +- Migrate TypeScript plugin.py

Phase 4: Transpiler State Extraction
  |- 4.2.1 Create LanguageTranspiler base class
  |- Migrate PythonTranspiler
  +- Migrate TypeScriptTranspiler
```

### Phase Dependency Graph

```
Phase 1 ---------------------------------> Phase 3
                                             |
           (independent)                     |
                                             v
Phase 2                                    Phase 4
```

**Dependencies:**
- **Phase 1 -> Phase 3:** Phase 3's `LanguageGenerator.generate()` calls `detect_service_features()`. Phase 1 promotes features into that function.
- **Phase 2 is independent** of both Phase 1 and Phase 3. Can be implemented at any point.
- **Phase 3 -> Phase 4:** `LanguageTranspiler` is consumed by `create_transpiler_for_service()`, called from `LanguageGenerator.generate()`.
- **Phase 1 and Phase 2 can run in parallel** if needed, but sequential execution is simpler (see Decision D9 in the consolidation doc).

Within each phase, steps are sequential (top to bottom).

---

## Per-Phase Validation

Each phase must pass this validation before proceeding:

### 1. Diff Test

Generate reference projects with **both Python and TypeScript** targets before and after. Output must be byte-identical.

```bash
# Before change:
powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" \
  "d:/datrix/datrix/examples/03-domains/ecommerce/system.dtrx" \
  "d:/datrix/.generated/python/docker-compose/local/03-domains/ecommerce-before" -L python
powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" \
  "d:/datrix/datrix/examples/03-domains/ecommerce/system.dtrx" \
  "d:/datrix/.generated/python/docker-compose/local/03-domains/ecommerce-before-ts" -L typescript

# After change:
powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" \
  "d:/datrix/datrix/examples/03-domains/ecommerce/system.dtrx" \
  "d:/datrix/.generated/python/docker-compose/local/03-domains/ecommerce-after" -L python
powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" \
  "d:/datrix/datrix/examples/03-domains/ecommerce/system.dtrx" \
  "d:/datrix/.generated/python/docker-compose/local/03-domains/ecommerce-after-ts" -L typescript

# Diff (must be empty):
diff -r ecommerce-before ecommerce-after
diff -r ecommerce-before-ts ecommerce-after-ts
```

**Representative subset** (not just one example):
- `ecommerce` — multi-service, RDBMS + cache + pubsub + CQRS + GraphQL
- `01-basic-entity` — minimal: single entity, no API
- `03-basic-api` — REST API with CRUD
- `21-background-jobs` — jobs + transpiled bodies
- `09-events` — pubsub events with dispatch/subscribe

### 2. Unit Tests

```bash
pytest datrix-common -x && pytest datrix-codegen-python -x && pytest datrix-codegen-typescript -x
```

### 3. Type Checking

```bash
mypy --strict
```

on all three packages.

### 4. Anti-Pattern Scan

```bash
libcst.ps1 -All && semgrep.ps1 -All
```

No new violations.

---

## Rollback Strategy

Each phase is a single PR. Sub-items may be separate commits within one PR, or separate PRs if the phase is large:

- **Phase 1 (Smaller Wins):** One PR — independent module-level extractions
- **Phase 2 (Registry):** One PR — self-contained new module + import-time registration
- **Phase 3 (LanguageGenerator):** Consider splitting: (a) extract helpers to `language_helpers.py`, (b) add `LanguageGenerator` base class, (c) migrate Python plugin, (d) migrate TypeScript plugin
- **Phase 4 (LanguageTranspiler):** One PR if <=500 LOC changed, split if larger

If issues found after merge: `git revert` the PR. Language packages are independently deployable — no cross-package dependencies prevent rollback.

---

## Testing Strategy

### LanguageGenerator Tests

**Unit tests** (`datrix-common/tests/unit/generation/test_language_generator.py`):
- `MinimalLanguageGenerator` — real subclass using real objects (PythonTranspiler, PythonTypeResolver), NOT mocks. Implements only the required abstract methods with the simplest valid objects.

**Helper function tests** (`datrix-common/tests/unit/generation/test_language_helpers.py`):
- Build real AST objects via `TreeSitterParser` or direct construction
- `test_derive_default_dialect_postgresql_fallback()` — no RDBMS blocks falls back to `"postgresql"`
- `test_effective_observability_config_default()` — None input returns Prometheus + OTEL + JSON
- `test_register_module_level_names_snake()` / `_camel()` — verify casing per language

**Integration tests:**
- Generate ecommerce with PythonGenerator before migration
- Generate with migrated PythonGenerator(LanguageGenerator)
- Diff output — must be identical

### TypeMappingRegistry Tests

**File:** `datrix-common/tests/unit/generation/test_type_mapping_registry.py`

1. **Registration:** Register, re-register (error), query registered languages
2. **Unmapped types:** Detect gaps when one language has more types than another
3. **Cross-language completeness:** Import real `datrix_codegen_python.type_mappings` and `datrix_codegen_typescript.type_mappings`, validate no gaps via `global_registry.validate_completeness()`
4. **Error messages:** KeyError on unknown type/language includes available options

### LanguageTranspiler Tests

**Unit tests** (`datrix-common/tests/unit/transpiler/test_language_transpiler.py`):
- `test_set_known_entity_names()` — stores and retrieves
- `test_reset_common_state_preserves_configuration()` — config preserved, per-file state cleared
- `test_python_literal_keywords()` — `True` / `False` / `None`
- `test_typescript_literal_keywords()` — `true` / `false` / `null`
- `test_shared_visit_unary_op()` — parameterized via operator tables

**Protocol conformance tests:**
```python
from datrix_common.transpiler.protocols import TranspilerStateProtocol

def test_python_transpiler_satisfies_protocol():
    assert isinstance(PythonTranspiler(), TranspilerStateProtocol)

def test_typescript_transpiler_satisfies_protocol():
    assert isinstance(TypeScriptTranspiler(), TranspilerStateProtocol)
```

**Integration tests:**
- Transpile same AST expressions before and after migration
- Output must be identical

---

## API Storage Defaults Migration

**From:** RDBMS-only bindings and service-wide fallbacks
**To:** Generalized storage bindings with explicit API defaults

### Migration Steps

1. Add generalized `StorageEntityKey` and `StorageEntityBinding` to `datrix_common.generation.storage_identity`
2. Replace RDBMS-only binding helpers with generalized storage helpers
3. Add default storage fields to `RestApi` and `GraphqlApi` AST nodes
4. Extend API attribute parsing for `basePath`, `rdbms`, and `nosql`
5. Reject duplicate and unknown API attributes in the transformer
6. Add semantic validation for API defaults and extern-service restrictions
7. Attach `StorageEntityBinding` directly to AST nodes that reference storage entities
8. Update REST resource/batch semantic resolution to attach bindings
9. Update REST endpoint and API-local function resolution to use API defaults
10. Update GraphQL operation, type inference, and data-loader resolution to use API defaults
11. Remove REST single-block fallback from Python generation
12. Remove GraphQL first-block behavior from Python generation
13. Update TypeScript REST and GraphQL generation/test setup to consume semantic bindings
14. Update fixtures and examples by intent:
    - Use API defaults for APIs with one primary storage block
    - Use block-qualified names for multi-block and cross-block examples

### Backward Compatibility

**No backward compatibility.** Services with multiple storage blocks and no API defaults will fail in semantic analysis with clear error messages listing the available blocks. This is intentional — the old "first block" behavior was unstable and unpredictable.

### Verification Checklist

**Transformer tests:**
- `rest_api Api : basePath("/api"), rdbms(db) { ... }`
- `rest_api Api : basePath("/api"), nosql(store) { ... }`
- `graphql_api Api : basePath("/graphql"), rdbms(db) { ... }`
- `graphql_api Api : basePath("/graphql"), nosql(store) { ... }`
- Duplicate `basePath`, `rdbms`, or `nosql` fails
- Unknown API attribute fails
- `basePath` behavior remains unchanged

**Semantic tests:**
- API default RDBMS block must exist
- API default NoSQL block must exist
- API default block kind must match the attribute
- Bare RDBMS entity without RDBMS default fails
- Bare NoSQL entity without NoSQL default fails
- Bare entity present in both declared default blocks fails
- Bare entity missing from declared defaults fails even if present in one non-default block
- Explicit `block.Entity` works when API default points elsewhere
- Unused API defaults are valid
- `rdbms(...)` and `nosql(...)` inside `extern service { rest_api ... }` fail
- Storage entities in extern-service REST signatures fail, even block-qualified

**REST tests:**
- REST endpoint body with bare `Member.findOne(...)` uses `rest_api ... rdbms(memberDb)`
- REST API-local function body uses API defaults
- REST `resource` and `batch` can use API defaults or explicit block-qualified names
- Adding an unrelated second storage block does not change resolution
- No single-RDBMS fallback remains

**GraphQL tests:**
- GraphQL operation body with bare `Member.findOne(...)` uses `graphql_api ... rdbms(memberDb)`
- GraphQL type and data-loader inference use API defaults
- Pure GraphQL API without storage access remains valid without defaults
- GraphQL storage access without default or explicit block fails
- No first-RDBMS-block selection remains

**Search-based acceptance:**
- API generators do not call `next(iter(service.rdbms_blocks...))`
- API generators do not call single-block fallback helpers
- REST and GraphQL ownership paths do not use service-wide `dict[str, Entity]` maps
- Generators do not call API default resolution helpers; they consume attached semantic bindings
