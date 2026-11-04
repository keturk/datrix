---
description: Work ONE findings file from d:\datrix\findings end to end in this session — check it against the current code, and when it still holds fix it, prove it with a tagged test and targeted runs, update the docs that describe it, and delete it through finding-close. Use when Jon asks to "implement a finding", "fix the next finding", or runs /implement-finding. To work through several findings, one fresh session each and a batch of sessions side by side, Jon runs scripts/skill/implement-finding.ps1.
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
/implement-finding                     # the first finding of the first inbox subfolder that holds one
/implement-finding FINDING: <path>
```

| Field | Meaning | Default |
|---|---|---|
| `FINDING` | The findings file to work | the first file of the first inbox subfolder that holds one (area order), else the inbox's own files: `skill-assist.ps1 finding-select --count 1`; `--dir <subfolder>` (absolute, or relative to `findings`) limits it to that folder |
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
   **When the fix needs more than the finding states** — a premise of it is false (a field, record
   or fact it says exists does not), or the correct fix adds a capability, model field, phase or
   diagnostic the finding does not ask for — do not build it, do not ask Jon and do not dispatch the
   decision advisor. Fix every defect that does not depend on it. Then rewrite the finding in place:
   delete the sections you fixed, correct the false premise, and under each section left state what
   is needed (the growth, the packages and files it reaches, the counted size) so Jon or a later
   session can act on it without re-deriving it. Add one metadata line `- **Needs Jon:** <what is
   awaited, in one sentence>` beside `Keywords`/`Area`: selection (`finding-select`, and so the
   default `FINDING` and `implement-finding.ps1`) skips a finding that has it, and Jon deletes the
   line to put the finding back in turn. Reply `Finding fix: UPDATED`; the script keeps the finding
   and moves on to the next one.
3. **Land the check that would have caught it**: a tagged test in the owning package, or a validator
   at the seam (execution-contract §12). One test may prove several defects; say which.
4. **Run only the tests of what you changed**, in the foreground (never `run_in_background`): the
   files you touched (`test.ps1 <pkg> -Specific`) and, under `CLOSE: script`, nothing else — the
   script runs the related tests itself once the batch has ended (see below), so a tag or `e2e` run
   of yours repeats it. Without `CLOSE: script`, also run the feature tags of the behaviour you
   changed in every package it reaches (`-Tag`, at most 3 per run). Never a whole suite. Prefer not to
   pipe the output through a filter: a pipe hides `test.ps1`'s exit code, so a piped run counts only
   when its output still ends with `test.ps1`'s own `Total: N | Passed: N | Failed: 0` line for every
   `test.ps1` call (`| tail` keeps it; `| head`, `| grep` and `Select-String` drop it). Code no
   `test.ps1` reaches (the `datrix/scripts` tree hosts no test suite) is proven by its gate
   (`*-gate.ps1`, `-Only <check>` to target it; never `-SelfTest`/`-HarnessSelfTest`): that run
   counts when its output keeps the gate's last line `[GATE] <name> PASSED exit=0` for every gate
   call. Your **last** `test.ps1` or gate run must pass: under `CLOSE: script` the script reads it
   from the session log and keeps the finding when it failed, never ran, or proved nothing.
   **Under `CLOSE: script` other finding sessions edit the same tree beside yours** (the script runs a
   batch of them side by side). Their half-made edits can reach your runs, in a package they are
   changing or one yours imports. A failure in your own run is yours only when its traceback frames,
   or the symbols and fixtures it names (`find_references`), reach a file you wrote. One that does not
   is another session's unfinished work: do not investigate, fix or loosen it, and write **no** findings
   file for it (it may be gone when that session ends); say so in your reply and carry on — the
   script's own runs judge it on the still tree. A run that dies with `Could not acquire package lock`
   lost the venv install-check lock to another session's run and ran no test: run it again. Never take
   over another session's `.test_results` run.
   **Your own runs are not the whole proof for package code.** Under `CLOSE: script`, after every
   session of the batch has replied, the script derives the related tests from the files you wrote and
   runs them on the still tree: the test files you wrote, and the other test files of every package
   that name the code you changed. If any fails, the script resumes this session with the output, and
   no other session edits while you repair; fix the cause and reply again. A failure there that your
   change cannot have caused (its frames and named symbols never reach a file you wrote) was red
   before you or was broken by another session's finished fix: do not investigate, fix or loosen it;
   write a findings file for it and reply `Finding fix: BLOCKED B4` with the failing ids and the
   frames that prove your change is not in them.
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
unrelated → a new findings file (execution-contract §5A). Do not edit this finding to record it
(only the `UPDATED` rewrite of step 2 edits it).

## Reply

What changed (`file:line`) and the test commands you ran and what they printed. End with exactly one line:

- `Finding fix: ALREADY RESOLVED` — every defect is gone from the code; you changed nothing;
- `Finding fix: DONE` — every defect fixed, its test landed, your last test run green, docs updated;
- `Finding fix: UPDATED` — step 2's growth case: what could be fixed is fixed and tested, the finding
  now holds only what is left and what it needs, with its `Needs Jon` line; the script checks that
  the file changed and carries the line; or
- `Finding fix: BLOCKED B<n>` — with the four-part proof above it (verbatim error, the fix you
  attempted at `file:line` and ran, why it failed, the code). A decision only Jon can make is B2:
  state both designs and your recommendation. Fix every defect the block does not touch first, and
  leave the finding in place.
