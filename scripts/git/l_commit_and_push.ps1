<#
.SYNOPSIS
Build commit-messages.json using a local Ollama model, then run commit-and-push.ps1.

.DESCRIPTION
Uses DatrixPaths.psm1 (same as commit-and-push.ps1) for workspace root and repository
directory names. For each repo that has uncommitted changes, collects git status and
diff context, then calls Ollama once per repo (plain-text commit message; no JSON batch).
Each generated message is printed to the console, then written to commit-messages.json
(keys = repo directory names, values = multi-line strings). No conventional-commit prefix
(feat:/chore:) on the subject line. Invokes commit-and-push.ps1 after writing the file.

.PARAMETER OllamaBaseUrl
Base URL for Ollama (no trailing path). Default matches local Act Mode setup.

.PARAMETER OllamaModel
Model name. Default: qwen3-coder:30b

.PARAMETER OllamaTimeoutMs
HTTP timeout in milliseconds for the generate request. Large diffs may need more than 30s.

.PARAMETER MessagesPath
Output JSON path. Default: commit-messages.json under the workspace root.

.PARAMETER MaxDiffCharsPerRepo
Maximum characters of unified diff text to include per repo (excluding stat block).

.PARAMETER OllamaNumPredict
Ollama option num_predict (max tokens). Lower values discourage long tutorial-style answers. Default 896.

.PARAMETER SkipCommitPush
If set, only writes commit-messages.json and does not run commit-and-push.ps1.

.EXAMPLE
PS D:\datrix> .\datrix\scripts\git\l_commit_and_push.ps1

.EXAMPLE
PS D:\datrix> .\datrix\scripts\git\l_commit_and_push.ps1 -OllamaTimeoutMs 120000 -SkipCommitPush
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$OllamaBaseUrl = 'http://10.94.0.100:11434',

    [Parameter(Mandatory = $false)]
    [string]$OllamaModel = 'qwen3-coder:30b',

    [Parameter(Mandatory = $false)]
    [int]$OllamaTimeoutMs = 180000,

    [Parameter(Mandatory = $false)]
    [string]$MessagesPath = '',

    [Parameter(Mandatory = $false)]
    [int]$MaxDiffCharsPerRepo = 45000,

    [Parameter(Mandatory = $false)]
    [int]$OllamaNumPredict = 896,

    [switch]$SkipCommitPush
)

$ErrorActionPreference = 'Stop'

# Git emits CRLF / path hints on stderr. PowerShell 7+ maps native stderr to error records; with
# $ErrorActionPreference = 'Stop' that aborts the script (RemoteException / NativeCommandError).
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

function Get-ScriptDirectory {
    if ($PSScriptRoot) { return $PSScriptRoot }
    return Split-Path -Parent $MyInvocation.MyCommand.Path
}

