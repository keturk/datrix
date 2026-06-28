---
description: Analyze project bug reports, classify as app-definition or generator-level, fix root causes, and update reports with resolution
model: claude-opus-4-8
---

# Fix Bug Report

**Reasoning effort: HIGH.** Apply STOP AND THINK on every bug — read the generator/template/transformer and the offending app definition before forming a hypothesis. One correct root-cause fix beats five quick patches.

Analyze structured bug reports, classify each as an app-definition fix or a generator-level fix, implement the appropriate changes, and update each bug report with the resolution.

## How to Invoke

```
/fix-bug-report D:\<project-repo>\.bug-report\2026-05-29-some-bug.md
/fix-bug-report D:\<project-repo>\.bug-report\bug-1.md D:\<project-repo>\.bug-report\bug-2.md
/fix-bug-report D:\<project-repo>\.bug-report\*.md
```

The argument is one or more absolute paths to bug report markdown files (or a glob pattern).

## Full Workflow

**Read the complete workflow document before proceeding:**

```
D:\<project-repo>\claude\fix-bug-report.md
```

That document contains all phases (Triage → Fix → Update → Report), classification rules, project paths, checkpoint formats, runaway detection, and anti-patterns.
