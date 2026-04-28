<#
.SYNOPSIS
Build commit-messages.json using a local Ollama model; print each message to the console.

.DESCRIPTION
Uses DatrixPaths.psm1 (same as commit-and-push.ps1) for workspace root and repository
directory names. For each repo that has uncommitted changes, collects git status and
diff context, then calls Ollama once per repo (plain-text commit message; no JSON batch).
Each generated message is printed to the console and written to commit-messages.json
(keys = repo directory names, values = multi-line strings). No conventional-commit prefix
(feat:/chore:) on the subject line. Git commit/push is opt-in via -CommitAndPush (see
datrix\scripts\git\commit-and-push.ps1).

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

.PARAMETER CommitAndPush
If set, after writing commit-messages.json runs commit-and-push.ps1 with that file.

.EXAMPLE
PS D:\datrix> .\datrix\scripts\git\l_commit_and_push.ps1

.EXAMPLE
PS D:\datrix> .\datrix\scripts\git\l_commit_and_push.ps1 -CommitAndPush
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

    [switch]$CommitAndPush
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
    POST /api/generate without format=json. Optional system prompt keeps instructions out of the user
    blob so coder models are less likely to reply as "someone comparing pasted diffs".
    #>
    param(
        [string]$BaseUrl,
        [string]$Model,
        [string]$Prompt,
        [int]$TimeoutMs,
        [int]$NumPredict,
        [string]$System = ''
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
    if (-not [string]::IsNullOrWhiteSpace($System)) {
        $body['system'] = $System
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

function Test-OllamaCommitMessageMalformed {
    <#
    .SYNOPSIS
    True when the model answered like a chatbot analyzing a paste instead of writing a commit message.
    #>
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) {
        return $true
    }
    $t = $Text.TrimStart()
    $nlIdx = $t.IndexOf("`n", [StringComparison]::Ordinal)
    $firstLine = if ($nlIdx -ge 0) { $t.Substring(0, $nlIdx) } else { $t }
    if ($firstLine.Length -gt 120) {
        return $true
    }
    if ($t -match '(?i)^(you''re|you are|it looks|here''s|here is|below is|the following|this diff|this code|this script|this powershell|###|## )') {
        return $true
    }
    $apos = [char]0x2019
    if ($t.StartsWith("You${apos}re ", [StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    if ($t.StartsWith("Here${apos}s ", [StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    if ($t -match '(?i)^(let me know|i''m happy to|would you like|please provide|i can help|need help with)') {
        return $true
    }
    $take = [Math]::Min(200, $t.Length)
    $head = $t.Substring(0, $take)
    if ($head -match '(?i)(comparing two|version control system|pasted a large|your message)') {
        return $true
    }
    $probeLen = [Math]::Min(1200, $t.Length)
    if ($probeLen -gt 0) {
        $probe = $t.Substring(0, $probeLen)
        if ($probe -match '(?i)(the script you''ve|the script you have|powershell script automates|here''s a breakdown|breakdown of its functionality|^\d+\.\s+\*\*|\*\*key features|key features:|prerequisites:|sample output|designed to:\s*$|###\s|##\s|\*\*usage:\*\*|\*\*dependencies:\*\*)') {
            return $true
        }
    }
    return $false
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
    $lines += '-- git diff HEAD --name-status --'
    $lines += $Dr.NameStatus
    $lines += '-- git diff HEAD --stat --'
    $lines += $Dr.DiffStat
    $lines += '-- git diff HEAD (possibly truncated) --'
    $lines += $Dr.DiffSample
    if (-not [string]::IsNullOrWhiteSpace($Dr.UntrackedNote)) {
        $lines += $Dr.UntrackedNote.TrimEnd()
    }
    return ($lines -join "`n")
}

function Get-DirtyRepoBundleSectionPathsOnly {
    <#
    .SYNOPSIS
    No unified diff body — only paths and stat (last resort prompt for chatty models).
    #>
    param([pscustomobject]$Dr)
    $lines = @()
    $lines += "=== REPO: $($Dr.Name) (branch: $($Dr.Branch)) ==="
    $lines += '-- git status --porcelain --'
    $lines += $Dr.Porcelain
    $lines += '-- git diff HEAD --name-status --'
    $lines += $Dr.NameStatus
    $lines += '-- git diff HEAD --stat --'
    $lines += $Dr.DiffStat
    if (-not [string]::IsNullOrWhiteSpace($Dr.UntrackedNote)) {
        $lines += $Dr.UntrackedNote.TrimEnd()
    }
    return ($lines -join "`n")
}

function Get-FallbackCommitMessageFromDr {
    <#
    .SYNOPSIS
    Deterministic commit message from name-status and porcelain when the LLM will not comply.
    #>
    param([pscustomobject]$Dr)
    $bullets = @()
    foreach ($line in ($Dr.NameStatus -split "`r?`n")) {
        $u = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($u)) { continue }
        $parts = $u -split "`t+", 3
        if ($parts.Count -ge 2) {
            $code = $parts[0].Trim()
            $path = $parts[-1].Trim()
            $bullets += "- $path ($code)"
        } else {
            $bullets += "- $u"
        }
        if ($bullets.Count -ge 28) { break }
    }
    if ($bullets.Count -eq 0) {
        foreach ($line in ($Dr.Porcelain -split "`r?`n")) {
            $u = $line.Trim()
            if ($u.Length -gt 2) {
                $bullets += "- $u"
            }
            if ($bullets.Count -ge 28) { break }
        }
    }
    $subject = "Update $($Dr.Name)"
    if ($bullets.Count -eq 0) {
        return $subject
    }
    return ($subject + "`n`n" + ($bullets -join "`n"))
}

function Get-DirtyRepoBundleSectionLite {
    <#
    .SYNOPSIS
    Shorter prompt payload: paths + stat + small diff excerpt only (reduces model "explaining the script" when the diff is huge self-documentation).
    #>
    param(
        [pscustomobject]$Dr,
        [int]$ExcerptMaxChars = 2200
    )
    $lines = @()
    $lines += "=== REPO: $($Dr.Name) (branch: $($Dr.Branch)) ==="
    $lines += '-- git status --porcelain --'
    $lines += $Dr.Porcelain
    $lines += '-- git diff HEAD --name-status --'
    $lines += $Dr.NameStatus
    $lines += '-- git diff HEAD --stat --'
    $lines += $Dr.DiffStat
    $short = Get-TruncatedDiff -DiffText $Dr.DiffSample -MaxChars $ExcerptMaxChars
    $lines += '-- unified diff excerpt (short) --'
    $lines += $short
    if (-not [string]::IsNullOrWhiteSpace($Dr.UntrackedNote)) {
        $lines += $Dr.UntrackedNote.TrimEnd()
    }
    return ($lines -join "`n")
}

function Request-SingleRepoCommitMessagePlainText {
    param(
        [string]$RepoName,
        [string]$RepoBundle,
        [string]$RepoBundleLite,
        [string]$RepoBundlePathsOnly,
        [pscustomobject]$DrForFallback,
        [string]$BaseUrl,
        [string]$Model,
        [int]$TimeoutMs,
        [int]$NumPredict
    )
    # Instructions live in `system` so the user prompt is only repo name + raw git data (reduces "you pasted a diff" replies).
    $systemPrompt = @'
You output ONLY the body of one git commit message. You are not a tutor or reviewer.

GIT_OUTPUT may contain full source files (including automation scripts). Never write a walkthrough, feature list, README, or "what this script does" article. Never say "the script you've provided" or similar. Write a git log entry: what changed, in imperative mood.

Forbidden in your output: addressing the reader (no "you", "your", "you're comparing", "it looks like you pasted", "here is", "below is", "let me know"); markdown headings (##, ###); fenced code blocks; questions; suggestions section; tables; explaining what git or a diff is.

Required shape (plain text):
- Line 1: one short summary of the change (no feat:/fix:/chore: prefix).
- Line 2: completely empty.
- Lines 3+: optional lines starting with "- " naming files or areas (from the git data only). Max 22 bullet lines. Whole message max 3200 characters.
'@

    function Build-UserPrompt([string]$Bundle) {
        return @"
Repository folder name: $RepoName

Machine-readable git output only. Write the commit message from this data; do not describe the format of the data.

<<<GIT_OUTPUT>>>
$Bundle
<<<END_GIT_OUTPUT>>>
"@
    }

    $userPrompt = Build-UserPrompt -Bundle $RepoBundle
    $resp = Invoke-OllamaGenerate -BaseUrl $BaseUrl -Model $Model -Prompt $userPrompt `
        -TimeoutMs $TimeoutMs -NumPredict $NumPredict -System $systemPrompt
    if (-not $resp.response) {
        throw "Ollama returned no .response field for repo '$RepoName'"
    }
    $msg = Normalize-PlainCommitMessageFromOllama -Raw ([string]$resp.response)

    if (Test-OllamaCommitMessageMalformed -Text $msg) {
        Write-Warning "Repo '$RepoName': first model reply looked like chat/analysis; retrying with stricter prompt (full bundle)."
        $systemRetry = $systemPrompt + @'

If you already started to explain the diff: STOP. Erase that. Output ONLY the commit lines (subject, blank, optional "- " lines). Nothing else.
'@
        $userRetry = @"
Repository folder name: $RepoName

Retry. Previous output was rejected (prose to the reader). Output ONLY commit message lines as specified in system.

<<<GIT_OUTPUT>>>
$RepoBundle
<<<END_GIT_OUTPUT>>>
"@
        $resp2 = Invoke-OllamaGenerate -BaseUrl $BaseUrl -Model $Model -Prompt $userRetry `
            -TimeoutMs $TimeoutMs -NumPredict $NumPredict -System $systemRetry
        if (-not $resp2.response) {
            throw "Ollama retry returned no .response for repo '$RepoName'"
        }
        $msg = Normalize-PlainCommitMessageFromOllama -Raw ([string]$resp2.response)
    }

    if ((Test-OllamaCommitMessageMalformed -Text $msg) -and (-not [string]::IsNullOrWhiteSpace($RepoBundleLite))) {
        Write-Warning "Repo '$RepoName': retrying with abbreviated GIT_OUTPUT (paths/stat/short excerpt only)."
        $systemLite = $systemPrompt + @'

GIT_OUTPUT below is intentionally shortened. Infer the commit from paths and stat; do not narrate tooling.
'@
        $userLite = Build-UserPrompt -Bundle $RepoBundleLite
        $resp3 = Invoke-OllamaGenerate -BaseUrl $BaseUrl -Model $Model -Prompt $userLite `
            -TimeoutMs $TimeoutMs -NumPredict $NumPredict -System $systemLite
        if (-not $resp3.response) {
            throw "Ollama third attempt returned no .response for repo '$RepoName'"
        }
        $msg = Normalize-PlainCommitMessageFromOllama -Raw ([string]$resp3.response)
    }

    if ((Test-OllamaCommitMessageMalformed -Text $msg) -and (-not [string]::IsNullOrWhiteSpace($RepoBundlePathsOnly))) {
        Write-Warning "Repo '$RepoName': retrying with paths-only GIT_OUTPUT (no unified diff)."
        $systemPaths = @'
You output ONLY a git commit message body (subject line, blank line, then "- path" lines). Max 28 bullets.
GIT_OUTPUT has NO file contents—only path lists and diff stat. Do not describe PowerShell, Ollama, or how tools work. Do not use markdown headings or numbered feature lists.
'@
        $userPaths = Build-UserPrompt -Bundle $RepoBundlePathsOnly
        $resp4 = Invoke-OllamaGenerate -BaseUrl $BaseUrl -Model $Model -Prompt $userPaths `
            -TimeoutMs $TimeoutMs -NumPredict $NumPredict -System $systemPaths
        if (-not $resp4.response) {
            throw "Ollama paths-only attempt returned no .response for repo '$RepoName'"
        }
        $msg = Normalize-PlainCommitMessageFromOllama -Raw ([string]$resp4.response)
    }

    if (Test-OllamaCommitMessageMalformed -Text $msg) {
        Write-Warning "Repo '$RepoName': LLM output still unusable; using deterministic fallback from git paths."
        if ($null -eq $DrForFallback) {
            $excerpt = $msg.Substring(0, [Math]::Min(280, $msg.Length))
            throw "Ollama returned chat-style text for repo '$RepoName' and no fallback data was provided. Start of output: $excerpt"
        }
        $msg = Get-FallbackCommitMessageFromDr -Dr $DrForFallback
    }
    return $msg
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
    $nameStatus = Convert-GitOutputToString -Output (git -C $repoPath -c core.autocrlf=false diff HEAD --name-status 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "git diff HEAD --name-status failed in ${repoName}: $nameStatus"
    }
    $diffLimited = Get-TruncatedDiff -DiffText $diffText -MaxChars $MaxDiffCharsPerRepo
    $dirtyRepos += [pscustomobject]@{
        Name          = $repoName
        Path          = $repoPath
        Branch        = $branch.TrimEnd()
        Porcelain     = $porcelain.TrimEnd()
        NameStatus    = $nameStatus.TrimEnd()
        DiffStat      = $diffStat.TrimEnd()
        DiffSample    = $diffLimited
        UntrackedNote = $untrackedNote
    }
}

if ($dirtyRepos.Count -eq 0) {
    $emptyJson = '{}'
    [System.IO.File]::WriteAllText($MessagesPath, $emptyJson, [System.Text.UTF8Encoding]::new($false))
    Write-Host "No uncommitted changes. Wrote empty object to $MessagesPath" -ForegroundColor Cyan
    if ($CommitAndPush) {
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
    $sectionLite = Get-DirtyRepoBundleSectionLite -Dr $dr
    $sectionPaths = Get-DirtyRepoBundleSectionPathsOnly -Dr $dr
    $msg = Request-SingleRepoCommitMessagePlainText -RepoName $repoName -RepoBundle $section `
        -RepoBundleLite $sectionLite -RepoBundlePathsOnly $sectionPaths -DrForFallback $dr `
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

if ($CommitAndPush) {
    $commitScript = Join-Path $scriptDir 'commit-and-push.ps1'
    & $commitScript -MessagesPath $MessagesPath
} else {
    Write-Host "Skipping commit-and-push.ps1 (pass -CommitAndPush to run it after writing JSON)." -ForegroundColor DarkGray
}
