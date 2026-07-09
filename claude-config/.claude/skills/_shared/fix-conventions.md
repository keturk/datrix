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

## Runaway Fix Detection

If at any point you notice:
- Modified more than **double** the estimated number of files
- Working for **more than 3 tool-call rounds** without completing
- Simple fix revealed **cascading issues** in other files
- About to modify code **outside stated scope**

**STOP immediately:**
```
Fix is growing beyond estimate. Current state:
- Originally estimated: [scope]
- Actually touching: [what's grown]
- Reason for growth: [why]

Recommend: [continue / revert and rethink / split into smaller tasks]
```

## Fix Introduced a New Failure

If running tests after a fix reveals a **NEW** failure (not the original issue), do NOT immediately fix it. STOP and report:
```
Fix introduced a new failure:
- Original issue: [what was fixed]
- New failure: [what broke]
- My assessment: [related to my change, or different issue?]

Options:
1. Investigate the new failure (may expand scope)
2. Revert my change and rethink
3. Keep the fix, document new failure as separate issue
```
**WAIT** for user decision.

## Cross-Package Handoff

The package that owns the failing generator/code identifies which skill to hand off to. **Never reach across package boundaries yourself** — report the finding and hand off to the owning package's fix skill.

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
