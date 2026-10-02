---
model: claude-opus-5-5
effort: medium
description: Merge every findings file under d:\datrix\reports\finding into one consolidated findings file — an existing one (merged into, IDs kept) or a new one. Splits umbrella files into single defects, merges duplicates that name the same defect, groups by owning surface, ranks by severity, and archives the ingested sources with a ledger so no finding and no cited path is lost. Use when Jon asks to "consolidate findings", "merge the findings", "clean up reports/finding", or runs /consolidate-findings.
---

# Consolidate Findings

Agents write one findings file per issue into `d:\datrix\reports\finding\` and are told not to
search the folder first (execution-contract §5A), so the folder fills with duplicates, overlapping
reports and umbrella files listing many defects. This skill is the "merged later" step: it turns
the inbox into one consolidated, de-duplicated, ranked register.

**The one rule: nothing is lost.** Every defect stated in every source file ends as an entry in the
consolidated file, and every source file name appears in the ledger. Merging two findings is a
claim that they describe the same defect; splitting one is a claim that it describes several. Both
need the text to support them.

This skill only consolidates. It fixes no code, files no tasks, and edits no repo.

## How to invoke

```
/consolidate-findings                      # merge into d:\datrix\reports\findings-consolidated.md
/consolidate-findings <path-to-consolidated.md>
```

- **Target exists** → merge the inbox into it. Existing entries keep their IDs, text and status.
- **Target missing** → create it.
- The target must live under `d:\datrix\reports\` and must not be directly inside
  `reports\finding\` (that folder is the inbox; a file there would be ingested as a finding on the
  next run). Refuse any other path and say why.

## Inputs

- **Inbox:** every `*.md` file directly in `d:\datrix\reports\finding\`. Subfolders
  (`archive\`) are not inbox. List them with
  `Get-ChildItem d:\datrix\reports\finding -File -Filter *.md | Sort-Object Name`.
- **Existing consolidated file**, if the target exists. Read it fully first.

If the inbox is empty, say so in one line and stop. There is nothing to do.

## Phase 1 — Read everything

Read every inbox file **in full** with `Read`. Do not skim, grep for headings, or sample — an
umbrella file can hold twenty defects under one title, and a heading scan finds one. Read the
existing consolidated file in full too.

The files are small; read them yourself. Do not dispatch subagents for this.

## Phase 2 — Extract atomic findings

Turn each source file into one or more **atomic findings**: one defect, one root cause. For each,
record:

| Field | Source |
|---|---|
| Title | One line, stating the defect — not the symptom list |
| Kind | `bug` / `security` / `design flaw` / `test gap` / `doc drift` / `tooling` / `other` — as the source says, or from the text |
| Severity | `critical` / `high` / `medium` / `low`. Use the source's severity when it gives one. Otherwise judge from the stated impact: security exposure or silent data loss → high or above; wrong output on a shipped target → medium; tooling friction or doc drift → low. Mark a judged severity `(assessed)` |
| Area | The owning package or surface (e.g. `datrix-codegen-python`, `task tooling`, `test runner`). A defect spanning several packages uses the most shared layer it names, and lists the rest under Where |
| Where | Every `file:line` the source cites, verbatim |
| Issue | What is wrong and the evidence, as the source states it |
| Impact | As the source states it |
| Direction | Only if the source gives one |
| Sources | The source file name(s) |
| First seen | The earliest `YYYYMMDD-HHMMSS` among its sources (from the file name) |

**Splitting.** A file listing several independent defects (numbered residual lists, "also in this
file" sections) becomes several findings, each carrying the same source file name. Keep a
sub-item with its parent only when it has the same root cause.

**Carry, don't rewrite.** Keep the source's evidence, citations and wording of the defect. Shorten
prose; never change a claim, a path, a line number, or a severity the source stated. A guess the
source labelled as a guess stays labelled.

**Leave out what must not be in a shareable file:** secrets, credentials, and customer or project
domain names. If a source contains one, describe the defect without it and say in your reply that
the source had to be redacted.

## Phase 3 — Merge duplicates

Two atomic findings — from the inbox, or one from the inbox and one already in the consolidated
file — are the **same finding** when they name the same defect: the same root cause at the same
location, or the same wrong behaviour of the same construct. Same area or similar title is not
enough.

- **Same finding** → one entry. Union the Where lists, Sources and evidence. Keep the higher
  severity. Keep the earliest First seen. An existing entry keeps its ID.
- **Related, different defects** (same file, different bug; same symptom, different targets with
  different causes) → separate entries, each naming the other under **Related**.
- **Sources disagree** (one says a thing is realized, another says it is not) → one entry marked
  `**Conflict:**`, quoting both claims with their sources. Do not pick a side without reading the
  code; if you do read it, cite what you read.

## Phase 4 — Status

Every new entry starts as `open`. Do not mark anything resolved on a hunch or because a file name
sounds like a fix landed.

An entry becomes `resolved` only when you read the cited code and it no longer contains the defect.
Record the evidence on the entry: `**Resolved:** YYYY-MM-DD — <file:line read and what it now
does>`. Resolved entries stay in the file (move them to the Resolved section); they are never
deleted.

Checking whether findings are still live is optional per run. Do it when Jon asks, or when a new
source says a finding was fixed. Otherwise leave statuses as they are and say you did not check.

## Phase 5 — Write the consolidated file

Assign new entries the next free ID `F-NNN` (three digits, continuing from the highest ID in the
file). IDs are never reused or renumbered, so a reference to `F-017` stays valid across runs.

Write the whole file with `Write` (read it first when it exists). Layout:

```markdown
# Consolidated Findings

