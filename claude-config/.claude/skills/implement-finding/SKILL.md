---
description: Work ONE findings file from d:\datrix\reports\finding end to end in this session — check it against the current code, and when it still holds fix it, prove it with a tagged test and targeted runs, update the docs that describe it, and delete it through finding-close. Use when Jon asks to "implement a finding", "fix the next finding", or runs /implement-finding. To work through several findings, one fresh session each, Jon runs scripts/skill/implement-finding.ps1.
---

# Implement Finding

Agents write a findings file for every defect they could not fix in place (execution-contract
§5A). This skill drains that inbox **one finding at a time**, in one session: it checks the finding
against the code and, when it still holds, fixes it. A finding leaves the folder only through
`finding-close`.

**Invoking this skill is Jon's authorization to fix a design-sized finding.** A finding that says
"why not fixed in place: needs its own design" is still fixed here. The execution contract governs
the work as it does any task: the fix is the size the defect needs, across every package and target
it reaches; only a B1–B4 blocker with its four-part proof stops it.

## How to invoke

```
/implement-finding                     # the first finding of the inbox, by name
/implement-finding FINDING: <path>
```

| Field | Meaning | Default |
|---|---|---|
| `FINDING` | The findings file to work | the first file by name: `skill-assist.ps1 finding-select --count 1` |
| `CLOSE` | `script` when `implement-finding.ps1` started the session: it deletes the finding itself | you delete it (step 6) |

## Steps

Before your first edit, read the mandatory cores and the knowledge pack of each area you touch.

1. **Does it still hold?** Read the finding and, for each defect it lists, the code it cites at and
   around the cited lines (citations drift; follow symbols with the code index). A defect is gone
   only when the behaviour is gone on every surface the finding names. When every defect is gone,
   change nothing, go to step 6 and reply `Finding fix: ALREADY RESOLVED`.
2. **Fix each defect that holds** at its root, at the most agnostic layer that can own it, on every
   target it reaches. Where defects share a root cause or a fix site, fix it once, there. Follow the
   finding's suggested direction when the code still agrees; when the code shows a better root
   cause, fix that and say why.
3. **Land the check that would have caught it**: a tagged test in the owning package, or a validator
   at the seam (execution-contract §12). One test may prove several defects; say which.
4. **Run only the tests of what you changed**, in the foreground (never `run_in_background`): the
   files you touched (`test.ps1 <pkg> -Specific`) and the feature tags of the behaviour you changed,
   in every package it reaches (`-Tag`, at most 3 per run). Never a whole suite. Do not pipe the
   output through a filter: a pipe hides `test.ps1`'s exit code, so a piped run proves nothing. Your **last** `test.ps1` run must pass: under `CLOSE: script` the script
   reads it from the session log and keeps the finding when it failed or never ran.
5. **Update the documentation** your change makes wrong, and every doc the finding names as stale —
   it must describe the behaviour the code now has. No design-doc or task reference and no customer
   term in a committed file. **Remove pointers to this finding** from other findings files (a
   `**Related:**` line naming it): drop it, or repoint it when the defect it pointed to lives on in
   another file.
6. **Close it.** Under `CLOSE: script`, stop here: the script deletes the finding. Otherwise delete it
   — only through the script, never with `Remove-Item`:

```bash
powershell -File "d:/datrix/datrix/scripts/skill/skill-assist.ps1" finding-close --finding "<finding>"
```

   Exit 0 deleted it. Exit 2 names another findings file that still points at it — step 5 is not done.

Something else you find on the way: small and on a surface you touched → fix it; design-sized or
unrelated → a new findings file (execution-contract §5A). Do not edit this finding to record it.

## Reply

What changed (`file:line`), the test commands you ran and what they printed, and the path of every
new findings file you wrote. End with exactly one line:

- `Finding fix: ALREADY RESOLVED` — every defect is gone from the code; you changed nothing;
- `Finding fix: DONE` — every defect fixed, its test landed, your last test run green, docs updated; or
- `Finding fix: BLOCKED B<n>` — with the four-part proof above it (verbatim error, the fix you
  attempted at `file:line` and ran, why it failed, the code). A decision only Jon can make is B2:
  state both designs and your recommendation. Fix every defect the block does not touch first, and
  leave the finding in place.
