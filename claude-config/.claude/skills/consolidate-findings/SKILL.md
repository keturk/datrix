---
model: claude-sonnet-5-5
effort: medium
description: Tidy the findings inbox at d:\datrix\reports\finding in place — group related findings into themes (one seam, subsystem or defect class), write each theme as one numbered consolidated-NNN-<slug>.md file holding every defect of that theme as its own section, and delete the superseded sources. Keeps no archive and no register; the folder itself is the result. Use when Jon asks to "consolidate findings", "merge the findings", "clean up reports/finding", or runs /consolidate-findings.
---

# Consolidate Findings

Agents write one findings file per issue into `d:\datrix\reports\finding\` and are told not to
search the folder first (execution-contract §5A), so the folder fills with duplicates, overlapping
reports and umbrella files listing many defects. This skill is the "merged later" step: it leaves
the folder holding **one `consolidated-NNN-<slug>.md` file per theme** — a group of related
findings that one person would fix and review together.

A theme is **not** a single defect. A consolidated file holds as many distinct defects as the theme
has, each stated in full as its own numbered section. Grouping is by relatedness; it never shortens
or blends the defects inside.

This is a cleanup, not a record. It produces no consolidated register, no index, no ledger, and no
archive. Superseded files are deleted, not copied anywhere. The only output is the folder.

**The one rule: no defect is lost.** Every defect stated in a file you delete must be stated in a
section of a file that remains, with its evidence and every `file:line`. Duplicates collapse into
one section; distinct defects stay distinct sections, side by side inside their theme.

This skill only tidies findings files. It fixes no code, files no tasks, and edits no repo.

## How to invoke

```
/consolidate-findings
```

## Inputs

Every `*.md` file directly in `d:\datrix\reports\finding\`. List them with
`Get-ChildItem d:\datrix\reports\finding -File -Filter *.md | Sort-Object Name`.

- **Raw files** — agent-written `YYYYMMDD-HHMMSS-<slug>.md`: the inbox.
- **Consolidated files** — `consolidated-NNN-<slug>.md`: results of earlier runs, read so new
  findings can be merged into them.

If there are no raw files, say so in one line and stop.

## Phase 1 — Read everything

Read every file **in full** with `Read`. Do not skim, grep for headings, or sample — an umbrella
file can hold twenty defects under one title, and a heading scan finds one. The files are small;
read them yourself and do not dispatch subagents.

## Phase 2 — Extract atomic findings

Turn each file into one or more **atomic findings**: one defect, one root cause. For each, note:
title (one line, the defect — not the symptom list), what is wrong and the evidence, every
`file:line` cited (verbatim), the impact, a direction only if the source gave one, severity only if
the source gave one, and the file name(s) it came from.

**Splitting.** A file listing several independent defects (numbered residual lists, "also in this
file" sections) becomes several atomic findings, so each can be grouped with the findings it belongs
with. Keep a sub-item with its parent only when it has the same root cause. Splitting is for
grouping: the pieces may land in different themes, or all in one.

**Carry, don't rewrite.** Keep the source's evidence, citations and wording of the defect. Shorten
prose; never change a claim, a path, a line number, or a severity the source stated. A guess the
source labelled as a guess stays labelled.

**Leave out what must not be in a shareable file:** secrets, credentials, and customer or project
domain names. If a source contains one, describe the defect without it and say in your reply that
the source had to be redacted.

## Phase 3 — Group into themes, collapse duplicates

**The failure this phase exists to prevent:** renaming each raw file to `consolidated-NNN-…`, or
merging only findings that say the identical thing. Both leave a folder as long as the inbox. A real
inbox holds clusters of *related* findings — the same seam seen from the python side, the
typescript side and a test side; five different symptoms of one broken contract; a subsystem with a
handful of unrelated small defects. They belong in one file.

**Step 1 — build the index first.** Before writing any file, list every atomic finding (including
those in existing `consolidated-*` files) as one line: `source file | seam or construct | owning
package(s) | one-clause defect`. Sort and group the lines by seam, construct and owning area, not by
file name or date. Read the grouped index top to bottom and name each theme.

**Step 2 — a theme is anything one person would fix and review together.** Findings belong to one
theme when any of these holds:

- They share a seam, construct or contract (serverless handler parameters, docker config-store
  environment, API-key verification, gateway edge auth, redis connection) — even if the defects
  differ.
- They are the same defect seen from different targets, layers, tests or dates.
- One pins, tests or documents the other.
- They sit in the same generator, template family or script, and fixing one means touching the
  code of the other.
- One is a sub-case or consequence of another.

Different severity, kind (bug, test gap, doc drift) or target does **not** separate them. Do not
create a theme per defect "because the fixes are independent": independence decides whether two
findings are the same *section*, not whether they share a *file*. When unsure whether a finding
fits a theme, put it in — a slightly broad theme is cheaper to read than the folder it replaces.

A theme should stay readable: when one would pass about twelve sections, split it along its most
natural seam into two themes, each named for what it covers. A finding that truly belongs to
nothing else becomes a single-section file; that should be the exception.

**Step 3 — collapse duplicates inside a theme.** Two atomic findings are the **same section** only
when they name the same defect — the same root cause, or the same wrong behaviour of the same
construct, including across targets when the remedy is one design.

- **Same defect** → one section. Union the `file:line` lists and the evidence; when the sources
  cover different sites, give each site its own bullet. Keep the higher stated severity.
- **Different defects in the same theme** → separate sections, each carrying its own evidence in
  full. Where useful, a section names the sections it depends on or contradicts.
- **Sources disagree** (one says a thing is realized, another says it is not) → one section marked
  `**Conflict:**`, quoting both claims. Do not pick a side without reading the code; if you do read
  it, cite what you read.

**Step 4 — check the ratio.** Count atomic findings in and theme files out. A run that turns N
inputs into roughly N files has not grouped; go back to the index and name the themes the lone
files belong to. Report both numbers.

## Phase 4 — Write the resulting files

Each theme gets exactly one **consolidated file** in `d:\datrix\reports\finding\`, named
`consolidated-NNN-<slug>.md` (`NNN` three digits, `<slug>` naming the theme).

- **Numbering.** Continue from the highest `NNN` among existing `consolidated-*` files (start at
  `001`). Numbers are never reused or renumbered.
- **Raw files** (anything not prefixed `consolidated-`) are always superseded. Each defect in them
  goes **first** into an existing consolidated file whose theme it fits, as a new section or as
  added evidence on a section it duplicates. Only a defect that fits no existing file and no other
  new theme gets a new file. A raw file never becomes a consolidated file by being renamed.
- **Existing consolidated files** keep their number and are in scope for grouping: earlier runs
  saw only part of the inbox, and an earlier run may have written one file per defect. Fold files
  of one theme into the lowest-numbered of them, carrying each file's defects over as sections, and
  delete the others. When a file's theme broadens, update its title and slug (the number stays;
  rename the file to match) and repoint any **Related** lines in other files that named the old
  name.
- Raw files and folded-away consolidated files are deleted in Phase 6.

Layout of a file the skill writes:

```markdown
# <theme — the seam, subsystem or defect class>

