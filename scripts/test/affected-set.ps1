#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Derive the reverse-dependency closure of Datrix packages from actual imports.

.DESCRIPTION
 Activates the Datrix virtual environment and runs affected_set.py. Discovers
 every datrix-* package from disk (no hardcoded package list), builds the
 import graph from each package's src/, tests/, and root-level conftest.py
 plus declared pyproject.toml dependencies, and prints each requested
 package's transitive reverse-dependency closure (the packages that must
 also be tested when it changes). Writes affected-set.json to
 <workspace>\.tmp\test\ by default. A plain-Python self-test suite runs
 automatically, unconditionally, as step 1 of every invocation.

.PARAMETER Projects
 One or more package names (comma-separated or space-separated) to report
 closures for.

.PARAMETER All
 Report every discovered package's closure.

.PARAMETER Output
 Output JSON path (default <workspace>\.tmp\test\affected-set.json).

.PARAMETER SelfTest
 Run only the scanner's own self-test suite and exit -- skips the real
 derivation. The same self-test also runs automatically, unconditionally, as
 step 1 of every normal invocation.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\affected-set.ps1 -Projects datrix-language

.EXAMPLE
 .\affected-set.ps1 -All

.EXAMPLE
 .\affected-set.ps1 -SelfTest
#>

[CmdletBinding()]
param(
    [Parameter(Position=0, ValueFromRemainingArguments=$true)]
    [string[]]$Projects,

    [switch]$All,

    [string]$Output,

    [switch]$SelfTest,

    [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
foreach ($project in $Projects) {
    if ($project) { $pythonArgs += @("--projects", $project) }
}
if ($All) { $pythonArgs += "--all" }
if ($Output) { $pythonArgs += @("--output", $Output) }
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($Dbg) { $pythonArgs += "--debug" }

# Shared with the suite stamp and the affected gate, so it lives in the shared scripts package
# and runs as a module.
exit (Invoke-DatrixPythonScript -Module "datrix_scripts.affected_set" -Arguments $pythonArgs)
