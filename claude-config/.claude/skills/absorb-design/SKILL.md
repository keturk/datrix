---
description: Absorb a design document into existing docs across all repos, replace all references, and delete the source
model: claude-sonnet-5-5
effort: high
---

# Absorb Design Document

Transfer all knowledge from a design document into the appropriate existing documentation files across all datrix-* repos' docs folders, replace all references to the source file, and delete it. No tasks, no decisions — purely a knowledge-transfer operation.

## When to Use

- A design document has been approved and needs its content distributed to official docs
- User says "absorb", "distribute this doc", or "merge this into our docs"
- User wants to eliminate a standalone design doc by folding it into the canonical docs (this is the default — source is deleted after transfer)
- After `/operationalize-design` if only the doc-transfer + cleanup phases are needed

## How to Invoke

```
/absorb-design

DOCUMENT: d:\datrix\datrix\docs\designs\some-design.md
```

With options:
```
/absorb-design

DOCUMENT: d:\datrix\datrix\docs\designs\some-design.md
DRY RUN: true
KEEP SOURCE: true   # Override: do NOT delete the source after transfer
VERIFIED: D:\datrix\.tmp\verify-proven-some-design.md   # verify's PROVEN replies: the licence to delete
```

## Prereqs
Read first: CLAUDE.md, MEMORY.md. Also read the design document itself in full before proceeding.

## Inputs

| Parameter | Required | Description |
|-----------|----------|-------------|
| DOCUMENT | Yes | Path to the design document to absorb |
| DRY RUN | No | If `true`, produce the transfer plan but do not write any files |
| KEEP SOURCE | No | If `true`, preserve the source document after transfer (default: delete source and replace all references) |
| VERIFIED | No | A file holding the `/verify-implementation` replies for this DOCUMENT that end `Design conformance: PROVEN`. `implement-design.ps1`, `implement-design-direct.ps1`, `/implement-design` and `/implement-design-direct` pass it. It is the licence to delete (see "Deletion licence") |

## Deletion licence

Deleting the source removes the one document a conformance check measures against, so a design that describes work to implement is deleted only when that work is proven. Decide this once, before Phase 1, from these in order:

1. **VERIFIED is given.** Read the file. If its last `Design conformance:` line reads `PROVEN` and the report names this DOCUMENT, the design is proven: absorb and delete it (unless KEEP SOURCE). The design's own `Status:` line and wording ("Draft", "Not yet operationalized", "red tests", "unresolved defects", "needs a fix") describe the state *before* it was implemented and never outweigh the proof: the direct path never rewrites `Status:` (only `/task-orchestrator` does). Do not ask. If the file is missing, ends `INCOMPLETE`, carries no verdict, or names another design, the proof failed: transfer nothing, delete nothing, and report that verify must run again.
2. **No VERIFIED, and the `Status:` line reads `Implemented`** — proven: absorb and delete.
3. **No VERIFIED, and the document describes work not shown to be implemented** — run Phases 1–3 and the reference cleanup, keep the source, and ask Jon in one line whether to delete it.
4. **The document is knowledge only** (no implementation scope: a decision record, a reference write-up) — absorb and delete; there is nothing to prove.

A requirement in the design is never "task-level, not docs" grounds to keep the source once rule 1 or 2 holds: proven means those requirements are met in code.

## Target Documentation Folders

Discover docs folders dynamically — do not rely on a hardcoded list (a fixed table
silently drifts out of sync as repos are added, e.g. `datrix-codegen-k8s`):

```bash
ls -d d:/datrix/datrix*/docs/
```

Match each knowledge unit to the repo whose scope it falls under (language/architecture
→ `datrix`; CLI → `datrix-cli`; per-provider/language generator → the matching
`datrix-codegen-*`; shared codegen utilities → `datrix-codegen-common`; shared
framework/contributing rules → `datrix-common`; extension system → `datrix-extensions`;
parser/AST/grammar → `datrix-language`).

