#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Skill assists: the mechanical phases of agent skills, done by scripts and local models.

.DESCRIPTION
    Each command takes over one phase a skill used to spend a Claude model on, and writes its output
    under <workspace>\.tmp\assist\, printing the path and a one-line summary. Exact checks are exact;
    anything a local model wrote is checked against its inputs (citations, quotes, set comparisons) and
    marked as a lead. A verdict is never delegated: the skill still decides.

      context-digest     --phase N                  shared-context digest for a phase's implementers
      readiness          --phase N [--no-model]     readiness-audit evidence (missing edges, stale names,
                                                    already-satisfied leads)
      findings-index     [--dir D]                  atomic-finding index of the findings inbox
      findings-check     --delete F... [--dir D]    would deleting F lose a citation or leave a dangling
                                                    Related pointer?
      checklist          --design PATH              conformance checklist draft for a design
      absorb-transfer    --design PATH --target T.. is each design section present in the target docs?
      absorb-references  --design PATH [--also P..] every line that still names the design
      bug-resolution     --report R --repo P.. ...  the Resolution section for a fixed bug report

    Lines carrying a registered customer term are withheld before anything is sent to a model, and
    without the term corpus nothing is sent. Python lives in library\dev\skill_assist.py and
    library\assist\.

    Exit codes:
      0 = done
      1 = the request could not be carried out (the message says what to pass instead)
      2 = the check found something the skill must act on
      3 = no local model answered: the skill does this phase itself, as it did before the assist

.PARAMETER Command
    The assist to run (see the list above).

.PARAMETER Arguments
    The command's own arguments, passed through (python style: --phase 12).

.PARAMETER LocalMachines
    Machines to search for model servers, in preference order. Omit for the default list in
    library/shared/local_llm.py.

.PARAMETER LlmModel
    Models to use, best first. Omit to use any model already in memory.

.PARAMETER LlmTimeout
    Request timeout in seconds. Default: 300.

.EXAMPLE
    .\skill-assist.ps1 context-digest --phase 12

.EXAMPLE
    .\skill-assist.ps1 checklist --design "D:\datrix\design\<the design file>.md"

.EXAMPLE
    .\skill-assist.ps1 findings-check --delete 20261005-002142-x.md 20261005-002143-y.md
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet("context-digest", "readiness", "findings-index", "findings-check", "checklist",
        "absorb-transfer", "absorb-references", "bug-resolution")]
    [string]$Command,
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)] [string[]]$Arguments = @(),
    [Parameter()] [string[]]$LocalMachines = @(),
    [Parameter()] [string[]]$LlmModel = @(),
    [Parameter()] [int]$LlmTimeout = 300
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = Split-Path -Parent $scriptDir
$cliScript = Join-Path $scriptsDir "library\dev\skill_assist.py"
$commonDir = Join-Path $scriptsDir "common"
. (Join-Path $commonDir "venv.ps1")
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force

# The commands that may ask a local model; the others are exact and take no model flags.
$modelCommands = @("readiness", "findings-index", "checklist", "absorb-transfer", "bug-resolution")

function Invoke-Cleanup {
    Disable-DatrixVenv
}

Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

trap {
    Write-Host ""
    Write-Warning "Interrupted by user (Ctrl-C)"
    Invoke-Cleanup
    exit 130
}

try {
    $venvActivated = Ensure-DatrixVenv
    if (-not $venvActivated) {
        Write-Error "Failed to activate virtual environment"
        exit 1
    }
    $venvPath = Get-DatrixVenvPath
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"
    if (-not (Test-Path $pythonExe)) {
        $pythonExe = Join-Path $venvPath "bin\python"
    }

    # @(...) so a single argument stays an array and splats as one argument.
    $pyArgs = @($Command) + @($Arguments)
    if ($modelCommands -contains $Command) {
        $pyArgs += Get-DatrixLocalLlmArguments -LocalMachines $LocalMachines -LlmModel $LlmModel -LlmTimeoutSeconds $LlmTimeout
    }

    & $pythonExe $cliScript @pyArgs
    exit $LASTEXITCODE
}
catch {
    Write-Host ""
    Write-Host "Error occurred:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Invoke-Cleanup
    exit 1
}
finally {
    Invoke-Cleanup
}