function Invoke-OllamaGenerate {
    <#
    .SYNOPSIS
    POST /api/generate without format=json so local coder models return plain text, not JSON schemas.
    #>
    param(
        [string]$BaseUrl,
        [string]$Model,
        [string]$Prompt,
        [int]$TimeoutMs,
        [int]$NumPredict
    )
    $baseTrimmed = $BaseUrl.TrimEnd('/')
    $uri = "$baseTrimmed/api/generate"
    $body = [ordered]@{
        model   = $Model
        prompt  = $Prompt
        stream  = $false
        options = @{
            num_predict = $NumPredict
        }
    }
    $jsonBody = $body | ConvertTo-Json -Compress -Depth 10
    $timeoutSec = [Math]::Max(1, [int][Math]::Ceiling($TimeoutMs / 1000.0))
    try {
        return Invoke-RestMethod -Uri $uri -Method Post -Body $jsonBody `
            -ContentType 'application/json; charset=utf-8' -TimeoutSec $timeoutSec
    } catch {
        throw "Ollama request failed: $_"
    }
}

function Normalize-PlainCommitMessageFromOllama {
    param([string]$Raw)
    if ([string]::IsNullOrWhiteSpace($Raw)) {
        throw 'Ollama returned empty commit message text.'
    }
    $t = $Raw.Trim()
    if ($t -match '(?s)^```(?:\w*\r?\n)?([\s\S]*?)\r?```\s*$') {
        $t = $Matches[1].Trim()
    }
    return $t.Trim()
}

function Get-TruncatedDiff {
    param([string]$DiffText, [int]$MaxChars)
    if ([string]::IsNullOrEmpty($DiffText)) { return '' }
    if ($DiffText.Length -le $MaxChars) { return $DiffText }
    return $DiffText.Substring(0, $MaxChars) + "`n[... diff truncated for prompt size ...]"
}

function Get-DirtyRepoBundleSection {
    param([pscustomobject]$Dr)
    $lines = @()
    $lines += "=== REPO: $($Dr.Name) (branch: $($Dr.Branch)) ==="
    $lines += '-- git status --porcelain --'
    $lines += $Dr.Porcelain
    $lines += '-- git diff HEAD --stat --'
    $lines += $Dr.DiffStat
    $lines += '-- git diff HEAD (possibly truncated) --'
    $lines += $Dr.DiffSample
    if (-not [string]::IsNullOrWhiteSpace($Dr.UntrackedNote)) {
        $lines += $Dr.UntrackedNote.TrimEnd()
    }
    return ($lines -join "`n")
}

function Request-SingleRepoCommitMessagePlainText {
    param(
        [string]$RepoName,
        [string]$RepoBundle,
        [string]$BaseUrl,
        [string]$Model,
        [int]$TimeoutMs,
        [int]$NumPredict
    )
    $prompt = @"
You are filling in a git commit message for repository folder: $RepoName
Read ONLY the git bundle below (status, paths, diff). Do not explain the code to a reader. Do not tutor, review, or suggest improvements. Do not ask questions. Do not use markdown headings (no ### lines). No fenced code blocks. No "Summary of" sections.

Output EXACTLY this shape (plain text only):
Line 1: One concise summary of what changed (not a prefix like feat:).
Line 2: blank.
Lines 3+: zero or more lines starting with "- " naming paths or areas touched (derive from the bundle; stay under 25 lines total).

Hard limits: total output under 35 lines; under 3500 characters.

Repository bundle:
$RepoBundle
"@
    $resp = Invoke-OllamaGenerate -BaseUrl $BaseUrl -Model $Model -Prompt $prompt -TimeoutMs $TimeoutMs -NumPredict $NumPredict
    if (-not $resp.response) {
        throw "Ollama returned no .response field for repo '$RepoName'"
    }
    return Normalize-PlainCommitMessageFromOllama -Raw ([string]$resp.response)
}

function Convert-GitOutputToString {
    <#
    .SYNOPSIS
    Coerce git stdout (and 2>&1 merged streams) to a single string.
    Multi-line git output becomes string[] in PowerShell; empty output can be $null.
    Calling .TrimEnd() on those causes "cannot call a method on a null-valued expression".
    #>
    param([object]$Output)
    if ($null -eq $Output) {
        return ''
    }
    if ($Output -is [string]) {
        return $Output
    }
    $lines = @($Output | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) {
            return $_.Exception.Message
        }
        return "$_"
    })
    return ($lines -join "`n")
}

$scriptDir = Get-ScriptDirectory
$scriptsDir = Join-Path $scriptDir '..'
$datrixCommon = Join-Path $scriptsDir 'common\DatrixPaths.psm1'
if (-not (Test-Path -LiteralPath $datrixCommon)) {
    throw "DatrixPaths.psm1 not found at $datrixCommon"
}
Import-Module $datrixCommon -Force
$root = Get-DatrixWorkspaceRoot -ScriptPath $MyInvocation.MyCommand.Path
$repoPaths = @(Get-DatrixDirectoryPaths -WorkspaceRoot $root)

if ([string]::IsNullOrWhiteSpace($MessagesPath)) {
    $MessagesPath = Join-Path $root 'commit-messages.json'
} elseif (-not [System.IO.Path]::IsPathRooted($MessagesPath)) {
    $MessagesPath = Join-Path $root $MessagesPath
}

