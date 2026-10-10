---
model: claude-sonnet-5-5
effort: medium
description: Merge the findings inbox at d:\datrix\reports\finding in place — group every set of findings one fix session would tackle together (the same or SIMILAR issues — same defect, seam, fix site or defect class, or one shared remedy) into one file per theme, leaving no two similar files behind, carry every source's evidence and citations as numbered sections, delete the originals, and name every file NNNN-<area>-<slug>.md numbered contiguously in area order (python, typescript, backends, clients, language, migration, seed, kernel, docker, aws, azure, component, tests, tooling, docs). Use when Jon asks to "merge findings", "dedupe the findings", "merge similar findings", or runs /merge-findings.
---

# Merge Findings

Agents write one findings file per issue into `d:\datrix\reports\finding\` and are told not to
search the folder first (execution-contract §5A), so the same or a closely related defect gets
reported several times — by different agents, from different targets, on different days. This
skill collapses them: **each issue, and each family of similar issues, ends up in one file**, and
the inbox is renamed so it reads by area.

**The bar: no similar files left behind.** The test for every pair of findings is *could one fix
session tackle these together?* If yes, they end up in one file. `/implement-finding` picks up one
file and fixes every section in it, so a file is one session's worth of work. Finishing with two
files that one person would naturally fix together is a failed run, not a cautious one.

Two findings belong in one file when any holds:

- they name the same defect (same root cause, or the same wrong behaviour of the same construct,
  on one or several targets);
- one is the cause and the other a symptom it explains;
- they are the same defect class in the same subsystem, so one design or one sweep would fix
  them together (e.g. three incremental-generation hash gaps; two scripts that default a target
  name silently; every Azure data store's network/auth posture);
- they sit on the same seam, contract or construct (a handler parameter set, a config-store
  environment, an API-key check), even when the defects differ;
- they sit at the same fix site — the same generator, template family, module or script — so
  fixing one means opening the code of the other;
- one pins the other: a test gap, doc drift or tooling gap about the behaviour the other reports,
  or a sub-case or consequence of it;
- they are the same kind of test breakage with one remedy (fixtures missing a config that
  generation now requires; tests red because the code they pin changed).

Different severity, kind (bug, test gap, doc drift) or target never separates findings. When unsure
whether a finding fits a group, **put it in**: a slightly broad file costs less than a second session
rediscovering the same code. Keep findings apart only when they share nothing but a package and a
fix of one would not touch the other's code.

**Session size.** A file holds what one session can carry: roughly up to eight sections. A group
that would pass that splits along its most natural seam into two files, each named for what it
covers — never into one file per defect.

Each merged file opens with one paragraph naming what the sections have in common and the shared
remedy, so the grouping is justified on the page.

**The one rule: no defect is lost.** Every defect, piece of evidence and `file:line` stated in a file
you delete must be stated in the file that survives.

This skill only tidies findings files. It fixes no code, files no tasks, edits no repo, and
dispatches no subagents.

## How to invoke

```
/merge-findings
```

## Inputs

Every `*.md` file directly in `d:\datrix\reports\finding\`:
`Get-ChildItem d:\datrix\reports\finding -File -Filter *.md | Sort-Object Name`.

- **Raw files** — `YYYYMMDD-HHMMSS-<slug>.md`, written by agents since the last run (§5A format).
- **Merged files** — `NNNN-<area>-<slug>.md`, written by earlier runs: one theme, one numbered
  section per source defect. They take part as merge targets; a raw file that belongs to an
  existing theme becomes a new section of it.
- **Consolidated files** — `consolidated-NNN-<slug>.md` from `/consolidate-findings`: treat as
  merged files and rename them into the `NNNN-<area>-<slug>.md` scheme.

If the folder holds fewer than two files, say so in one line and stop.

## Phase 1 — Index, then read everything

```bash
powershell -File "d:/datrix/datrix/scripts/skill/skill-assist.ps1" findings-index
```

`d:\datrix\.tmp\assist\findings-index.md` lists every atomic finding as
`seam | packages | defect | source | citations`, sorted by seam. It is a lead, not a verdict. Exit 3
means no local model answered: build the same index by hand from your reads.

Then read every file **in full**. A title is not the issue. Decide from the text and its citations.

## Phase 2 — Group and assign areas

Write the groups down before editing: for each group, its files, the one-line theme, and its area.
A file in no group still gets an area (it is renamed, not merged).

Then check the ratio: files in vs files out. A run that leaves close to as many files as it started
with has not merged — go back to the index, walk each area's singles, and find the group each
belongs to. A single should be the exception, and every single that shares an area with a group
needs a one-clause reason why one session would not take it with that group.

**Areas, in this order** (the order sets the numbering): `python`, `typescript`, `backends` (both
languages or the shared language layer), `clients` (Angular, Flutter), `language` (parser,
semantic analysis, DSL), `migration`, `seed`, `kernel` (shared generation, secrets, hosting,
pooling, observability export), `docker`, `aws`, `azure`, `component`, `tests` (red or weak test
suites), `tooling` (scripts, gates, skills), `docs`. A finding goes to the most specific area
that owns its fix; a defect seen on several targets with one shared remedy goes to the shared area.

## Phase 3 — Write each merged file

One file per multi-source group, written with `Write` under a temporary number:

```markdown
# <one-line statement of the theme — the root cause or defect class, not a symptom>

