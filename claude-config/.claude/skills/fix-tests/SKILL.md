---
model: sonnet
---

# Fix Test Failures Skill

Systematically fix test failures one at a time with verification between each fix. Prevents cascading regressions from batch-fixing and ensures each fix is verified green before moving on.

## When to Use

- User has test output showing multiple failures
- User asks to "fix tests", "fix failures", or "make tests pass"
- User provides a test log or test command output with failures
- After a refactoring that broke multiple tests

## How to Invoke

With a structured test results directory (preferred):
```
/fix-tests

RUN: D:\datrix\datrix-codegen-typescript\.test_results\test-results-20260503-172652
```

With a test command (will produce structured output):
```
/fix-tests

COMMAND: powershell -File d:/datrix/datrix/scripts/test/test.ps1 datrix-codegen-python
```

With a legacy log file (falls back to manual triage):
```
/fix-tests

LOG: D:\datrix\.generated\.results\generate-results-20260503-172334.log
```

With inline failures:
```
/fix-tests

FAILURES:
tests/test_foo.py::test_bar - TypeError: expected str got int
tests/test_baz.py::test_qux - AttributeError: 'NoneType' has no attribute 'name'
```

## Prereqs
Read first: CLAUDE.md, MEMORY.md.

### Project Structure
Read `d:\datrix\{package-name}\.project-structure.md`. Regenerate if missing: `powershell -File "d:/datrix/datrix/scripts/dev/project-structure.ps1" {package-name}`.

## Scope Check

After reading the failures:

1. **Count distinct root causes** — group failures that share a common origin
2. **Confirm language scope** — are these Python or TypeScript failures? Do NOT cross languages
3. **Estimate blast radius** — how many files will each fix touch?

**If more than 5 distinct root causes:** STOP and propose splitting into separate sessions.

## Workflow — One at a Time with Verification

### Phase 1: Triage (scripted)

1. **Collect the failure data with the script** (read `datrix/scripts/test/quick-reference.md` first; a pre-tool hook enforces this). Given a RUN directory, pass it; given only a package (e.g. after COMMAND mode ran `test.ps1`), pass `-Project` to auto-locate the newest run:
   ```bash
   powershell -File "d:/datrix/datrix/scripts/test/collect-failure-data.ps1" "{run-dir}"        # or:
   powershell -File "d:/datrix/datrix/scripts/test/collect-failure-data.ps1" -Project {package}
   ```
2. **Read the produced `failure-data.json`.** This gives you total counts, every error/failure cluster with its representative (traceback tail embedded), and a ready-to-run `test_command` per cluster. Do NOT read `index.json`'s failure arrays or `full.log` for triage.
3. **Present the clusters to the user:**
   ```
   Found {N} test failures from {M} clusters:

   Cluster 1: {pattern} @ {source_location} — {count} failures
     Representative: {test_id}
   Cluster 2: {pattern} @ {source_location} — {count} failures
     Representative: {test_id}

   Starting with Cluster 1.
   ```
4. **Legacy fallback (any of: no `index.json`, `"result": "INCOMPLETE"`, or an unrecognized `schema_version` — `collect-failure-data.ps1` fails loud in these cases):** the run has no usable structured data — triage `full.log` with the triage script instead of reading it:
   ```bash
   powershell -File "d:/datrix/datrix/scripts/dev/triage-failures.ps1" "{run-dir}/full.log" -Format pytest -OutputFile "D:\datrix\.test-output\fix-tests-triage.md"
   ```
   Read the triage report; Grep `full.log` only for representative detail it lacks. This same fallback applies throughout the rest of this workflow wherever structured data would otherwise be used.
5. Prioritize: error clusters first (import/collection errors block other tests), then failure clusters by count descending. (`failure-data.json` already lists error clusters first.)

### Phase 2: Fix Loop (repeat for each root cause)

For each root cause, follow this strict sequence:

#### Step A: Read Before Fixing

