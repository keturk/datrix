---
description: Analyze project bug reports, classify as app-definition or generator-level, fix root causes, and update reports with resolution
model: claude-opus-4-8
---

# Fix Bug Report

**Reasoning effort: HIGH.** Apply STOP AND THINK on every bug — read the generator/template/transformer and the offending app definition before forming a hypothesis. One correct root-cause fix beats five quick patches.

Analyze structured bug reports, classify each as an **app-definition fix** or a **generator-level fix**, implement the appropriate changes, and update each bug report with the resolution.

Bug reports are written by another agent that operates directly on a deployed product's generated code (e.g. on a staging server). That agent **cannot see the Datrix toolchain, generators, or app definitions** — it can only patch generated output in place. **Every fix it describes is a temporary patch that will be overwritten on the next regeneration.** Your job is to make the fix permanent in the source that survives regeneration: the **app definition** or the **generator/template**. Treat the report's "Files Modified" / "What Was Changed" sections as diagnostic evidence of the correct output, not as completed work — do not skip or classify a bug as already-resolved just because the deployed patch currently works; it vanishes on the next regeneration.

## How to Invoke

```
/fix-bug-report D:\<product-repo>\.bug-report\2026-05-29-some-bug.md
/fix-bug-report D:\<product-repo>\.bug-report\bug-1.md D:\<product-repo>\.bug-report\bug-2.md
/fix-bug-report D:\<product-repo>\.bug-report\*.md
```

The argument is one or more absolute paths to bug report markdown files (or a glob pattern).

## Project Layout (Option A — standalone product repos)

Each customer/product is a **single, self-contained product repository** that consumes the Datrix toolchain internally. There is **no `datrix-projects` container** and no symlink/junction bridging — that model was retired. Derive every concrete path from the bug-report argument; never hardcode a customer name or a `datrix-projects\...` path.

