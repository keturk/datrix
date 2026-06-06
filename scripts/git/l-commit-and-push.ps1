#!/usr/bin/env pwsh
<#
.SYNOPSIS
Build commit-messages.json using a local Ollama model; optionally commit and push.

.DESCRIPTION
Thin wrapper around scripts\library\git\l-commit-and-push.py. The Python
implementation collects changes from each dirty Datrix repository, calls Ollama
once per repo, validates the commit message quality, writes commit-messages.json,
and can then invoke commit-and-push.ps1.

.PARAMETER OllamaBaseUrl
Base URL for Ollama (no trailing path). Default matches local Act Mode setup.

.PARAMETER OllamaModel
Model name. Default: qwen3-coder:30b-ctx32k

.PARAMETER OllamaTimeoutMs
HTTP timeout in milliseconds for the generate request.

.PARAMETER MessagesPath
Output JSON path. Default: commit-messages.json under the workspace root.

.PARAMETER MaxDiffCharsPerRepo
Maximum prompt characters of tracked diff context to include per repo.

.PARAMETER OllamaNumPredict
Ollama option num_predict (max tokens). Default 896.

.PARAMETER CommitAndPush
If set, after writing commit-messages.json runs commit-and-push.ps1 with that file.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$OllamaBaseUrl = 'http://10.94.0.100:11434',

    [Parameter(Mandatory = $false)]
    [string]$OllamaModel = 'qwen3-coder:30b-ctx32k',

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

$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$datrixRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)
$pythonScript = Join-Path $datrixRoot 'scripts\library\git\l-commit-and-push.py'

if (-not (Test-Path -LiteralPath $pythonScript)) {
    Write-Error "Python implementation not found at: $pythonScript"
    exit 1
}

$workspaceRoot = Split-Path -Parent $datrixRoot
$venvPython = Join-Path $workspaceRoot '.venv\Scripts\python.exe'
$pythonExe = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { 'python' }

$args = @(
    $pythonScript,
    '--ollama-base-url', $OllamaBaseUrl,
    '--ollama-model', $OllamaModel,
    '--ollama-timeout-ms', $OllamaTimeoutMs,
    '--max-diff-chars-per-repo', $MaxDiffCharsPerRepo,
    '--ollama-num-predict', $OllamaNumPredict
)

if (-not [string]::IsNullOrWhiteSpace($MessagesPath)) {
    $args += @('--messages-path', $MessagesPath)
}

if ($CommitAndPush) {
    $args += '--commit-and-push'
}

& $pythonExe @args
exit $LASTEXITCODE
