# Self-Correcting Codegen Fix Loop

Iterative fix loop that makes a change to a generator/template, runs targeted tests, analyzes failures, adjusts, and repeats until green — with a hard iteration limit to prevent spirals.

Designed for bugs where the exact fix isn't obvious upfront and requires iterative refinement guided by test feedback.

## When to Use

- User describes a codegen bug that needs iterative refinement to fix
- User says "fix this until tests pass", "iterate until green", or "fix loop"
- The correct fix requires testing different approaches (not a clear one-shot fix)
- Previous attempts at fixing a bug have gone in circles

## How to Invoke

```
/codegen-fix-loop

BUG: Enum naming uses camelCase instead of PascalCase in TypeScript entity files
PACKAGE: datrix-codegen-typescript
TEST COMMAND: powershell -File "d:/datrix/datrix/scripts/test/test-single.ps1" "tests/generators/test_enum_generator.py" -Project datrix-codegen-typescript
```

With specific files:
```
/codegen-fix-loop

BUG: String interpolation drops second placeholder in computed fields
PACKAGE: datrix-codegen-python
FILES TO READ FIRST:
- datrix-codegen-python/src/datrix_codegen_python/transpiler/expression_transpiler.py
- datrix-codegen-python/tests/transpiler/test_string_interpolation.py
TEST COMMAND: powershell -File "d:/datrix/datrix/scripts/test/test-single.ps1" -Project datrix-codegen-python -Keyword "test_string_interpolation"
MAX ITERATIONS: 5
```

## Prereqs
Read first: CLAUDE.md, MEMORY.md. Also read `FILES TO READ FIRST` (if provided) and `generate.ps1` (if not already familiar).

### Project Structure
Read `d:\datrix\{PACKAGE}\.project-structure.md`. Regenerate if missing: `powershell -File "d:/datrix/datrix/scripts/dev/project-structure.ps1" {PACKAGE}`.

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| MAX_ITERATIONS | 5 | Hard limit on fix attempts |
| PACKAGE | (required) | Which codegen package to test |
| TEST COMMAND | (required) | Exact command to run for verification |
| FILES TO READ FIRST | (optional) | Mandatory reading before first attempt |

## Workflow — Iterative Loop with Hard Limit

### Phase 0: Understand (Read Only — ONE TIME)

Before ANY fix attempt:

1. Read the files listed in `FILES TO READ FIRST` (or identify relevant files from BUG description)
2. Read the failing test(s) to understand expected behavior
3. Read the source code being tested (generator, template, transpiler)
4. Summarize understanding:

```
UNDERSTANDING:

Bug: {one sentence}
Root cause hypothesis: {what I think is wrong based on reading the code}
Files to modify: {list}
Expected behavior: {what the test expects}
Actual behavior: {what currently happens}
```

**DO NOT proceed without completing this phase.** No fabricating assumptions.

### Phase 1-N: Fix Iterations

Each iteration follows this strict cycle:

#### A. Propose Change

Before editing, state:
```
ITERATION {N}/{MAX}:

Change: {what I'm going to do}
File: {file:line}
Rationale: {why this should fix it, informed by previous iteration's failure if applicable}
```

#### B. Apply Change

- Make the smallest possible edit
- **NO debug logging** — zero print/logger instrumentation
- **NO unrelated changes**
- If reverting a previous attempt, state clearly what's being reverted

#### C. Run Tests

Execute the TEST COMMAND exactly as provided.

#### D. Analyze Result

```
ITERATION {N} RESULT: PASS / FAIL

[If PASS]:
  Fix confirmed. Proceeding to verification.

[If FAIL]:
  Error: {key error message}
  Analysis: {what the error tells me about why my fix was wrong}
  Adjustment for next iteration: {what I'll do differently}
```

**Key analysis rules:**
- Read the FULL error output — don't just look at the first line
- Compare against the PREVIOUS iteration's error — is it the same? Different? Worse?
- If the error is WORSE (more failures than before), revert immediately
- If the error is the SAME as 2 iterations ago, you're looping — STOP

#### E. Loop or Exit

- **If PASS** → exit loop, proceed to Final Verification
- **If FAIL and iterations remaining** → go to next iteration
- **If FAIL and MAX_ITERATIONS reached** → STOP with report
- **If error is WORSE than previous iteration** → REVERT and STOP
- **If same error seen 2+ times** → pattern detected, STOP

### Hard Stop Conditions

STOP the loop immediately if:

1. **MAX_ITERATIONS reached** without passing
2. **Error is worse** (more failures) than the previous iteration
3. **Same error repeats** across 2+ non-consecutive iterations (looping)
4. **Scope creep** — fix requires changes outside the stated PACKAGE
5. **Cascading failures** — fix breaks previously-passing tests

On hard stop:
```
FIX LOOP STOPPED — Iteration {N}/{MAX}

Reason: {why stopped}
Attempts made:
1. {change} → {result}
2. {change} → {result}
...

Current state: {reverted to clean / partial fix in place}
Recommendation: {what a human should investigate}
```

### Final Verification (after PASS)

Once tests pass:

1. Run the FULL package test suite (not just the targeted test):
   ```
   powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {PACKAGE}
   ```

2. Run debug artifact check:
   ```
   powershell -File "d:/datrix/datrix/scripts/dev/check-debug-artifacts.ps1" {PACKAGE}
   ```

3. If full suite passes → report success
4. If full suite has NEW failures → STOP and report (the targeted fix broke something else)

```
FIX LOOP COMPLETE

Bug: {description}
Fixed in: {N} iterations
Change: {file:line} — {what was changed}
Full test suite: {pass}/{total} PASS
Debug artifacts: CLEAN
```

## Anti-Patterns

- **NO exploring the project structure** — read `.project-structure.md` for the target package, don't rediscover it
- **NO fixing without reading first** — Phase 0 is mandatory, every time
- **NO debug scatter** — zero temporary logging in any iteration
- **NO ignoring test output** — read the FULL error, not just the summary
- **NO infinite loops** — hard limit is enforced, no exceptions
- **NO cross-package changes** — stay within PACKAGE boundary
- **NO reverting to try the same thing again** — if you revert, the NEXT attempt must be different
- **NO guessing at the fix** — each iteration's rationale must reference specific code or error output
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
