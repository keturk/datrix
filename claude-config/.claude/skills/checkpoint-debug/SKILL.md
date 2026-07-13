---
model: sonnet
---

# Checkpoint Debugging Skill

Structured debugging workflow that fixes issues one at a time with explicit checkpoints between each fix. Designed for sessions with multiple bugs or large-scale refactoring verification.

## When to Use

- Multiple bugs to fix in a single session
- Post-refactoring cleanup with many breakages
- Any task where past sessions have suffered from "attempt everything at once" failures
- User asks to "debug", "fix issues", or provides a list of problems to address

## How to Invoke

```
/checkpoint-debug

ISSUES:
1. Enum naming uses camelCase instead of PascalCase in TypeScript entity generator
2. Import paths missing namespace prefix for cross-block references
3. Docker health check URL wrong for services with custom base paths
```

Or with a log:
```
/checkpoint-debug

LOG: D:\datrix\.generated\.results\generate-results-20260503-172334.log
```

## Prereqs
Read first: CLAUDE.md, MEMORY.md.

### Project Structure
Read `d:\datrix\{package-name}\.project-structure.md`. Regenerate if missing: `powershell -File "d:/datrix/datrix/scripts/dev/project-structure.ps1" {package-name}`.

## Workflow — Checkpoint-Based

### Phase 1: Issue Inventory

1. Read all provided issues, logs, or error output
2. Create a numbered issue list with severity (Critical/High/Medium/Low)
3. Identify dependencies between issues (does fixing #1 also fix #3?)
4. Propose an execution order:

```
Issue Inventory ({N} issues):

| # | Issue | Severity | Dependencies | Est. Files |
|---|-------|----------|-------------|------------|
| 1 | {description} | Critical | None | 2 |
| 2 | {description} | High | Blocked by #1 | 1 |
| 3 | {description} | Medium | None | 3 |

Proposed order: #1 → #2 → #3
(#2 depends on #1; #3 is independent but lower severity)
```

**WAIT for user to approve the order or adjust.**

### Phase 2: Fix Cycle (repeat for each issue)

Each issue follows this strict checkpoint cycle:

#### Checkpoint A: Understand

- Read all relevant code for this specific issue
- State the root cause in one sentence
- State the exact files and lines to change
- State what the change will be
- **DO NOT fabricate assumptions — read the code**

```
CHECKPOINT A — Issue #{N}: {title}
Root cause: {one sentence}
Files to change: {list}
Change: {description}

Proceeding to fix.
```

#### Checkpoint B: Fix

- Apply the fix — smallest possible edit
- **NO debug logging.** No prints, no temporary instrumentation
- **NO unrelated changes**
- List what was changed:

```
CHECKPOINT B — Issue #{N}: Fix Applied
Changed:
- {file:line} — {what changed}
- {file:line} — {what changed}

Running verification.
```

#### Checkpoint C: Verify

- Run the relevant test(s) or build step
- Report results:

```
CHECKPOINT C — Issue #{N}: Verification
Result: PASS ✓ / FAIL ✗

[If PASS]: Moving to issue #{N+1}.
[If FAIL]: {error output}. Reassessing root cause.
```

**If FAIL:** Maximum 3 attempts. After 3, STOP and report the issue as unresolved.

**If new failures introduced:** STOP immediately and report. WAIT for user decision.

#### Checkpoint D: Regression Check

After every 3 fixes (or after a fix that touches shared code), run the full test suite:

```
CHECKPOINT D — Regression Check (after issues #{X}-#{Y})
Full test results: {pass}/{total}
New failures: {none / list}
```

### Phase 3: Final Summary

```
Checkpoint Debug Summary:

| # | Issue | Status | Fix |
|---|-------|--------|-----|
| 1 | {description} | FIXED | {file:line — what changed} |
| 2 | {description} | FIXED | {file:line — what changed} |
| 3 | {description} | UNRESOLVED | {why — blocked on X} |

Final test results: {pass}/{total}
Issues fixed: {N}/{M}
Issues unresolved: {N} (see details above)
```

## Anti-Patterns

- **NO exploring the project structure** — read `.project-structure.md` for the target package, don't rediscover it
- **NO parallel fixing** — one issue at a time, verified before moving on
- **NO debug scatter** — zero temporary logging or instrumentation
- **NO scope creep** — if you discover a new issue during a fix, log it as a new item, don't chase it
- **NO assumption-driven fixes** — read the code at every checkpoint
- **NO skipping checkpoints** — every fix gets Understand → Fix → Verify
- **NO workarounds** — don't steer around issues, don't paper over them. **Fix the root cause, wherever it lives** (CLAUDE.md rule). This is not a binary between "workaround" and "stop": the third option — do the real work — is the default. Stopping is licensed only by a proven B1–B4 blocker with the four-part proof (`.claude/skills/_shared/execution-contract.md`).
- **NO dodging** — "out of scope", "pre-existing", "categorically behavioral", "should be tracked separately", "not my package" are **not** blockers; they are the work. A `SubagentStop` hook greps reports for this vocabulary.
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
