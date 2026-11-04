---
description: Take ONE findings file that waits on Jon (it carries a `- **Needs Jon:**` line, written by /implement-finding when the fix needs more than the finding states), investigate whether the issue still holds and whether its options are the right ones, then discuss the decision with Jon and update the finding with it so the next /implement-finding session can act. Use when Jon asks to "discuss a finding", "go through the findings that need me", or runs /discuss-finding.
---

# Discuss Finding

`/implement-finding` fixes what a finding states and, when the correct fix needs more (a false
premise, a new capability, field, phase or diagnostic), rewrites the finding with what is needed and
adds `- **Needs Jon:** <what is awaited>`. Selection skips such a finding until the line is gone. This
skill is how the line goes: it brings Jon a decision that has already been investigated, and records
the decision in the finding. It changes no code.

**Jon asked for this discussion, so the question goes to Jon directly: do not dispatch the decision
advisor for it.** Both question gates let this skill's questions through: `AskUserQuestion`, or a
reply whose last words are the question (end it on its question mark).

## How to invoke

```
/discuss-finding                      # the first finding that waits on Jon (area order, then name)
/discuss-finding FINDING: <path>
```

Without `FINDING`, list the waiting findings with `Grep` for `^- \*\*Needs Jon:\*\*` in
`d:\datrix\findings` (files only), order them by the area order of `skill-assist.ps1 finding-select`
(python, typescript, clients, language, schema, seed, kernel, docker, aws, azure, component, tests,
tooling, docs, other folders by name, loose files last) and take the first.

## Steps

Before your first edit, read the mandatory cores and the knowledge pack of each area the finding
touches.

1. **Does it still hold?** Read the finding and its `Needs Jon` line. For every section left, read the
   code it cites at and around the cited lines (citations drift; follow symbols with the code index)
   and check each claim it makes, above all the premise the previous session called false. Run the
   cheapest check that answers (a read, a grep, a parse, a targeted test), never a deploy. If every
   defect is gone from the code, say so with the evidence, delete the finding with `finding-close`
   (below) and stop: there is nothing to discuss.
2. **Are the options the right ones?** For each decision the finding awaits, list the options the
   finding names and look for the ones it missed: what the docs and design guidelines (G1–G12,
   `design-principles.md`) settle, what the security ranking settles (the more secure option wins, and
   settles a choice by itself), what the other targets do (`multi-target-invariants.md`: one semantics
   on every target), what exists already that would solve it (code index, `find_canonical`), and what
   each option costs in files and packages (count them; no human hours). Drop an option a rule rules
   out and say which rule. If the rules leave a single answer, it is not a question: state it as your
   recommendation and say Jon can overrule it.
3. **Discuss.** Tell Jon, briefly and in this order: the finding in one sentence; whether it still
   holds, with `file:line` evidence; the decision awaited; the options that survived, each with what it
   changes and costs; your recommendation and why. Ask with `AskUserQuestion` when the options are
   discrete (recommended option first), in prose when the answer is open. Answer Jon's follow-up
   questions from the code, investigating further when he asks something you have not checked. Do not
   write the finding until Jon has decided.
4. **Record the decision.** Rewrite the finding in place so a fresh `/implement-finding` session can
   implement it without asking anything: delete the `Needs Jon` line; correct the premises the
   investigation disproved; put the chosen design in each section's `Suggested direction` (what to
   build, where, on which targets, which tests); add one line `- **Decided:** <date> — <the decision
   in one sentence, and the reason Jon gave>` beside `Keywords`/`Area`. Drop an option Jon rejected
   rather than leaving it as an alternative. No design or task number, no customer term. If the
   finding named other findings, keep those pointers true.
5. **Declined or dropped.** When Jon decides the issue is not to be fixed, delete the finding with
   `finding-close` (below) and say so; a decline is final, so write nothing in its place. When Jon
   wants more information first, keep the `Needs Jon` line, add what he asked for under the section,
   and stop.
6. **Next.** After one finding is settled, say which findings still wait (count and file names) and
   stop; the next one is a new `/discuss-finding`.

Deleting a finding goes only through the script, never `Remove-Item`:

```bash
powershell -File "d:/datrix/datrix/scripts/skill/skill-assist.ps1" finding-close --finding "<finding>"
```

Exit 0 deleted it. Exit 2 names another findings file that still points at it: repoint or drop that
pointer first.

Something else you find on the way that this finding does not need is a new findings file
(execution-contract §5A); do not edit this one to record it.

## Reply

What you found and what Jon decided, with the finding's path and the edit you made (or that you
deleted it). No recap of the discussion Jon was in.
