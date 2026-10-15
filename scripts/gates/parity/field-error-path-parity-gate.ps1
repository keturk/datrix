#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Field-error-path parity gate -- every registered language spells
 `request-validation` problem-body `errors[].field` paths with one
 dot-separated, `body`-prefix-free, `[n]`-array-indexed rule.

.DESCRIPTION
 A generated service's `request-validation` problem body carries an
 `errors[].field` value the UI form layer maps onto a form control. A client
 keyed on it must see the same path shape whichever language served the
 request, so the shape has one home:
 datrix_common.datrix_model.problem_types.FIELD_ERROR_PATH_RULE (a
 dot-separated wire-name path relative to the request body root, no leading
 `body` segment, `[n]` for array elements). This gate censuses every
 registered language package's own construction technique for that shape and
 holds each language to:

   * REALIZATION -- every registered language is obligated to construct the
     canonical shape for the rule's own worked example. A language that does
     not fails by name, and no declaration can excuse it; a divergent
     construction (a literal `body` prefix, or an array index not spelled
     `[n]`) fails naming the found and expected spelling. Hard zero.

 Language set from the installed datrix.languages entry points at runtime --
 never a table here. Runs a built-in non-vacuity self-test on every
 invocation.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (per-language census detail).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real census.

.EXAMPLE
 .\field-error-path-parity-gate.ps1

.EXAMPLE
 .\field-error-path-parity-gate.ps1 -SelfTest
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

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\field_error_path_parity.py") -Arguments $pythonArgs -RequirePackages -Gate "field-error-path-parity")
