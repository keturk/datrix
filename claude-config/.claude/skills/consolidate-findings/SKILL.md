---
model: claude-opus-5-5
effort: medium
description: Tidy the findings inbox at d:\datrix\reports\finding in place — group related findings into themes (one seam, subsystem or defect class), write each theme as one numbered consolidated-NNN-<slug>.md file holding every defect of that theme as its own section, and delete the superseded sources. Keeps no archive and no register; the folder itself is the result. Use when Jon asks to "consolidate findings", "group the findings into themes", "clean up reports/finding", or runs /consolidate-findings. For collapsing only files that describe the same issue, use /merge-findings.
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

**How the work is split.** You decide the grouping; scripts do the reading and the writing. A local
model drafts where each new finding goes, you correct the plan, and the assembler writes every theme
file by carrying each source's text verbatim, so no defect, citation or wording is retyped. Do not
read the inbox file by file and do not write theme files by hand: on a real inbox that costs
hundreds of thousands of tokens and is where defects get dropped.

## How to invoke

```
/consolidate-findings
```

## Inputs

Every `*.md` file directly in `d:\datrix\reports\finding\`:

- **Raw files** — agent-written `YYYYMMDD-HHMMSS-<slug>.md`: the inbox. Each is one **unit**, id = its
  file stem.
- **Consolidated files** — `consolidated-NNN-<slug>.md`: results of earlier runs. Each `## N.` section
  is one unit, id `CNNN.N` (so `C009.3` is section 3 of `consolidated-009-…`).

If there are no raw files, say so in one line and stop.

## Phase 1 — Draft the plan

```bash
powershell -File "d:/datrix/datrix/scripts/skill/skill-assist.ps1" findings-plan
```

It writes two files under `d:\datrix\.tmp\assist\`:

- `findings-plan.json` — the plan: every theme as `file` (the consolidated file it keeps, or `""` for
  a new theme), `slug`, `title`, `scope`, and `sections` (a list of sections, each a list of unit
  ids; the first unit of a section is its heading, every further one is the same defect reported
  again).
- `findings-plan.md` — the review view: only the themes the model changed, each section with its unit
  titles, and a `REVIEW` line for every decision the model made (a unit added, a duplicate merged, a
  new theme, a fold, a unit it could not place).

The model saw only each unit's title and opening lines, with any line carrying a registered customer
term withheld. Every id it answered was checked; a unit it misplaced or skipped becomes its own new
theme flagged `not placed`. Exit 3 means no local model answered: run it again with `--no-model`
(every raw unit becomes its own theme) and do the placing yourself in Phase 2.

## Phase 2 — Correct the plan

Read `findings-plan.md` and settle every `REVIEW` line by editing `findings-plan.json` with `Edit`.
Open a source file only to settle a decision its title does not; read it by range.

**The failure this phase exists to prevent:** a plan that leaves each raw file its own theme, or
merges only findings that say the identical thing. Both leave a folder as long as the inbox. A real
inbox holds clusters of *related* findings — the same seam seen from the python side, the
typescript side and a test side; five different symptoms of one broken contract; a subsystem with a
handful of unrelated small defects. They belong in one theme.

**A theme is anything one person would fix and review together.** Units belong to one theme when any
of these holds:

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
units are the same *section*, not whether they share a *theme*. When unsure, put it in — a slightly
broad theme is cheaper to read than the folder it replaces.

**Sections.** Two units are the **same section** only when they name the same defect — the same root
cause, or the same wrong behaviour of the same construct, including across targets when the remedy
is one design. Different defects in one theme are separate sections.

**What you edit in the JSON:**

- Move a unit id between sections or themes; put two ids in one section to collapse a duplicate;
  split a section into two lists to separate defects the model merged.
- Fold two themes into one by moving one theme's sections into the other and deleting the emptied
  theme (keep the lower-numbered `file`; the folded file is deleted, its number retired, and every
  `**Related:**` pointer to it is repointed by the assembler).
- Give every new theme a `title` naming the seam or subsystem and a lowercase-hyphenated `slug`, and
  a `scope` (one or two sentences) when it has more than one section. When a kept theme broadens,
  change its `title` and `slug`; its number stays and the file is renamed.
- A theme passing about twelve sections (the view flags it): split it along its most natural seam
  into two themes.

Every unit id must appear exactly once. A dropped, repeated or invented id, a bad slug, or one
`file` used by two themes is refused by Phase 3 with the list of what is wrong.

**Check the ratio.** Count units in and themes out (the view's header). A plan that turns N new
findings into roughly N new themes has not grouped; go back and name the themes the lone units
belong to.

## Phase 3 — Preview the assembly

```bash
powershell -File "d:/datrix/datrix/scripts/skill/skill-assist.ps1" findings-assemble
```

It writes every theme file into `d:\datrix\.tmp\assist\findings-preview\` and changes nothing in the
inbox. Each theme file is `# title`, its preamble (**Scope**, **Where**, **Related**, merged from every
file folded into it), then `## 1.` … one section per plan section: the first unit's title and body,
and each further unit as an `**Also reported as:** <title>` paragraph with its own body. Raw files'
headings are nested one level, garbled characters (`â€”` for `—`) are restored, line ends are LF.

Before writing, it proves that every non-blank line of every source — titles, bodies, preamble —
appears in the output, and that no output carries a registered customer term. Exit 2 names what
failed and writes nothing:

- **A customer term** — redact the source file itself with `Edit` (describe the defect without the
  term), say in your report that it was redacted, and run again.
- **Lost lines** — the plan or a source is malformed; fix it and run again.

Read the preview of any theme you are unsure of; you need not read them all.

## Phase 4 — Apply

```bash
powershell -File "d:/datrix/datrix/scripts/skill/skill-assist.ps1" findings-assemble --apply
```

It writes the theme files into the inbox, runs the no-loss check (`findings-check`: every `path:line`
and backticked file path of each superseded file appears in a remaining file, every `**Related:**`
pointer names a remaining consolidated file, no mojibake, no raw file left), and deletes the
superseded sources **only when that check passes**. Exit 2 deletes nothing and lists what fails: fix
the remaining files with `Edit`, then run `findings-check --delete <the superseded files>` yourself
and delete them with `Remove-Item` once it passes.

Do not copy, move or rename the superseded files anywhere, and do not create an `archive` folder or
any other file recording what was deleted.

## Phase 5 — Finish by hand, only where a script cannot

Edit the written files with `Edit` only for what the assembler does not do:

- **Sources disagree** (one says a thing is realized, another says it is not): mark that section
  `**Conflict:**`, quoting both claims. Do not pick a side without reading the code; if you do read
  it, cite what you read.
- **An umbrella raw file** that listed several independent defects arrived as one section: split it
  into sections, or move a defect to the theme it belongs to, carrying its text unchanged.
- **Secrets or credentials** in a source (the term check covers customer terms only): remove them and
  say so in your report.

Never shorten a claim, change a path, a line number or a stated severity, and never add status
fields, IDs or a "merged from" list. When you move a defect between files, add it at its new place
before removing it from the old one, and give the receiving section its own `## N.` number.

## Report to Jon

Keep it short: raw files in, existing consolidated files in, units in, theme files out (the Phase 2
ratio), the new theme files with their numbers and one-line themes, which existing files were folded
together, any conflicts flagged, any redaction, and the Phase 4 check result (the counts, not "looks
fine"). If theme files out is close to units in on ten or more findings, say why they did not group.
