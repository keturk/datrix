#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate: no registered customer term appears in a Datrix framework repo.

.DESCRIPTION
 Runs lib\customer_domain_isolation_gate.py in the shared venv,
 which scans the git-TRACKED content of every framework repo in the workspace (datrix
 plus every datrix-* clone) against the hashed customer-term corpus at
 scripts/config/customer-term-hashes.json.

 WHY IT EXISTS: customer/project domain language must never appear in a framework repo.
 That rule was prose only, and customer cloud-resource names plus paths into a customer
 checkout reached committed files through Claude Code permission entries and a docstring
 example. This is the check that would have caught them before the commit.

 WHY THE CORPUS IS HASHED: a plaintext denylist naming the customer would itself be the
 violation it polices. Only SHA-256 digests of lowercased terms are stored, so the term
 never exists in the repo while the check still travels with the checkout and enforces on
 every machine.

 REDACTION: reported excerpts mask the matched token as <customer-term>. Open the reported
 file:line to see it -- echoing it back invites it into a summary or commit message.

 The scanner's self-test runs before every scan; a detector that stopped detecting reports
 a clean tree, which is indistinguishable from a clean tree.

 Exit codes:
   0 = no violations (or zero terms registered, reported as NOT ENFORCED)
   1 = at least one violation, or the scanner self-test failed
   2 = usage error, or the corpus is missing/malformed

.PARAMETER Repo
 Limit the scan to these repo names. Default: every framework repo in the workspace.

.PARAMETER PendingOnly
 Scan only what a 'git add -A' would stage, instead of every tracked file.

.PARAMETER AddTerm
 Register a customer term by SHA-256 digest and exit. The term itself is never written.

.PARAMETER Hint
 Non-identifying note stored alongside a registered digest.

.PARAMETER SelfTest
 Run only the scanner self-test and scan nothing.

.PARAMETER Dbg
 Print the python invocation before running.

.EXAMPLE
 .\customer-domain-isolation-gate.ps1
 Scan every tracked file in every framework repo.

.EXAMPLE
 .\customer-domain-isolation-gate.ps1 -Repo datrix
 Scan only the showcase repo.

.EXAMPLE
 .\customer-domain-isolation-gate.ps1 -AddTerm acmecorp -Hint "customer project"
 Register a new customer term by digest.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string[]]$Repo,

    [Parameter()]
    [switch]$PendingOnly,

    [Parameter()]
    [string]$AddTerm,

    [Parameter()]
    [string]$Hint = "customer project",

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
foreach ($name in $Repo) { $pythonArgs += @("--repo", $name) }
if ($PendingOnly) { $pythonArgs += "--pending-only" }
if ($AddTerm) { $pythonArgs += @("--add-term", $AddTerm, "--hint", $Hint) }
if ($SelfTest) { $pythonArgs += "--self-test" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\customer_domain_isolation_gate.py") -Arguments $pythonArgs -Gate "customer-domain-isolation" -ShowCommand:$Dbg)
