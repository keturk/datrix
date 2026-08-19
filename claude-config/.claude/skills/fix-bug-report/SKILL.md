---
description: Analyze project bug reports from any deployment profile, classify as app-definition or generator-level, fix root causes without breaking sibling profiles, and update reports with resolution
model: opus
---

# Fix Bug Report

**Reasoning effort: HIGH.** Apply STOP AND THINK on every bug — read the generator/template/transformer and the offending app definition before forming a hypothesis. One correct root-cause fix beats five quick patches.

Analyze structured bug reports, classify each as an **app-definition fix** or a **generator-level fix**, implement the appropriate changes, and update each bug report with the resolution.

**Reports arrive from several deployment profiles of the same product**, each with its own generated tree and its own inherited config. Two failures are equally wrong: a fix that cures the reporting profile and leaves the same defect standing in a sibling, and a fix that cures one profile by changing a value another profile depended on. Every fix therefore carries an explicit profile scope — see "Deployment Profiles" below, which governs Phases 1–4.

Bug reports are written by another agent that operates directly on a deployed product's generated code (e.g. on a staging server). That agent **cannot see the Datrix toolchain, generators, or app definitions** — it can only patch generated output in place. **Every fix it describes is a temporary patch that will be overwritten on the next regeneration.** Your job is to make the fix permanent in the source that survives regeneration: the **app definition** or the **generator/template**. Treat the report's "Files Modified" / "What Was Changed" sections as diagnostic evidence of the correct output, not as completed work — do not skip or classify a bug as already-resolved just because the deployed patch currently works; it vanishes on the next regeneration.

## How to Invoke

```
/fix-bug-report D:\<Product>\.bug-report\2026-05-29-some-bug.md
/fix-bug-report D:\<Product>\<product>-platform\.bug-report\bug-1.md D:\<Product>\<product>-platform\.bug-report\bug-2.md
/fix-bug-report D:\<Product>\<product>-platform\.bug-report\*.md
```

The argument is one or more absolute paths to bug report markdown files (or a glob pattern).

## Project Layout — two product shapes, one derivation

A customer/product consumes the Datrix toolchain from outside it. There is **no `datrix-projects` container** and no symlink/junction bridging — that model was retired. Derive every concrete path from the bug-report argument; never hardcode a customer name or a `datrix-projects\...` path.

**Products come in two shapes, and a product may move from the first to the second.** Decide which one you are in before deriving anything — the derivation differs, and using the wrong one lands you on a directory that does not exist or, worse, on the ops repo instead of the DSL.

