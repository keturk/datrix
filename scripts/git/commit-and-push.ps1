#!/usr/bin/env pwsh
<#
.SYNOPSIS
Generate commit messages for every dirty Datrix repo and commit+push them.

.DESCRIPTION
The behaviour is datrix_scripts.git.commit_and_push. It splits each dirty Datrix
repository's changes into themed change sets, generates one commit message per set,
commits each set separately, and pushes each repo once.

Themes are areas, not top-level folders: container directories (src\<package>,
tests\<tier>, scripts, examples) are stepped through, so a generator and its tests
land in one commit while an unrelated docs edit gets its own. Each message
describes one coherent change, which is what keeps subjects within 72 characters.

Message source is chosen automatically:
 * The local machines (-LocalMachines) are searched for an Ollama server on port
   11434. What each holds and can load is discovered, not configured. Models already
   in memory on any machine are used first, in machine order; a model is loaded only
   when nothing is resident. A model that fails to answer hands over to the next.
 * If no local model can answer, the script falls back to the Claude Code CLI, run
   with no tools and none of the workspace's CLAUDE.md, hooks or skills.

Force a backend with -MessageSource local|claude. No commit-messages.json is
written -- generation and commit/push happen in one pass.

Before a message is generated or anything is staged, every dirty repo's pending
files are also scanned for a reference to a design document, a task file or an
item label (task-NN-MM, design NNN, a lettered item label in parentheses or
before a colon, the possessive of a bare task id -- see
gates/repo-hygiene/design-task-reference-gate.ps1). Those files are gitignored and numbered per
machine, so a committed reference dangles after a clone. One hit aborts the whole
run with nothing committed, naming file, line and label. There is NO skip switch:
a reference cannot be committed.

Likewise, every dirty repo's pending .py files are linted for pyflakes findings
(ruff check --select F) and top-level blank-line findings (ruff check --preview
--select E302,E305), each run from the repo root so its per-file-ignores apply; see
gates/repo-hygiene/python-lint-correctness-gate.ps1: an unused import, an undefined name, a
test function shadowed by a same-named redefinition, or a top-level def/class without two
blank lines before or after it. The checked-in output under
examples/**/generated/ is generator output and is not linted here. One finding aborts the whole
run with nothing committed, naming file, line and code. There is NO skip switch;
a genuinely required finding is suppressed on its own line with `# noqa: <code>`
and the reason.

Exit codes: 0 = committed and pushed (or a dry run, nothing to commit, a passing -SelfTest);
1 = a check or git command failed, or a self-test check failed; 2 = a bad argument.

.PARAMETER MessageSource
auto (default), local, or claude. auto tries every discovered local model and
falls back to Claude; local tries every discovered local model and errors if none
can answer.

.PARAMETER LocalMachines
Machines (host name or IP address) to search for model servers, in preference
order. Omit to search the default list in common/lib/datrix_scripts/local_llm.py (--help
shows it): the Dell T5820 and T7920 (RTX 3090) and the ASUS GX10.

.PARAMETER LocalTimeoutMs
HTTP timeout (ms) for each local generate request, with the model already loaded.
Default 180000.

.PARAMETER LocalLoadTimeoutMs
Timeout (ms) for readying a model before the first message: loading it into
Ollama's memory, or renewing a loaded one. Default 900000: a cold load of a
large model from a slow disk takes minutes.

.PARAMETER LocalMaxTokens
Maximum tokens a local model may generate for one message. Default 896.

.PARAMETER ClaudeModel
Claude model used by the Claude Code CLI fallback. Default: sonnet

.PARAMETER ClaudeTimeoutMs
Timeout (ms) for each Claude CLI invocation. Default 300000.

.PARAMETER MaxDiffCharsPerCommit
Maximum prompt characters of diff context sent to the model for one change set.
Default 45000.

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
gates/repo-hygiene/polystring-case-roundtrip-gate.ps1). A name the generator re-cases is a
PolyString that already carries .snake/.pascal/...; the round trip discards
the variants and hides that the value was a name, and it reached more than a
thousand sites while the only check was an on-demand Semgrep warning. Pass
this only for a confirmed false positive -- it prints a warning and commits
regardless.

.PARAMETER GateRepairAttempts
How many times a failed lint, PolyString or design/task-reference gate is handed to a
Claude agent to fix before every check is re-run. Default 3; 0 reports the failure and
ends the run instead. A dry run never repairs, since it must change nothing.

The agent reads, searches and edits files only (no shell: it cannot stage, commit, push or
run this script), under the workspace's own CLAUDE.md and hooks. The re-run of the checks is
the proof; the commit and push continue once they pass. The customer-domain and
ignored-source checks are never handed over: the first redacts its term on purpose, and the
second is fixed by loosening a .gitignore rule or the exemption file, which a person decides.

.PARAMETER GateRepairModel
Claude model of the gate repair agent. Default: claude-sonnet-5-5

.PARAMETER GateRepairEffort
Effort level of the gate repair agent: low, medium, high, xhigh or max. Default: medium

.PARAMETER GateRepairTimeoutMs
Timeout (ms) for each gate repair agent run. Default 1800000.

.PARAMETER SelfTest
Run only the module's self-test (a planted customer term, registered by digest in a
temporary workspace's corpus, fails the whole run with nothing committed or staged; the
local-model option mapping; the census that no git script runs stash/reset/checkout/revert/
restore) and the wrapper seam checks.

.EXAMPLE
.\git\commit-and-push.ps1
Auto-detect backend, generate messages, commit and push every dirty repo.

.EXAMPLE
.\git\commit-and-push.ps1 -MessageSource claude
Force the Claude Code CLI as the message source.

.EXAMPLE
.\git\commit-and-push.ps1 -DryRun
Print the generated messages without committing.

.EXAMPLE
.\git\commit-and-push.ps1 -LocalMachines 10.94.0.102, 10.94.0.101
Search only these machines, in this order: the GX10 first, then the T7920.
#>
[CmdletBinding()]
param(
 [ValidateSet('auto', 'local', 'claude')]
 [string]$MessageSource,
 [string[]]$LocalMachines,
 [int]$LocalTimeoutMs,
 [int]$LocalLoadTimeoutMs,
 [int]$LocalMaxTokens,
 [string]$ClaudeModel,
 [int]$ClaudeTimeoutMs,
 [int]$MaxDiffCharsPerCommit,
 [ValidateRange(1, [int]::MaxValue)]
 [int]$MaxCommitsPerRepo,
 [switch]$DryRun,
 [switch]$SkipCustomerDomainCheck,
 [switch]$SkipIgnoredSourceCheck,
 [switch]$SkipPolyStringCaseCheck,
 [ValidateRange(0, [int]::MaxValue)]
 [int]$GateRepairAttempts,
 [string]$GateRepairModel,
 [ValidateSet('low', 'medium', 'high', 'xhigh', 'max')]
 [string]$GateRepairEffort,
 [int]$GateRepairTimeoutMs,
 [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.git.commit_and_push" -Parameters $PSBoundParameters
exit $LASTEXITCODE
