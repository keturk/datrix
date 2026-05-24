---
description: Absorb a design document into existing docs across all repos, replace all references, and delete the source
model: sonnet
disable-model-invocation: true
---

# Absorb Design Document

Transfer all knowledge from a design document into the appropriate existing documentation files across all 14 repo doc folders, replace all references to the source file, and delete it. No tasks, no decisions — purely a knowledge-transfer operation.

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
```

## Prereqs
Read first: CLAUDE.md, MEMORY.md. Also read the design document itself in full before proceeding.

## Inputs

| Parameter | Required | Description |
|-----------|----------|-------------|
| DOCUMENT | Yes | Path to the design document to absorb |
| DRY RUN | No | If `true`, produce the transfer plan but do not write any files |
| KEEP SOURCE | No | If `true`, preserve the source document after transfer (default: delete source and replace all references) |

## Target Documentation Folders

These are the 14 documentation locations where content may be placed:

| Repo | Path | Scope |
|------|------|-------|
| datrix | `d:\datrix\datrix\docs` | Language, architecture, user guides |
| datrix-cli | `d:\datrix\datrix-cli\docs` | CLI commands, workflows |
| datrix-codegen-aws | `d:\datrix\datrix-codegen-aws\docs` | AWS generator (RDS, Aurora, MSK, etc.) |
| datrix-codegen-azure | `d:\datrix\datrix-codegen-azure\docs` | Azure generator (Flexible Server, Event Hubs, etc.) |
| datrix-codegen-common | `d:\datrix\datrix-codegen-common\docs` | Shared codegen utilities |
| datrix-codegen-component | `d:\datrix\datrix-codegen-component\docs` | Component-level generator |
| datrix-codegen-docker | `d:\datrix\datrix-codegen-docker\docs` | Docker/Compose generation |
| datrix-codegen-k8s | `d:\datrix\datrix-codegen-k8s\docs` | Kubernetes manifest generation |
| datrix-codegen-python | `d:\datrix\datrix-codegen-python\docs` | Python/FastAPI generator |
| datrix-codegen-sql | `d:\datrix\datrix-codegen-sql\docs` | SQL schema generation |
| datrix-codegen-typescript | `d:\datrix\datrix-codegen-typescript\docs` | TypeScript/NestJS generator |
| datrix-common | `d:\datrix\datrix-common\docs` | Shared framework, APIs, contributing rules |
| datrix-extensions | `d:\datrix\datrix-extensions\docs` | Extension system |
| datrix-language | `d:\datrix\datrix-language\docs` | Parser, AST, grammar, syntax reference |

---

## Pipeline

### Phase 1: Analyze — Map Content to Targets

**Goal:** Read the design document and produce a transfer plan.

1. Read the design document in full
2. Break it into discrete knowledge units (sections, decisions, patterns, API contracts, examples)
3. For each unit, determine:
   - **Target repo** — which of the 14 repos owns this knowledge
   - **Target file** — which existing file it belongs in (or if a new file is truly needed)
   - **Target section** — where in the file to insert or update
   - **Transfer action** — one of: `APPEND` (add new section), `UPDATE` (replace existing content), `CREATE` (new file, only when no existing file fits)
4. Classify any content that does NOT belong in docs:
   - Implementation details → skip (belongs in code/docstrings)
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

1. Re-read the original design document
2. For each knowledge unit in the transfer plan, confirm it exists in the target
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

1. **Search for all references** to the source document across the entire `d:\datrix` tree:
   - File paths (exact and relative variants, forward- and back-slash)
   - Document title / ID (e.g. `ARCH-16`, the filename stem)
   - Grep all `.md`, `.py`, `.ts`, `.json`, `.yaml`, `.toml` files
2. **Replace or remove each reference:**
   - If a reference points readers to the design doc for details → replace with a pointer to the target doc(s) where the content now lives
   - If a reference is a backlog/index entry → remove the line entirely
   - If a reference is in CLAUDE.md or MEMORY.md → update or remove as appropriate
3. **If KEEP SOURCE is true** → preserve the source document and skip deletion
4. **Otherwise (default)** → delete the source design document
5. **Verify** — re-grep for the document path and ID to confirm zero remaining references

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
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
