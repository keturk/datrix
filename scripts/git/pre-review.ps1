#!/usr/bin/env pwsh
<#
.SYNOPSIS
 First-pass review of pending changes in every Datrix repo, before commit-and-push.

.DESCRIPTION
 The behaviour is datrix_scripts.git.pre_review. Reviews only the lines pending changes ADD to
 Python files, across every workspace repository with uncommitted changes.

 Definite findings, read from each file's syntax tree and reported only on added lines:
   get-none       .get(key, None) silent fallback
   bare-except    except: with no exception named
   except-pass    an except whose body is only pass / ...
   todo-comment   TODO / FIXME / XXX / HACK
   untyped-def    a parameter or return without an annotation
   placeholder    a body of only pass / ... / a docstring / raise NotImplementedError
                  (Protocol, ABC, @abstractmethod and @overload declarations are exempt)
   syntax-error   the file does not parse
 These run on this machine and alone decide the exit code.

 -ModelReview also asks a local model for advisory findings on non-test files. Measured
 on qwen3.6-35b, those were nearly all false positives, so it is off by default and never
 changes the exit code.

 Exit codes:
   0 = no definite findings (or a passing -SelfTest)
   1 = definite findings (listed), or a self-test check failed
   2 = the review could not run

.PARAMETER ModelReview
 Also ask a local model for advisory findings (sends added code to a model server on the
 local network).

.PARAMETER LocalMachines
 With -ModelReview: machines to search for model servers, in preference order.

.PARAMETER LlmModel
 With -ModelReview: models to use, best first.

.PARAMETER LlmTimeout
 With -ModelReview: request timeout in seconds. Default: 180.

.PARAMETER SelfTest
 Run only the module's self-test (the local-model option mapping, the census that no git script
 runs stash/reset/checkout/revert/restore) and the wrapper seam checks.

.EXAMPLE
 .\git\pre-review.ps1
#>
[CmdletBinding()]
param(
 [switch]$ModelReview,
 [string[]]$LocalMachines,
 [string[]]$LlmModel,
 [int]$LlmTimeout,
 [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.git.pre_review" -Parameters $PSBoundParameters
exit $LASTEXITCODE
