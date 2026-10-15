#!/usr/bin/env pwsh
<#
.SYNOPSIS
    First-pass review of pending changes in every Datrix repo, before commit-and-push.

.DESCRIPTION
    Wraps scripts\git\lib\pre_review.py. Reviews only the lines pending changes ADD to
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
      0 = no definite findings
      1 = definite findings (listed)
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

.EXAMPLE
    .\pre-review.ps1
#>

[CmdletBinding()]
param(
    [Parameter()] [switch]$ModelReview,
    [Parameter()] [string[]]$LocalMachines = @(),
    [Parameter()] [string[]]$LlmModel = @(),
    [Parameter()] [int]$LlmTimeout = 180
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixScriptCommon.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pyArgs = @()
if ($ModelReview) {
    $pyArgs += "--model-review"
    $pyArgs += Get-DatrixLocalLlmArguments -LocalMachines $LocalMachines -LlmModel $LlmModel -LlmTimeoutSeconds $LlmTimeout
}

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\pre_review.py") -Arguments $pyArgs)
