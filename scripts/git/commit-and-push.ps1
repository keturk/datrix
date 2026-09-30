#!/usr/bin/env pwsh
<#
.SYNOPSIS
Generate commit messages for every dirty Datrix repo and commit+push them.

.DESCRIPTION
Single entry point that wraps scripts\library\git\commit-and-push.py. The Python
implementation splits each dirty Datrix repository's changes into themed change
sets, generates one commit message per set, commits each set separately, and
pushes each repo once.

Themes are areas, not top-level folders: container directories (src\<package>,
tests\<tier>, scripts, examples) are stepped through, so a generator and its tests
land in one commit while an unrelated docs edit gets its own. Each message
describes one coherent change, which is what keeps subjects within 72 characters.

Message source is chosen automatically:
 * The local machines (-LocalMachines) are searched for model servers: Ollama on
   port 11434 and OpenAI-compatible servers (vLLM, llama-server) on 8000, 8080 and
   8081. What each serves is discovered, not configured. Models already in memory
   on any machine are used first, in machine order; an Ollama model is loaded only
   when nothing is resident. A model that fails to answer hands over to the next.
 * If no local model can answer, the script falls back to the Claude Code CLI, run
   with no tools and none of the workspace's CLAUDE.md, hooks or skills.

Force a backend with -MessageSource local|claude. No commit-messages.json is
written -- generation and commit/push happen in one pass.

.PARAMETER MessageSource
auto (default), local, or claude. auto tries every discovered local model and
falls back to Claude; local tries every discovered local model and errors if none
can answer.

.PARAMETER LocalMachines
Machines (host name or IP address) to search for model servers, in preference
order. Omit to search the default list in library/shared/local_llm.py (--help
shows it): the Dell T5820 and T7920 (RTX 3090) and the ASUS GX10.

.PARAMETER LocalTimeoutMs
HTTP timeout (ms) for each local generate request, with the model already loaded.

.PARAMETER LocalLoadTimeoutMs
Timeout (ms) for readying a model before the first message: loading an Ollama
model into memory, or a server's first answer. Default 900000: a cold load of a
large model from a slow disk takes minutes.

.PARAMETER LocalMaxTokens
Maximum tokens a local model may generate for one message. Default 896.

.PARAMETER ClaudeModel
Claude model used by the Claude Code CLI fallback. Default: sonnet

.PARAMETER ClaudeTimeoutMs
Timeout (ms) for each Claude CLI invocation. Default 300000.

.PARAMETER MaxDiffCharsPerCommit
Maximum prompt characters of diff context sent to the model for one change set.

.PARAMETER MaxCommitsPerRepo
Upper bound on themed commits per repo (default 8); past it the smallest change
sets are folded into one "other changes" commit. 1 commits each repo as a single
change.

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

.PARAMETER SkipPolyStringCaseCheck
Skip the PolyString case round-trip check that runs before anything is staged.

Every dirty repo's pending .py files are parsed, and any call to a
datrix_common.utils.text case function whose argument is str()-wrapped,
str()-bound in the same scope, a nested case call, or an extract_simple_name()
call aborts the whole run with nothing committed (see
test/polystring-case-roundtrip-gate.ps1). A name the generator re-cases is a
PolyString that already carries .snake/.pascal/...; the round trip discards
the variants and hides that the value was a name, and it reached more than a
thousand sites while the only check was an on-demand Semgrep warning. Pass
this only for a confirmed false positive -- it prints a warning and commits
regardless.

.EXAMPLE
.\commit-and-push.ps1
Auto-detect backend, generate messages, commit and push every dirty repo.

.EXAMPLE
.\commit-and-push.ps1 -MessageSource claude
Force the Claude Code CLI as the message source.

.EXAMPLE
.\commit-and-push.ps1 -DryRun
Print the generated messages without committing.

.EXAMPLE
.\commit-and-push.ps1 -LocalMachines 10.94.0.102, 10.94.0.101
Search only these machines, in this order: the GX10 first, then the T7920.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [ValidateSet('auto', 'local', 'claude')]
    [string]$MessageSource = 'auto',

    [Parameter(Mandatory = $false)]
    [string[]]$LocalMachines = @(),

    [Parameter(Mandatory = $false)]
    [int]$LocalTimeoutMs = 180000,

    [Parameter(Mandatory = $false)]
    [int]$LocalLoadTimeoutMs = 900000,

    [Parameter(Mandatory = $false)]
    [int]$LocalMaxTokens = 896,

    [Parameter(Mandatory = $false)]
    [string]$ClaudeModel = 'sonnet',

    [Parameter(Mandatory = $false)]
    [int]$ClaudeTimeoutMs = 300000,

    [Parameter(Mandatory = $false)]
    [int]$MaxDiffCharsPerCommit = 45000,

    [Parameter(Mandatory = $false)]
    [ValidateRange(1, [int]::MaxValue)]
    [int]$MaxCommitsPerRepo = 8,

    [switch]$DryRun,

    [switch]$SkipCustomerDomainCheck,

    [switch]$SkipIgnoredSourceCheck,

    [switch]$SkipPolyStringCaseCheck
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
    '--local-timeout-ms', $LocalTimeoutMs,
    '--local-load-timeout-ms', $LocalLoadTimeoutMs,
    '--local-max-tokens', $LocalMaxTokens,
    '--claude-model', $ClaudeModel,
    '--claude-timeout-ms', $ClaudeTimeoutMs,
    '--max-diff-chars-per-commit', $MaxDiffCharsPerCommit,
    '--max-commits-per-repo', $MaxCommitsPerRepo
)

# The default machine list lives only in library/shared/local_llm.py; it is overridden
# only when -LocalMachines is passed.
foreach ($localMachine in $LocalMachines) {
    $pyArgs += @('--local-machine', $localMachine)
}

if ($DryRun) {
    $pyArgs += '--dry-run'
}

if ($SkipCustomerDomainCheck) {
    $pyArgs += '--skip-customer-domain-check'
}

if ($SkipIgnoredSourceCheck) {
    $pyArgs += '--skip-ignored-source-check'
}

if ($SkipPolyStringCaseCheck) {
    $pyArgs += '--skip-polystring-case-check'
}

& $pythonExe @pyArgs
exit $LASTEXITCODE
