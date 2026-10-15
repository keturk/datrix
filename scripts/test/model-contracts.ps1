#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Inspect and migrate schema-derived model contracts (datrix_testing.model_contracts).

.DESCRIPTION
 Runs datrix_testing.model_contracts.cli in the shared venv.
 A package's runner module, tests/test_model_contracts.py, proves every schema fact of
 every model the package declares -- each required field, default, bound, pattern and
 the unknown-key refusal -- as one pytest item, by mutating a sample the real loader fed
 the model while it loaded a committed .dcfg fixture. This tool shows those facts and
 retires the test functions that restate them.

   facts      Print the model set, each sampled model's items with the fixture its sample
              came from, the models no fixture reaches and the code-built ones. Writes nothing.
   inventory  Resolve every schema-shaped test of the package (a test whose whole body is
              pytest.raises around one construction, or one construction and default
              asserts) to the model, field and fact it restates, and whether an item proves
              it. Writes the report under D:\datrix\.tmp\case-proposals\.
   migrate    Write a proposal there: every test an item proves is proposed for deletion,
              every other one stays code with its reason. Never writes into a repository.
   accept     Delete the tests an approved proposal proposes, by AST, with the module-local
              dead code they leave, and lower the package's pins. Refused unless Jon's
              approval names the proposal's current sha256 and every security test it
              deletes, and unless every deleted test is still proven by an item the package
              collects now.

.PARAMETER Command
 facts, inventory, migrate or accept.

.PARAMETER Arguments
 The command's positional arguments:
   facts     <package> [<Model>]
   inventory <package>
   migrate   <package>
   accept    <proposal>

.EXAMPLE
 .\model-contracts.ps1 facts datrix-codegen-docker

.EXAMPLE
 .\model-contracts.ps1 facts datrix-common ExternOAuth2ClientCredentialsConfig

.EXAMPLE
 .\model-contracts.ps1 migrate datrix-codegen-aws

.EXAMPLE
 .\model-contracts.ps1 accept D:\datrix\.tmp\case-proposals\datrix-codegen-aws.model-contracts.proposal.json
#>

[CmdletBinding()]
param(
 [Parameter(Position=0, Mandatory=$true)]
 [ValidateSet("facts", "inventory", "migrate", "accept")]
 [string]$Command,

 [Parameter(Position=1, ValueFromRemainingArguments=$true)]
 [string[]]$Arguments = @(),

 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

exit (Invoke-DatrixPythonScript -Module "datrix_testing.model_contracts.cli" -Arguments (@($Command) + $Arguments) -ShowCommand:$Dbg)
