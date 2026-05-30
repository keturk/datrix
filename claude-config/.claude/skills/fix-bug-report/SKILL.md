---
description: Analyze project bug reports, classify as app-definition or generator-level, fix root causes, regenerate, and update reports with resolution
model: opus
---

# Fix Bug Report

Analyze structured bug reports, classify each as an app-definition fix or a generator-level fix, implement the appropriate changes, regenerate the application, and update each bug report with the resolution.

## How to Invoke

```
/fix-bug-report D:\g\CurvAero\.bug-report\2026-05-29-some-bug.md
/fix-bug-report D:\g\CurvAero\.bug-report\bug-1.md D:\g\CurvAero\.bug-report\bug-2.md
/fix-bug-report D:\g\CurvAero\.bug-report\*.md
```

The argument is one or more absolute paths to bug report markdown files (or a glob pattern).

## Full Workflow

**Read the complete workflow document before proceeding:**

```
D:\datrix\datrix-projects\curvaero\claude\fix-bug-report.md
```

That document contains all phases (Triage → Fix → Regenerate → Update → Report), classification rules, project paths, checkpoint formats, runaway detection, and anti-patterns.