- **Shape 1 — single product repo.** One self-contained git repo holds the DSL, the generated trees, the wrapper scripts and `.bug-report\`.
- **Shape 2 — sibling repos under a workspace.** An **unversioned workspace directory** holds several sibling git repos — the same shape Datrix itself uses under `$env:DATRIX_HOME`. The DSL, the generated output, and the scripts/docs/bug-reports each live in their **own repo**, so the "product root" is a directory that is *not* a repo, and the repo holding `.bug-report\` is *not* the DSL repo.

| Role | Shape 1 — single repo | Shape 2 — sibling repos |
|---|---|---|
| **Datrix toolchain** | `$env:DATRIX_HOME` (default `D:\datrix`) | same |
| **Product root** | the directory holding `.bug-report\` — a git repo | the **workspace** directory holding the sibling repos — **not** a git repo |
| **Bug reports (input)** | `<product-root>\.bug-report\` | `<workspace>\<name>-platform\.bug-report\` — in the ops/platform repo. Gitignored, local-only, in both shapes. |
| **App definition (DSL)** | `<product-root>\<name>-backend\` | `<workspace>\<name>-backend\` — **its own repo**. `.dtrx` / `.dcfg` source of truth; app-definition fixes go here. |
| **Generated code (output)** | `<product-root>\generated\<profile>\` | `<workspace>\<name>-generated\<profile>\` — **its own repo, with no `generated\` wrapper level**. Auto-generated; **never edit**. |
| **Generation wrapper** | `<product-root>\scripts\<profile>\generate.ps1` | `<workspace>\<name>-platform\scripts\<profile>\generate.ps1` — same repo as `.bug-report\`. Local-only; deploys nothing. |
| **Migration ledger** | `<dsl-root>\.datrix\rdbms-migrations\` | same — it follows the **DSL root**, so under Shape 2 it is tracked inside the `*-backend` repo, never in the generated repo |

**Derive it, in this order, and stop on the first that resolves:**

1. `<report-repo>` = the directory holding the `.bug-report\` directory the report sits in.
2. **Shape 1** if `<report-repo>` itself contains a `*-backend` directory holding the DSL (`system.dtrx` / `.dtrx` files). Product root = `<report-repo>`.
3. **Shape 2** if the *parent* of `<report-repo>` contains a `*-backend` **sibling** holding the DSL. Workspace = that parent; DSL root = the `*-backend` sibling; generated root = the `*-generated` sibling; scripts root = `<report-repo>\scripts\`.
4. **Neither resolves → stop and say what you looked for and where.** A plausible-but-wrong product root is how a fix lands in the ops repo and the DSL is never touched. Read the report's "Files Modified" paths and the actual directory listing; do not guess.

**A report's paths are the *deployed* server's paths, not necessarily yours.** The remote tree keeps the `generated/<profile>/` layout even for products that no longer have a `generated\` directory locally, so a report saying `generated/devd/services/...` maps to `<workspace>\<name>-generated\devd\services\...` under Shape 2. Map it; do not assume the string is a local path.

---

## Deployment Profiles — Every Fix Has a Profile Scope

**A product declares several deployment profiles (environments), and the bug reports you are given come from more than one of them.** Enumerate the product's actual profile set from the **scripts root**: a profile is a subdirectory holding a `generate.ps1`. Cross-check against the generated root (`<product-root>\generated\` under Shape 1, the `*-generated` repo under Shape 2) — but the two sets are **not** required to match: the generated root holds a tree only for profiles that have actually been generated on this machine, so a profile with a wrapper and no tree is normal and is **not** evidence the profile does not exist. Never assume a set, a count, or which profiles a given product runs.

**Identify each report's profile before triaging it.** Reports name it in the filename segment and/or a `Platform:` / `Environment:` field; failing that, the `generated/<profile>/...` paths under "Files Modified" name it (that is the deployed server's layout — map it to the local tree per "Project Layout"). A report carrying its own generated-tree sweep already names the other profile trees it found the pattern in — read that as evidence and confirm it; do not accept it on faith and do not skip doing your own.

**Before editing anything, write down two sets:**

1. **Exhibiting** — the profiles where the defect is actually present, proven by reading each profile's emitted artifact. Not "the profile that reported it".
2. **Reached** — the profiles your edit will change: derived from the `extends` graph for an app-definition fix, or from which generator package emits the artifact and which profiles target that platform for a generator fix.

The fix is correct only when **Reached ⊇ Exhibiting**, and every profile in **Reached − Exhibiting** is one you intended to touch and have verified is still correct. Under-reach ships a fix that leaves a profile broken; over-reach breaks a profile that was fine. Both are the same defect: an unstated profile scope.

### App-definition fixes — the inheritance graph is the hazard

`.dcfg` files declare one `base { }` block plus `profile <name> as "<alias>" extends <parent> { }` blocks.

- **Editing `base` reaches every profile that does not override that key.** Fixing one profile's symptom there is exactly how the other profiles change silently.
- **A profile may extend another profile**, not just `base` — so editing the parent moves the child with it.
- **The inheritance direction is per file, not global.** The same two profile names can be parent→child in one `.dcfg` and child→parent in another. An edge you learned in one file is a *hypothesis* about the next one: read the `extends` clause in the file you are about to edit, every time.
- **Merge semantics decide reach:** nested blocks deep-merge, **lists replace wholesale**, and `key = null` deletes an inherited block. Adding an element to a list in `base` does **not** reach a profile that redeclares that list — that profile needs its own entry, or the fix silently misses it.

This is not hypothetical: a value tuned for one environment has already become the silent default of the environment extending it, because the `extends` clause went unread.

### Generator fixes — profiles do not share a target

Profiles differ in `deployment { runtime, provider }`, so they exercise **different generator packages**. A platform package reaches only the profiles targeting that platform; `datrix-common` / `datrix-codegen-common` reach all of them. Read each profile's deployment block and build the mapping — that mapping *is* the reach set, computed rather than guessed.

It cuts both ways, and both directions are your work:

- The same emitter feeds other profiles → the defect is **latent in profile trees nobody reported against**. Found it, you fix it — for every profile the emitter reaches.
- A shared-layer fix reaches profiles whose artifact was already correct → prove those trees still are.

### Verification is per profile, on the artifact

Static first (CLAUDE.md's ladder): compute the reach set from the `extends` graph and the emitter, then regenerate **only the profiles in that set**, each with its own wrapper. Regeneration is local and deploys nothing.

```
powershell -File "<scripts-root>/<profile>/generate.ps1"
```

Then census the result. **Census every repo the run can write**, which is shape-dependent — a census that covers one repo of a split product silently misses the other:

```
# Shape 1 — one repo holds everything
git -C <product-root> status --porcelain generated/
git -C <product-root> diff --stat -- generated/

