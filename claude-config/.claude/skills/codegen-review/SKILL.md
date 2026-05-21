---
description: Review generated code against Datrix quality standards and submission checklist
model: sonnet
disable-model-invocation: true
---

# Codegen Review

## Submission Checklist

- [ ] No placeholders/TODOs
- [ ] No mocks/fakes
- [ ] No silent fallbacks
- [ ] All tests pass (pytest)
- [ ] Tests follow test guidelines (real objects, output validation, error cases)
- [ ] Generated code valid (if applicable)
- [ ] Docstrings on public APIs
- [ ] Standard logging with key=value format
- [ ] Cognitive complexity ≤15 per function
- [ ] No redundant code
- [ ] No magic constants
- [ ] No `Any` type annotations
- [ ] Logic map markers added/updated if applicable
- [ ] Queried logic map database before writing significant new logic

## Repository Rules

### datrix-common
- ZERO runtime deps on other Datrix packages (datrix-language is dev/test only)
- Only stdlib + external packages at runtime
- YAML/JSON builders for data format generation

### datrix-language
- Parser + CST-to-AST transformers only (thin package)
- Immutable CST nodes (frozen dataclasses)
- All lookups raise on not found

### datrix-codegen-* (component, python, typescript, sql)
- Jinja2 templates + ruff format (Python) / Prettier (TypeScript)
- Exhaustive type mappings. Validate generated code.

### datrix-codegen-* (docker, k8s, aws, azure)
- YAML/JSON builders. Validate manifests.

## Code Examples

### Type Hints
```python
def generate_model(self, entity: Entity) -> Path:
    ...
```
Exception: Pydantic `@model_validator(mode="before")` — `Any` accepted for `data` parameter only.

### Logging
```python
import logging
logger = logging.getLogger(__name__)
logger.info("operation_started param=%s", value)
logger.info("operation_completed duration_ms=%.2f", duration)
```

### Error Messages
```python
raise ValidationError(
    f"Field '{field.name}' has invalid type '{field.type}'.\n"
    f"Valid types: {', '.join(VALID_TYPES)}\n"
    f"Did you mean '{suggest_similar(field.type, VALID_TYPES)}'?"
)
```

### Magic Constants
```python
# BAD: if status == 200: timeout = 30
# GOOD:
HTTP_OK = 200
DEFAULT_TIMEOUT_SECONDS = 30
if status == HTTP_OK:
    timeout = DEFAULT_TIMEOUT_SECONDS
```