**Scope:** <one or two sentences: what this theme covers and how its defects relate>
**Where:** `repo/path/…`, `…`   (the packages and areas it spans)
**Related:** <other consolidated files, if any>

## 1. <the defect, one line>

**Severity:** <only if a source stated it>  ·  **Kind:** <bug / security / design flaw / test gap / doc drift / tooling, as the sources say>
**Where:** `repo/path/file.py:48-61`, `...`

**Issue.** ...

**Impact.** ...

**Direction.** ...   (only if a source gave one)

## 2. <next defect>
...
```

A single-section file may omit **Scope** and put the defect's fields directly under the title.

Do not add status fields, IDs, or a "merged from" list: the folder is a working inbox, not a
history.

**Encoding.** Write files with the `Write` tool as plain UTF-8. Source text may arrive already
garbled (`â€¦` for `…`, `Â§` for `§`, `â€”` for `—`); restore the intended character when carrying it
and never copy the garbling forward. Never write a file through a shell redirect or `Set-Content`.

**Related lines.** Every `consolidated-NNN` named under **Related** must exist after Phase 6. Check
after deleting; a pointer to a deleted file is a defect in the consolidation.

## Phase 5 — Prove nothing was lost

Before deleting anything, for **every file you are about to delete** list the defects you counted in
it and, for each, the remaining file and section number that now states it. Every defect must map to
a section of a remaining file, and every `file:line` the deleted file cited must appear in that
section. Do this by re-reading the
files you wrote, not from memory.

Any defect or citation without a home is a defect in your consolidation: fix the remaining file,
then re-check.

## Phase 6 — Delete the superseded sources

Only after Phase 5 passes, delete each superseded file (grouped-away sources and split umbrellas)
with `Remove-Item`. Do not copy, move or rename them anywhere, and do not create an `archive`
folder or any other file recording what was deleted.

## Report to Jon

Keep it short: raw files in, existing consolidated files in, atomic findings in, theme files out
(the Phase 3 ratio) with their numbers and one-line themes, which existing files were folded
together, any conflicts flagged, any redaction, and the Phase 5 result (the counts, not "looks
fine"). If theme files out is close to atomic findings in on ten or more findings, say why the
findings did not group.