| Role | Location | Notes |
|---|---|---|
| **Datrix toolchain** | `$env:DATRIX_HOME` (default `D:\datrix`) | Framework + `datrix-codegen-*` generator packages. Generator-level fixes go here. |
| **Product repo root** | the ancestor of the bug-report file (parent of `.bug-report\`) | e.g. `D:\g\<Product>` — a standalone git repo. |
| **Bug reports (input)** | `<product-repo>\.bug-report\` | The files you are given. Gitignored, local-only. |
| **App definition (DSL)** | `<product-repo>\<name>-backend\` | `.dtrx` / `.dcfg` — source of truth. App-definition fixes go here. |
| **Generated code (output)** | `<product-repo>\generated\<profile>\` | Auto-generated; **never edit** — overwritten on regeneration. |

To resolve the **app-definition directory**: take the product repo root (parent of the `.bug-report\` directory holding the report) and locate the `*-backend` DSL directory inside it. If the layout is ambiguous, read the report's "Files Modified" paths and the repo's top-level structure rather than guessing.

## Prereqs

Read first: `$DATRIX_HOME` `CLAUDE.md`, `MEMORY.md`, `datrix-common/docs/contributing/ai-agent-rules.md` + `test-guidelines/`.

---

## Bug Report Structure

Bug reports follow this structure:

```markdown
# Bug: {Title}

**Date**: YYYY-MM-DD
**Severity**: {Critical|High|Medium|Low}

## Summary
{What's wrong — runtime error, wrong behavior, crash}

## Files Modified
{Table of files manually patched in generated code}

## What Was Changed and Why
{Description of the manual fix applied to generated code}

## Implications for the Datrix Code Generator
{Root cause analysis — KEY SECTION for classification}
{Points to generator/template issues, or describes why the app definition is wrong}
```

The **"Implications for the Datrix Code Generator"** section is the primary classification signal. If it describes a pattern that the code generator emits incorrectly, the fix belongs in the generator. If it describes incorrect inputs (wrong URLs, wrong field names in the DSL), the fix belongs in the app definition.

Report layout varies between products (a product may use a richer template with `Root Cause` / `Required: Permanent Fix` sections). Read what the report actually contains — the section names above are the common case, not a guarantee.

---

## Workflow

### Phase 1: Triage (Read Only)

1. **Read all provided bug report files.**

2. **For each bug report, extract:**
   - Title and severity
   - Summary of the problem
   - Files that were manually modified (in generated code)
   - The "Implications for the Datrix Code Generator" section (if present)

3. **Classify each bug into one of three categories:**

   **Default assumption: fix the product's app definition.** Only classify as a generator fix when the evidence unambiguously points to a systematic generator defect that would affect any project — not just this one. When classification is ambiguous, choose Category A.

   **Category A — App Definition Fix (preferred):**
   The bug can be resolved by modifying `.dtrx` or `.dcfg` files in the app definition directory. Decisive indicators:
   - The "Implications" section says "not a codegen issue" or describes DSL-level misconfiguration
   - The fix is project-specific — other projects using the same generator would not have this bug
   - The generated code structure is correct but the inputs (DSL definitions) are wrong (e.g. wrong API URLs, field mappings, config values, missing validators/constraints)

   **Category B — Generator/Template Fix (only when necessary):**
   The bug requires changing Datrix generator code (`datrix-codegen-*` packages). **Only use this category when there is clear evidence of a systematic generator defect.** Decisive indicators:
   - The "Implications" section describes a systematic pattern that would affect ANY project using this generator
   - The same bug would occur in any project using the same generator features — it is NOT specific to this product
   - The bug report title or implications mention "codegen", "template", "generator", or "transpiler", or describe wrong emitted syntax/type mappings/missing null-safety in generated code

   **Category C — Both App and Generator Fix:**
   The bug has aspects requiring changes in both. Handle the app definition fix first (Category A), then the generator fix (Category B) only if the generator defect is confirmed.

   **Category D — Cannot Fix (Report Only):**
   The bug describes issues outside the scope of app definitions and code generators. Examples: external API changes/outages, infrastructure/deployment issues.
   - Mark these as "SKIPPED — requires manual intervention" and explain why

4. **Group related bugs:**
   - If multiple bugs share the same generator root cause (e.g., several bugs all caused by `.to_string()` emission), group them under a single fix
   - Note which individual bug reports will be resolved by each grouped fix
   - Grouping reduces redundant work and prevents conflicting edits

5. **Plan execution order:**
   - App definition fixes first (Category A) — prioritize fixing the product's app
   - Generator fixes second (Category B) — only when a systematic generator defect is confirmed
   - Combined fixes (Category C) — app definition part first, then generator part only if confirmed necessary
   - Within each category, fix higher-severity bugs first

6. **End-of-phase report:**

   ```
   TRIAGE COMPLETE

   Bug reports analyzed: {N}

   Category A (App Definition Fix): {count}
     - {bug-filename}: {title} — change: {what to modify in .dtrx/.dcfg}

   Category B (Generator/Template Fix): {count}
     - {bug-filename}: {title} — change: {generator/template to fix}

   Category C (Both): {count}
     - {bug-filename}: {title} — generator: {fix} + app: {fix}

   Category D (Cannot Fix): {count}
     - {bug-filename}: {title} — reason: {why it can't be fixed here}

   Grouped root causes: {count unique fixes} (covering {N} individual bugs)

   Execution plan:
   1. [B] {generator fix description} — resolves: {bug-file-1}, {bug-file-2}
   2. [A] {app fix description} — resolves: {bug-file-3}
   ...
   ```

7. **Scope gate:**
   - If total scope exceeds **6 distinct root causes** → STOP and propose splitting into batches
   - If any single fix touches **more than 5 files** → flag it and ask for confirmation before proceeding

8. **If confident** → proceed to Phase 2
9. **If NOT confident** (ambiguous classification, unclear root cause) → **keep investigating.** Unclear root cause is a state of your knowledge, not a blocker — read the generator, the AST, and the emitted output until the classification is forced by evidence. Escalate (`_shared/decision-escalation-protocol.md`) if a genuine architectural fork emerges. Present triage and wait **only** for a real B2 (two defensible designs, expensive to reverse) — and bring **your recommendation**, not a bare question.

---

### Phase 2: Fix (Write Code)

Process fixes in the planned order from Phase 1 (app definition fixes first).

#### For App Definition Fixes (Category A — do these first):

1. **Read the bug report's Summary and What Was Changed sections** to understand what's wrong
2. **Read the relevant `.dtrx` or `.dcfg` files** in the product's app definition directory (`<product-repo>\<name>-backend\`)
3. **Implement the fix** in the app definition:
   - Correct API URLs, field mappings, configuration values
   - Add missing validators, constraints, or integration settings
   - Ensure the change follows Datrix DSL syntax
4. **Read surrounding context** in the `.dtrx` file to ensure consistency with adjacent definitions

#### For Generator/Template Fixes (Category B — only when a generator defect is confirmed):

1. **Read the "Implications for the Datrix Code Generator" section** — this describes the root cause and often suggests the fix approach
2. **Locate the generator/template code** under `$DATRIX_HOME`:
   - Search in `datrix-codegen-python`, `datrix-codegen-typescript`, `datrix-codegen-common`, etc.
   - Look for the template (`.j2`) or generator (`.py`) file mentioned or implied
   - Use the "Files Modified" section in the bug report — the generated file path reveals which generator produced it
3. **Read the affected generator/template code**
4. **Implement the fix:**
   - Fix the root cause in the generator/template, NOT in generated code
   - Follow all code standards (type hints, mypy strict, cognitive complexity <=15)
   - Check for logic map markers (`@canonical`, `@pattern`, `@boundary`, `@invariant`) before modifying
5. **If the fix affects a codegen package with its own fix skill**, delegate:
   - `datrix-codegen-python` → use `/fix-codegen-python` patterns
   - `datrix-codegen-typescript` → use `/fix-codegen-typescript` patterns
   - etc.

#### After Each Fix:

```
CHECKPOINT — Bug: {title}
Category: {A|B|C}
Status: FIXED
Changed: {file:line} — {what changed}
Bug reports resolved by this fix: {list of bug filenames}
```

**Confidence gate:** Low confidence means **read more**, not stop — confidence comes from evidence, not from permission. Stop and present findings only on a proven B1–B4 blocker (`.claude/skills/_shared/execution-contract.md` §1), with the four-part proof.

---

### Phase 3: Update Bug Reports

For each bug report that was fixed:

1. **Append a Resolution section** to the end of the bug report file:

   ```markdown

   ---

   ## Resolution

   **Date**: {YYYY-MM-DD}
   **Status**: Resolved
   **Fix Type**: App Definition | Generator/Template | Both

   ### Changes Made

   | File | Changes |
   |------|---------|
   | `{file-path}` | {description of change} |

   ```

2. **Do NOT modify the original content** of the bug report — only append the Resolution section at the end

3. **For bugs that could NOT be fixed** (Category D or failed fixes), append:

   ```markdown

   ---

   ## Resolution

   **Date**: {YYYY-MM-DD}
   **Status**: Unresolved
   **Reason**: {why this bug could not be fixed — out of scope / requires manual intervention / fix attempt failed}

   ### Investigation Notes

   {What was examined and why the fix could not be applied}
   ```

---

### Phase 4: Final Report

```
FIX-BUG-REPORT COMPLETE

Bug reports processed: {N}
Resolved: {N}
Unresolved: {N}
Skipped: {N}

Generator/Template fixes:
1. {file:line} — {what changed} — resolves: {bug titles}

App definition fixes:
1. {file:line} — {what changed} — resolves: {bug titles}

Fixed bug reports (absolute paths):
- {product-repo}\.bug-report\{bug-filename}: {title} — Resolved

Unresolved bug reports (absolute paths):
- {product-repo}\.bug-report\{bug-filename}: {title} — {reason}

Repositories with changes:
- {repo-or-package-name}: {files changed}
```

---

## Runaway Fix Detection

See `d:\datrix\.claude\skills\_shared\fix-conventions.md` (also applies per-bug: more than 3 tool-call rounds per bug without completing is a runaway signal here too).

---

## Anti-Patterns

- **NO fixing generated code directly** — fix generators/templates or app definitions; generated code under `<product-repo>\generated\` is overwritten on regeneration
- **NO hardcoding customer names or `datrix-projects\...` paths** — that container was retired; derive product paths from the bug-report argument and `$DATRIX_HOME`
- **NO debug scatter** — zero temporary logging statements
- **NO modifying original bug report content** — only append the Resolution section
- **NO committing changes** — user decides when to commit
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
- **NO fabricating file locations** — if unsure where a generator/template is, search first
- **NO skipping the triage phase** — classification prevents wasted effort on wrong fix location
- **NO batch-modifying multiple generators without checkpoints** — one fix at a time with verification
- **NO workarounds** — don't steer around issues, don't paper over them. **Fix the root cause, wherever it lives** (CLAUDE.md rule). This is not a binary between "workaround" and "stop": the third option — do the real work — is the default. Stopping is licensed only by a proven B1–B4 blocker with the four-part proof (`.claude/skills/_shared/execution-contract.md`).
- **NO dodging** — "out of scope", "pre-existing", "categorically behavioral", "should be tracked separately", "not my package" are **not** blockers; they are the work. A `SubagentStop` hook greps reports for this vocabulary.
- **NO treating staging fixes as resolved** — bug reports describe temporary patches to generated code made by an agent without Datrix access; every bug still needs a permanent fix in the app definition or generator