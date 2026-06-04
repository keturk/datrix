<#
.SYNOPSIS
 Fully automated commit-and-push: invokes Claude Code to analyze changes, generate commit messages, and push.

.DESCRIPTION
 This wrapper script automates the entire commit-and-push workflow:
 1. Invokes Claude Code in CLI mode to analyze all Datrix repos and generate commit-messages.json
 2. If Claude successfully generates the JSON file, automatically runs commit-and-push.ps1
 3. Reports success or failure

 Claude Code CLI must be available in PATH as 'claude' or 'claude.exe'.

.PARAMETER MessagesPath
 Optional. Path where Claude should write commit-messages.json. Default: D:\datrix\commit-messages.json

.PARAMETER Dbg
 Optional. Pass debug flag to commit-and-push.ps1 for verbose output.

.EXAMPLE
 .\auto-commit-and-push.ps1
 Generates commit-messages.json in D:\datrix and commits/pushes all dirty repos.

.EXAMPLE
 .\auto-commit-and-push.ps1 -Dbg
 Same as above with debug output during commit/push phase.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$MessagesPath = 'D:\datrix\commit-messages.json',

    [switch]$Dbg
)

$ErrorActionPreference = 'Stop'

# Resolve script locations
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$commitAndPushScript = Join-Path $scriptPath "commit-and-push.ps1"

if (-not (Test-Path $commitAndPushScript)) {
    Write-Error "commit-and-push.ps1 not found at: $commitAndPushScript"
}

# Ensure workspace root exists
$workspaceRoot = 'D:\datrix'
if (-not (Test-Path $workspaceRoot)) {
    Write-Error "Workspace root not found: $workspaceRoot"
}

