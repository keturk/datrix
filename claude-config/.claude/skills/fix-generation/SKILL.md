---
description: Diagnose and fix code-generation failures from a generate-results log — one failing example at a time, in one language, verified by regenerating only that example before moving to the next
model: opus
---

# Fix Generation

Diagnose and fix **generation-time** failures captured in a `generate-results-*.log` produced by `generate.ps1`. These are failures of the generation pipeline itself (parse → transform → generate), **not** test failures of already-generated code. For test failures of already-generated code use `/fix-codegen-*` instead.

**Reasoning effort: HIGH.** Apply STOP AND THINK on every error — read the generator/template/transformer and the offending `.dtrx`/`.dcfg` before forming a hypothesis. One correct root-cause fix beats five quick patches.

**The log is a QUEUE, not a batch.** However many examples the log names, you work **exactly one at a time**: fix every issue in the current example, regenerate **only that example** until it succeeds, then take the next failing example from the **original** log. See [Step 0](#step-0-the-governing-rule--one-example-at-a-time) — it overrides everything else in this file.

**Two failure classes (every error is exactly one):**
1. **App-definition** — the generated project's own source is wrong or incomplete (missing `.dcfg`, invalid `.dtrx`, semantic violation in user-defined entities/services). Fix the project source (a framework example under `datrix/examples/...`).
2. **Generator / framework** — the generator, template, transformer, or config resolver crashes or emits invalid output. Fix the framework codegen package source/template.

Deciding **which** class an error belongs to is the central judgment call — see [Classification](#classification).

## How to Invoke

```
/fix-generation D:\datrix\.generated\.results\generate-results-20260614-235227.log
```

Minimal form (auto-detect the latest log):
```
/fix-generation
```
With no argument, use the most recent `generate-results-*.log` under `D:\datrix\.generated\.results\`.

Optional scope narrowing:
```
/fix-generation D:\datrix\.generated\.results\generate-results-20260614-235227.log

SCOPE: docker generator only
```

## Documentation Quick Reference

See `d:\datrix\.claude\skills\_shared\fix-conventions.md` for the mandatory documentation reads and the Project Structure step. Also read `d:\datrix\datrix\scripts\dev\quick-reference.md` → Code Generation section BEFORE running any datrix script — verify every parameter you pass against it (a pre-tool hook enforces this).

## Scope

- **Fix target:** generator source, templates, transformers, config resolvers, OR the generated project's `.dtrx`/`.dcfg`/config — depending on classification. **Never** edit files under `.generated/` or `.projects/` (regenerating overwrites them).
- **Language:** confirm the target language from the **Output** path segment in the log (`...\python\...`, `...\typescript\...`, `...\dotnet\...`, `...\java\...`, or any other registered `datrix.languages` target) — cross-check it against the `stage=generate:{generator}` token. Do NOT cross languages: a fix scoped to one language's generator must not touch another's. Datrix is a multi-language generator; the set of languages grows, so treat the language as whatever the Output segment/generator token says, not a fixed Python/TypeScript pair.
- **Git:** each `datrix-*` package and `datrix` itself are independent git repositories. Commits/status are per-repo.
- **No git reverts** and **no workarounds** (CLAUDE.md). Trace to root cause or STOP and report.

---

## Pre-Requisite Context (DO NOT RE-INVESTIGATE)

The following describes the generation log format, the generation commands, and conventions. Use it directly — do not spend tool calls rediscovering it.

### Generation Log Format

```
Generate Results Log
Timestamp: 2026-06-14 23:52:27
================================================================================
Log file: D:\datrix\.generated\.results\generate-results-20260614-235227.log

Running generate all...

 Source: D:\datrix\datrix\examples\01-foundation\system.dtrx
 Output: D:\datrix\.generated\python\docker-compose\local\01-foundation

=== Detailed output for foundation ===
ERROR datrix_cli.pipeline.generation pipeline_stage_failed stage=generate:docker error=Pipeline failed at stage 'generate': Generator 'docker': load duration_ms=4.64
Pipeline error: Pipeline failed at stage 'generate': Generator 'docker': load
=== End output for foundation ===

[1/48] foundation: Failed
```

Structure per project:
- ` Source:` — the `.dtrx` file that was generated (use this to **regenerate** for verification).
- ` Output:` — the output directory; the language is the path segment after `.generated\` (or after `.projects\<name>\`).
- `=== Detailed output for {name} ===` … `=== End output for {name} ===` — the full stderr/stdout for that project.
- `ERROR datrix_cli.pipeline.generation pipeline_stage_failed stage=generate:{generator} error={message} duration_ms=...` — the structured failure line. **`{generator}`** names the failing generator (docker, python, typescript, sql, …).
- `Pipeline error: {message}` — the human-readable error (often a multi-line block with "Searched locations" / "Suggestions").
- `[N/48] {name}: Failed` — per-project status footer. Only `Failed` projects need attention; skip `Success`.

### Generator → Package Mapping

The `stage=generate:{generator}` token identifies the package that owns the failing generator:

| `{generator}` | Owning package | Fix skill (cross-package handoff) |
|---|---|---|
| `python` | `datrix-codegen-python` | `/fix-codegen-python` |
| `typescript` | `datrix-codegen-typescript` | `/fix-codegen-typescript` |
| `dotnet` | `datrix-codegen-dotnet` | `/fix-codegen-dotnet` |
| `java` | `datrix-codegen-java` | `/fix-codegen-java` |
| `docker` | `datrix-codegen-docker` | `/fix-codegen-docker` |
| `sql` | `datrix-codegen-sql` | `/fix-codegen-sql` |
| `aws` | `datrix-codegen-aws` | `/fix-codegen-aws` |
| `azure` | `datrix-codegen-azure` | `/fix-codegen-azure` |
| `component` | `datrix-codegen-component` | `/fix-codegen-component` |
| (shared codegen base) | `datrix-codegen-common` | `/fix-codegen-common` |

Datrix is a multi-language, multi-platform generator — this table grows. A `{generator}` token with no row here means the table is stale, **not** that the generator is unowned: its package is `datrix-codegen-{generator}`, and its fix skill is `/fix-codegen-{generator}`.

Config resolution and `.dcfg` loading live in `datrix-common` / `datrix-cli` — failures in `Unable to resolve ... config` originate there or in the project's config tree (see Classification).

### Generation / Regeneration Commands

**ALWAYS verify parameters against `datrix/scripts/dev/quick-reference.md` before running** (a pre-tool hook blocks the call otherwise). Framework examples are generated with `generate.ps1` (run from bash with `powershell -File`):

`{lang}` below is the target language taken from the failing project's **Output** segment / `stage=generate:{generator}` token — `python`, `typescript`, `dotnet`, `java`, or any other registered `datrix.languages` target. Always regenerate with the **same** `{lang}` the project failed under.

| Target | Command |
|---|---|
| **The one example you are currently fixing** (the ONLY sanctioned form) | `powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" "{source.dtrx}" -L {lang}` |
| **Debug logging** | append `-Dbg` |

**Group generation does not exist for you.** `-All`, `-Domains`, and `-TestSet` are **hard-blocked by
`PreToolUse` → `validate-script-invocation.py`**, and the block cannot be overridden by the
`VERIFIED_AGAINST_QUICK_REFERENCE` marker. Do not attempt them, and do not go looking for a wrapper,
loop, or alternate script that gets around them. Every generation you run names **one** `.dtrx` — the
example you are currently fixing — in **one** language: the `{lang}` it failed under. Generating the
same example in the other registered languages is a separate, permission-gated question (Step 0,
rule 4), not part of verifying your fix.

`-L`/`-Language` is **mandatory** and is the real generation target (it also selects the output-path language segment — the two can never disagree). `-Runtime`/`-R` is an output-path selector only; the real runtime/provider come from each project's `config/system.dcfg` deployment block. Use `-ConfigProfile {test\|staging\|production}` to select a non-default profile.

### Triage Script (PRIMARY parse path — do not read the raw log first)

`triage-failures.ps1` parses the generate log and groups failures by likely root cause into a Markdown report:

```bash
powershell -File "d:/datrix/datrix/scripts/dev/triage-failures.ps1" "{log-path}" -Format generate -OutputFile "D:\datrix\.test-output\generation-triage.md"
```

The triage report — not the raw log — is your working input. Never read a whole multi-project log into context; read only the block of the **one example you are currently working** (Step 1).

### Generation Status Helper

`status-generation.ps1` reports which projects succeeded/failed from the latest log (no parameters):
```bash
powershell -File "d:/datrix/datrix/scripts/dev/status-generation.ps1"
```

---

## Workflow

### Step 0: THE GOVERNING RULE — one example at a time

**A log naming twenty failing examples is a queue, not a batch.** You work it strictly serially:

```
build the queue from the log (Step 1)
for each failing example, in order:
    read ONLY this example's log block
    diagnose → fix → regenerate THIS example (same language)   ← repeat until it succeeds
    it succeeds → done with it; never generate it again
    take the next failing example from the ORIGINAL log
```

Six hard rules. They are not style preferences — they are the difference between a bounded task and an open-ended sweep that consumes a week of budget.

1. **Never generate more than one example.** Every `generate.ps1` invocation you make names the `.dtrx` of the example you are currently fixing. Not a sibling, not a "related" example, not a representative of some other cluster.
2. **Fix ALL of the current example's issues before moving on.** An example commonly fails in layers — each fix surfaces the next error. Regenerating that *same* example after each fix is the one repetition this skill sanctions; keep looping on it until it generates successfully.
3. **The next example comes from the ORIGINAL log** — the one you were given. Do not re-run generation to produce a fresh log, and do not re-triage between examples. The queue was fixed at Step 1.
4. **Fix only the language that failed.** If the log shows ecommerce failing on java, you fix java. **Do not generate that example for the other registered languages** to find out whether they are affected too. Widening from one language to four is Jon's budget decision — ask in one line and wait.
5. **Never re-generate an example you already fixed.** No mid-run regression sweeps, no "let me just re-check the earlier ones", no final pass over the passing set. If a shared generation path changed and Jon wants a corpus-wide regression check, that is his call to make explicitly — it is not part of this skill.
6. **Never run group generation** — `-All`, `-Domains`, `-TestSet` are hard-blocked by `PreToolUse` → `validate-script-invocation.py` and cannot be overridden.

To prove a fix generalises — to another language, another example, or another shape — **write a test**
in the owning package. It proves the invariant permanently; a regeneration proves it once and
evaporates, at a fraction of the coverage and several times the price.

### Step 1: Triage the Log and Build the Queue (scripted — never read the whole log)

1. Run the triage script (see [Triage Script](#triage-script-primary-parse-path--do-not-read-the-raw-log-first)) on the provided log (or the latest `generate-results-*.log` if none given), then run `status-generation.ps1` for the succeeded/failed roster.
2. **Read the triage report**, not the raw log.
3. Write down the **queue**: the ordered list of `Failed` example names from the log. Order by triage group (examples sharing a signature adjacent) so a landed fix is likely to clear the next entry too — but the queue is still worked one entry at a time. **Skip** every `Success` project.
4. If the queue has more than **5 distinct failure signatures**, STOP and propose splitting into multiple sessions.

The triage grouping is a **diagnostic hint about likely shared root cause — it is not a work unit.** You never "fix a cluster"; you fix the example at the head of the queue. When a later queue entry shares the current one's signature, note it and move on: whether it is truly fixed is answered when its turn comes and you generate it, not by generating it now.

### Step 2: Take the Head of the Queue

Take the **first unfixed example** in the queue. Grep the log for its `=== Detailed output for {name} ===` block (with enough `-A` context) and extract: `name`, `Source` (`.dtrx` path), `Output` (→ language and output surface), `{generator}` from `stage=generate:`, and the full `Pipeline error:` message. Read **only** this example's block.

Everything from here to Step 6 concerns this one example.

### Step 3: Classify the Current Error

Decide **app-definition** vs **generator/framework** for this example's front-line error — see [Classification](#classification) for the decision rules. Confidence required: be explicit (HIGH / MEDIUM / LOW) and justify.

### Step 4: Root Cause Analysis (STOP AND THINK)

Trace this example's failure end to end:

**For a generator/framework error:**
1. Open the owning package (from the mapping table) and read its `.project-structure.md`.
2. Locate the generator entry point and the failing phase named in the error (e.g. `load`). Read the actual code — do not guess what `'docker': load` means.
3. Trace: `.dtrx` → parser → transformer → generator phase → template/output. Identify the exact line that raises or emits wrong output.
4. Build a causal chain from DSL input to the failure.

**For an app-definition error:**
1. Open the project's `Source` `.dtrx` and its config tree (`config/...`, `.dcfg` files) under the project directory.
2. Confirm what is genuinely missing or invalid vs. what the generator wrongly demands.
3. **Critical check:** a "config not found" can be either class. If the project legitimately declares a feature that *requires* the config, the project is missing the file (app-definition). If the generator demands a config that the DSL never opted into (or should synthesize a default for), the generator is wrong (framework). Read both sides before deciding.

### Step 5: Confidence Gate

- **HIGH** → proceed to fix.
- **MEDIUM** → present the diagnosis and WAIT for Jon's approval.
- **LOW** → write an issue report to `d:\datrix\issues\codegen-issue-{timestamp}.md` (format below), STOP on this example, and move to the next queue entry.

### Step 6: Fix, Regenerate This Example, Repeat Until It Passes

This is the inner loop. It runs on **one** example and generates **only** that example.

1. **Read the file(s) to modify** before editing.
2. Make the **smallest** root-cause edit. Follow CLAUDE.md code standards (type hints, no `Any`, named constants, cognitive complexity ≤15, %-style logging, error messages with what/expected/valid/fix).
3. **No debug scatter**, no placeholders, no silent fallbacks, no workarounds.
4. Update any logic-map markers (`@canonical`, `@pattern`, `@boundary`, `@invariant`) on modified code.
5. **Cross-package handoff:** if the root cause is in a package different from the one you're scoped to, do NOT reach across — report it and hand off to that package's `/fix-codegen-*` skill (per the mapping table).
6. **Regenerate this example only**, in the language it failed under:
   ```bash
   powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" "{source-dtrx-path}" -L {lang}
   ```
7. Assess the result:
   - **Succeeds** → this example is done. Go to Step 7.
   - **Same error** → the fix is incomplete; investigate deeper and loop (max 3 attempts on the same error before aborting this example).
   - **A different error** → this is the next layer of the *same* example. Go back to Step 3 with the new error and keep looping. Layered failures are normal and do not mean the previous fix was wrong.

**Never regenerate a different example inside this loop** — not to check whether the fix generalises, not as a regression check, not because the triage report says a sibling shares the signature. Never regenerate while the fix that unblocks the current error is still in flight: a regeneration run is expensive (`dotnet build`/formatters), and running it before the fix lands only re-proves a failure you already know about.

### Step 7: Advance the Queue

The current example generates successfully. Do **not** generate it again for any reason.

Take the next `Failed` example from the **original** log and return to Step 2. Repeat until the queue is empty.

Once the queue is empty, run the debug-artifact check on each package you modified:
```bash
powershell -File "d:/datrix/datrix/scripts/dev/check-debug-artifacts.ps1" {package-name}
```

### Step 8: Report

```
FIX-GENERATION COMPLETE

Log: {log path}
Failed examples in queue: {N}

Examples fixed (in order):
1. {example} [{lang}] — {class} — root cause at {file:line} — {what changed} — regenerated: SUCCESS
2. {example} [{lang}] — cleared by the fix for #1 (no code change) — regenerated: SUCCESS
3. ...

Verification:
- Each example above regenerated individually with its own Source; no group/-All runs.
- Debug-artifact check: CLEAN / FOUND {...}

Unresolved (if any):
- {example}: {reason / handed off to /fix-codegen-X / issue report path}
```

---

## Classification

| Signal in `Pipeline error` | Likely class | Fix location |
|---|---|---|
| `Configuration file '...' not found` / `Unable to resolve ... config` | **Either** — investigate both sides | Project `config/` tree **or** config resolver (`datrix-common`/`datrix-cli`) |
| Jinja2 `TemplateError` / `UndefinedError` / render traceback | Generator/framework | Template + the generator that builds its context |
| Python exception inside a `datrix_codegen_*` frame (`AttributeError`, `KeyError`, `TypeError`) — every generator is Python regardless of the **target** language (dotnet/java/typescript/python/…) | Generator/framework | Generator/transformer source in the owning `datrix-codegen-{generator}` package |
| `Generator '{name}': {phase}` with no further detail | Generator/framework | The named generator's `{phase}` step |
| Tree-sitter parse error / syntax error in `.dtrx` | App-definition | The project `.dtrx` |
| Semantic validation error naming a user-defined entity/service/field | App-definition | The project `.dtrx` |
| Unsupported DSL construct ("not yet implemented") | Generator/framework (missing feature) | Generator — or STOP and report if out of scope |

**Decision rule:** when a message could be either class, read **both** the project source and the generator/resolver code before deciding. The deciding question is: *did the DSL ask for something the framework should have honored, or did the project fail to provide something the DSL genuinely requires?*

### Issue Report Format (LOW confidence / cannot fix)

See `d:\datrix\.claude\skills\_shared\fix-conventions.md` for the report template. Write to `d:\datrix\issues\codegen-issue-{timestamp}.md`.

---

## Abort Conditions

STOP immediately if:
- The queue holds more than **5 distinct failure signatures** — propose splitting.
- A fix would modify code **outside the declared language/package scope** — hand off instead.
- More than **3 attempts** on the same error in the same example without convergence — write an issue report for that example and advance the queue.
- A fix reveals **cascading issues** in unrelated subsystems.

On abort, write a partial issue report and report what was diagnosed, attempted, and what remains.

## Anti-Patterns

- **NO generating more than one example** — every `generate.ps1` call names the `.dtrx` of the example you are currently fixing (Step 0, rule 1).
- **NO moving to the next example before the current one generates successfully** — an example's later errors are layers of the same example, not a reason to switch (Step 0, rule 2).
- **NO re-generating an already-fixed example** — no mid-run regression checks, no final sweep over the passing set (Step 0, rule 5).
- **NO group generation** — `-All`, `-Domains`, `-TestSet` are hard-blocked and cannot be overridden; do not seek a wrapper or loop that evades the block.
- **NO generating an example in a language it did not fail under** without asking Jon first (Step 0, rule 4).
- **NO re-running generation to produce a fresh log mid-run** — the queue comes from the original log (Step 0, rule 3).
- **NO treating a triage cluster as a work unit** — it is a hint about shared root cause; you still work the queue one example at a time.
- **NO editing generated output** under `.generated/` or `.projects/` — fix the generator/template/project source; regeneration overwrites it.
- **NO regenerating while the fix that unblocks the current error is still in flight** — it only re-proves a known failure (Step 6).
- **NO running a datrix script without checking** `datrix/scripts/dev/quick-reference.md` first — a pre-tool hook enforces this.
- **NO exploring the repo from scratch** — read `.project-structure.md` and the context above.
- **NO reading the whole generate log into context** — triage script first, then Grep only the current example's block (Steps 1–2).
- **NO cross-package fixes** — hand off to the owning package's `/fix-codegen-*` skill.
- **NO debug scatter, NO placeholders/TODOs, NO silent fallbacks, NO workarounds** (CLAUDE.md).
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule).
- **NO guessing cryptic errors** (e.g. `Generator 'docker': load`) — read the generator's code to learn what the phase does.
