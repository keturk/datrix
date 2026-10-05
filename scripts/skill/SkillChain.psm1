# Runs skills as headless Claude Code steps, each in its own `claude -p` session.
#
# A skill invoked from inside another skill runs on the caller's model; only a slash command typed
# as the prompt switches to the skill's own `model:` and `effort:`. Each step here is such a prompt,
# so every step runs on its skill's model, with the hooks, CLAUDE.md and guards of an interactive
# session. Used by skill-chain.ps1, implement-design.ps1 and implement-design-direct.ps1 beside it.

$script:Options = $null
$script:SessionId = ""
$script:StepNumber = 0
$script:Steps = New-Object System.Collections.Generic.List[object]

function Initialize-SkillChain {
    <#
    .SYNOPSIS
        Set the options every later step uses and pick the run's log folder. Exits 1 when the
        claude CLI is not on PATH.
    #>
    param(
        [Parameter(Mandatory)] [string]$Workspace,
        [switch]$Resume,
        [string]$PermissionMode = "auto",
        [double]$MaxBudgetUsd = 0,
        [switch]$DryRun,
        [switch]$Quiet
    )
    if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
        Write-Host "The claude CLI is not on PATH. Install it: npm install -g @anthropic-ai/claude-code" -ForegroundColor Red
        exit 1
    }
    # The CLI writes UTF-8; without this, Windows PowerShell decodes it with the OEM code page.
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $script:Options = [pscustomobject]@{
        Workspace = $Workspace
        Resume = [bool]$Resume
        PermissionMode = $PermissionMode
        MaxBudgetUsd = $MaxBudgetUsd
        DryRun = [bool]$DryRun
        Quiet = [bool]$Quiet
        RunDir = Join-Path $Workspace (".tmp\skill-chain\" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    }
    $script:SessionId = ""
    $script:StepNumber = 0
    $script:Steps.Clear()
}

function Get-SkillChainRunDir {
    return $script:Options.RunDir
}

$ProgressTextLimit = 300
$ProgressDetailLimit = 140

function Get-ShortText {
    param([string]$Text, [int]$Limit)
    $flat = ($Text -replace "\s+", " ").Trim()
    if ($flat.Length -le $Limit) { return $flat }
    return $flat.Substring(0, $Limit) + "..."
}

function Get-ToolDetail {
    <# The one field of a tool call that says what it does: a path, a description, a pattern. #>
    param([object]$ToolInput)
    $fields = @("description", "file_path", "notebook_path", "path", "pattern", "skill", "name", "dotted_path", "topic",
        "question", "query", "paths", "files", "url", "command", "prompt")
    foreach ($field in $fields) {
        $value = $ToolInput.$field
        if ($value) { return Get-ShortText (@($value) -join ", ") $ProgressDetailLimit }
    }
    return ""
}

function Write-StepEvent {
    <# One console line per agent message, tool call, and refused or failed tool call. #>
    param([object]$StreamEvent)
    $time = Get-Date -Format "HH:mm:ss"
    if ($StreamEvent.type -eq "assistant") {
        foreach ($block in @($StreamEvent.message.content)) {
            if ($block.type -eq "text" -and $block.text.Trim()) {
                Write-Host "  [$time] $(Get-ShortText $block.text $ProgressTextLimit)"
            } elseif ($block.type -eq "tool_use") {
                Write-Host "  [$time] $($block.name) $(Get-ToolDetail $block.input)" -ForegroundColor DarkGray
            }
        }
    } elseif ($StreamEvent.type -eq "user") {
        foreach ($block in @($StreamEvent.message.content)) {
            if ($block.type -eq "tool_result" -and $block.is_error) {
                $content = if ($block.content -is [string]) { $block.content } else { (@($block.content) | ForEach-Object { $_.text }) -join " " }
                Write-Host "  [$time] ! $(Get-ShortText $content $ProgressDetailLimit)" -ForegroundColor DarkYellow
            }
        }
    }
}

function Invoke-ChainStep {
    <#
    .SYNOPSIS
        Run one prompt as a headless step and return its row: Name, IsError, Subtype, Result,
        SessionId, Models, Turns, Minutes, CostUsd, Denials, DryRun. The step streams its events:
        each is kept in <label>.stream.jsonl and, unless Quiet, shown as one line; the final
        result is kept in <label>.json.
    #>
    param([Parameter(Mandatory)] [string]$Name, [Parameter(Mandatory)] [string]$Prompt)
    $options = $script:Options
    $script:StepNumber += 1
    $label = "{0:D2}-{1}" -f $script:StepNumber, $Name
    Write-Host ""
    Write-Host "=== step $label ===" -ForegroundColor Cyan
    Write-Host $Prompt
    if ($options.DryRun) {
        return [pscustomobject]@{ Name = $label; IsError = $false; Result = ""; SessionId = ""; DryRun = $true }
    }
    New-Item -ItemType Directory -Force -Path $options.RunDir | Out-Null
    $cliArgs = @("-p", $Prompt, "--output-format", "stream-json", "--verbose", "--permission-mode", $options.PermissionMode)
    if ($options.Resume -and $script:SessionId) { $cliArgs += @("--resume", $script:SessionId) }
    if ($options.MaxBudgetUsd -gt 0) { $cliArgs += @("--max-budget-usd", "$($options.MaxBudgetUsd)") }
    $jsonPath = Join-Path $options.RunDir "$label.json"
    $streamPath = Join-Path $options.RunDir "$label.stream.jsonl"
    $errPath = Join-Path $options.RunDir "$label.stderr.txt"
    $started = Get-Date
    $result = $null
    $stream = [System.IO.StreamWriter]::new($streamPath, $false, [System.Text.UTF8Encoding]::new($false))
    Push-Location $options.Workspace
    try {
        $null | & claude @cliArgs 2> $errPath | ForEach-Object {
            $line = [string]$_
            $stream.WriteLine($line)
            try { $streamEvent = $line | ConvertFrom-Json } catch { return }
            if ($streamEvent.type -eq "result") {
                $result = $streamEvent
            } elseif (-not $options.Quiet) {
                Write-StepEvent $streamEvent
            }
        }
    } finally {
        Pop-Location
        $stream.Dispose()
    }
    if (-not $result) {
        Write-Host "Step $label printed no result event (see $streamPath and $errPath)." -ForegroundColor Red
        return [pscustomobject]@{ Name = $label; IsError = $true; Subtype = "no-result"; Result = ""; SessionId = ""; DryRun = $false }
    }
    [System.IO.File]::WriteAllText($jsonPath, ($result | ConvertTo-Json -Depth 20), [System.Text.UTF8Encoding]::new($false))
    if ($result.session_id) { $script:SessionId = $result.session_id }
    $models = @($result.modelUsage.PSObject.Properties | ForEach-Object { $_.Name }) -join ", "
    $minutes = [math]::Round(((Get-Date) - $started).TotalMinutes, 1)
    $denials = @($result.permission_denials).Count
    $row = [pscustomobject]@{
        Name = $label; IsError = [bool]$result.is_error; Subtype = $result.subtype; Result = [string]$result.result
        SessionId = $result.session_id; Models = $models; Turns = $result.num_turns; Minutes = $minutes
        CostUsd = [math]::Round([double]$result.total_cost_usd, 2); Denials = $denials; DryRun = $false
    }
    $script:Steps.Add($row)
    $colour = if ($row.IsError) { "Red" } else { "Green" }
    Write-Host ("{0}: {1}; models {2}; {3} turns; {4} min; list cost {5} USD; {6} permission denial(s); session {7}" -f `
        $label, $(if ($row.IsError) { "ERROR ($($row.Subtype))" } else { "done" }), $models, $row.Turns, $minutes,
        $row.CostUsd, $denials, $row.SessionId) -ForegroundColor $colour
    return $row
}

function Write-ChainTail {
    param([string]$Text, [int]$Lines = 25)
    $all = $Text -split "`r?`n"
    $all[[math]::Max(0, $all.Count - $Lines)..($all.Count - 1)] | ForEach-Object { Write-Host "  $_" }
}

function Write-ChainSummary {
    if ($script:Steps.Count -eq 0) { return }
    Write-Host ""
    Write-Host "=== chain summary (logs: $($script:Options.RunDir)) ===" -ForegroundColor Cyan
    $script:Steps | Format-Table Name, Models, Turns, Minutes, CostUsd, Denials, @{ n = "Error"; e = { $_.IsError } } -AutoSize | Out-String | Write-Host
}

function Stop-Chain {
    <#
    .SYNOPSIS
        Print why the chain stops, the step's last reply and how to continue its session, then exit
        with Code: 1 for an error or a failed check, 2 for a decision only Jon can make.
    #>
    param([Parameter(Mandatory)] [int]$Code, [Parameter(Mandatory)] [string]$Message, [object]$Row)
    Write-Host ""
    Write-Host $Message -ForegroundColor $(if ($Code -eq 2) { "Yellow" } else { "Red" })
    if ($Row -and $Row.Result) {
        Write-Host "The step's last reply ends:"
        Write-ChainTail $Row.Result
    }
    if ($Row -and $Row.SessionId) {
        Write-Host "Continue that session interactively: claude --resume $($Row.SessionId)"
    }
    Write-ChainSummary
    exit $Code
}

$VerdictPattern = "Design conformance:\W*(PROVEN|INCOMPLETE)"

function Get-SessionReplies {
    <#
    .SYNOPSIS
        Every assistant text of a step's session, in order, read from its transcript. The JSON
        result holds only the LAST reply, and a Stop hook that refuses a reply makes the session
        send another one, so a verdict can sit in an earlier reply. Falls back to Result when the
        transcript is not found.
    #>
    param([Parameter(Mandatory)] [object]$Row)
    $projectKey = $script:Options.Workspace -replace "[^A-Za-z0-9]", "-"
    $transcript = Join-Path $env:USERPROFILE ".claude\projects\$projectKey\$($Row.SessionId).jsonl"
    if (-not $Row.SessionId -or -not (Test-Path $transcript)) { return @($Row.Result) }
    $replies = New-Object System.Collections.Generic.List[string]
    foreach ($line in [System.IO.File]::ReadLines($transcript)) {
        if (-not $line.Contains('"type":"assistant"')) { continue }
        try { $entry = $line | ConvertFrom-Json } catch { continue }
        foreach ($block in @($entry.message.content)) {
            if ($block.type -eq "text" -and $block.text) { $replies.Add([string]$block.text) }
        }
    }
    if ($replies.Count -eq 0) { return @($Row.Result) }
    return $replies.ToArray()
}

function Get-DesignVerdict {
    <#
    .SYNOPSIS
        PROVEN, INCOMPLETE, or "" when no reply of the step carries a verdict line. The last
        verdict in the session wins.
    #>
    param([Parameter(Mandatory)] [object]$Row)
    $verdict = ""
    foreach ($reply in (Get-SessionReplies $Row)) {
        foreach ($match in [regex]::Matches($reply, $VerdictPattern)) { $verdict = $match.Groups[1].Value }
    }
    return $verdict
}

function Invoke-DesignVerify {
    <#
    .SYNOPSIS
        Run /verify-implementation until it replies PROVEN. On INCOMPLETE, its reply is saved to a
        file and OnIncomplete runs with that path (the step that implements again) before the next
        round; after MaxRounds the chain stops with exit 1. A reply with neither verdict stops with 2.
    #>
    param(
        [Parameter(Mandatory)] [string]$Prompt,
        [Parameter(Mandatory)] [scriptblock]$OnIncomplete,
        [int]$MaxRounds = 3
    )
    for ($round = 1; $round -le $MaxRounds; $round++) {
        $row = Invoke-ChainStep "verify" $Prompt
        if ($row.DryRun) { return }
        if ($row.IsError) { Stop-Chain 1 "/verify-implementation ended in error ($($row.Subtype))." $row }
        $verdict = Get-DesignVerdict $row
        if ($verdict -eq "PROVEN") { return }
        if ($verdict -ne "INCOMPLETE") {
            Stop-Chain 2 "/verify-implementation replied with neither PROVEN nor INCOMPLETE; read its reply." $row
        }
        if ($round -eq $MaxRounds) {
            Stop-Chain 1 "The design is still INCOMPLETE after $MaxRounds verify round(s); it is not absorbed." $row
        }
        $report = Join-Path $script:Options.RunDir "verify-round-$round.md"
        $replies = (Get-SessionReplies $row) -join "`n`n---`n`n"
        [System.IO.File]::WriteAllText($report, $replies, [System.Text.UTF8Encoding]::new($false))
        Write-Host "Verify round ${round}: INCOMPLETE (report: $report). Implementing again." -ForegroundColor Yellow
        & $OnIncomplete $report
    }
}

function Invoke-DesignAbsorb {
    <#
    .SYNOPSIS
        Run /absorb-design. Without KeepSource the design must be gone afterwards; when it is not,
        absorb stopped at one of its questions and the chain stops with exit 2.
    #>
    param([Parameter(Mandatory)] [string]$DesignPath, [switch]$KeepSource)
    $keep = if ($KeepSource) { "`nKEEP SOURCE: true" } else { "" }
    $row = Invoke-ChainStep "absorb" "/absorb-design`nDOCUMENT: $DesignPath$keep"
    if ($row.DryRun) { return }
    if ($row.IsError) { Stop-Chain 1 "/absorb-design ended in error ($($row.Subtype))." $row }
    if (-not $KeepSource -and (Test-Path $DesignPath)) {
        Stop-Chain 2 "/absorb-design finished but the design still exists, so it stopped at a question; read its reply." $row
    }
}

function Complete-Chain {
    Write-ChainSummary
    exit 0
}

Export-ModuleMember -Function Initialize-SkillChain, Get-SkillChainRunDir, Invoke-ChainStep, Write-ChainSummary, Stop-Chain,
    Invoke-DesignVerify, Invoke-DesignAbsorb, Complete-Chain
