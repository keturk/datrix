---
description: Phased fix execution discipline — Understand, Fix, Verify with runaway detection
model: sonnet
disable-model-invocation: true
---

# Fix Execution Discipline

Follow this phased approach.

**Governed by `.claude/skills/_shared/execution-contract.md` — read it.** Your default outcome is *the problem is fixed*. **Low confidence is not a stopping condition — it is a signal to read more.** Uncertainty is a state of your knowledge, not a property of the bug. Stop only on a proven B1–B4 blocker (§1), with the four-part proof (§3).

## Phase 1: Understand (Read Only)

- **Read the FULL issue report first:**
  - Root Cause Analysis section (if present)
  - Recommended Fix section (if present)
  - Open Questions section (if present)
- **If the issue has a "Recommended Fix" section:**
  - START with that approach unless you have a specific technical reason to deviate
  - If the recommendation is unclear (e.g., mentions "spec test context" but you don't see how to identify it), **STOP and ASK** before investigating alternatives
  - Don't rediscover what's already documented
- Read the failing code, templates, generators to understand implementation details
- Identify the exact root cause and the exact lines to change
- **End-of-phase assessment:**
  - Root cause (one sentence)
  - Files to modify (exact paths)
  - What the change will be (brief description)
  - Estimated scope: Small (1-2 files, <20 lines), Medium (3-5 files), Large (6+ files)
- **If confident** → proceed to Phase 2 (include brief status note)
- **If NOT confident** (ambiguous root cause, multiple causes, Large scope, unclear recommended fix) → **keep investigating.** None of these are blockers: ambiguous root cause → read more; multiple causes → fix them; Large scope → do the work. Escalate (`_shared/decision-escalation-protocol.md`) if a genuine architectural fork emerges — escalation continues the work, it does not end it. Present a diagnosis and wait **only** for a real B2 (two defensible designs, expensive to reverse, nothing in the docs settles it) — and then present **your recommendation**, not a bare question.

## Phase 2: Fix (Write Code)

- Make the changes identified in Phase 1
- **Check for logic map markers:** Before modifying any function or class, look for `# @canonical`, `# @pattern`, `# @boundary`, or `# @invariant` comments above it. If a marker exists, update it. If deleting marked code, remove the marker.
- **Scope: expand, don't abandon.** The stated scope is the *expected* surface, not a fence. If the root cause lies outside it, **follow it and fix it there**, then report the expansion. A fix growing beyond its estimate is not a stopping condition — an estimate is a prediction, not a permission slip. (Patching at the boundary to stay "in scope" is a workaround — see Anti-Patterns.)
- **End-of-phase assessment:**
  - What was changed (file:line summary)
  - Any unexpected complications
- **If confident** → proceed to Phase 3
- **If NOT confident** → read more code until you are. Confidence comes from evidence, not from permission.

## Phase 3: Verify (Run Tests)

- Run the relevant tests
- **If tests pass:** verify the root cause is actually gone (not just the symptom), then report success with pasted evidence
- **If NEW failure: it is yours. Fix it.** A regression you introduced is not a new topic requiring authorization — it is the unfinished half of the job you are already doing. Read the error text, trace it, fix it at the root cause, re-run.

  A new failure usually means your model of the root cause was **wrong**, not that the fix needs a footnote. Treat it as evidence and re-diagnose. Do not stop to ask permission to finish.

  **Do not** revert (CLAUDE.md forbids git reverts), and **do not** "keep the fix and document the new failure as a separate issue" — shipping a known regression with a note attached is exactly the workaround this repo bans.

  Escalate (`_shared/decision-escalation-protocol.md`) only if the new failure reveals a genuine architectural fork you cannot defensibly decide. Escalation continues the work; it does not end it.

## Runaway Fix Detection

If at any point you notice:
- Modified more than **double** the estimated number of files
- Working for **more than 3 tool-call rounds** without completing
- Simple fix revealed **cascading issues** in other files
- About to modify code **outside stated scope**

**STOP immediately:**
```
Fix is growing beyond estimate. Current state:
- Originally estimated: [scope]
- Actually touching: [what's grown]
- Reason for growth: [why]

Recommend: [continue / revert and rethink / split into smaller tasks]
```

## Anti-Patterns

- **NO workarounds** — don't steer around issues, don't paper over them. **Fix the root cause, wherever it lives.** This is not a binary between "workaround" and "stop": the third option — do the real work — is the default. Stopping is licensed only by a proven B1–B4 blocker (execution-contract §1–§3).
- **NO dodging** — "out of scope", "pre-existing", "categorically behavioral", "should be tracked separately", "not my package" are **not** blockers; they are the work. A `SubagentStop` hook greps reports for this vocabulary.
- **NO debug scatter** — zero temporary logging statements
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