- **Area:** <area> (<packages / surfaces>)
- **Found:** <earliest Found of the group> (also reported <date>, <date>, ...)
- **Kind:** <the sources' kinds>

<One paragraph: what the sections have in common and the shared remedy.>

## 1. <source title>

- **Found:** <source's Found; from its filename timestamp when the body has none>
- **Where:** ...
- **Kind:** ...

### Issue / ### Impact / ### Suggested direction
<the source's body, its headings demoted one level>

## 2. <next source title>
...
```

An existing merged file that gains a source gets a new numbered section; never renumber or split
its existing sections.

**Carry, don't rewrite.** Keep each source's body verbatim except for heading levels and
references to other findings files (point them at the section or theme name instead). Never change
a claim, path, line number or severity. A guess the source labelled as a guess stays labelled.

**Sources disagree** → keep both, under a `**Conflict:**` line quoting each claim. Do not pick a
side without reading the cited code; if you read it, cite what you read.

**Dates.** A raw file whose body has no `**Found:**` line carries its date only in its filename:
add `- **Found:** YYYY-MM-DD HH:MM` (from the timestamp) before it is renamed or merged.

**Leave out what must not be in a findings file:** secrets, credentials, customer or project domain
names. If a source carried one, describe the defect without it and say so in your reply.

**Encoding.** Write with `Write`/`Edit` as plain UTF-8. Restore garbled characters (`â€”` → `—`,
`Â§` → `§`, `â€¦` → `…`); never copy mojibake forward. Never write through a shell redirect.

## Phase 3b — Sweep for what is still similar

Re-read the title, opening paragraph and **Where** lines of every file now in the folder — merged
files, singles, and existing merged files from earlier runs — and, for each pair in the same area or
sharing a package, seam or fix site, ask the session question again. A theme written in Phase 3 is
often the natural home of a single left alone in Phase 2, and two themes can turn out to be one.
Merge every pair that qualifies (Phase 3 again, within the session size) until no pair does.

## Phase 4 — Prove nothing was lost

Run the check over every file you are about to delete (every source now carried by a merged file):

```bash
powershell -File "d:/datrix/datrix/scripts/skill/skill-assist.ps1" findings-check --keep-raw --delete <file> <file> ...
```

Exit 0 means every `path:line` citation and backticked path of each file to delete appears in a
remaining file, every `**Related:**` pointer resolves, and no remaining file carries mojibake. Exit
2 lists what fails — add the exact citation to the merged file, run it again. Also confirm by count
that every source is a section of exactly one merged file.

## Phase 5 — Delete, then renumber

1. Delete every merged-away source with `Remove-Item` once Phase 4 passes. Do not archive it.
2. Rename every remaining file to `NNNN-<area>-<slug>.md`: four-digit numbers from `0001`,
   contiguous, ordered by the area order above (within an area, merged themes before single
   findings is fine). Rename through a temporary prefix so no rename collides with an existing name.
3. Grep the folder for any old filename (`YYYYMMDD-HHMMSS-...md`, or a number that changed) and
   repoint it.

## Report to Jon

Short: files in, files out, how many merged themes and how many singles. One line per merged theme
(new name and how many sources). Then each single that shares an area with a theme, with its
one-clause reason; conflicts flagged, redactions, and the Phase 4 exit code.
