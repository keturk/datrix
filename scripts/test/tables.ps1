#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Inspect and migrate table contracts (datrix_testing.tables).

.DESCRIPTION
 Runs datrix_testing.tables.cli in the shared venv.
 A package's runner module, tests/test_tables.py, proves every row of every table the
 package's tests/conftest.py registered -- the builtin registry for its language, its type
 map, its emit tables, its DAL generator file declarations -- as one pytest item per row
 (per row x axis cell for a matrix). This tool shows those items and retires the per-row
 hand tests they make redundant.

   rows       Print every registered table, its tags, tier, lookup names and item ids.
              Writes nothing.
   inventory  Resolve every per-row hand test (a test whose whole body looks a registered
              table's row up and compares it) to the rows it reads: covered (an item proves
              it by existing), decision (a row's value compared with a literal -- a case row
              or code, never deleted) or uncovered. Writes the report under
              D:\datrix\.tmp\case-proposals\.
   migrate    Write a proposal there: every covered test is proposed for deletion, every other
              one stays code with its reason. Never writes into a repository.
   accept     Delete the tests an approved proposal proposes, by AST, with the module-local
              dead code they leave, and lower the package's pins. Refused unless Jon's
              approval names the proposal's current sha256 and every security test it
              deletes, and unless every deleted test is still covered by an item the package
              collects now.

.PARAMETER Command
 rows, inventory, migrate or accept.

.PARAMETER Arguments
 The command's positional arguments:
   rows      <package> [<table>]
   inventory <package>
   migrate   <package>
   accept    <proposal>

.EXAMPLE
 .\tables.ps1 rows datrix-codegen-python

.EXAMPLE
 .\tables.ps1 rows datrix-codegen-python builtins

.EXAMPLE
 .\tables.ps1 migrate datrix-codegen-python

.EXAMPLE
 .\tables.ps1 accept D:\datrix\.tmp\case-proposals\datrix-codegen-python.tables.proposal.json
#>

[CmdletBinding()]
param(
 [Parameter(Position=0, Mandatory=$true)]
 [ValidateSet("rows", "inventory", "migrate", "accept")]
 [string]$Command,

 [Parameter(Position=1, ValueFromRemainingArguments=$true)]
 [string[]]$Arguments = @(),

 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

exit (Invoke-DatrixPythonScript -Module "datrix_testing.tables.cli" -Arguments (@($Command) + $Arguments) -ShowCommand:$Dbg)
