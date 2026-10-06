# Execution Contract — Evidence and Static Verification (§2A, §12)

Part of the [execution contract](./execution-contract.md); section numbers are stable and cited by number across the repo.

**Read when:** you are about to guess at a cause or edit "to see if it helps" (§2A); you are about to generate, build, deploy or run something to learn whether a change works, a deploy or run just failed, you touch a producer/consumer pair, you write a matcher that claims a file is clean, or you add a step or call into an existing chain (§12).

---

## 2A. Investigate, don't guess — act on evidence, never on a hunch

**Hypothesizing is not investigating.** Guessing at a cause, changing something, and seeing if the
symptom moves is banned. "Throwing mud at the wall to see what sticks" wastes the turn and usually
fixes nothing. Every action you take must be justified by evidence you have *already gathered* —
read code, captured error text, an observed value — not by a theory you have not yet confirmed.

The rule:

- **Read to the fact before you touch anything.** The cause of a failure is discoverable by reading
  the relevant code, the error output, and the data. Find it. Do not assume what a function
  returns, what a config holds, what a symbol means, or where control flows — open the file and
  confirm it. "Never assume/fabricate — look it up" (CLAUDE.md § Core Principles) is not advice; it
  is the method.
- **A hypothesis is a question, not a license to edit.** If you have a theory, the next step is to
  *confirm or kill it with data* (read the code path, add a targeted observation, capture the real
  value) — not to apply a speculative fix and hope. Confirm first, then act once.
- **No speculative edit.** Do not change code "to see if it helps," do not fix a thing you have not
  first proven is the cause, do not try several changes at once hoping one lands. One confirmed
  root cause → one deliberate fix.
- **When you don't know, get the data — you are never stuck for lack of a guess.** The answer to
  "what's causing this?" is always another read, another captured error, another observed value —
  never a fresh guess layered on an unconfirmed one. This binds with § "No second hypothesis
  without the error text": if the evidence is invisible, your first action is to *make it visible*,
  not to theorize around it.

An edit whose only justification is "I think this might be it" is a defect in method, whether or not
it happens to work. State the evidence that drove each change; if you cannot, you have not
investigated yet.

---

## 12. Prove it statically before you prove it at runtime

§2A says act on evidence, not on a hunch. This section says **where to go get that evidence**: the
cheapest rung that can actually falsify the claim, which is almost never a deploy.

A deployment or a runtime run is the **most expensive and latest-arriving** evidence in the repo. It
costs minutes to hours, it costs real cloud money, it reports one failure at a time, and it reports
it *after* the artifact is already out in the world. Nearly every defect it finds was sitting in a
file on disk the whole time, discoverable by reading or parsing that file. Waiting for a deploy to
tell you something a `grep` would have told you is not thoroughness — it is the slowest possible way
to be wrong.

### 12.1 The evidence ladder — start at the top, stop as soon as the question is settled

Each rung costs roughly an order of magnitude more than the one above it, and reports later:

1. **Read the source / template / config** that produces the artifact.
2. **Parse the emitted artifact** and compute over it (set difference, key census, structural query).
3. **Targeted test** in the owning package (`test.ps1 <pkg> -Specific "…"`).
4. **A repo static gate** — the scans and parity gates listed in 12.5.
5. **The tagged tests of the changed behaviour** in every package the change reaches
   (`test.ps1 <pkg-a> <pkg-b> -Tag <tag>`; `_shared/verification-strategy.md`). There is no
   whole-suite rung: no agent runs a whole package suite, ever.
6. **Generate the affected project** and inspect the output.
7. **Deploy / run it.**

**Never reach for a lower rung to answer a question an upper rung settles.** "I'll just deploy and
see" is the single most expensive sentence available to you. Conversely, do not stop at an upper rung
that *cannot* settle the question — a unit test does not prove a cloud resource name is free.

### 12.2 Every seam gets a set comparison, and the comparison lives in code

The dominant defect class in a generator is the **seam**: artifact A produces a set of names or
values, artifact B consumes a set, and **nothing compares the two**. A compose file interpolating
variables nobody supplies; a config-store key declared but never given a value; an environment file
assigning a key blank and shadowing the real value; a bicep member key the resolver spells
differently. Every one of these is a **set difference you can compute without running anything**.

So, whenever you touch a producer or a consumer:

- Name both sides explicitly — *this* code writes the keys, *that* code reads them.
- Compute `consumed − produced`. It must be empty, or every element must be explained.
- **Then put that comparison somewhere it runs by itself** — a generation-time validator in the
  owning package, or a test. A set difference you computed by hand proves today's tree; a validator
  proves every tree from now on. This is the same rule as CLAUDE.md's "to prove a fix generalises,
  write a test," applied to seams.

A validator that fails **at generation time** with the key, the producer that should have supplied
it, and the fix, is worth more than any amount of deploy-time diagnosis.

### 12.3 A runtime failure is first a static-analysis failure

When a deploy or a run fails, the fix is only half the work. The other half is a mandatory second
question:

> **What check would have caught this before the run, and where does it live?**

