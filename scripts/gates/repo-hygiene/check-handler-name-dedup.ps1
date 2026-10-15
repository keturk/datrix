#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Hard-zero gate: no datrix-codegen-* package may de-duplicate a handler name.

.DESCRIPTION
 AST-scans every datrix-codegen-* package's src/ tree for a package-local
 handler-name de-duplicator -- the retired

     while <name> in used:
         <name> = f"{base}{suffix}"
         suffix += 1

 shape over a derived REST handler / controller method name.

 Every handler name is derived ONCE, in the shared API-level derivation
 (datrix_codegen_kernel.generation.api_helpers: compute_rest_api_handler_names /
 rest_api_handler_names_by_endpoint), which REFUSES to hand two endpoints of
 one rest_api a single name -- it raises, naming both routes. A package-local
 de-duplicator does the opposite: it renames one side of the collision
 (getOrders / getOrders2) while every other consumer of that route -- the
 browser client, the API test generator, the other language targets -- keeps
 calling it by the un-numbered name. The collision is hidden, not resolved.

 A match needs three things together, so the gate flags the retired shape and
 not its legitimate neighbours:

   1. A numeric-suffix allocation loop (the shape above).
   2. An ACCUMULATING container -- named like a claim set (used/seen/taken/
      claimed/existing/...) or mutated by the enclosing function. This is what
      makes the rename order-dependent and invisible to other consumers, and
      it is what separates the retired shape from deterministic shadow
      avoidance against a fixed set of other symbols.
   3. A HANDLER-shaped subject -- a handler/controller/endpoint/route/action
      token in the module path, the function name, or an identifier the loop
      touches. This is what separates it from local-variable, test-method and
      temp-file name allocation, which no second emitter consumes.

 There is no exemption file, on purpose: a REST handler name that needs local
 de-duplication is a name that should have come from the shared table.

 The scanner's own self-test runs first on every invocation -- it plants each
 retired form and requires detection, and plants each legitimate near-miss and
 requires it clean -- so neither a scanner that can only return zero nor one
 that flags everything is believed. A run discovering fewer than two packages
 fails rather than passing vacuously.

 Exit codes:
   0 = clean, or a successful -SelfTest run
   1 = a violation was found
   2 = usage error, too few packages discovered, or the self-test failed

.PARAMETER BaseDir
 Monorepo root directory (default: auto-detect).

.PARAMETER SelfTest
 Run only the scanner's self-test and exit, skipping the real scan.

.PARAMETER ShowFiles
 Print each file as it is scanned.

.PARAMETER Dbg
 Print the interpreter and arguments before running.

.EXAMPLE
 .\check-handler-name-dedup.ps1
 Scan every datrix-codegen-* package, fail on any violation.

.EXAMPLE
 .\check-handler-name-dedup.ps1 -SelfTest
 Prove the scanner detects every retired form and clears every near-miss.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$BaseDir = "",

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$ShowFiles,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($BaseDir) { $pythonArgs += @("--base-dir", $BaseDir) }
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($ShowFiles) { $pythonArgs += "--verbose" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\check_handler_name_dedup.py") -Arguments $pythonArgs -Gate "handler-name-dedup" -ShowCommand:$Dbg)
