#!/usr/bin/env pwsh
<#
.SYNOPSIS
Generate commit messages for every dirty Datrix repo and commit+push them.

.DESCRIPTION
Single entry point that wraps scripts\library\git\commit-and-push.py. The Python
implementation collects changes from each dirty Datrix repository, generates one
commit message per repo, then stages, commits, and pushes it.

Message source is chosen automatically:
 * If a local Ollama endpoint is reachable, messages come from the local model.
 * Otherwise the script falls back to the Claude Code CLI.

Force a backend with -MessageSource ollama|claude. No commit-messages.json is
written -- generation and commit/push happen in one pass.

.PARAMETER MessageSource
auto (default), ollama, or claude. auto probes Ollama and falls back to Claude.

.PARAMETER OllamaBaseUrl
Base URL for Ollama (no trailing path). Default matches the local Act Mode setup.

.PARAMETER OllamaModel
Ollama model name. Default: qwen3-coder:30b-ctx32k

.PARAMETER OllamaTimeoutMs
HTTP timeout (ms) for each Ollama generate request.

.PARAMETER OllamaNumPredict
Ollama option num_predict (max tokens). Default 896.

.PARAMETER ClaudeModel
Claude model used by the Claude Code CLI fallback. Default: sonnet

.PARAMETER ClaudeTimeoutMs
Timeout (ms) for each Claude CLI invocation. Default 300000.

.PARAMETER MaxDiffCharsPerRepo
Maximum prompt characters of tracked diff context to include per repo.

.PARAMETER DryRun
Generate and print commit messages but do not commit or push.

.EXAMPLE
.\commit-and-push.ps1
Auto-detect backend, generate messages, commit and push every dirty repo.

.EXAMPLE
.\commit-and-push.ps1 -MessageSource claude
Force the Claude Code CLI as the message source.

.EXAMPLE
.\commit-and-push.ps1 -DryRun
Print the generated messages without committing.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [ValidateSet('auto', 'ollama', 'claude')]
    [string]$MessageSource = 'auto',

    [Parameter(Mandatory = $false)]
    [string]$OllamaBaseUrl = 'http://10.94.0.100:11434',

    [Parameter(Mandatory = $false)]
    [string]$OllamaModel = 'qwen3-coder:30b-ctx32k',

    [Parameter(Mandatory = $false)]
    [int]$OllamaTimeoutMs = 180000,

    [Parameter(Mandatory = $false)]
    [int]$OllamaNumPredict = 896,

    [Parameter(Mandatory = $false)]
    [string]$ClaudeModel = 'sonnet',

    [Parameter(Mandatory = $false)]
    [int]$ClaudeTimeoutMs = 300000,

    [Parameter(Mandatory = $false)]
    [int]$MaxDiffCharsPerRepo = 45000,

    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$datrixRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)
$pythonScript = Join-Path $datrixRoot 'scripts\library\git\commit-and-push.py'

if (-not (Test-Path -LiteralPath $pythonScript)) {
    Write-Error "Python implementation not found at: $pythonScript"
    exit 1
}

$workspaceRoot = Split-Path -Parent $datrixRoot
$venvPython = Join-Path $workspaceRoot '.venv\Scripts\python.exe'
$pythonExe = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { 'python' }

$pyArgs = @(
    $pythonScript,
    '--message-source', $MessageSource,
    '--ollama-base-url', $OllamaBaseUrl,
    '--ollama-model', $OllamaModel,
    '--ollama-timeout-ms', $OllamaTimeoutMs,
    '--ollama-num-predict', $OllamaNumPredict,
    '--claude-model', $ClaudeModel,
    '--claude-timeout-ms', $ClaudeTimeoutMs,
    '--max-diff-chars-per-repo', $MaxDiffCharsPerRepo
)

if ($DryRun) {
    $pyArgs += '--dry-run'
}

& $pythonExe @pyArgs
exit $LASTEXITCODE