$dirtyRepos = @()
foreach ($repoPath in $repoPaths) {
    $repoName = Split-Path -Leaf $repoPath
    $gitDir = Join-Path $repoPath '.git'
    if (-not (Test-Path -LiteralPath $gitDir)) {
        Write-Host "${repoName}: not a git repo, skipping" -ForegroundColor DarkGray
        continue
    }
    $porcelain = Convert-GitOutputToString -Output (git -C $repoPath status --porcelain 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "git status failed in ${repoName}: $porcelain"
    }
    if ([string]::IsNullOrWhiteSpace($porcelain)) {
        Write-Host "${repoName}: clean" -ForegroundColor Green
        continue
    }
    Write-Host "${repoName}: collecting changes" -ForegroundColor Yellow
    $branch = Convert-GitOutputToString -Output (git -C $repoPath branch --show-current 2>&1)
    if ($LASTEXITCODE -ne 0) { $branch = '(unknown branch)' }
    # -c core.autocrlf=false for this process only: avoids Windows "LF will be replaced by CRLF" stderr noise in prompts.
    $diffStat = Convert-GitOutputToString -Output (git -C $repoPath -c core.autocrlf=false diff HEAD --stat 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "git diff HEAD --stat failed in ${repoName}: $diffStat"
    }
    $diffText = Convert-GitOutputToString -Output (git -C $repoPath -c core.autocrlf=false diff HEAD 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "git diff HEAD failed in ${repoName}: $diffText"
    }
    $untrackedList = @(git -C $repoPath ls-files --others --exclude-standard 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "git ls-files untracked failed in ${repoName}"
    }
    $untrackedNote = if ($untrackedList.Count -gt 0) {
        "`n-- untracked paths (names only) --`n" + ($untrackedList -join "`n")
    } else { '' }
    $diffLimited = Get-TruncatedDiff -DiffText $diffText -MaxChars $MaxDiffCharsPerRepo
    $dirtyRepos += [pscustomobject]@{
        Name          = $repoName
        Path          = $repoPath
        Branch        = $branch.TrimEnd()
        Porcelain     = $porcelain.TrimEnd()
        DiffStat      = $diffStat.TrimEnd()
        DiffSample    = $diffLimited
        UntrackedNote = $untrackedNote
    }
}

if ($dirtyRepos.Count -eq 0) {
    $emptyJson = '{}'
    [System.IO.File]::WriteAllText($MessagesPath, $emptyJson, [System.Text.UTF8Encoding]::new($false))
    Write-Host "No uncommitted changes. Wrote empty object to $MessagesPath" -ForegroundColor Cyan
    if (-not $SkipCommitPush) {
        $commitScript = Join-Path $scriptDir 'commit-and-push.ps1'
        & $commitScript -MessagesPath $MessagesPath
    }
    exit 0
}

$filtered = [ordered]@{}
foreach ($dr in $dirtyRepos) {
    $repoName = $dr.Name
    Write-Host "Calling Ollama ($OllamaModel) for $repoName..." -ForegroundColor Cyan
    $section = Get-DirtyRepoBundleSection -Dr $dr
    $msg = Request-SingleRepoCommitMessagePlainText -RepoName $repoName -RepoBundle $section `
        -BaseUrl $OllamaBaseUrl -Model $OllamaModel -TimeoutMs $OllamaTimeoutMs -NumPredict $OllamaNumPredict
    $filtered[$repoName] = [string]$msg

    Write-Host ""
    Write-Host "========== Commit message: $repoName ==========" -ForegroundColor Green
    Write-Host $msg
    Write-Host "========== end $repoName ==========" -ForegroundColor Green
    Write-Host ""
}

# No -Compress: one line per top-level key is easier to inspect; -Compress looked like a single-line "one repo" file.
$outJson = $filtered | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText($MessagesPath, $outJson, [System.Text.UTF8Encoding]::new($false))
Write-Host "Wrote $MessagesPath" -ForegroundColor Green

if (-not $SkipCommitPush) {
    $commitScript = Join-Path $scriptDir 'commit-and-push.ps1'
    & $commitScript -MessagesPath $MessagesPath
}
