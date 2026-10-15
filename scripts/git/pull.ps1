#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Pull every Datrix repository, then summarize which pulled and which did not.

.DESCRIPTION
    Wraps scripts\git\lib\pull.py. Pulls each git repository directly under the
    workspace root in turn, printing git's output under its name, then prints one summary
    grouping every repository by outcome:
      Updated                    new commits pulled (old..new, commit count)
      Up to date                 nothing to pull
      Conflict                   the pull stopped with unmerged paths (listed)
      Blocked by local changes   the pull would overwrite local changes or untracked
                                 files (listed); nothing merged -- run /resolve-conflicts
      Failed                     anything else (no upstream, network, auth); git's error shown

    Exit codes:
      0 = every repository updated or up to date
      1 = at least one repository conflicted, was blocked, or failed
      2 = the run could not start

.EXAMPLE
    .\pull.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\pull.py"))
