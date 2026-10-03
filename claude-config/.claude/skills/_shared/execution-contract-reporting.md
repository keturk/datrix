# Execution Contract — Findings, Report Vocabulary, No Design-Doc Citations (§5A, §7, §7A)

Part of the [execution contract](./execution-contract.md); section numbers are stable and cited by number across the repo.

**Read when:** you noticed something that is not yours to fix now and must write a findings file (§5A); you are about to write a report, a `## How Solved`, or an `## Implementation Notes` section, or a stop gate refused one (§7); you are about to write a code comment, docstring, committed doc, commit message or PR body (§7A).

---

## 5A. Findings files — nothing you notice is dropped

Some things you notice are not yours to fix now:

- a defect whose fix would need its own design (§5 above);
- a design flaw, a wrong or risky pattern, or a gap in a doc, test, or tool;
- a defect on a surface you did **not** touch, noticed in passing.

Each one gets a **findings file**. Ignoring it, or mentioning it only in your reply, is not an
outcome. Write the file, then carry on with your own task. A findings file is never a reason to
stop, and it never replaces fixing a small defect on a surface you touched. That is still §5
outcome 1.

**Where.** `d:\datrix\reports\finding\`, one file per issue, named
`YYYYMMDD-HHMMSS-<short-kebab-slug>.md` from the current local time (e.g.
`20260927-141503-compose-env-key-never-supplied.md`). Get the time from the shell
(`Get-Date -Format yyyyMMdd-HHmmss`). Create the folder if it is missing. Write it with the
`Write` tool.

**No search first.** Do not read or search the folder for an existing entry. Duplicates are fine;
`/consolidate-findings` merges them later.

**Content.** Brief: enough for someone with no context to understand and fix the issue, and no
more. Aim for under 30 lines.

```markdown
# <one-line statement of the issue>

- **Found:** <YYYY-MM-DD HH:MM> while <the task you were doing, one line>
- **Where:** <repo/path/file.py:123> (every location you saw)
- **Kind:** bug | design flaw | security | test gap | doc drift | tooling | other

## Issue
<2-5 sentences: what is wrong and the evidence you saw — a line you read, an error you captured.>

## Impact
<1-3 sentences: what breaks, for whom, and when.>

## Suggested direction
<Optional, 1-3 lines. Omit it if you do not know.>
```

State only what you saw. A guess is labelled as a guess. The file sits outside every repo, but
treat it as shareable anyway: no secrets, credentials, or customer data.

**Report it.** Cite the file path in your reply or report, e.g.
`Finding: d:\datrix\reports\finding\20260927-141503-compose-env-key-never-supplied.md`. The stop
gates accept that path as a disposition, the same as a filed task path.

---

## 7. Banned report vocabulary

These phrases must **never** appear in an agent report, a `## How Solved`, or an
`## Implementation Notes` section unless immediately followed by a valid §3 blocker proof, a §5
filed task ID, or a §5A findings file path:

```
out of scope · outside the scope · not part of this task · beyond the scope
pre-existing (as an excuse) · categorically behavioral · environmental issue
should be tracked separately · left as-is · left for a follow-up · future work
would require broader changes · someone else's · not my file · deferred
partial · workaround · dual path · not yet wired · remains unchanged · TODO
```

Two further families are banned outright — they do not describe *whose* work it is, they describe
shipping the wrong work. A proof or a task ID does **not** excuse either one:

```
EXPEDIENT (§14):  quick fix · temporary fix · interim fix · stopgap · band-aid
                  minimal change to get it green · for now · good enough for now
                  harden it later · revisit this later · proper fix can come later
                  to save context/tokens/budget · smallest thing that unblocks

DOWNGRADE (§13):  disabled the auth check · relaxed the validation · loosened CORS
                  turned off TLS verification · bypassed authorization
                  hardcoded the credential · less secure but simpler · insecure default
```

A `SubagentStop` hook greps for these, and the always-on `Stop` gate greps the main loop for the
same two families. A hit without an accompanying proof or task ID marks the report **invalid** and
the task **not complete** — regardless of test-suite color.

This is not a vocabulary game: **do not evade the grep by rephrasing.** Rephrasing a dodge to slip
past the check is a worse offense than the dodge, because it is deliberate. The rule is the
*behavior*, not the wordlist.

---

## 7A. Never cite a design doc or task file in a committed artifact

Design docs (`design/`) and task files are `.gitignored` and authored on two machines, so their
numbering collides (two different `044-…` docs, same-numbered tasks) and none of them exists after
a clone. **A reference to one from anything committed is a dangling pointer** — it points at the
wrong artifact, or nothing, on another machine.

So a design-doc or task-file number, filename, ID, or path must **never** appear in: code comments,
docstrings, committed documentation (`docs/`, READMEs), commit messages, or PR bodies. State *what*
the code does and *why* — never "implements design 044-x" or "per task 03-12". This is exempt only
for design/task files referencing *each other* (`Design reference:`, `Depends on:`): that is
internal, gitignored orchestration machinery, not a committed artifact.
