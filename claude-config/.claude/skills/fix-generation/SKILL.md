---
description: Diagnose and fix code-generation failures from a generate-results log — classify each as app-definition or generator/framework level, trace to root cause, fix, and verify by regenerating only the affected project
model: claude-sonnet-4-6
---

# Fix Generation

Diagnose and fix **generation-time** failures captured in a `generate-results-*.log` produced by `generate.ps1`. These are failures of the generation pipeline itself (parse → transform → generate), **not** test failures of already-generated code. For test failures use `/troubleshoot-and-fix` or `/fix-codegen-*` instead.

**Reasoning effort: HIGH.** Apply STOP AND THINK on every cluster — read the generator/template/transformer and the offending `.dtrx`/`.dcfg` before forming a hypothesis. One correct root-cause fix beats five quick patches. Generation failures fan out: a single root cause typically fails dozens of projects with an identical signature, so misdiagnosing one cluster wastes the whole batch.

**Two failure classes (every cluster is exactly one):**
1. **App-definition** — the generated project's own source is wrong or incomplete (missing `.dcfg`, invalid `.dtrx`, semantic violation in user-defined entities/services). Fix the project source (a framework example under `datrix/examples/...`).
2. **Generator / framework** — the generator, template, transformer, or config resolver crashes or emits invalid output. Fix the framework codegen package source/template.

