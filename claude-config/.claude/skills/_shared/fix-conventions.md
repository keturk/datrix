# Fix Conventions (shared) — referenced by /fix, /fix-issue, /fix-bug-report, /fix-tests, /fix-generation, /troubleshoot-and-fix, /troubleshoot-generated, /codegen-fix-loop

Shared conventions used across the fix/troubleshoot skill family. The invoking skill's own scope, phases, and package-specific detail live in its own `SKILL.md` — this doc holds only the parts that were duplicated verbatim across multiple skills.

## Documentation Quick Reference

Full index with "When to use" guidance: `d:\datrix\datrix\docs\doc_index.md`.

**Essential reads (MANDATORY before starting):**
- `d:\datrix\datrix-common\docs\contributing\ai-agent-rules.md` → Core rules, STOP AND THINK principle
- `d:\datrix\datrix\docs\architecture\architecture-overview.md` → System architecture
- `d:\datrix\datrix\docs\architecture\design-principles.md` → Design philosophy

**Quick refs:**
- `d:\datrix\datrix\docs\architecture\architecture-cheat-sheet.md`
- `d:\datrix\datrix\docs\architecture\design-principles-cheat-sheet.md`

### Project Structure

Read `d:\datrix\{package-name}\.project-structure.md`. Regenerate if missing: `powershell -File "d:/datrix/datrix/scripts/dev/project-structure.ps1" {package-name}`.

> **Governed by `.claude/skills/_shared/execution-contract.md`.** Default outcome: *the problem is fixed*. Stopping is licensed only by a proven B1–B4 blocker with the four-part proof.

## Runaway Fix Detection — a re-diagnosis trigger, not an exit

These are signals that your **model of the root cause is probably wrong**:
- Modified more than **double** the estimated number of files
- Simple fix revealed **cascading issues** in other files
- You are patching the same symptom in more than one place

**They mean: stop *patching* and re-diagnose.** They do **not** mean stop working.

Go back to the error text, find the *single* upstream cause that explains all the symptoms, and fix it there. A fix that sprawls across many files is usually one correct fix wearing a disguise — find it. If a genuine architectural fork emerges that you cannot defensibly decide, **escalate** (`decision-escalation-protocol.md`) — escalation continues the work.

Scope growth alone is **never** a reason to stop: an estimate is a prediction, not a permission slip. Report the expansion and carry on. Only propose a split **pre-flight** (before starting), per CLAUDE.md § Scope: Expansion, Not Abandonment.

## Fix Introduced a New Failure — it is yours; fix it

A regression you introduced is **not a new topic requiring authorization.** It is the unfinished half of the job you are already doing.

Read the error text, trace it, fix it at the root cause, re-run. A new failure usually means your model of the root cause was **wrong** — treat it as evidence and re-diagnose, not as grounds for a footnote.

**Never:**
- **Revert** — CLAUDE.md forbids git reverts outright.
- **"Keep the fix, document the new failure as a separate issue"** — shipping a known regression with a note attached is precisely the workaround this repo bans.
- **Stop and wait for permission to finish your own job.**

## Cross-Package Handoff — routing, not an exit

The owning package's fix skill carries the package-specific context, so route the fix **through** it. That is what "handoff" means here.

**Handoff is a routing mechanism, never a way to put the problem down.** "This lives in another package, so it isn't mine" is not a blocker — it is one of the dodges the execution contract exists to eliminate. Concretely:

- **In an interactive session:** invoke the owning package's fix skill and **see the fix through to green**. You are still the one accountable for the outcome.
- **In an orchestrated run:** follow the root cause into the owning package and fix it there (per the contract's scope-expansion rule), or — if a `PARALLEL_WAVE` lock prevents it — return `EXPANSION_REQUIRED` naming the files. Never return BLOCKED for "wrong package."
- **Mind the cross-surface impact rule** (CLAUDE.md): a shared-layer fix must pass **every** consuming package's suite, not just the one you started in.

Reporting a cross-package finding and stopping there is **not** an outcome.

| `{generator}` / owning package | Fix skill (cross-package handoff) |
|---|---|
| `python` → `datrix-codegen-python` | `/fix-codegen-python` |
| `typescript` → `datrix-codegen-typescript` | `/fix-codegen-typescript` |
| `docker` → `datrix-codegen-docker` | `/fix-codegen-docker` |
| `sql` → `datrix-codegen-sql` | `/fix-codegen-sql` |
| `aws` → `datrix-codegen-aws` | `/fix-codegen-aws` |
| `azure` → `datrix-codegen-azure` | `/fix-codegen-azure` |
| `component` → `datrix-codegen-component` | `/fix-codegen-component` |
| (shared codegen base) → `datrix-codegen-common` | `/fix-codegen-common` |

Config resolution and `.dcfg` loading live in `datrix-common` / `datrix-cli` — failures in `Unable to resolve ... config` originate there or in the project's config tree (investigate both sides before deciding which owns the fix).

## Issue Report Format (LOW confidence / cannot fix)

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
