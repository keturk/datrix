#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Review task files with the Task Review System (lib\review.py).

.DESCRIPTION
 Activates the Datrix virtual environment and runs lib\review.py: Tier 1 (one task at a
 time) and, per review/config.toml, Tier 2 (the whole phase), both on local model servers.
 Every argument is passed through unchanged, so the flags are review.py's own (--task,
 --phase, --verify, --tier2, --tier2-on-threshold, --tier2-phase-gate, --config,
 --local-machine, --local-model). See quick-reference.md for the exit codes.

.EXAMPLE
 .\review.ps1 --phase <NN> --tier2-phase-gate

.EXAMPLE
 .\review.ps1 --task <path to one task file>
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ReviewArguments
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @(if ($ReviewArguments) { $ReviewArguments } else { @() })
exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\review.py") -Arguments $pythonArgs)
