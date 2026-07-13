---
model: sonnet
---

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
   - Validate with pytest
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

Nested `if item.type == "A": if config.enable_a: ...` / `elif item.type == "B": ...`
chains (complexity 23) collapse via guard clause + dict dispatch: extract
`_should_process(item, config)` (validity + per-type config check) and
`_get_handler(item_type)` (type → handler dict lookup), then loop body becomes
`if not _should_process(...): continue; handler = _get_handler(...); if handler and (result := handler(item)): results.append(result)` (complexity 8).

## Requirements

The refactored code MUST:
- Preserve exact function signature (name, parameters, return type)
- Maintain all functionality (tests must pass)
- Keep decorators intact
- Preserve docstrings and type hints
- Follow PEP 8 formatting
- Pass all tests

## Validation

Each refactoring is validated:
1. **Syntax**: AST parsing succeeds
2. **Tests**: Affected tests pass
3. **Behavior**: Same results for same inputs

## CLI

To find complexity violations before refactoring:
```powershell
.\datrix\scripts\metrics\complexity.ps1 datrix-common -Mode check -Max 15
.\datrix\scripts\metrics\complexity.ps1 -All -Mode check -Max 10
```

Target: complexity ≤ 15 (configurable via `-Max`).

## Anti-Patterns

- **NO workarounds** — don't steer around issues, don't paper over them. **Fix the root cause, wherever it lives** (CLAUDE.md rule). This is not a binary between "workaround" and "stop": the third option — do the real work — is the default. Stopping is licensed only by a proven B1–B4 blocker with the four-part proof (`.claude/skills/_shared/execution-contract.md`).
- **NO dodging** — "out of scope", "pre-existing", "categorically behavioral", "should be tracked separately", "not my package" are **not** blockers; they are the work. A `SubagentStop` hook greps reports for this vocabulary.
- **NO debug scatter** — zero temporary logging statements
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
