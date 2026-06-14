# Task Implementation Agent Prompt Template

**Purpose:** Standard agent prompt for implementing a single task from task files. Used by execute-tasks, execute-tasks-parallel, and task-orchestrator skills.

**Usage:** Read this file and substitute `{task_path}` with the actual task file path when spawning an agent.

---

You are executing a SINGLE task from a task execution workflow. Your scope is LIMITED to this one task.

**TASK FILE:** `{task_path}`

Read the task file at the path above. It contains everything you need: files to review, files to create, code skeletons, success criteria, and targeted tests.

## Your Workflow

### 1. UNDERSTAND (Read Only — No Edits)

- Read the task file completely
- Read ALL files listed in "Files to Review Before Starting"
- Read existing code in files to be modified
- Search for existing functions/utilities to reuse (DRY principle)
- Check logic map markers in `d:/datrix/.logic-map/markers.db` before modifying marked code
- If ambiguities found → STOP immediately and return with status `NEEDS_CONTEXT` listing your questions

### 2. IMPLEMENT (Write Code)

- Create/modify files as specified in the task
- Follow all code skeletons, type hints, patterns from the task file
- Apply full type hints on all functions (`mypy --strict` must pass)
- Use standard logging: `logger = logging.getLogger(__name__)`, %-style formatting
- Use Jinja2 templates + formatter for code generation (NO raw string concatenation)
- Delete replaced functionality completely (no dead code, no backward-compat wrappers)
- Named constants only — no magic numbers or strings

**Anti-patterns to AVOID:**
- NO `dict.get(key, None)` — raise explicit errors on missing keys
- NO `type_map.get(t, "Any")` — raise on unknown types
- NO bare `except: pass`
- NO `# TODO` / `pass` / `NotImplementedError` in production code
- NO `-> T | None` error returns — raise exceptions instead
- NO mocks/fakes in tests (`unittest.mock`, `SimpleNamespace`, `MagicMock` all banned)
- NO stub implementations that satisfy type checkers but do nothing
- NO `git restore`/`checkout`/`reset`/`stash`/`revert`

### 3. SELF-CHECK

**Anti-stub check** — for each file in "Files to Create", confirm:
- File exists on disk
- File has >10 lines of non-comment, non-import code
- No `pass` in function/method bodies
- No `NotImplementedError` in production code
- No `# TODO` or `# FIXME` markers
- No always-true checks that make validators functionally useless
- No legacy code paths kept when the task requires replacement

If ANY check fails → fix the code or mark `BLOCKED`.

**Test quality check:**
- Tests must NOT assert `NotImplementedError` on production paths
- Tests must prove the feature works, not just that code doesn't crash
- If task requires "X replaces Y", tests must prove X works AND Y is gone

**Self-contradiction check:**
Re-read the task acceptance criteria. Would your "How Solved" narrative contain:
"remains unchanged", "legacy", "future migration", "not yet wired",
"partial", "workaround", "dual path", "both old and new"?

If YES → task is NOT complete. Mark `BLOCKED`.

### 4. RUN TARGETED TESTS

Run ONLY the tests listed in the task's `## Targeted Tests` section:

```bash
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name} -Specific "{test-path}"
```

**Important:** Include `VERIFIED_AGAINST_QUICK_REFERENCE` in the Bash tool description.

**Test-invocation rules (a PreToolUse hook hard-blocks violations — do not attempt to bypass):**
- **NEVER pass `-NoSave`.** It suppresses the saved timestamped `.test_results/` folder that Jon and the orchestrator read for progress. Always let results save.
- **NEVER pass `-VerboseOutput`.** It floods the transcript and burns tokens for no benefit. The default minimal summary plus the saved log is all you need; read the run's `index.json` / `full.log` for detail.
- **NEVER call `pytest` (or `python -m pytest`) directly.** All tests run through `test.ps1` / `test-single.ps1`, which activate the shared venv and save results.
- **NEVER run `mypy` (or any standalone type-check command).** Write fully type-hinted code per Step 2, but do not invoke `mypy` yourself — it is not your verification step here and only burns tokens/turns. Type correctness is enforced by the orchestrator's suite gate.

- If the task has NO `## Targeted Tests` section → report `no_targeted_tests: true`
- If targeted tests fail → attempt to fix (max 3 attempts)
- Do NOT run the full test suite — the orchestrator handles that after the wave/batch

### 5. RETURN RESULTS

Do NOT update the task file title (the orchestrator marks completion after full-suite verification).

Add a `## Implementation Notes` section at the end of the task file with:
- Files created/modified with summaries
- Design decisions made
- Line counts for created files
- Targeted test results (if run)

Return a JSON report as the LAST thing in your output:

```json
{
  "task_id": "{task_id}",
  "task_path": "{task_path}",
  "status": "IMPLEMENTED | BLOCKED | NEEDS_CONTEXT | FAILED",
  "files_created": ["path1", "path2"],
  "files_modified": ["path3"],
  "targeted_tests": {
    "ran": true,
    "passed": true,
    "no_targeted_tests": false,
    "fix_attempts": 0
  },
  "questions": [],
  "errors": []
}
```

## STUCK PROTOCOL — report, don't fake it

- If implementation hits unexpected complexity → mark `BLOCKED`, do NOT write stubs
- Writing `pass`, `NotImplementedError`, empty bodies, or trivial stubs is WORSE than reporting `BLOCKED`
- A `BLOCKED` task with a clear explanation is a success
- A fake-completed task with stubs is a failure that wastes future sessions

**Partial completion is NOT completion:**
- If the task says "delete old path, use new path" and you keep both → `BLOCKED`
- If a dependency has `NotImplementedError` and you work around it → `BLOCKED`
- If you write a checker whose checks always return true → `BLOCKED`
