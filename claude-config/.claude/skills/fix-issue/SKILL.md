---
description: Fix issues from structured issue reports with Root Cause Analysis and Recommended Fix
model: claude-opus-4-8
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

## Documentation Quick Reference

See `d:\datrix\.claude\skills\_shared\fix-conventions.md` for the mandatory documentation reads and the Project Structure step. Also read MEMORY.md and `d:\datrix\datrix-common\docs\contributing\test-guidelines\` (unit, integration, E2E test standards) before starting.

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

Follow the Understand → Fix → Verify discipline from `/fix` (`d:\datrix\.claude\skills\fix\SKILL.md`), with the issue-report specifics below:

### Understand — issue-report deltas

- Read the issue file's Root Cause Analysis, Recommended Fix, and Open Questions sections.
- **Start with the Recommended Fix** unless you have a specific technical reason to deviate; if it's unclear (e.g., mentions context flags without showing where they're set), **STOP and ASK** before investigating alternatives.
- If **Open Questions** contains anything unresolved that affects the fix, **STOP and ASK** for clarification.
- Identify which project contains the bug: codegen package bug → fix there; generated-code bug → fix the generator/template that produced it. NEVER fix generated code directly.

### Verify — issue-report deltas

Determine what to test **based on issue type**:
- If the issue has **Log folder(s)**: re-run the tests that originally failed.
- If the issue affects a codegen package: run that package's **targeted/affected tests** (not the full suite — see Phase 4 for the one-time full-suite gate).
- If the issue affects generated code: regenerate the affected example(s), confirm the generated code now matches expectations, and run the example's targeted tests.
- Test commands: `powershell -File "d:/datrix/datrix/scripts/test/test-single.ps1" "{test-path}" -Project {package-name} -VerboseOutput`, or `test.ps1 {package-name}` scoped to the affected tests.
- **Fix introduced a new failure:** see `d:\datrix\.claude\skills\_shared\fix-conventions.md`.
- If the original failure persists: fix was insufficient — report what's still wrong and ask for guidance.

### Phase 4: Final Gate and Report

After all issues in this invocation are fixed and their targeted tests pass, run the affected package's **full test suite ONCE** as the final gate: `powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package-name}`. This replaces per-issue full-suite runs (see Anti-Patterns).

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
2. If the root cause is in a different datrix package with its own fix skill, activate that skill. Every package has one, and the name is derived — `datrix-<name>` → `/fix-<name>`:
   - `datrix-cli` → `/fix-cli`
   - `datrix-common` → `/fix-common`
   - `datrix-codegen-python` → `/fix-codegen-python`
   - `datrix-codegen-typescript` → `/fix-codegen-typescript`
   - `datrix-codegen-dotnet` → `/fix-codegen-dotnet`, `datrix-codegen-java` → `/fix-codegen-java`, and so on for any codegen package
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

See `d:\datrix\.claude\skills\_shared\fix-conventions.md` (also applies per-issue: more than 3 tool-call rounds per issue without completing, or an unclear recommended fix with investigation not converging, are runaway signals here too).

---

## Anti-Patterns

- **NO ignoring Recommended Fix section** — that's the designed solution, use it
- **NO fixing generated code directly** — always fix the generator/template
- **NO debug scatter** — zero temporary logging statements
- **NO modifying unrelated code** — stay focused on the issue
- **NO running full test suites for each issue** — verify only affected tests
- **NO committing changes** — user decides when to commit
- **NO fabricating file locations** — if Root Cause Analysis says "exact file TBD", search for it first
- **NO workarounds** — don't steer around issues, don't paper over them. **Fix the root cause, wherever it lives** (CLAUDE.md rule). This is not a binary between "workaround" and "stop": the third option — do the real work — is the default. Stopping is licensed only by a proven B1–B4 blocker with the four-part proof (`.claude/skills/_shared/execution-contract.md`).
- **NO dodging** — "out of scope", "pre-existing", "categorically behavioral", "should be tracked separately", "not my package" are **not** blockers; they are the work. A `SubagentStop` hook greps reports for this vocabulary.
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