**Last consolidated:** YYYY-MM-DD HH:MM
**Open:** N (critical a · high b · medium c · low d) · **Resolved:** M · **Sources ingested:** S

## Index

| ID | Sev | Area | Title | Status |
|---|---|---|---|---|
| F-001 | high | datrix-codegen-python | Rate limiter keys on an unverified JWT | open |
...  (open entries first, by severity then ID; resolved last)

## <Area>

### F-001 — <title>

- **Severity:** high · **Kind:** security · **Status:** open
- **First seen:** YYYY-MM-DD · **Sources:** 20260929-164000-rate-limit-trusts-unverified-jwt.md
- **Where:** `repo/path/file.py:48-61`, `...`
- **Related:** F-014

**Issue.** ...

**Impact.** ...

**Direction.** ...   (only if a source gave one)

... one `##` section per Area, areas alphabetical, entries by severity then ID ...

## Resolved

### F-00X — <title>
... same fields, plus **Resolved:** ...

## Source ledger

| Source file | Entries |
|---|---|
| 20260929-150100-correctness-residuals-from-designs-040-049.md | F-020, F-021, ... |
...  (every file ever ingested, sorted by name; existing rows kept)
```

## Phase 6 — Prove nothing was lost

Before touching the inbox, check the consolidated file you just wrote:

1. **Every inbox file is in the ledger.** Compute `inbox file names − ledger file names`. It must
   be empty.
2. **Every ledger row points at real entries.** Every ID in the ledger exists as a `### F-NNN`
   heading, and every entry's Sources names only ledger files.
3. **Every item of an umbrella file is accounted for.** For each source you split, the number of
   defects you counted in it equals the number of entries (or merged entries) its ledger row
   lists — or you say which items you merged and into what.
4. **Existing entries survived.** Every `F-NNN` that was in the file before this run is still in
   it.

Do these by parsing the file you wrote (headings, the ledger table), not by memory. Report the
counts. Any non-empty difference is a defect in your consolidation: fix the file, then re-check.

## Phase 7 — Archive the ingested sources

Only after Phase 6 passes, move each ingested inbox file to `d:\datrix\reports\finding\archive\`
(create it if missing) with `Move-Item`. Do not delete them: agent reports and task notes cite
findings by path, and the archive plus the ledger keeps every cited path resolvable. If a file of
the same name is already in `archive\`, stop and tell Jon rather than overwrite it.

## Report to Jon

Keep it short:

- the consolidated file path, and whether it was created or merged into;
- sources ingested, entries added, entries merged into existing ones, conflicts flagged;
- the open counts by severity, and the IDs of any new critical or high entries;
- the Phase 6 check results (the counts, not "looks fine");
- whether statuses were checked against the code this run.