# Shape 2 — the generated tree and the DSL are separate repos
git -C <generated-root> status --porcelain
git -C <generated-root> diff --stat -- <profile>/
git -C <dsl-root>       status --porcelain .datrix/    # ledger revisions appended by the run
git -C <dsl-root>       diff --stat
```

- Every profile tree appearing in that diff must be one you intended to change. **An unexpected profile tree in the diff IS the "you broke another profile" signal** — caught statically, before anything is deployed.
- For each **exhibiting** profile: parse/grep the specific artifact and show the defect is gone.
- For each **reached-but-not-exhibiting** profile: show the artifact is unchanged, or changed exactly as intended.

**"I fixed it in `base`" is not evidence.** A profile that overrides that key is still broken. Per-profile artifact output, or the fix is unproven — this is the "fix the class, not the instance" rule applied along the profile axis.

**Never deploy, sync, or run a release/provision script** — product repos require per-instance human approval for those, and nothing in this skill's verification needs them. Generation wrappers, `status`/`verify` scripts, and reads are the whole toolkit.

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
   - **The reporting profile**, and any other profile trees the report's own sweep names

3. **Determine each bug's profile scope** — the `Exhibiting` and `Reached` sets from "Deployment Profiles" above. Read the emitted artifact in *every* profile tree the emitter or config key can reach before you call a set complete; the reporting profile is a starting point, not the answer. Classification (A/B/C/D) and profile scope are independent axes — every bug needs both.

4. **Classify each bug into one of three categories:**

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

5. **Group related bugs:**
   - If multiple bugs share the same generator root cause (e.g., several bugs all caused by `.to_string()` emission), group them under a single fix
   - Note which individual bug reports will be resolved by each grouped fix
   - **Group across profiles too:** two reports from two profiles with one root cause are one fix with a union `Exhibiting` set — not two fixes, and never one fix that quietly serves only the profile you read first
   - Grouping reduces redundant work and prevents conflicting edits

6. **Plan execution order:**
   - App definition fixes first (Category A) — prioritize fixing the product's app
   - Generator fixes second (Category B) — only when a systematic generator defect is confirmed
   - Combined fixes (Category C) — app definition part first, then generator part only if confirmed necessary
   - Within each category, fix higher-severity bugs first
   - **Batch by reach:** order fixes so each profile's tree is regenerated once at the end, after every edit that reaches it — not once per bug

7. **End-of-phase report:**

   ```
   TRIAGE COMPLETE

   Bug reports analyzed: {N}
   Product shape: {single repo | sibling repos}   (derived per "Project Layout")
   Profiles in this product: {profile-1, profile-2, …}   (wrappers in the scripts root; trees present in the generated root: {…})

   Category A (App Definition Fix): {count}
     - {bug-filename}: {title} — reported on: {profile}
       exhibiting: {profiles} | reached by fix: {profiles} | change: {what to modify in .dtrx/.dcfg}

   Category B (Generator/Template Fix): {count}
     - {bug-filename}: {title} — reported on: {profile}
       exhibiting: {profiles} | reached by fix: {profiles} | change: {generator/template to fix}

   Category C (Both): {count}
     - {bug-filename}: {title} — exhibiting: {profiles} — generator: {fix} + app: {fix}

   Category D (Cannot Fix): {count}
     - {bug-filename}: {title} — reason: {why it can't be fixed here}

   Grouped root causes: {count unique fixes} (covering {N} individual bugs)

   Execution plan:
   1. [B] {generator fix description} — resolves: {bug-file-1}, {bug-file-2} — regenerates: {profiles}
   2. [A] {app fix description} — resolves: {bug-file-3} — regenerates: {profiles}
   ...

   Profiles to regenerate (union of reach sets): {profiles}
   ```

8. **Scope gate:**
   - If total scope exceeds **6 distinct root causes** → STOP and propose splitting into batches
   - If any single fix touches **more than 5 files** → flag it and ask for confirmation before proceeding
   - A fix reaching several profiles is **one** root cause, not one per profile — profile count never inflates this gate, and never licenses fixing a subset

9. **If confident** → proceed to Phase 2
10. **If NOT confident** (ambiguous classification, unclear root cause, undetermined profile scope) → **keep investigating.** Unclear root cause is a state of your knowledge, not a blocker — read the generator, the AST, and the emitted output until the classification is forced by evidence. Escalate (`_shared/decision-escalation-protocol.md`) if a genuine architectural fork emerges. Present triage and wait **only** for a real B2 (two defensible designs, expensive to reverse) — and bring **your recommendation**, not a bare question.

---

### Phase 2: Fix (Write Code)

Process fixes in the planned order from Phase 1 (app definition fixes first).

#### For App Definition Fixes (Category A — do these first):

1. **Read the bug report's Summary and What Was Changed sections** to understand what's wrong
2. **Read the relevant `.dtrx` or `.dcfg` files** in the product's app definition directory (`<dsl-root>`, derived per "Project Layout")
3. **Read the profile structure of the exact file you are about to edit** — its `base { }` block and every `profile … extends …` clause in it. The inheritance direction in a neighbouring `.dcfg` tells you nothing about this one. From that, decide where the edit belongs:
   - **In `base`** — only when the corrected value is right for every profile inheriting it. List those profiles and confirm none of them overrides the key with something the fix must also change.
   - **In one profile block** — when the value is environment-specific. Then check every *other* exhibiting profile: each needs its own edit, and a profile extending the one you edited inherits it whether you meant that or not.
   - **In a parent profile** — only with the child profiles' inherited result stated explicitly.
4. **Implement the fix** in the app definition:
   - Correct API URLs, field mappings, configuration values
   - Add missing validators, constraints, or integration settings
   - Ensure the change follows Datrix DSL syntax
   - Remember lists **replace** rather than merge: a list edit in `base` misses every profile that redeclares that list
5. **Read surrounding context** in the `.dtrx` file to ensure consistency with adjacent definitions

#### For Generator/Template Fixes (Category B — only when a generator defect is confirmed):

1. **Read the "Implications for the Datrix Code Generator" section** — this describes the root cause and often suggests the fix approach
2. **Locate the generator/template code** under `$DATRIX_HOME`:
   - Search in `datrix-codegen-python`, `datrix-codegen-typescript`, `datrix-codegen-common`, etc.
   - Look for the template (`.j2`) or generator (`.py`) file mentioned or implied
   - Use the "Files Modified" section in the bug report — the generated file path reveals which generator produced it
3. **Read the affected generator/template code**
4. **Establish the emitter's profile reach before editing it.** Map each profile's `deployment { runtime, provider }` to the package that owns this emitter. A platform package reaches only the profiles targeting it; a shared layer reaches all of them. Then go read the corresponding artifact in **each** reached profile's tree:
   - Present and wrong there too → that profile joins `Exhibiting`; the one fix covers it, and you verify it there.
   - Present and correct there → the fix must keep it correct; that tree is a regression surface, not a bystander.
   - Absent there → say so, with the reason (that profile does not use the feature), rather than leaving the tree unmentioned.
5. **Implement the fix:**
   - Fix the root cause in the generator/template, NOT in generated code
   - Follow all code standards (full type hints — never run a type-checker, cognitive complexity <=15)
   - Check for logic map markers (`@canonical`, `@pattern`, `@boundary`, `@invariant`) before modifying
   - Place it at the most target-agnostic layer that can own it, and never branch on a profile name — profiles are a product's config, invisible to the generator, which sees only runtime/provider/target
6. **If the fix affects a codegen package with its own fix skill**, delegate. Every codegen package has one, and the name is derived — `datrix-codegen-<lang>` → `/fix-codegen-<lang>`:
   - `datrix-codegen-python` → use `/fix-codegen-python` patterns
   - `datrix-codegen-typescript` → use `/fix-codegen-typescript` patterns
   - `datrix-codegen-dotnet` → `/fix-codegen-dotnet`, `datrix-codegen-java` → `/fix-codegen-java`, and so on for any codegen package

#### After Each Fix:

```
CHECKPOINT — Bug: {title}
Category: {A|B|C}
Status: FIXED
Changed: {file:line} — {what changed}
Exhibiting profiles: {list}    Reached by this edit: {list}
Reached − exhibiting: {list} — intended because {reason}
Bug reports resolved by this fix: {list of bug filenames}
```

#### Profile Gate (after the last edit that reaches a given profile):

Regenerate each profile in the union of the reach sets with its own wrapper, then produce the census and the per-profile artifact evidence described in "Deployment Profiles → Verification is per profile, on the artifact". Paste the command and its output — a regeneration you did not run, or a profile tree you did not look at, is an unverified claim.

The gate passes only when all three hold:

1. Every exhibiting profile's artifact shows the defect gone.
2. The generated-tree census (every repo the run can write — see "Verification is per profile, on the artifact") names no profile tree you did not intend to change.
3. Every reached-but-not-exhibiting profile's artifact is unchanged, or changed exactly as intended and stated.

A profile that fails any of the three is unfinished work, not a footnote — go fix it. Partial-profile completion is the same dodge as "out of scope".

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
   **Profiles exhibiting**: {list}
   **Profiles reached by the fix**: {list}

   ### Changes Made

   | File | Changes |
   |------|---------|
   | `{file-path}` | {description of change} |

   ### Per-Profile Verification

   | Profile | Regenerated | Artifact checked | Result |
   |---------|-------------|------------------|--------|
   | `{profile}` | yes/no — {why not} | `{generated-root}/{profile}/{path}` | defect gone / unchanged as intended / feature absent |

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
1. {file:line} — {what changed} — resolves: {bug titles} — profiles: {exhibiting} of {reached}

App definition fixes:
1. {file:line} — {what changed} — resolves: {bug titles} — profiles: {exhibiting} of {reached}

Per-profile verification:
- {profile}: regenerated {yes/no} — {artifact}: {defect gone | unchanged | changed as intended}

Generated-tree census (one line per repo the run can write):
  git -C {repo} diff --stat …   →  {profile trees touched}
  Ledger delta in {dsl-root}\.datrix\: none | {revisions appended}
  Unintended profile trees in the diff: none | {list — and what you did about it}

Fixed bug reports (absolute paths):
- {bug-report-dir}\{bug-filename}: {title} — Resolved

Unresolved bug reports (absolute paths):
- {bug-report-dir}\{bug-filename}: {title} — {reason}

Repositories with changes:
- {repo-or-package-name}: {files changed}
```

---

## Runaway Fix Detection

See `d:\datrix\.claude\skills\_shared\fix-conventions.md` (also applies per-bug: more than 3 tool-call rounds per bug without completing is a runaway signal here too).

---

## Anti-Patterns

- **NO fixing generated code directly** — fix generators/templates or app definitions; everything under the generated root is overwritten on regeneration, whether that root is `<product-root>\generated\` or a `*-generated` repo of its own
- **NO deriving the product root by assuming a shape** — the repo holding `.bug-report\` is the product root in Shape 1 and the *ops* repo in Shape 2, where the DSL is a sibling. Run the "Project Layout" derivation and stop if neither branch resolves
- **NO hardcoding customer names or `datrix-projects\...` paths** — that container was retired; derive product paths from the bug-report argument and `$DATRIX_HOME`
- **NO editing without a stated profile scope** — the `Exhibiting` and `Reached` sets are written down before the edit, not reconstructed after it
- **NO editing a `base` block to cure one profile's symptom** without listing every profile that inherits the key and confirming each one wants the new value
- **NO carrying an inheritance edge between files** — `extends` runs in whichever direction *this* `.dcfg` declares; read the clause in the file you are editing, every time
- **NO stopping at the reporting profile** — the same emitter or config key feeding another profile makes that profile yours too; a latent copy is a defect, not a coincidence
- **NO "fixed in `base`, so all profiles are fixed"** — a profile overriding that key is still broken. Per-profile artifact evidence, or it is unproven
- **NO branching on a profile name inside a generator** — profiles are product config; the generator sees runtime/provider/target only
- **NO regenerating profiles outside the reach set** and **NO deploy/sync/release/provision of any profile** — regeneration wrappers and reads are the whole verification toolkit here
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