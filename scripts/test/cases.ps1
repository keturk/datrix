#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Author, migrate and check declarative test cases (datrix_testing.cases).

.DESCRIPTION
 Runs datrix_testing.cases.cli in the shared venv.
 A case is one row of a package's tests/cases/<area>.cases.yaml: a stage run
 on a committed input, one observed value, and an authored expectation. The
 package's one runner module, tests/test_cases.py, runs every row as a pytest
 item; this tool creates, inspects, migrates and checks them.

   observe  Run a stage and print the value a selector reads, with its parsed
            context. Writes nothing.
   new      Append one authored case to tests/cases/<area>.cases.yaml. Every
            field comes from you; the tool validates the row, refuses a known
            id or fact, resolves the selector, and appends it. Refused while
            the approval gate is armed for the package.
   migrate  Inventory the package's counted substring assertions (or every
            assertion of the named modules) and write a proposal under
            D:\datrix\.tmp\case-proposals\ -- never into the repository.
            With -Annotations, propose moving the named modules' diagnostic,
            transpiled and language-server tests onto fixture annotations and
            per-code diagnostic fixtures instead.
   accept   Move an approved proposal's rows into case files (an annotation
            proposal's annotations and per-code fixtures into the fixtures),
            remove the code they replace, and lower the package's pins.
   check    Check everything the package commits about its cases: case files,
            fixture annotations, per-code fixtures and docs fences.

.PARAMETER Command
 observe, new, migrate, accept or check.

.PARAMETER Arguments
 The command's positional arguments:
   observe <input> <stage> <observer> <selector>      (with -Package)
   observe                                            (with -Package and -At <file>:<line>)
   new     <package> <area>                           (with the named fields)
   migrate <package> [<module> ...]
   migrate <package> <module> ...                     (with -Annotations)
   accept  <proposal> [<case id> ...]
   check   <package>

.PARAMETER Package
 observe: the package whose named inputs and registrations to load.

.PARAMETER At
 observe: a fixture line, <file>:<line>, in place of <input> <stage> <observer> <selector>;
 prints what each annotation kind would observe on that line (the diagnostics firing there,
 the code emitted for the function declared there, the language server's answers at its $0).

.PARAMETER Annotations
 migrate: propose fixture annotations (and per-code fixtures) for the named modules'
 diagnostic, transpiled and language-server tests, in place of case rows.

.PARAMETER Id
 new: the case id, <area>.<slug>.

.PARAMETER Tags
 new: the feature tags, comma-separated.

.PARAMETER CaseInput
 new: the named input (alias -Input).

.PARAMETER Stage
 new: the stage (generate, analyze, or one the package registers).

.PARAMETER Observer
 new: the observer kind.

.PARAMETER Selector
 new: the selector, a YAML flow mapping ({path: a, unit: statements, owner: f}).

.PARAMETER Expectation
 new: the expectation, a YAML flow value; omitted for an absent case.

.PARAMETER Reason
 new: one sentence naming the decision the case protects.

.EXAMPLE
 .\cases.ps1 check datrix-codegen-docker

.EXAMPLE
 .\cases.ps1 observe basic generate surface "{path: docker-compose.yml, unit: keys, key: [services]}" -Package datrix-codegen-docker

.EXAMPLE
 .\cases.ps1 new datrix-codegen-docker compose -Id compose.basic.api.port -Tags compose -Input basic -Stage generate -Observer surface -Selector "{path: docker-compose.yml, unit: value, key: [services, api, ports, '0']}" -Expectation "'8000:8000'" -Reason "The API is published on its service port."

.EXAMPLE
 .\cases.ps1 migrate datrix-codegen-typescript

.EXAMPLE
 .\cases.ps1 migrate datrix-semantic unit/validators/test_service_semver.py -Annotations

.EXAMPLE
 .\cases.ps1 accept D:\datrix\.tmp\case-proposals\datrix-codegen-typescript-substring.proposal.json
#>

[CmdletBinding()]
param(
 [Parameter(Position=0, Mandatory=$true)]
 [ValidateSet("observe", "new", "migrate", "accept", "check")]
 [string]$Command,

 [Parameter(Position=1, ValueFromRemainingArguments=$true)]
 [string[]]$Arguments = @(),

 [string]$Package,
 [string]$Id,
 [string]$Tags,
 [Alias("Input")]
 [string]$CaseInput,
 [string]$Stage,
 [string]$Observer,
 [string]$Selector,
 [string]$Expectation,
 [string]$Reason,
 [string]$At,
 [switch]$Annotations,
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$ExitUsage = 2

# An absent case takes no expectation, so only a given -Expectation is passed on.
$ExpectationGiven = $PSBoundParameters.ContainsKey("Expectation")

function Get-CommandArguments {
 $pythonArgs = @($Command)
 switch ($Command) {
  "observe" {
   if (-not $Package) { throw "observe needs -Package <package>: the package whose inputs to load." }
   $pythonArgs += @("--package", $Package)
   if ($At) { $pythonArgs += @("--at", $At) }
   $pythonArgs += $Arguments
  }
  "new" {
   $pythonArgs += $Arguments
   foreach ($field in @(@("--id", $Id), @("--tags", $Tags), @("--input", $CaseInput), @("--stage", $Stage),
                        @("--observer", $Observer), @("--selector", $Selector), @("--reason", $Reason))) {
    if (-not $field[1]) { throw "new needs $($field[0] -replace '--', '-'): every field of a case comes from you." }
    $pythonArgs += $field
   }
   if ($ExpectationGiven) { $pythonArgs += @("--expectation", $Expectation) }
  }
  "migrate" {
   $pythonArgs += $Arguments
   if ($Annotations) { $pythonArgs += "--annotations" }
  }
  default { $pythonArgs += $Arguments }
 }
 return ,$pythonArgs
}

try {
 $pythonArgs = Get-CommandArguments
}
catch {
 Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
 exit $ExitUsage
}
exit (Invoke-DatrixPythonScript -Module "datrix_testing.cases.cli" -Arguments $pythonArgs -ShowCommand:$Dbg)
