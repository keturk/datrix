#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Count calls to named functions (and subprocess launches) while one workload runs in-process.

.DESCRIPTION
 Runs lib\call_count.py in the shared venv. The workload is one `datrix generate` of -Source in
 -Language, or importing the -Import modules. Counters are installed before any workload module
 loads, so names bound at import time are counted too. Prints the counts, the wall time and one
 verdict line; -Expect bounds make it exit 1 when a count is out of bounds. A self-test of the
 counter runs first on every invocation (exit 2 if it fails).

.PARAMETER Source
 system.dtrx (or project folder) to generate. Needs -Language.

.PARAMETER Language
 Generation language: any registered datrix.languages target.

.PARAMETER Import
 Comma-separated modules to import instead of generating.

.PARAMETER Count
 Comma-separated targets, module:qualname (e.g. importlib.metadata:entry_points).

.PARAMETER Expect
 Comma-separated bounds <target><op><n>, op one of <=, ==, >= ("subprocess" names the launch count).

.PARAMETER Json
 Also write the result JSON to this path.

.PARAMETER SelfTest
 Run only the counter self-test.

.EXAMPLE
 .\call-count.ps1 -Source datrix/examples/03-domains/ecommerce/system.dtrx -Language python -Count "importlib.metadata:entry_points" -Expect "importlib.metadata:entry_points<=5"

.EXAMPLE
 .\call-count.ps1 -Import datrix_codegen_aws -Count "datrix_codegen_kernel.dgen.compiler:generator_definition_file" -Expect "datrix_codegen_kernel.dgen.compiler:generator_definition_file==0"
#>

[CmdletBinding()]
param(
 [string]$Source,
 [string]$Language,
 [string]$Import,
 [string]$Count,
 [string]$Expect,
 [string]$Json,
 [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($Source) { $pythonArgs += @("--source", $Source) }
if ($Language) { $pythonArgs += @("--language", $Language) }
if ($Import) { $pythonArgs += @("--import-modules", $Import) }
if ($Count) { $pythonArgs += @("--count", $Count) }
if ($Expect) { $pythonArgs += @("--expect", $Expect) }
if ($Json) { $pythonArgs += @("--json", $Json) }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\call_count.py") -Arguments $pythonArgs -RequirePackages)