Land that check together with the fix. If you fix the instance and ship no check, you have
guaranteed that the next member of the same defect class also waits for a deploy to be discovered —
and you will pay the same minutes and the same money again. "Found it, you fix it" (§5) covers the
instance; this covers the class.

### 12.4 Parse structure; do not eyeball it with a regex

A matcher that cannot see what it claims to cover is worse than no matcher — it produces a confident
"clean" result and it will be believed. This has already cost a full deploy cycle here: a single-line
`grep -o '\${[^}]*}'` over a generated compose file found **10** mandatory interpolations where
**44** existed, because the YAML emitter wraps them across lines. The count was reported as fixed on
that basis.

- Use a real parser (`yaml`, `json`, Python `ast`, the tree-sitter parser) or normalize first
  (collapse whitespace) before matching.
- **Prove your matcher is non-vacuous**: check that it finds an instance you already know is there.
  A scan that can only return zero is not evidence.
- Report the census, not the verdict — "44 required variables, 44 supplied" beats "looks fine."

### 12.5 Use the checks that already exist before writing a new one

These are cheap, already maintained, and cover most cross-cutting classes. Run the ones whose surface
you touched (paths relative to `d:/datrix/datrix/scripts/`):

| Surface | Check |
|---|---|
| Python anti-patterns | `scan/semgrep.ps1` (`-ListRules`, `-Rule <name>`), `scan/libcst.ps1` |
| Layering / target-name leakage | `scan/check-import-boundaries.ps1` (`-CheckTargetLiterals`, `-CheckProviderConditionals`, `-CheckSharedVocabulary`, `-CheckSharedTargetNames`) |
| Debug scatter, stale bytecode | `scan/check-debug-artifacts.ps1`, `scan/check-python-bytecode.ps1` |
| Docs drift | `dev/check-docs.ps1`, `gates/repo-hygiene/check-docs-conformance.ps1` |
| Generated-output preservation | A test in the owning package rendering the construct and asserting its output (no stored snapshot exists — `datrix/docs/architecture/generated-output-stability.md`); cross-language presence: `gates/parity/artifact-role-parity-gate.ps1` over a complete local `.generated/` corpus |
| Realization / parity holes | `gates/parity/block-realization-parity-gate.ps1`, `gates/realization/standing-conformance-gate.ps1`, `gates/parity/supported-domain-parity-gate.ps1`, `gates/parity/observability-axis-parity-gate.ps1`, `gates/realization/gendsl-corpus-resolution-gate.ps1` |
| Scripts-tree layout, dangling script paths | `test/shared-library-gate.ps1 -Only check_scripts_tree` |
| Duplicate logic | code-index `find_canonical` / `find_symbol` (MCP tools, or `dev/code-index.ps1 -Canonical` / `-Symbol`) |

Full selection rules: `_shared/verification-strategy.md`. **Never run a standalone type-checker** —
`mypy` and equivalents are not part of verification here (CLAUDE.md § Running Python).

### 12.6 Be systematic: fix the class, not the instance

Symptom-by-symptom is how a five-minute defect becomes a five-hour deploy loop — each round trip
surfaces exactly one more instance of a class you could have enumerated in one pass.

When a defect appears, **characterize the class before fixing the instance**: what is the general
shape (a seam, a missing validator, an own-vs-shared enumeration mismatch, a blank-shadowing key),
and where else does that shape occur? Enumerate all occurrences with one static pass, then fix them
together and land the check from §12.3. One pass over the whole class beats N deploys that each
reveal one member of it.

### 12.7 An insertion is an integration — there is no "just placing a call"

Adding a step to a pipeline, a leg to a release script, a stage to a generator, a hook to a chain, or
a call between two existing functions **is an integration by default**, and it is only complete when
you have read the neighbours. A step's real contract is not its own body — it is **the postcondition
it must leave behind and the precondition the next step demands.** That contract lives in the
neighbouring code, so it cannot be established by reading the thing you inserted.

Before the insertion lands, know all three:

- **What the upstream step guarantees** when it hands over.
- **What the downstream step requires** to start — its explicit guards, its `Test-Path`s, its
  early `raise`/`Write-Error` blocks, and the assumptions its header prose states.
- **What both sides believe about any shared resource** the new step touches: which file, which
  path, which key, written by whom, on which machine. Two steps holding different answers is the
  seam of §12.2, and it is found by one `grep` for the resource name across the directory.

Two traps make this feel unnecessary at exactly the moment it is not:

- **Editing the frame is not reading the contents.** You can add a leg, renumber the banner, add a
  skip flag, and wire a probe — touching the orchestrator repeatedly — without any of those edits
  forcing you to read what a single step does. Structural familiarity is not knowledge of behavior.
- **An answer settled in a neighbouring context is not settled here.** A decision made for one
  profile, target, or environment is a *hypothesis* about this one (§2A), not a conclusion. Carrying
  it across unexamined is how an assumption enters without ever feeling like a guess. Re-derive it,
  or confirm the neighbour's code agrees — especially when a sibling file's own documentation says
  it does the opposite.
