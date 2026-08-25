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

.PARAMETER SkipCustomerDomainCheck
Skip the customer-domain isolation check that runs before anything is staged.

Before any message is generated, every dirty repo's pending changes are scanned
against the hashed customer-term corpus (scripts/config/customer-term-hashes.json);
one hit aborts the whole run with nothing committed, so a violation in the last
repo cannot leave the first four already pushed. Customer/project domain language
must never enter a framework repo, and prose alone did not stop it. Pass this only
for a confirmed false positive -- it prints a warning and commits regardless.

.PARAMETER SkipIgnoredSourceCheck
Skip the ignored-source check that runs before anything is staged.

The same seam asked in the opposite direction: the isolation check asks what a
`git add -A` must not carry IN, this one asks what it silently leaves OUT. Every
dirty repo's working tree is compared against what `git add -A` would stage, and
any file git refuses to stage must be a reviewed, scoped entry in
scripts/config/ignored-source-exemptions.json. One unexplained file aborts the
whole run with nothing committed, naming the file AND the .gitignore line
responsible. An unanchored stock `MANIFEST` pattern once swallowed a package's
shipped templates -- invisible locally, the files on disk and the tests green,
and only visible after a clone as a package that cannot generate. Pass this only
for a confirmed false positive -- it prints a warning and commits regardless.

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

    [switch]$DryRun,

    [switch]$SkipCustomerDomainCheck,

    [switch]$SkipIgnoredSourceCheck
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

if ($SkipCustomerDomainCheck) {
    $pyArgs += '--skip-customer-domain-check'
}

if ($SkipIgnoredSourceCheck) {
    $pyArgs += '--skip-ignored-source-check'
}

& $pythonExe @pyArgs
exit $LASTEXITCODE
