---
description: Fix issues from structured issue reports with Root Cause Analysis and Recommended Fix
---

# Fix Issue

Read a structured issue report from `d:\datrix\issues\` and apply the fix following the phased approach (Understand → Fix → Verify). Issue reports contain Root Cause Analysis and Recommended Fix sections that guide implementation.

## How to Invoke

```
/fix-issue d:\datrix\issues\YYYYMMDD-HHMMSS-issue-description.md
```

The argument is the absolute path to an issue markdown file.

**Multiple issues:**
```
/fix-issue d:\datrix\issues\YYYYMMDD-HHMMSS-issue-1.md d:\datrix\issues\YYYYMMDD-HHMMSS-issue-2.md
```

Process issues sequentially — complete one before starting the next.

## Prereqs
Read first: CLAUDE.md, MEMORY.md, `datrix-common/docs/contributing/ai-agent-rules.md` + `test-guidelines/`.

---

## Issue File Structure

Issue files follow this structure:

```markdown
# Issue: {Title}

**Date:** YYYY-MM-DD HH:MM
**Issue ID:** YYYYMMDD-HHMMSS-{slug}
**Affected example(s):** {project names}
**Test type(s):** {unit_tests|integration_tests}
**Log folder(s):** {paths to test result folders}

## Failure Summary
{High-level description of what's failing and why}

### Failed Tests
{Table of failing tests with error types}

### Error Details
{Detailed error messages, stack traces, and failing code}

## Root Cause Analysis
{Traced source, root cause explanation, affected code}

## Impact Assessment
{Severity, blast radius, affected examples}

## Recommended Fix
{Step-by-step fix instructions — USE THIS}

## Open Questions
{Unresolved questions that may need clarification}
```

---

## Workflow

### Phase 1: Understand (Read Only)

1. **Read the issue file** at the provided path.
2. **Extract key information:**
   - Issue title and ID
   - Affected examples/projects
   - Test type and log folders
   - Failure summary
3. **Read the "Root Cause Analysis" section:**
   - Note the traced source (generator/template/DSL)
   - Understand the root cause
   - Identify affected code locations
4. **Read the "Recommended Fix" section:**
   - **START with the recommended approach** unless you have a specific technical reason to deviate
   - If the recommendation is unclear (e.g., mentions context flags without showing where they're set), **STOP and ASK** before investigating alternatives
   - Don't rediscover what's already documented
5. **Read the "Open Questions" section:**
   - If there are unresolved questions that affect the fix, **STOP and ASK** for clarification
6. **Identify which project(s) contain the bug:**
   - If bug is in a codegen package (e.g., `datrix-codegen-python`), fix there
   - If bug is in generated code, fix the generator/template that produced it
   - NEVER fix generated code directly
7. **Read the affected files** identified in Root Cause Analysis
8. **End-of-phase assessment:**
   - Root cause (one sentence)
   - Files to modify (exact paths with line numbers if known)
   - What the change will be (brief description)
   - Estimated scope: Small (1-2 files, <20 lines), Medium (3-5 files), Large (6+ files)
9. **If confident** → proceed to Phase 2 (include brief status note)
10. **If NOT confident** (ambiguous root cause, multiple causes, Large scope, unclear recommended fix, unresolved open questions) → **STOP and present diagnosis, WAIT**

### Phase 2: Fix (Write Code)

1. **Make the changes identified in Phase 1**
   - Follow the Recommended Fix section's instructions
   - If the issue mentions specific line numbers or code patterns, use those
2. **Check for logic map markers:** Before modifying any function or class, look for `# @canonical`, `# @pattern`, `# @boundary`, or `# @invariant` comments above it. If a marker exists, update it. If deleting marked code, remove the marker.
3. **Stay within stated scope** — if fix grows beyond estimate, STOP and report
4. **For template changes:** If modifying Jinja2 templates, verify the template syntax is correct
5. **For generator changes:** If modifying generator code, ensure proper typing and follow all code quality standards
6. **End-of-phase assessment:**
   - What was changed (file:line summary)
   - Any unexpected complications
7. **If confident** → proceed to Phase 3
8. **If NOT confident** → **STOP and present changes, WAIT**

### Phase 3: Verify (Run Tests)

1. **Determine what to test based on issue type:**
   - **If issue has "Log folder(s)":** Re-run the tests that originally failed
   - **If issue affects a codegen package:** Run that package's test suite
   - **If issue affects generated code:** Regenerate the affected example(s) and run their tests
2. **For generated code issues:**
   - If affected example is from CurvAero project, regenerate it using the appropriate generation script
   - Check that the generated code now matches expectations (no more errors in generated files)
   - Run the example's unit tests
3. **Run the relevant tests:**
   - For datrix packages: `powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name}`
   - For single test: `powershell -File "d:/datrix/datrix/scripts/test/test-single.ps1" "{test-path}" -Project {package-name} -VerboseOutput`
4. **Assess results:**
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
     **WAIT** for user decision
   - **If original failure persists:** Fix was insufficient — report what's still wrong and ask for guidance

### Phase 4: Report

```
FIX-ISSUE COMPLETE

Issue file: {issue-file-path}
Issue ID: {issue-id}
Issue title: {title}

Root cause: {one-sentence summary}

Files changed:
1. {file:line} — {what changed}
2. {file:line} — {what changed}

Verification:
- Regenerated: {affected examples, if applicable}
- Tests run: {which tests}
- Result: {PASS/FAIL with counts}

Impact:
- Issue resolved: {YES/NO}
- New issues found: {YES/NO — list if any}
```

---

## Multiple Issues

If invoked with multiple issue file paths:

1. **Read all issue files first** to assess overall scope
2. **If issues are related** (same root cause, same affected files):
   - Combine fixes into a single changeset
   - Report which issues are addressed by each change
3. **If issues are independent:**
   - Process sequentially: Understand → Fix → Verify for each
   - Report progress after each issue is resolved
4. **If total scope exceeds Medium** (6+ files, complex changes):
   - STOP and propose processing issues in separate invocations or batches

---

## Cross-Project Root Cause

If investigation reveals the root cause is in a different project than expected:

1. Report the finding: which project contains the root cause, which file/line, and why
2. If the root cause is in a different datrix package with its own fix skill, activate that skill:
   - `datrix-cli` → `/fix-cli`
   - `datrix-common` → `/fix-common`
   - `datrix-codegen-python` → `/fix-codegen-python`
   - `datrix-codegen-typescript` → `/fix-codegen-typescript`
   - etc.
3. Otherwise, proceed with the fix in the current context

---

## Git Workflow

Each datrix package is an independent git repository. After completing fixes:

1. **Verify git status in the changed package(s):**
   ```bash
   cd /d/datrix/{package-name} && git status
   ```
2. **DO NOT commit automatically** — user will decide when to commit
3. **Report which repositories have changes** so user can review and commit

---

## Runaway Fix Detection

If at any point you notice:

- Modified more than **double** the estimated number of files
- Working for **more than 3 tool-call rounds per issue** without completing
- Simple fix revealed **cascading issues** in other files
- About to modify code **outside stated scope**
- Recommended fix is unclear and investigation isn't converging

**STOP immediately:**
```
Fix is growing beyond estimate. Current state:
- Originally estimated: [scope]
- Actually touching: [what's grown]
- Reason for growth: [why]

Recommend: [continue / revert and rethink / split into smaller tasks]
```

---

## Anti-Patterns

- **NO ignoring Recommended Fix section** — that's the designed solution, use it
- **NO fixing generated code directly** — always fix the generator/template
- **NO debug scatter** — zero temporary logging statements
- **NO modifying unrelated code** — stay focused on the issue
- **NO running full test suites for each issue** — verify only affected tests
- **NO committing changes** — user decides when to commit
- **NO fabricating file locations** — if Root Cause Analysis says "exact file TBD", search for it first
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
