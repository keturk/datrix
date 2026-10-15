#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Census every whole-suite test.ps1/affected-gate.ps1 form in agent-facing instruction documents.

.DESCRIPTION
 Activates the Datrix virtual environment and runs instruction_surface.py. Scans
 claude-config/.claude/CLAUDE.md, rules/*.md and skills/**/*.md for a bare
 test.ps1 form (no -Specific/-Keyword), -All, -Rerun, or an unqualified tier
 switch, outside a <!-- forbidden-example --> context. A plain-Python self-test
 suite runs automatically, unconditionally, as step 1 of every invocation.

.PARAMETER SelfTest
 Run only the scanner's own self-test suite and exit -- skips the real census.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\instruction-surface-gate.ps1

.EXAMPLE
 .\instruction-surface-gate.ps1 -SelfTest
#>

[CmdletBinding()]
param(
    [switch]$SelfTest,
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\instruction_surface.py") -Arguments $pythonArgs -Gate "instruction-surface")
