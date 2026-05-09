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

## Mandatory Reading (BEFORE any work)

Before doing ANY work, read:

1. **`d:\datrix\.claude\CLAUDE.md`** — Project rules. All rules apply.
2. **`C:\Users\KErca\.claude\projects\d--datrix\memory\MEMORY.md`** — Persistent memory. Check for relevant lessons.

**DO NOT skip these.** Skipping = rejected fixes.

## Scope Check

After reading the failures:

1. **Count distinct root causes** — group failures that share a common origin
2. **Confirm language scope** — are these Python or TypeScript failures? Do NOT cross languages
3. **Estimate blast radius** — how many files will each fix touch?

**If more than 5 distinct root causes:** STOP and propose splitting into separate sessions.

## Workflow — One at a Time with Verification

### Phase 1: Triage

1. **Locate the run directory.** Find the most recent `test-results-*` directory under `.test_results/`.
2. **Read `index.json`.** This gives you:
   - Total counts (passed, failed, error, skipped)
   - Failure list with error types and source locations
   - Pre-computed failure clusters with representative failures
3. **If `index.json` exists and has `failure_clusters`:** Use the clusters directly. Do NOT re-read `full.log` for triage. Present the clusters to the user:
   ```
   Found {N} test failures from {M} clusters:

   Cluster 1: {pattern} @ {source_location} — {count} failures
     Representative: {test_id}
   Cluster 2: {pattern} @ {source_location} — {count} failures
     Representative: {test_id}

   Starting with Cluster 1.
   ```
4. **If `index.json` does not exist** (old-format log): Fall back to current behavior — read `full.log` and group manually.
5. **If `index.json` has `"result": "INCOMPLETE"`:** Fall back to reading `full.log` for triage. The test run was interrupted and structured data is unavailable.
6. **If `schema_version` is unrecognized:** Warn the user and fall back to legacy triage (read `full.log` and group manually).
7. Prioritize: error clusters first (import/collection errors block other tests), then failure clusters by count descending.

### Phase 2: Fix Loop (repeat for each root cause)

For each root cause, follow this strict sequence:

#### Step A: Read Before Fixing

1. Read the representative failure file: `failures/{NNN}-{name}.txt` (from the cluster's `representative_failure_id` → failure's `log_file` in `index.json`)
2. This gives you the full traceback, captured stdout/stderr, and the cluster assignment
3. Read the source file at the `source_location` indicated in the cluster
4. Read the test file to understand what the test expects
5. Read any relevant templates/generators if this is a codegen issue
6. **DO NOT read `full.log`.** The individual failure file has everything you need.
7. **If no structured failure files exist** (legacy format): Fall back to reading the log file and searching for the specific test failure.
8. **DO NOT hypothesize without reading. DO NOT fabricate assumptions.**

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

#### Step E: Regression Check

1. After re-running, read the NEW `index.json` from the latest run directory
2. Compare failure count: did it decrease?
3. Check if the cluster you fixed is gone or reduced
4. Check if any NEW clusters appeared (clusters not present in the previous `index.json`)
5. **If new clusters appear:** STOP immediately.
   ```
   Fix for cluster {N} introduced {X} new failures in {Y} new clusters:
   - {new cluster pattern} — {count} failures
   - {new cluster pattern} — {count} failures

   Options:
   1. Investigate the new failures (may expand scope)
   2. Revert and rethink the approach
   3. Keep the fix and document new failures as separate issues
   ```
   **WAIT for user decision.**
6. **If no `index.json`** (legacy format): Run the full test suite and check for new failures by reading the log.

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

- **NO batch-fixing** — fix one root cause, verify, then move on
- **NO debug scatter** — no temporary logging, prints, or instrumentation left in code
- **NO guessing** — read the failing code before proposing a fix
- **NO cross-language fixes** — confirm Python vs TypeScript scope first
- **NO scope creep** — don't fix unrelated issues discovered during investigation
- **NO mechanical grep-and-replace** — understand the root cause, don't just pattern-match symptoms
