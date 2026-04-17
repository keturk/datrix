# Codegen Consolidation: Migration & Testing Strategy

**Last Updated:** April 16, 2026

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
  "d:/datrix/datrix/examples/02-domains/ecommerce/system.dtrx" \
  "d:/datrix/.projects/ecommerce-before" -L python
powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" \
  "d:/datrix/datrix/examples/02-domains/ecommerce/system.dtrx" \
  "d:/datrix/.projects/ecommerce-before-ts" -L typescript

# After change:
powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" \
  "d:/datrix/datrix/examples/02-domains/ecommerce/system.dtrx" \
  "d:/datrix/.projects/ecommerce-after" -L python
powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" \
  "d:/datrix/datrix/examples/02-domains/ecommerce/system.dtrx" \
  "d:/datrix/.projects/ecommerce-after-ts" -L typescript

# Diff (must be empty):
diff -r ecommerce-before ecommerce-after
diff -r ecommerce-before-ts ecommerce-after-ts
```

**Representative subset** (not just one example):
- `ecommerce` — multi-service, RDBMS + cache + pubsub + CQRS + GraphQL
- `01-basic-entity` — minimal: single entity, no API
- `03-basic-api` — REST API with CRUD
- `21-background-jobs` — jobs + transpiled bodies
- `09-events` — pubsub events with emit/subscribe

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

**Unit tests** (`datrix-common/tests/generation/test_language_generator.py`):
- `MinimalLanguageGenerator` — real subclass using real objects (PythonTranspiler, PythonTypeResolver), NOT mocks. Implements only the required abstract methods with the simplest valid objects.

**Helper function tests** (`datrix-common/tests/generation/test_language_helpers.py`):
- Build real AST objects via `TreeSitterParser` or direct construction
- `test_derive_default_dialect_postgresql_fallback()` — no RDBMS blocks falls back to `"postgresql"`
- `test_effective_observability_config_default()` — None input returns Prometheus + OTEL + JSON
- `test_register_module_level_names_snake()` / `_camel()` — verify casing per language

**Integration tests:**
- Generate ecommerce with PythonGenerator before migration
- Generate with migrated PythonGenerator(LanguageGenerator)
- Diff output — must be identical

### TypeMappingRegistry Tests

**File:** `datrix-common/tests/test_type_mapping_registry.py`

1. **Registration:** Register, re-register (error), query registered languages
2. **Unmapped types:** Detect gaps when one language has more types than another
3. **Cross-language completeness:** Import real `datrix_codegen_python.type_mappings` and `datrix_codegen_typescript.type_mappings`, validate no gaps via `global_registry.validate_completeness()`
4. **Error messages:** KeyError on unknown type/language includes available options

### LanguageTranspiler Tests

**Unit tests** (`datrix-common/tests/transpiler/test_language_transpiler.py`):
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