---

## Pipeline

### Phase 1: Analyze — Map Content to Targets

**Goal:** Read the design document and produce a transfer plan.

1. Read the design document in full
2. Break it into discrete knowledge units (sections, decisions, patterns, API contracts, examples)
3. For each unit, determine:
   - **Target repo** — which datrix-* repo owns this knowledge
   - **Target file** — which existing file it belongs in (or if a new file is truly needed)
   - **Target section** — where in the file to insert or update
   - **Transfer action** — one of: `APPEND` (add new section), `UPDATE` (replace existing content), `CREATE` (new file, only when no existing file fits)
4. Classify any content that does NOT belong in docs:
   - Implementation details → skip (belongs in code/docstrings)
   - Transfer **content**, never a pointer back to the design doc — the source is being deleted and is `.gitignored`. Target docs must not cite the design doc's number, filename, or ID (execution-contract §7A).
   - Task-level instructions → skip (belongs in task files)
   - Discussion/rationale that's already resolved → skip

**End-of-phase output:**

```
TRANSFER PLAN:

Source: {document path}
Knowledge units: {N}
Skipped units: {N} (implementation detail / task-level / discussion)

Transfers:
1. "{unit title}" → {target-file} [{action}] at section "{section heading}"
2. "{unit title}" → {target-file} [{action}] at section "{section heading}"
...

Skipped:
- "{unit title}" — Reason: {why it doesn't belong in docs}
```

**If DRY RUN is true** → output the plan and STOP.

**If any unit has no clear target** → flag it and ask the user:
```
Cannot determine target for:
- "{unit title}" — could go in {option A} or {option B}
Which do you prefer?
```
WAIT for user input before proceeding.

**If confident in all targets** → proceed to Phase 2.

---

### Phase 2: Transfer — Write Content Into Target Docs

**Goal:** Execute the transfer plan from Phase 1.

For each transfer, in order:

