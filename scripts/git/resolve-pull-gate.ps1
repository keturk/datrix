#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Repo-level gate for the pull-over-local-work script (lib\resolve_pull_gate.py).

.DESCRIPTION
    Activates the Datrix virtual environment and runs lib\resolve_pull_gate.py, which builds an
    origin repository and a clone of it in temporary directories and runs
    scripts/git/lib/resolve_pull.py over the clone: the clean reapply shelving only the overlap, a
    conflict left with its packet, the finish refusing markers and dropped local lines, a set-aside
    untracked file, a line-ending-only overlap, the diff3 parser, and the merge draft checked against
    both sides (against a real loopback model server). No real checkout is touched.

    Exit codes:
      0 = every check passed
      1 = at least one check (or the harness self-test) failed
      2 = usage error

.PARAMETER Only
    Run only the checks whose function name starts with this prefix (e.g. check_conflict).

.PARAMETER HarnessSelfTest
    Run one intentionally-failing dummy check and confirm it is reported [FAIL].

.PARAMETER SelfTest
    Run the harness self-test (the form gate runners call).

.PARAMETER Dbg
    Print the python invocation before running.

.EXAMPLE
    .\resolve-pull-gate.ps1
#>

[CmdletBinding()]
param(
    [Parameter()] [string]$Only = "",
    [Parameter()] [switch]$HarnessSelfTest,
    [Parameter()] [switch]$SelfTest,
    [Parameter()] [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($HarnessSelfTest) { $pythonArgs += "--harness-self-test" }
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($Only) { $pythonArgs += @("--only", $Only) }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\resolve_pull_gate.py") -Arguments $pythonArgs -Gate "resolve-pull" -ShowCommand:$Dbg)