Deciding **which** class a cluster belongs to is the central judgment call — see [Classification](#classification).

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

For complete documentation index with "When to use" guidance, see [doc_index.md](../../../../../datrix/docs/doc_index.md).

**Essential reads (MANDATORY before starting):**
- [ai-agent-rules.md](../../../../../datrix-common/docs/contributing/ai-agent-rules.md) → Core rules, STOP AND THINK principle
- [architecture-overview.md](../../../../../datrix/docs/architecture/architecture-overview.md) → Pipeline stages and where generation can fail

**Quick refs:**
- [architecture-cheat-sheet.md](../../../../../datrix/docs/architecture/architecture-cheat-sheet.md)
- [design-principles-cheat-sheet.md](../../../../../datrix/docs/architecture/design-principles-cheat-sheet.md)

**Generation scripts (READ BEFORE running any datrix script):**
- [generate.ps1 quick reference](../../../../../datrix/scripts/dev/quick-reference.md) → Code Generation section. Verify every parameter you pass against it (a pre-tool hook enforces this).

### Project Structure
Read `d:\datrix\{package-name}\.project-structure.md` for the package you will modify. Regenerate if missing: `powershell -File "d:/datrix/datrix/scripts/dev/project-structure.ps1" {package-name}`.

## Scope

- **Fix target:** generator source, templates, transformers, config resolvers, OR the generated project's `.dtrx`/`.dcfg`/config — depending on classification. **Never** edit files under `.generated/` or `.projects/` (regenerating overwrites them).
- **Language:** confirm Python vs TypeScript from the **Output** path in the log (`...\python\...` vs `...\typescript\...`). Do NOT cross languages.
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
| `docker` | `datrix-codegen-docker` | `/fix-codegen-docker` |
| `sql` | `datrix-codegen-sql` | `/fix-codegen-sql` |
| `aws` | `datrix-codegen-aws` | `/fix-codegen-aws` |
| `azure` | `datrix-codegen-azure` | `/fix-codegen-azure` |
| `component` | `datrix-codegen-component` | `/fix-codegen-component` |
| (shared codegen base) | `datrix-codegen-common` | `/fix-codegen-common` |

Config resolution and `.dcfg` loading live in `datrix-common` / `datrix-cli` — failures in `Unable to resolve ... config` originate there or in the project's config tree (see Classification).

### Generation / Regeneration Commands

**ALWAYS verify parameters against `datrix/scripts/dev/quick-reference.md` before running** (a pre-tool hook blocks the call otherwise). Framework examples are generated with `generate.ps1` (run from bash with `powershell -File`):

| Target | Command |
|---|---|
| **One example** | `powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" "{source.dtrx}" -L {python\|typescript}` |
| **Foundation group** | `powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" -TestSet foundation -L python` |
| **Domains group** | `powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" -Domains -L python` |
| **Non-foundation group** | `powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" -TestSet non-foundation -L python` |
| **Named test set** | `powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" -TestSet {set-name} -L python` |
| **All examples** | `powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" -All -L python` |
| **Debug logging** | append `-Dbg` |

`-L`/`-Runtime`/`-Provider` are output-path selectors only; the real language/runtime/provider come from project config. Use `-ConfigProfile {test\|staging\|production}` to select a non-default profile.

### Triage Helper (optional, fast pre-clustering)

`triage-failures.ps1` auto-detects the generate format and groups failures by likely root cause into a Markdown report:

```bash
powershell -File "d:/datrix/datrix/scripts/dev/triage-failures.ps1" "{log-path}" -Format generate -OutputFile "D:\datrix\.test-output\generation-triage.md"
```

Use it to get an initial cluster count quickly, then verify clusters yourself by reading the log — do not trust the grouping blindly.

### Generation Status Helper

`status-generation.ps1` reports which projects succeeded/failed from the latest log (no parameters):
```bash
powershell -File "d:/datrix/datrix/scripts/dev/status-generation.ps1"
```

---

## Workflow

### Step 1: Parse the Log

1. **Read the log** at the provided path (or the latest `generate-results-*.log` if none given).
2. For each `=== Detailed output for {name} ===` block whose footer is `Failed`, extract:
   - `name`, `Source` (`.dtrx` path), `Output` (→ language and output surface), `{generator}` from `stage=generate:`, and the full `Pipeline error:` message.
3. **Skip** every `Success` project entirely.

### Step 2: Cluster by Error Signature

Normalize each `Pipeline error` message (replace project-specific names/paths with `*`) and group identical signatures. A cluster = one probable root cause spanning many projects.

> Example: 30 projects each failing with `Generator 'docker': load` collapse to **one** cluster.

**If more than 5 distinct clusters:** STOP and propose splitting into multiple sessions.

### Step 3: Classify Each Cluster

For each cluster decide **app-definition** vs **generator/framework** — see [Classification](#classification) for the decision rules. Confidence required: be explicit (HIGH / MEDIUM / LOW) and justify.

### Step 4: Root Cause Analysis (STOP AND THINK)

Pick the cluster representative (one project) and trace end to end:

**For generator/framework clusters:**
1. Open the owning package (from the mapping table) and read its `.project-structure.md`.
2. Locate the generator entry point and the failing phase named in the error (e.g. `load`). Read the actual code — do not guess what `'docker': load` means.
3. Trace: `.dtrx` → parser → transformer → generator phase → template/output. Identify the exact line that raises or emits wrong output.
4. Build a causal chain from DSL input to the failure.

**For app-definition clusters:**
1. Open the project's `Source` `.dtrx` and its config tree (`config/...`, `.dcfg` files) under the project directory.
2. Confirm what is genuinely missing or invalid vs. what the generator wrongly demands.
3. **Critical check:** a "config not found" can be either class. If the project legitimately declares a feature that *requires* the config, the project is missing the file (app-definition). If the generator demands a config that the DSL never opted into (or should synthesize a default for), the generator is wrong (framework). Read both sides before deciding.

### Step 5: Confidence Gate

- **HIGH on all clusters** → proceed to fix.
- **MEDIUM on any** → present diagnosis and WAIT for Jon's approval.
- **LOW on any** → write an issue report to `d:\datrix\issues\codegen-issue-{timestamp}.md` (format below) and STOP for that cluster.

### Step 6: Fix (one cluster at a time)

1. **Read the file(s) to modify** before editing.
2. Make the **smallest** root-cause edit. Follow CLAUDE.md code standards (type hints, no `Any`, named constants, cognitive complexity ≤15, %-style logging, error messages with what/expected/valid/fix).
3. **No debug scatter**, no placeholders, no silent fallbacks, no workarounds.
4. Update any logic-map markers (`@canonical`, `@pattern`, `@boundary`, `@invariant`) on modified code.
5. **Cross-package handoff:** if the root cause is in a package different from the one you're scoped to, do NOT reach across — report it and hand off to that package's `/fix-codegen-*` skill (per the mapping table).

### Step 7: Verify by Regenerating the Affected Projects — ONE BY ONE

**Always regenerate one project/example at a time.** When a fix touches more than one failing project/example, verify each individually by regenerating its own `Source` — **never** run a whole group or `-All` to verify. Per-project regeneration isolates which projects the fix actually repaired, keeps a single new failure from being buried in a batch run, and avoids burning time re-running already-passing projects. Group/`-All` runs are reserved for a final full sweep that Jon explicitly requests — not for verification here.

Choose the regeneration command from each failing project's `Source` / `Output` (see [Generation / Regeneration Commands](#generation--regeneration-commands)):

- **Framework example** → regenerate that single `Source`, one at a time:
  `powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" "{source-dtrx-path}" -L {language}`
  If the cluster's root cause spans several examples, loop over them individually — regenerate the first, confirm SUCCESS, then the next, and so on. Do **NOT** use `-TestSet` / `-Domains` / `-All` to verify a fix.

Assess after **each** project's regeneration:
- **Generation succeeds** → fix confirmed for that project. Move to the next affected project.
- **Same error** → fix incomplete; investigate deeper (max 3 attempts per cluster).
- **Different error** → fix introduced a regression or uncovered a second root cause; reassess.

Confirm **every** affected project regenerates successfully before marking the cluster done — a fix that repairs the representative but not its siblings is not complete.

Then run the debug-artifact check on any modified package:
```bash
powershell -File "d:/datrix/datrix/scripts/dev/check-debug-artifacts.ps1" {package-name}
```

### Step 8: Report

```
FIX-GENERATION COMPLETE

Log: {log path}
Failed projects: {N} → Clusters: {C}

Clusters fixed:
1. [{class}] {normalized signature} ({K} projects) — fixed at {file:line} — {what changed}
2. [{class}] ...

Verification:
- Regenerated: {command(s) used} → {SUCCESS/FAIL}
- Debug-artifact check: CLEAN / FOUND {...}

Unresolved (if any):
- Cluster #{id}: {reason / handed off to /fix-codegen-X / issue report path}
```

---

## Classification

| Signal in `Pipeline error` | Likely class | Fix location |
|---|---|---|
| `Configuration file '...' not found` / `Unable to resolve ... config` | **Either** — investigate both sides | Project `config/` tree **or** config resolver (`datrix-common`/`datrix-cli`) |
| Jinja2 `TemplateError` / `UndefinedError` / render traceback | Generator/framework | Template + the generator that builds its context |
| Python exception inside a `datrix_codegen_*` frame (`AttributeError`, `KeyError`, `TypeError`) | Generator/framework | Generator/transformer source |
| `Generator '{name}': {phase}` with no further detail | Generator/framework | The named generator's `{phase}` step |
| Tree-sitter parse error / syntax error in `.dtrx` | App-definition | The project `.dtrx` |
| Semantic validation error naming a user-defined entity/service/field | App-definition | The project `.dtrx` |
| Unsupported DSL construct ("not yet implemented") | Generator/framework (missing feature) | Generator — or STOP and report if out of scope |

**Decision rule:** when a message could be either class, read **both** the project source and the generator/resolver code before deciding. The deciding question is: *did the DSL ask for something the framework should have honored, or did the project fail to provide something the DSL genuinely requires?*

### Issue Report Format (LOW confidence / cannot fix)

Write to `d:\datrix\issues\codegen-issue-{timestamp}.md`:

```markdown
# Codegen Issue: {title}

**Date:** {date}
**Log:** {log path}
**Cluster signature:** {normalized error}
**Affected projects:** {count} ({list})
**Confidence:** LOW

## Failure
{representative Pipeline error message}

## Investigation
{generator/template/project files examined; why root cause is unclear}

## Recommendation
{manual steps; candidate root causes to explore}
```

---

## Abort Conditions

STOP immediately if:
- More than **5 distinct clusters** — propose splitting.
- A fix would modify code **outside the declared language/package scope** — hand off instead.
- More than **3 attempts** on a single cluster without convergence.
- A fix reveals **cascading issues** in unrelated subsystems.
- Regenerating the representative produces **new, unrelated** failures.

On abort, write a partial issue report and report what was diagnosed, attempted, and what remains.

## Anti-Patterns

- **NO editing generated output** under `.generated/` or `.projects/` — fix the generator/template/project source; regeneration overwrites it.
- **NO over-regenerating to verify** — regenerate **one project/example at a time** (a project = one `system.dtrx`; there is no single-service generation mode, so a single-service change still regenerates that whole project — CLAUDE.md); never run a group (`-TestSet`/`-Domains`) or `-All` to verify a fix. When several projects are affected, verify each individually, one by one.
- **NO running a datrix script without checking** `datrix/scripts/dev/quick-reference.md` first — a pre-tool hook enforces this.
- **NO exploring the repo from scratch** — read `.project-structure.md` and the context above.
- **NO trusting triage grouping blindly** — confirm clusters against the raw log.
- **NO cross-package fixes** — hand off to the owning package's `/fix-codegen-*` skill.
- **NO debug scatter, NO placeholders/TODOs, NO silent fallbacks, NO workarounds** (CLAUDE.md).
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule).
- **NO guessing cryptic errors** (e.g. `Generator 'docker': load`) — read the generator's code to learn what the phase does.
```