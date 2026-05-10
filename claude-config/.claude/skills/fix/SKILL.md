---
description: Phased fix execution discipline — Understand, Fix, Verify with runaway detection
disable-model-invocation: true
---

# Fix Execution Discipline

Follow this phased approach. Assess confidence at each boundary — proceed when confident, STOP and report when not.

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
- **If NOT confident** (ambiguous root cause, multiple causes, Large scope, unclear recommended fix) → **STOP and present diagnosis, WAIT**

## Phase 2: Fix (Write Code)

- Make the changes identified in Phase 1
- **Check for logic map markers:** Before modifying any function or class, look for `# @canonical`, `# @pattern`, `# @boundary`, or `# @invariant` comments above it. If a marker exists, update it. If deleting marked code, remove the marker.
- Stay within stated scope — if fix grows beyond estimate, STOP and report
- **End-of-phase assessment:**
  - What was changed (file:line summary)
  - Any unexpected complications
- **If confident** → proceed to Phase 3
- **If NOT confident** → **STOP and present changes, WAIT**

## Phase 3: Verify (Run Tests)

- Run the relevant tests
- **If tests pass:** Report success, done
- **If NEW failure:** Do NOT immediately fix. STOP and report:
  ```
  Fix introduced a new failure:
  - Original issue: [what was fixed]
  - New failure: [what broke]
  - My assessment: [related to my change, or different issue?]

  Options:
  1. Investigate the new failure (may expand scope)
  2. Revert my change and rethink
  3. Keep the fix, document new failure as separate issue
  ```
- **WAIT** for user decision

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