1. Start from the cluster's `representative.traceback_tail` in `failure-data.json`; read the full `failures/{NNN}-{name}.txt` (the representative's `log_file`) only if the tail is insufficient
2. This gives you the full traceback, captured stdout/stderr, and the cluster assignment
3. Read the source file at the `source_location` indicated in the cluster
4. Read the test file to understand what the test expects
5. Read any relevant templates/generators if this is a codegen issue
6. **DO NOT read `full.log`.** The individual failure file has everything you need (unless in the legacy fallback above).
7. **DO NOT hypothesize without reading. DO NOT fabricate assumptions.**

#### Step B: Identify the Fix

1. State the root cause in one sentence
2. State the exact file(s) and line(s) to change
3. State what the change will be

#### Step C: Apply the Fix

1. Make the smallest possible edit that fixes the root cause
2. **NO debug logging.** No `print()`, no `logger.warning()`, no temporary instrumentation
3. **NO unrelated changes.** Don't clean up surrounding code, don't add docstrings, don't refactor

#### Step D: Verify

1. Run the specific failing test(s) for this root cause
2. **If tests pass:** Mark this root cause as fixed, report, move to next root cause
3. **If tests still fail:** Read the NEW error output carefully. Do NOT retry the same fix. Reassess:
   - Is the root cause different than initially thought?
   - Did the fix introduce a new problem?
   - Maximum 3 attempts per root cause. After 3 attempts, STOP and report:
     ```
     Could not fix root cause {N} after 3 attempts.
     Attempts made:
     1. {what was tried} — {why it failed}
     2. {what was tried} — {why it failed}
     3. {what was tried} — {why it failed}

     Recommend: {next steps}
     ```

#### Step E: Regression Check (scripted)

1. After re-running the suite, compare the previous and new run directories with the delta script:
   ```bash
   powershell -File "d:/datrix/datrix/scripts/test/classify-run-delta.ps1" -Previous "{previous-run-dir}" -Current "{new-run-dir}"
   ```
2. Read its verdict line (and `run-delta.json` in the new run dir for detail): `SUCCESS` = all previously-failing fixed, none new; `PARTIAL` = progress, none new; `NO_CHANGE`; `REGRESSION` = new failures appeared (exit code 0 only for SUCCESS).
3. Confirm the cluster you fixed appears in `resolved_clusters`.
4. **If `new_failures` is non-empty (REGRESSION):** STOP immediately — see `d:\datrix\.claude\skills\_shared\fix-conventions.md` ("Fix Introduced a New Failure") for the report template and options. **WAIT for user decision.** (Legacy fallback: run the full test suite and triage the log with `triage-failures.ps1`, then compare by hand.)

### Phase 3: Final Report

After all root causes are addressed:

```
Test Fix Summary:
- Root causes identified: {N}
- Fixed: {N}
- Could not fix: {N}
- New regressions: {N}

Fixes applied:
1. {file:line} — {what was changed} — {why}
2. {file:line} — {what was changed} — {why}

Final test results: {pass count}/{total count} passing
```

## Anti-Patterns

- **NO exploring the project structure** — read `.project-structure.md` for the target package, don't rediscover it
- **NO batch-fixing** — fix one root cause, verify, then move on
- **NO debug scatter** — no temporary logging, prints, or instrumentation left in code
- **NO guessing** — read the failing code before proposing a fix
- **NO cross-language fixes** — confirm Python vs TypeScript scope first
- **NO scope creep** — don't fix unrelated issues discovered during investigation
- **NO mechanical grep-and-replace** — understand the root cause, don't just pattern-match symptoms
- **NO workarounds** — don't steer around issues, don't paper over them. **Fix the root cause, wherever it lives** (CLAUDE.md rule). This is not a binary between "workaround" and "stop": the third option — do the real work — is the default. Stopping is licensed only by a proven B1–B4 blocker with the four-part proof (`.claude/skills/_shared/execution-contract.md`).
- **NO dodging** — "out of scope", "pre-existing", "categorically behavioral", "should be tracked separately", "not my package" are **not** blockers; they are the work. A `SubagentStop` hook greps reports for this vocabulary.
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
