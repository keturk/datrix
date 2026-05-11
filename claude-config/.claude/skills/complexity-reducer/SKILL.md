# Complexity Reducer Skill

Reduce cognitive and cyclomatic complexity in Python functions using Radon and cognitive_complexity analysis.

## When to Use

- User asks to "reduce complexity" in a project
- complexity.ps1 reports cognitive or cyclomatic complexity > 15
- User wants to improve code maintainability

## How to Invoke

Ask Claude Code directly:
```
"Reduce complexity in datrix-common"
"Fix complexity issues in datrix-codegen-sql"
"Refactor complex functions in datrix-language"
```

Or with options:
```
"Reduce complexity in datrix-common for functions above threshold 10"
"Fix the most complex function in datrix-codegen-python"
```

## Project Structure (DYNAMIC — read from generated file)

Before refactoring, read the project structure file for the target package's source and test directory trees:

- **`d:\datrix\{package-name}\.project-structure.md`**

Where `{package-name}` is the package specified in the invocation (e.g., `datrix-common`, `datrix-codegen-python`).

If the file is missing or stale, regenerate it:
```bash
powershell -File "d:/datrix/datrix/scripts/dev/project-structure.ps1" {package-name}
```

## Workflow

When invoked, Claude Code will:

1. **Identify Violations**: Run `datrix/scripts/metrics/complexity.ps1` (mode=check) to find blocks exceeding the max complexity
2. **Prioritize**: Process highest complexity first
3. **For Each Function**:
   - Read full function with imports and context
   - Apply refactoring strategies
   - Validate with pytest + mypy
   - Retry with error context if validation fails
   - Stage successful changes
4. **Report**: Summary of results

## Refactoring Strategies

Apply these strategies to reduce complexity:

1. **Early returns** - Flatten nesting with guard clauses
2. **Extract helpers** - Break repeated logic into private functions (`_helper`)
3. **Replace flags** - Use function calls instead of flag variables
4. **Comprehensions** - Convert nested loops to list/dict comprehensions
5. **Guard clauses** - Validate inputs at function start
6. **Strategy pattern** - Use dict dispatch for switch-like blocks
7. **Named booleans** - Extract complex conditions into descriptive variables
8. **Ternary expressions** - Simplify simple if-else assignments

## Example Refactoring

Before (complexity: 23):
```python
def process_items(items, config):
    results = []
    for item in items:
        if item.is_valid:
            if item.type == "A":
                if config.enable_a:
                    result = handle_a(item)
                    if result:
                        results.append(result)
            elif item.type == "B":
                if config.enable_b:
                    result = handle_b(item)
                    if result:
                        results.append(result)
    return results
```

After (complexity: 8):
```python
def _should_process(item, config):
    """Check if item should be processed based on config."""
    handlers = {
        "A": config.enable_a,
        "B": config.enable_b,
    }
    return item.is_valid and handlers.get(item.type, False)

def _get_handler(item_type):
    """Get handler function for item type."""
    return {"A": handle_a, "B": handle_b}.get(item_type)

def process_items(items, config):
    results = []
    for item in items:
        if not _should_process(item, config):
            continue
        handler = _get_handler(item.type)
        if handler and (result := handler(item)):
            results.append(result)
    return results
```

## Requirements

The refactored code MUST:
- Preserve exact function signature (name, parameters, return type)
- Maintain all functionality (tests must pass)
- Keep decorators intact
- Preserve docstrings and type hints
- Follow PEP 8 formatting
- Pass mypy --strict

## Validation

Each refactoring is validated:
1. **Syntax**: AST parsing succeeds
2. **Types**: mypy --strict passes
3. **Tests**: Affected tests pass
4. **Behavior**: Same results for same inputs

## CLI

To find complexity violations before refactoring:
```powershell
.\datrix\scripts\metrics\complexity.ps1 datrix-common -Mode check -Max 15
.\datrix\scripts\metrics\complexity.ps1 -All -Mode check -Max 10
```

Target: complexity ≤ 15 (configurable via `-Max`).
