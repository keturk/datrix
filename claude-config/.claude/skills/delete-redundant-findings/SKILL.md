---
model: claude-sonnet-5-5
effort: medium
description: Delete the redundant files from the findings inbox at d:\datrix\reports\finding — a file is redundant when another file in the inbox already states the same defect with all of its evidence and citations, so deleting it loses nothing. A script finds the candidate pairs, a local model judges each pair, and a script proves the deletion loses no citation before it removes anything. Merges nothing, renames nothing, writes no new file; a file that carries anything the survivor lacks is kept and left for /merge-findings. Use when Jon asks to "delete redundant findings", "remove duplicate findings", "drop the findings that are already covered", or runs /delete-redundant-findings.
---

# Delete Redundant Findings

Agents write one findings file per issue into `d:\datrix\reports\finding\` and are told not to
search the folder first (execution-contract §5A), so the same defect is reported again and again.
This skill removes the copies that add nothing. It is the narrow cousin of `/merge-findings`:
that skill *combines* related findings into themes; this one only *deletes* a file whose whole
content is already in another file.

**How the work is split.** Scripts find the candidate pairs and prove the deletion; a local model
reads each pair; you decide. Do not compare the files by reading the folder: on a real inbox the
script narrows 41 files to a dozen pairs, and the model has already read both sides of each. You
read only the pairs the plan proposes.

**A file is redundant when all three hold:**

1. **Same defect.** It names the same root cause, or the same wrong behaviour of the same construct,
   as a file that stays (the *survivor*) — on every target it names. Related, adjacent, same-seam or
   same-fix-site is *not* redundant; that is `/merge-findings` territory.
2. **Nothing unique.** Every claim, symptom, impact, `path:line` citation, backticked path and
   suggested direction in it is stated in the survivor. A different location, a second target, a
   stronger impact, an extra repro or a different suggested fix is something the survivor lacks, so
   the file stays.
3. **Mechanically provable.** The delete step passes (Phase 4).

A finding that is merely *already fixed* in the current code is not redundant — it is stale, and
`/implement-finding` closes it (`ALREADY RESOLVED`). Do not read the code to decide that here.

**When unsure, keep the file.** A leftover duplicate costs one read; a deleted finding is gone
(the folder is not a git repo). Only a file holding one finding is ever deleted — a theme file with
several sections is a survivor, never a candidate. The command never dooms both files of a pair.

This skill only deletes findings files. It fixes no code, files no tasks, edits no repo outside the
findings folder, writes no register or archive of what it deleted, and dispatches no subagents.

## How to invoke

```
/delete-redundant-findings
```

## Phase 1 — Find and judge the candidates

```bash
powershell -File "d:/datrix/datrix/scripts/skill/skill-assist.ps1" findings-redundant
```

**The inbox has area subfolders** (`organize-findings.ps1` sorts the loose files into
`d:\datrix\reports\finding\<area>\`). The command goes through the subfolders one at a time (then the
inbox's own loose files) and compares the `*.md` of a folder with each other only, never with another
folder's files: a duplicate is found inside `python`, not between `python` and `azure`. You pass no
folder. Every file is named by its path under the inbox (`azure/0167-….md`) in the plan, the view and the
delete step; a pointer in prose or in **Related:** names the file stem, as before. `--dir <folder>` (an
area name such as `python`) narrows the run to that one folder. A full inbox has hundreds of pairs for the
model to read and the run takes tens of minutes: start it with `run_in_background` and wait for the
notification.

It writes `d:\datrix\.tmp\assist\findings-redundant.json` (the plan) and `findings-redundant.md` (the
review view) and prints their paths with a one-line summary. Per file it works in three steps:

1. **Units.** A raw file is one unit; a theme file (`## 1.`, `## 2.`, …) is one unit per section.
2. **Candidates, exact.** A unit of a higher-ranked file is a candidate survivor when it cites every
   `path:line` and backticked path the file cites, or shares enough of its words. Rank is citations,
   then length, then name (the earlier name survives a tie).
3. **Verdict, model.** A local model reads both texts and answers SAME, PARTIAL or DIFFERENT. SAME
   stands only when the model lists nothing the doomed file has that the survivor lacks and quotes a
   line of each file that really occurs in that file; a line withheld for a customer term also
   downgrades it. The verdict is a lead.

The view lists **Proposed for deletion** (doomed file → survivor and section, the model's reason,
`delete: true|false`, notes) and **Looked alike, kept** (each pair with its verdict). A proposal
carries `delete: true` only when the survivor already cites everything the file cites. When the
survivor lacks citations, or the file cites nothing, `delete` is `false` and a note says why.

Exit 3 means no local model answered. Run `findings-redundant --no-model`: it lists the candidate
pairs unjudged, and you judge each by reading both files (Phase 2).

## Phase 2 — Read both files of every proposal, then decide

The model's verdict is a lead, never the decision. For each proposal read **both files in full** and
the survivor section named. Then:

- **Same defect, nothing unique** → the proposal stands. If it carries `delete: false` only because
  the survivor lacks citations that are evidence of that same defect, add them (and any one-sentence
  detail) to the survivor with `Edit`, then run Phase 1 again: the plan is rebuilt against the edited
  survivor. A larger addition is a merge — keep both files and name the pair in the report for
  `/merge-findings`.
- **Anything the survivor lacks that matters** (a second target, a different location, a stronger
  impact, a different fix) → reject: set `"delete": false` for that proposal in the plan JSON with
  `Edit`.
- **A proposal with `delete: false` that you confirm** → set `"delete": true` in the plan JSON with
  `Edit`. Only a file you have read both sides of.

Pairs listed under *Looked alike, kept* need no reading unless the verdict looks wrong to you; a
PARTIAL names what the survivor lacks, which is exactly why the file stays.

## Phase 3 — Repoint what names a doomed file

The delete step refuses while another findings file names a file it will delete. Find the mentions:

```powershell
Select-String -Path d:\datrix\reports\finding\*.md,d:\datrix\reports\finding\*\*.md -Pattern '<doomed file name without .md>' -SimpleMatch
```

Edit each mention (in **Related:**, **Where:** or prose) to name the survivor instead. The plan view
also lists the files that name each proposal.

## Phase 4 — Delete, with the proof

```bash
powershell -File "d:/datrix/datrix/scripts/skill/skill-assist.ps1" findings-redundant-delete
```

It deletes the proposals still marked `"delete": true`, and only when **every** one passes: the file
is unchanged since it was judged (hash), its survivor exists and is not itself being deleted, the
survivor still cites everything the file cites, no other findings file names it, and the no-loss check
(`findings-check --keep-raw`: every citation and path of the files to delete is in a remaining file, no
dangling `**Related:**`, no mojibake) passes. Otherwise it deletes nothing and lists each failure with
exit 2.

- **A file changed since it was judged** → run Phase 1 again.
- **Mojibake in a remaining file** → restore the characters (`â€”` → `—`, `Â§` → `§`, `â€¦` → `…`)
  with `Edit` in that file, then run Phase 4 again.
- **Never** weaken a proof or delete with `Remove-Item` to get past a failure.

Do not rename or renumber anything, do not move a deleted file anywhere, and do not create an
`archive` folder or any record of what was deleted.

## Report to Jon

Short: files in, files deleted, files out (`Get-ChildItem d:\datrix\reports\finding -Recurse -File -Filter *.md`
count). One line per deletion (`deleted → survivor §section`). Then the proposals you rejected with a
one-clause reason, any pair that needs `/merge-findings`, any sentence or citation added to a survivor,
and the Phase 4 exit code.
