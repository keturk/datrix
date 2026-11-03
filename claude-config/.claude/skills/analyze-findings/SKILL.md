---
model: claude-sonnet-5-5
effort: medium
description: Read the findings inbox at d:\datrix\findings and sort every finding into must-have (security, wrong or lost data, a shipped example that does not generate, a broken deploy or runtime, a red test, gate or guard, a per-target behaviour difference) or nice-to-have (dead code, one-home cleanups, doc drift, lint, performance, duplicate diagnostics, process notes), with a one-line reason each, so Jon can see what to fix first. Read-only: deletes, renames and edits nothing. Use when Jon asks to "analyze the findings", "which findings are must-haves", "which are nice to have", "prioritize the findings", or runs /analyze-findings.
---

# Analyze Findings

The findings inbox (`d:\datrix\findings\`, area subfolders plus loose files) fills with every
defect agents notice. This skill answers one question for Jon: **which of them must be fixed,
and which are nice to have.** It reads and classifies. It deletes, moves, renames, merges and
edits nothing, files no task, writes no register, and dispatches no subagents. What Jon does
with the answer (`/implement-finding`, `/delete-redundant-findings`, deleting a category) is his call.

## How to invoke

```
/analyze-findings            # the whole inbox
/analyze-findings aws kernel # only the named area subfolders
```

## The two classes

**Must-have** — leaving it unfixed ships a wrong or unsafe result, or blocks verification of
everything else. A finding is a must-have when its own text shows any one of:

1. Security. 2. Wrong or lost data. 3. A shipped example or named product does not generate.
4. A broken runtime. 5. A red test, gate, guard or script on the live tree. 6. A per-target
   behaviour difference. The six-point test is the one agents apply before filing a finding, and
   its wording lives in one place, `execution-contract-reporting.md` §5A: read it before you
   classify. Agents no longer file nice-to-haves, so a nice-to-have in the inbox is an older file.

Split the must-haves in two so the order is clear:

- **Tier 1 — fix first:** 1, 2, 3, 4 and 5 above.
- **Tier 2 — real defect, narrow trigger:** 6, and any item of 1–5 that only fires on an unusual
  input, one rarely used target, or after a deliberate misuse (a hidden code point, a nonstandard
  spelling), where the failure is loud and located.

**Nice-to-have** — the product behaves correctly today and the finding makes the code or the
workflow tidier: dead code with no production caller; a fact written in a second place that agrees
with its home today; documentation drift; lint and format findings; performance; a duplicate or
poorly worded diagnostic; a late error that is still an error; fixture or test-quality hygiene;
process notes (a commit that bundles changes); script robustness that does not block a gate.

**When unsure, rank the finding higher, not lower** — a nice-to-have that was a must-have is
the costly mistake. A finding that is a must-have only if a condition holds (an unguarded path is
real; an example profile is registered) is listed as nice-to-have **with the condition named**.
A finding that is not a Datrix defect at all (a product repo's own configuration that lags the
schema) is listed apart, with the repo that has to fix it.

## Phase 1 — Read each finding's head

A finding opens with its title, a `- **Kind:**` line (bug, security, design flaw, test gap, doc
drift, dead surface, process …) and an opening paragraph that states what is wrong and which
sections follow. For a theme file (`## 1.`, `## 2.`, …) the opening paragraph covers all its
sections. Print them without reading whole files:

```powershell
$root='d:\datrix\findings'
Get-ChildItem $root -Recurse -File -Filter *.md | Sort-Object FullName | ForEach-Object {
  $l = Get-Content $_.FullName -TotalCount 40
  "=== $($_.FullName.Substring($root.Length+1)) ($([int]($_.Length/1024))KB)"
  $l[0]
  $l | Where-Object { $_ -match '^- \*\*(Kind|Severity|Needs Jon)' } | Select-Object -First 3
  $p = $l | Select-Object -Skip 1 | Where-Object { $_ -notmatch '^\s*$' -and $_ -notmatch '^- \*\*' -and $_ -notmatch '^#' } | Select-Object -First 1
  if ($p.Length -gt 800) { $p.Substring(0,800) } else { $p }
}
```

A long inbox prints more than one result holds; the tool saves the output to a file, which you
read in ranges. For `/analyze-findings <area…>` limit `Get-ChildItem` to those subfolders.
A `- **Needs Jon:**` line means a decision is waiting; carry it into the report.

## Phase 2 — Read the body where the head cannot decide

The head decides most findings. Open the body (a ranged `Read`) when the head leaves one of
these open, and only then:

- the Kind says "bug" but the head does not say whether the output is wrong or merely untidy;
- the head says a check "does not exist yet" or "is not enforced" — is a real defect reachable?
- two findings look like one defect (read both sections before calling them duplicates).

Do not verify a finding against the current code here: whether it still holds is
`/implement-finding`'s first step. Say so in the report instead of implying it was checked.

## Phase 3 — Report to Jon

Counts first (files read; tier 1, tier 2, nice-to-have). Then:

1. **Must-have, tier 1**, grouped by the reason number above (security; wrong or lost data; does
   not generate; broken at deploy or runtime; red tests, gates and guards), each finding on one
   line: `area/NNNN` (or the date-stamped name) and the reason in a clause.
2. **Must-have, tier 2**, one line each.
3. **Nice-to-have**, grouped (dead code and one-home cleanups; diagnostics, performance, hygiene;
   docs and process), one line each, conditions named for the conditional ones.
4. **Apart:** findings that are not Datrix defects, and findings carrying `Needs Jon`.
5. **Duplicates noticed**, as pairs, for `/delete-redundant-findings` or `/merge-findings`. List
   them; delete nothing.
6. One sentence on the basis: classified from each finding's title, kind and opening paragraph
   (and the bodies you opened), not re-checked against the current code.

Close with the cheap tier 1 items (a red test with a one-line cause) only if there are some.
No other recommendations, and no offer to do the next step.