1. **Read the target file** (or confirm it doesn't exist for CREATE actions)
2. **Adapt the content** to match the target file's existing style:
   - Match heading levels, formatting, code block style
   - Use the same voice and level of detail as surrounding content
   - Maintain the target file's table of contents if it has one
3. **Write the content:**
   - `APPEND` — add at the appropriate location (not just the end)
   - `UPDATE` — replace the outdated section with the new content
   - `CREATE` — write a new file following the conventions of sibling docs in the same folder
4. **Track the change** — record what was written and where

**Conflict resolution rules:**
- Design document content WINS over existing docs (no backward compatibility)
- If the design CONTRADICTS existing content → replace the old content
- If the design ADDS to existing content → integrate at the right location
- If the design DUPLICATES existing content → skip (don't create redundancy)

**End-of-phase output:**

```
TRANSFERS COMPLETE:

Files modified:
1. {path} — {action}: "{section}" ({N} lines)
2. {path} — {action}: "{section}" ({N} lines)
...

Files created:
1. {path} ({N} lines)

Skipped (already present):
1. "{unit}" — already documented in {path}

Total: {N} files modified, {M} files created
```

---

### Phase 3: Verify — Ensure Complete Transfer

**Goal:** Confirm nothing was lost.

1. Have a local model check each section of the design against the docs you wrote to:
   ```bash
   powershell -File "d:/datrix/datrix/scripts/skill/skill-assist.ps1" absorb-transfer --design "{document path}" --target <each target file from Phase 2>
   ```
   `d:\datrix\.tmp\assist\transfer-{stem}.md` gives each section PRESENT / PARTIAL / MISSING with the target lines that carry it (citations checked against what the model was sent). Exit 2 means at least one section is partial or missing; exit 3, no local model answered (check every unit by hand).
2. Read the PARTIAL and MISSING sections against the targets yourself and settle each; spot-check PRESENT ones by opening their cited lines
3. Check for any content in the design document NOT covered by the plan:
   - Footnotes, appendices, inline notes
   - Diagrams or ASCII art
   - Links to external resources

**If all content is accounted for** → proceed to Phase 4.

**If content was missed:**
```
INCOMPLETE TRANSFER:

Missing content:
- "{description}" from line {N} — not transferred because: {reason}

Options:
1. Transfer it to {suggested target}
2. Skip it (explain why it's not needed)
3. Keep source document (do not delete)
```
WAIT for user decision.

---

### Phase 4: Cleanup — Replace References and Delete the Source

**Goal:** Remove every reference to the design document across the repo and delete it.

1. **Search for all references** to the source document with the script:
   ```bash
   powershell -File "d:/datrix/datrix/scripts/skill/skill-assist.ps1" absorb-references --design "{document path}"
   ```
   It lists every line in the package repos that names the document's file name, stem, title, or number in a design-reference form ("design NNN", "design/NNN", "design doc NNN"), across `.md`, `.py`, `.ts`, `.js`, `.json`, `.yaml`, `.toml`, `.ps1`, `.j2`, `.dtrx` and similar files. Task folders (`.tasks`) are not searched. Exit 0 = no reference; exit 2 = the listed lines need handling.
2. **Replace or remove each reference:**
   - If a reference points readers to the design doc for details → replace with a pointer to the target doc(s) where the content now lives
   - If a reference is a backlog/index entry → remove the line entirely
   - If a reference is in CLAUDE.md or MEMORY.md → update or remove as appropriate
3. **If KEEP SOURCE is true** → preserve the source document and skip deletion
4. **Otherwise (default)** → delete the source design document when the deletion licence holds (rules 1, 2 or 4); under rule 3, keep it and ask
5. **Verify** — run `absorb-references` again **before** step 4 deletes the source (it reads the document for its title): it must exit 0 (zero remaining references)

**End-of-phase output:**

```
CLEANUP:

References found: {N}
References replaced:
- {file} — replaced pointer to {new target}
References removed:
- {file} — removed backlog/index entry

Source deleted: {path}
Remaining references: 0
```

Or, if KEEP SOURCE was set:

```
CLEANUP:

References found: {N}
References updated:
- {file} — {action taken}

Source preserved: {path}
Remaining references: 0 (all updated to point to new locations)
```

---

## Final Summary

```
ABSORPTION COMPLETE

Source: {document path}
Knowledge units transferred: {N}
Knowledge units skipped: {N} (with reasons)
Files modified: {N}
Files created: {M}
References replaced/removed: {N}
Source document: DELETED / PRESERVED (if KEEP SOURCE flag used)

Modified files:
- {path 1}
- {path 2}
...
```

## Anti-Patterns

- **NO transferring without reading the target first** — always read the target file before writing to it
- **NO dumping content at the end of a file** — place content in the correct section
- **NO creating new standalone docs when existing docs cover the topic** — integrate, don't fragment
- **NO preserving the source document's structure in the target** — adapt to the target's style
- **NO preserving the source document** (unless KEEP SOURCE flag is explicitly set) — the default is to delete after transfer
- **NO leaving dangling references** to the deleted source — grep the entire repo and replace/remove every mention
- **NO transferring implementation details into docs** — those belong in code
- **NO duplicating content across multiple targets** — each unit goes to exactly one place
- **NO skipping content silently** — every skipped unit must be reported with a reason
- **NO modifying code files** — this skill only touches documentation files
- **NO workarounds** — don't steer around issues, don't paper over them. **Fix the root cause, wherever it lives** (CLAUDE.md rule). This is not a binary between "workaround" and "stop": the third option — do the real work — is the default. Stopping is licensed only by a proven B1–B4 blocker with the four-part proof (`.claude/skills/_shared/execution-contract.md`).
- **NO dodging** — "out of scope", "pre-existing", "categorically behavioral", "should be tracked separately", "not my package" are **not** blockers; they are the work. A `SubagentStop` hook greps reports for this vocabulary.
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
