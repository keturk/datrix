# Design Docs & Documentation Rules

Read this before implementing from a design doc, before writing to `design/`, and before
writing a commit message, PR body, code comment, or anything under a `docs/` folder.

## Design doc workflow

Docs in `design/` are numbered by priority. Read the full doc plus cross-referenced
architecture before implementing. **Design docs are scope boundaries** — do not add
unspecified features.

- Operationalize before coding: `/operationalize-design`.
- Absorb after completion: `/absorb-design` — **Jon types this one**; you cannot invoke it.
  Do not attempt it and do not report the refusal as a blocker.
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

## Security posture is settled at design time

Every design that touches auth, secrets, transport, input at a trust boundary, injection
surfaces, permissions/exposure, error and log content, crypto, or **the defaults the
generator emits on those surfaces** states its posture explicitly. An unstated posture is a
blocking open question, exactly like an unresolved alternative.

**A design may not specify a less secure option where a more secure one is available.**
A difference in security posture settles a design choice rather than creating one
(execution-contract §13) — so "Option A is simpler but unauthenticated" is not a design
alternative to weigh, it is a defect in the draft.

**And an insecure design does not become an implementer's problem.** If you are implementing
from a doc that specifies the weaker option, execution-contract §13.7 governs: say it to Jon
in one line — the weaker option, the exposure, the secure alternative — keep working
everything that does not depend on the answer, and never silently implement the weaker
option *or* silently substitute the stronger one. Do not edit the design doc to fix it.

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

**This is enforced, not advisory.** `datrix/scripts/test/customer-domain-isolation-gate.ps1`
scans every publishable file (tracked + untracked-but-not-ignored) of every framework repo
against a hashed term corpus, and `git/commit-and-push.ps1` runs the same scan over pending
changes before it stages anything — one hit aborts the whole commit run. Register a new
customer term with the gate's `-AddTerm` (it stores only a SHA-256 digest, so the term never
enters the repo it is banned from).

Two leak paths are worth knowing because they bypass anything you personally remember to
check. First, **Claude Code writes permission grants by itself**: answering a prompt with
"don't ask again" appends the literal command — customer resource names, customer checkout
paths and all — to `.claude/settings.local.json` (now gitignored) or `settings.json` (shared
and reviewed; keep customer-specific grants out of it). Second, **`commit-and-push` runs
`git add -A`**, so anything sitting in a repo directory gets committed whether or not anyone
looked at it.
