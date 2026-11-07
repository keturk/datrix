#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Work through the first findings files of the inbox, a batch of sessions side by side: one fresh
    session per finding checks it against the code, fixes it when it still holds, and the script
    deletes it once proven.

.DESCRIPTION
    The behaviour is datrix_scripts.skill.implement_finding, over the steps of
    datrix_scripts.skill.chain. The multi-finding form of /implement-finding. The selected findings
    are worked in batches of 4 (the inbox folders taken in turn, so a batch spans areas); the fix
    sessions of a batch run side by side, each headless /implement-finding session on -Model ending
    with one line:
      Finding fix: ALREADY RESOLVED   the code no longer has the defect; nothing was changed
      Finding fix: DONE               fixed, with a tagged test and targeted test runs
      Finding fix: UPDATED            fixed what needed no growth, rewrote the finding with what the rest needs
      Finding fix: BLOCKED B<n>       stopped with a B1-B4 proof; the finding stays for Jon

    The session never deletes the finding; the script does (datrix_scripts.skill.finding_inbox, the
    code behind skill-assist finding-close), not on a model's word: never while another findings
    file names it, and after DONE only when the tests related to what the session wrote pass. The
    script derives and runs those itself (datrix_scripts.skill.related_tests; targeted test.ps1 runs,
    never a whole suite): the test files the session wrote, and the other test files in any package
    that name a code name the session changed. They run only once every fix session of the batch
    has ended, so no session's half-made edits are judged; while any fails it resumes that session
    with the failures, as often as it takes, and since a repair can break a session proved before
    it, the sessions are proved again until a sweep needs no repair. A session that wrote no package
    source or test (the scripts tree hosts no test suite) is judged by its last foreground test.ps1
    or *-gate.ps1 run in the step's stream log (a gate passes on its "[GATE] <name> PASSED exit=0"
    verdict line, and -SelfTest runs do not count). Every finding of a batch is closed before the
    next batch starts.

    Every fix and repair step prints the finding's absolute path in its header as it starts:
      === step 01-fix D:\datrix\findings\kernel\<the finding>.md (claude-sonnet-5-5, medium) ===

    Step logs: <workspace>\.tmp\skill-chain\<timestamp>\.

    Exit codes: 0 every selected finding is deleted (or a passing -SelfTest); 1 a step ended in
    error, replied with no outcome line, a finding was left in place, or the findings could not be
    selected; 2 no failure, but at least one session stopped for a decision only Jon can make or
    rewrote its finding to say what it needs, or a command line the module cannot read.

.PARAMETER Count
    How many findings files to take, first by name. Default: 10.

.PARAMETER All
    Work every findings file of the folder given with -Dir, or, without -Dir, of every folder of
    <workspace>\findings in turn, with no count cap. Not with -Count or -Finding.

.PARAMETER Finding
    Work these findings files in place of the first -Count of the inbox.

.PARAMETER Dir
    Work only this folder: absolute, or relative to <workspace>\findings (-Dir azure). Default: the
    subfolders of <workspace>\findings in turn (the next only once the one before holds no more),
    then the files lying in it directly. -Finding is unchanged: those files are worked as given.

.PARAMETER Model
    The model of each session. Default: claude-sonnet-5-5.

.PARAMETER Effort
    The effort of each session. Default: medium.

.PARAMETER PermissionMode
    The permission mode of every session. Default: auto. The guards run in every mode.

.PARAMETER MaxBudgetUsd
    Stop a session that passes this list-price cost. Default: no cap.

.PARAMETER Quiet
    Show only each session's prompt and summary line.

.PARAMETER DryRun
    List the selected findings and print the sessions that would run; run none.

.PARAMETER SelfTest
    Run only the module's self-test (the chain checks, the outcome line, selecting and closing
    findings, a dry run) and the wrapper seam checks.

.EXAMPLE
    .\implement-finding.ps1

.EXAMPLE
    .\implement-finding.ps1 -Count 3 -DryRun

.EXAMPLE
    .\implement-finding.ps1 D:\datrix\findings\python

.EXAMPLE
    .\implement-finding.ps1 -All D:\datrix\findings\azure

.EXAMPLE
    .\implement-finding.ps1 -Finding "D:\datrix\findings\<the finding>.md"
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)] [string]$Dir,
    [int]$Count,
    [switch]$All,
    [string[]]$Finding,
    [string]$Model,
    [ValidateSet("low", "medium", "high", "xhigh", "max")] [string]$Effort,
    [ValidateSet("auto", "acceptEdits", "dontAsk", "bypassPermissions")] [string]$PermissionMode,
    [double]$MaxBudgetUsd,
    [switch]$DryRun,
    [switch]$Quiet,
    [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.skill.implement_finding" -Parameters $PSBoundParameters
exit $LASTEXITCODE
