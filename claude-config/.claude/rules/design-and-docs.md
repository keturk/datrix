# Design Docs & Documentation Rules

Read this before implementing from a design doc, before writing to `design/`, and before
writing a commit message, PR body, code comment, or anything under a `docs/` folder.

## Design doc workflow

Docs in `design/` are numbered by priority. Read the full doc plus cross-referenced
architecture before implementing. **Design docs are scope boundaries** — do not add
unspecified features.

- Operationalize before coding: `/operationalize-design`.
- Absorb after completion: `/absorb-design`.
- **Never modify a design doc during implementation.**

**One exception, and it is exactly one line.** At the very end of a `/task-orchestrator`
run (its Step 4), the orchestrator rewrites a design doc's `Status:` line to `Implemented`
— and only when every task referencing that doc, across ALL phases and not just the run's,
is COMPLETED and the phase passed its test + design-conformance gates. A doc with an
outstanding task anywhere is left untouched and reported instead. The body is never edited,
no partial/in-progress status is ever written, and nothing about this licenses a mid-run
design edit.

## No investigation deferred to implementation

Resolve every factual unknown *during* design:

- external product facts (APIs, versions, endpoints, claim shapes),
- codebase facts (does this symbol/literal exist, what shape does this code assume),
- scope boundaries.

A design doc must not contain "verify during implementation", "TBD", or assumptions
presented as fact. Look it up now (web docs, source reads), cite the source, and bake the
verified value in. If something genuinely cannot be determined, that is a blocking open
question to STOP on — not a task to hand to the implementer.

## Never reference a design doc or task file in a committed artifact

Design docs (`design/`) and task files are `.gitignored` and developed on two machines, so
their numbering collides — two different `044-…` docs or same-numbered tasks can exist, and
neither is present after a clone. A reference to one from anything committed is a dangling
pointer that resolves to the wrong thing, or nothing, elsewhere.

**No design-doc or task-file number, filename, ID, or path may appear in** code comments,
docstrings, committed documentation (`docs/`, READMEs), commit messages, or PR bodies.
Describe *what* the code does and *why* — never "implements design 044-x" or "per task
03-12".

Design/task files referencing *each other* (`Design reference:`, `Depends on:`) is exempt —
that is internal, gitignored orchestration machinery, not a committed artifact. When
absorbing or citing design content into official docs, carry over the *content*, never a
pointer to the source doc.

## Project domain isolation

Customer/project domain language MUST NOT appear in framework packages (`datrix`,
`datrix-cli`, `datrix-codegen-*`, `datrix-common`, `datrix-extensions`, `datrix-language`).
No customer name, no customer-specific service names, and no terms from a customer's
business domain may leak into framework code, docs, tests, or examples.

For framework docs/tests/examples, use the neutral e-commerce domain (Product, Order,
Customer, Warehouse, Variant, LineItem) or a fictional domain.