# Check if Claude Code CLI is available. Prefer native/cmd shims on Windows so
# PowerShell execution policy does not block the npm-generated claude.ps1 shim.
$claudeCmd = Get-Command 'claude.cmd' -ErrorAction SilentlyContinue
if (-not $claudeCmd) {
    $claudeCmd = Get-Command 'claude.exe' -ErrorAction SilentlyContinue
}
if (-not $claudeCmd) {
    $claudeCmd = Get-Command 'claude' -ErrorAction SilentlyContinue
}
if (-not $claudeCmd) {
    Write-Error @"
Claude Code CLI not found in PATH.

Please ensure 'claude' command is available. Install via:
  npm install -g @anthropic-ai/claude-code

Or ensure the Claude Code CLI is in your PATH.
"@
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Auto Commit and Push - Claude-Powered" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Invoke Claude Code to generate commit-messages.json
Write-Host "Step 1: Invoking Claude Code to analyze changes and generate commit messages..." -ForegroundColor Yellow
Write-Host ""

# Remove existing commit-messages.json if present to ensure we detect fresh generation
if (Test-Path $MessagesPath) {
    Write-Host "Removing existing commit-messages.json to ensure fresh generation..." -ForegroundColor Gray
    Remove-Item -LiteralPath $MessagesPath -Force
}

# Build the prompt for Claude.
# The schema below is REQUIRED, not advisory: commit-and-push.ps1 reads each
# commits[] entry's "repo" and "message". An entry without a usable message
# (no "message", and no "subject") aborts the whole run. The prompt pins the
# exact shape and a concrete example so generation is deterministic.
$claudePrompt = @"
Analyze all Datrix repositories for uncommitted changes and generate commit-messages.json.

Follow the /commit-and-push skill workflow:

1. Scan for changes in all repos under $workspaceRoot (use: git status --porcelain)
2. For each dirty repo, inspect diffs (git diff, git diff --cached, git diff --stat)
   so the commit message accurately describes what changed and why.
3. Write the JSON file to: $MessagesPath
4. Report which repos have changes and which are clean.

DO NOT run the commit-and-push.ps1 script - only generate the JSON file.

REQUIRED JSON SCHEMA - the file MUST be a single JSON object with a "commits"
array. Every entry MUST have a non-empty "repo" (the repo directory name) and a
non-empty "message" (the full commit message, with \n for line breaks). Include
ONLY repos that have uncommitted changes. Do not invent other field names for the
message - the consuming script reads "message". Extra sibling/metadata keys are
ignored by the script, so keep the file minimal.

Exact shape to produce:

{
  "commits": [
    {
      "repo": "datrix-common",
      "message": "Add transpiler context for DB session injection\n\n- context.py: add known_db_service_function_sessions mapping\n- scope.py: add in_lambda_body depth counter"
    },
    {
      "repo": "datrix-language",
      "message": "Resolve bare resource/batch entity refs to rest_api default RDBMS\n\n- api_transformer.py: accept the owning rest_api's declared default block"
    }
  ]
}

Message style:
- No conventional-commit prefix (no feat:/fix:/chore:) in the first line.
- First line: a clear, specific summary of what the commit does.
- Then a blank line (\n\n), then per-file or per-path bullet notes.
- Be specific - never "update files" or "various changes".
"@

# Invoke Claude Code in CLI mode with -p for non-interactive execution.
# Stream output so permission/tool failures are visible while the process runs.
Set-Location $workspaceRoot
$env:NO_COLOR = "1"
$claudeArgs = @(
    '-p', $claudePrompt,
    '--model', 'sonnet',
    '--permission-mode', 'acceptEdits',
    '--allowedTools',
        'Read',
        'Glob',
        'Grep',
        'Write',
        'Edit',
        'MultiEdit',
        'Bash(git:*)',
    '--add-dir', $workspaceRoot
)

$claudeOutput = @()
& $claudeCmd.Source @claudeArgs 2>&1 | Tee-Object -Variable claudeOutput
$claudeExitCode = $LASTEXITCODE

if ($claudeExitCode -ne 0) {
    Write-Host "Claude Code CLI failed with exit code: $claudeExitCode" -ForegroundColor Red
    Write-Host "Output:" -ForegroundColor Red
    Write-Host ($claudeOutput -join "`n")
    throw "Claude Code CLI invocation failed"
}

Write-Host "Claude Code output:" -ForegroundColor Gray
Write-Host ($claudeOutput -join "`n")
Write-Host ""

# Step 2: Verify commit-messages.json was created
Write-Host "Step 2: Verifying commit-messages.json was generated..." -ForegroundColor Yellow

if (-not (Test-Path $MessagesPath)) {
    Write-Error @"
Claude Code did not generate commit-messages.json at: $MessagesPath

This may happen if:
- No repos have uncommitted changes
- Claude encountered an error during analysis
- The CLI invocation failed

Check the Claude output above for details.
"@
}

# Validate JSON is parseable
$jsonText = Get-Content -LiteralPath $MessagesPath -Raw -Encoding UTF8
try {
    $messages = $jsonText | ConvertFrom-Json
} catch {
    Write-Error "Generated commit-messages.json is invalid JSON: $_"
}

if ($messages -isnot [PSCustomObject]) {
    Write-Error "Generated commit-messages.json root must be a JSON object."
}

# Count repos to commit, mirroring commit-and-push.ps1's two accepted schemas:
#  rich -> length of commits[]; flat -> number of top-level keys.
if ($null -ne $messages.commits) {
    $repoCount = @($messages.commits).Count
} else {
    $repoCount = @($messages.PSObject.Properties).Count
}
Write-Host "commit-messages.json generated successfully with $repoCount repo(s)" -ForegroundColor Green
Write-Host ""

# Step 3: Run commit-and-push.ps1
Write-Host "Step 3: Running commit-and-push.ps1..." -ForegroundColor Yellow
Write-Host ""

$commitArgs = @($MessagesPath)
if ($Dbg) {
    $commitArgs += '-Dbg'
}

& $commitAndPushScript @commitArgs

if ($LASTEXITCODE -ne 0) {
    Write-Error "commit-and-push.ps1 failed with exit code: $LASTEXITCODE"
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Auto Commit and Push completed successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
