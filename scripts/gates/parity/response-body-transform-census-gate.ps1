#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Response-body transform census gate.

.DESCRIPTION
 The response-bodies parity rows prove every registered language's response classes
 emit camelCase wire keys; a framework-level transform applied AFTER serialization
 (a global interceptor, a response-model setting) is invisible to them. Each
 registered language declares the regular expressions that spell such a transform in
 its framework (LanguageCapabilityDeclaration.response_body_transform_idioms). This
 gate generates the shared CQRS example once per registered language, greps the
 generated tree for them, and requires every hit to be a typed `transform_exemptions`
 entry of datrix/scripts/config/response-body-transform-exemptions.json (language,
 path suffix, matched text, reason). An unreviewed hit, a stale entry and a language
 with no declaration each fail by name; the review file is refused if it carries any
 key other than _comment and transform_exemptions.

 A census over generated text: it imports no conformance probe. Derives its language
 set from the installed `datrix.languages` entry points -- never a hardcoded literal.

 Runs a self-test on every invocation: the gate names no target, a planted transform
 line is reported at its coordinates, an exemption covers it, a stale exemption and a
 language with no declaration are reported, the review file refuses a set-aside list,
 a non-object entry and a blank reason, and fewer than two languages refuse the run.

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the self-test and skip generation.

.EXAMPLE
 .\response-body-transform-census-gate.ps1
 Census every registered language.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($Dbg) { $pythonArgs += "--debug" }
if ($SelfTest) { $pythonArgs += "--self-test" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\response_body_transform_census.py") -Arguments $pythonArgs -RequirePackages -Gate "response-body-transform-census")
