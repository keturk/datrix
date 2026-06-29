---
description: Produce an evidence-grounded analysis report on a user-supplied target (a package, design doc, feature, subsystem, or path) under d:\datrix\reports. Reads the mandatory Datrix orientation docs first, then analyzes the target with zero assumptions — every claim cited to a file and line read directly. Use when the user asks to "create a report", "write a report", "analyze X and report", or wants a documented, citable investigation of how some part of Datrix works.
model: claude-opus-4-8
---

# Create Report

**Reasoning effort: HIGH.** Apply STOP AND THINK throughout. Read the relevant source before forming any claim. One verified, cited statement beats five plausible-sounding inferences. This skill exists to produce a report a reader can *trust* — so the bar is: every factual statement is backed by something you read directly, or it is explicitly flagged as unknown.

Produce a detailed, evidence-grounded analysis report on a **user-supplied target** and write it as a Markdown file under `d:\datrix\reports`. The target is whatever the user names when invoking — a package (`datrix-codegen-azure`), a subsystem (secrets generation), a design doc, a feature, a behavior, or a path.

## When to Use

- User says "create a report on X", "write me a report about X", "analyze X and produce a report"
- User wants a documented, citable investigation they can keep and re-read
- User wants to understand how some part of Datrix works, with evidence

## How to Invoke

```
/create-report <target>
```

Examples: `/create-report how datrix-codegen-azure renders Key Vault references`, `/create-report the .dtrx parsing pipeline`, `/create-report design/03-pubsub-amqp.md`.

If no target is given, STOP and ask the user what to report on. Do not guess a subject.

## Phase 1 — Mandatory Orientation (read FIRST, every run)

Before touching the target, read these to ground yourself in how Datrix actually works. Do not skip these because the target "looks self-contained" — they define the vocabulary, boundaries, and invariants your report must respect.

1. `datrix/docs/architecture/architecture-cheat-sheet.md`
2. `datrix/docs/architecture/design-principles-cheat-sheet.md`
3. `datrix/docs/architecture/architecture-overview.md` (index — follow into its sub-docs under `datrix/docs/architecture/architecture/` as the target demands: `pipeline-and-capabilities.md`, `repository-architecture.md`, `builtin-traits-enums.md`)
4. `datrix-common/docs/contributing/ai-agent-rules.md` (index — sub-docs under `datrix-common/docs/contributing/ai-agent-rules/`: `prohibited-patterns.md`, `code-quality-standards.md`, `repo-specific-rules.md`, `canonical-imports.md`)

Per Jon's memory policy, the repo `docs/` folders are the **only** trusted knowledge store. If the target sits in a specific package, also read that package's own `docs/` before analyzing its source.

If any mandatory doc above is missing or moved, do not invent its content — note the gap and locate the real file (the architecture sub-docs live under a nested `architecture/architecture/` path; the agent-rules sub-docs under `ai-agent-rules/`).

## Phase 2 — Investigate the Target (NO assumptions)

- Read the actual source, config, templates, transformers, and generators that implement the target. Read the FULL relevant files, not excerpts you hope are representative.
- Trace behavior to its root in the code. Confirm Python vs TypeScript generator scope before describing either.
- Distinguish **what the code does** (verified by reading it) from **what you expect it does**. Only the former goes in the report as fact.
- When a claim depends on a literal, a path, a symbol, or a line — open it and confirm it exists *as stated*. Never cite a file:line you did not read.
- If the target's behavior depends on generated output, read the generator/template that emits it — not a sample of generated code, which can be stale or hand-patched.

**Zero-assumption rule:** if you cannot verify something by reading it, it is either (a) flagged as an explicit open question in the report, or (b) omitted. It never appears as an asserted fact. No "presumably", no "likely works by", no filling gaps with training-data guesses.

## Phase 3 — Verify Before Writing

Re-check the load-bearing claims of the report:
- Does each cited `file:line` still say what you claim?
- Are package boundaries respected (each `datrix-*` package owns only its surface — no cross-package or language/provider-matrix claims invented)?
- Have you separated framework behavior from any one customer project? Keep customer/project domain language out of statements about framework code.

## Phase 4 — Write the Report

Write to `d:\datrix\reports\<target-slug>-<topic>-YYYYMMDD.md` (the `reports/` folder already exists). Get today's date from the environment (it is provided in context; if unsure, run `date +%Y%m%d`). Use a short kebab-case slug derived from the target. Add `-HHMMSS` only if a same-day, same-topic file already exists.

Match the house format used by existing reports in that folder:

```markdown
# <Clear, specific title — what this report answers>

**Date:** YYYY-MM-DD
**Scope:** <exactly what is and isn't covered>
**Basis:** <which source trees / docs the findings derive from. State that every claim is cited to a file read directly and nothing is inferred from assumptions or generated output.>

---

## 1. Executive summary
<The answer up front: the key findings in a few tight paragraphs. A reader who stops here should still get the conclusion.>

---

## 2..N. <Substantive sections>
<The detailed analysis. Each non-trivial claim is followed by its evidence:>

Source: `relative/path/to/file.py:120-140`

<Include short, directly-quoted code/config snippets where they carry the point — quoted verbatim from the file, not paraphrased into pseudo-code.>

---

## Open questions / unverified
<Anything you could not confirm by reading. Be honest here — an empty list is fine only if it is genuinely empty. This section is what makes the rest trustworthy.>
```

Citation discipline: prefer `package/relative/path:line` (or the absolute `D:\datrix\...` path, as existing reports do). Every claim of fact carries a citation or lives under "Open questions".

## STOP and report instead of guessing when

- The target is ambiguous or names something you cannot locate — ask, don't assume.
- A mandatory orientation doc is missing and you'd have to invent its content.
- The investigation spans 3+ unrelated subsystems or would require chain-debugging beyond a focused report — propose narrowing the scope.
- You hit a factual unknown that materially affects the conclusion — surface it as an open question rather than papering over it.

## After Writing

Tell Jon the report path and give a one-paragraph summary of the headline finding. Do not commit or push unless asked.