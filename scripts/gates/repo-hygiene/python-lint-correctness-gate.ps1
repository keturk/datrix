#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate: pyflakes (ruff --select F) and top-level blank-line (ruff --preview
 --select E302,E305) findings are a hard zero in every package.

.DESCRIPTION
 Activates the Datrix virtual environment and runs the shared module
 datrix_scripts.python_lint_correctness (scripts/common/lib), which lints the src/ and
 tests/ trees of every workspace datrix* directory holding a pyproject.toml
 (plus the datrix showcase repo's scripts/), discovered at runtime. Each tree
 is linted from its package root so that package's own per-file-ignores
 apply, in two passes: F on stable ruff, and E302 + E305 (two blank lines
 before and after a top-level def/class), which exist only as ruff preview
 rules, with --preview. Both selections are explicit so no package config can
 hide a finding.

 HARD ZERO, NO BASELINE: any finding fails. A finding that is genuinely
 required is suppressed only by a line-level `# noqa: <code>` carrying the
 reason on the same line.

 The non-vacuity self-test runs before every scan (a planted F401 + F821 must
 be reported, a planted E302 + E305 must be reported, a clean package must
 report zero, a fixture per-file-ignores must suppress the F401 only), and the
 live run must scan at least one tree for every discovered package.

 Exit codes:
   0 = zero findings
   1 = at least one finding, or the self-test failed
   2 = usage error, or ruff could not run

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.PARAMETER Dbg
 Enable DEBUG logging and print the python invocation before running.

.EXAMPLE
 .\python-lint-correctness-gate.ps1
 Lint every package tree in the workspace.

.EXAMPLE
 .\python-lint-correctness-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($Dbg) { $pythonArgs += "--debug" }

# Shared with git/commit-and-push, so it lives in the shared scripts package and runs as a module.
exit (Invoke-DatrixPythonScript -Module "datrix_scripts.python_lint_correctness" -Arguments $pythonArgs -Gate "python-lint-correctness" -ShowCommand:$Dbg)
