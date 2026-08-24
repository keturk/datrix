#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate: a .gitignore rule may never shadow a publishable file.

.DESCRIPTION
 Activates the Datrix virtual environment and runs
 scripts/library/test/ignored_source.py, which computes -- for the datrix
 showcase repo and every datrix-* clone in the workspace, discovered at
 runtime -- the set difference between the working tree and what a
 'git add -A' would stage. Every element of that difference must be a
 reviewed, scoped entry in scripts/config/ignored-source-exemptions.json;
 anything else is a source file a .gitignore rule is silently deleting from
 every clone.

 WHY IT EXISTS: a package once carried the stock Python .gitignore's
 UNANCHORED `MANIFEST` line. Git matches an unanchored pattern at ANY depth,
 and core.ignorecase=true on this platform makes it case-insensitive, so it
 matched a templates/manifest/ directory and swallowed the Jinja2 templates
 inside it. Nothing was visible locally -- the files were on disk, the tests
 passed, the emitted output compiled. The loss only appears after a clone or
 a wheel install, as a package that cannot generate. It was found by hand,
 by comparing a file count against a `git add -A --dry-run` count. This is
 that comparison, living in code.

 GIT IS THE ORACLE: ignore matching is never re-implemented here.
 `git ls-files -o -i --exclude-standard` produces the difference and
 `git check-ignore -v` names the .gitignore file, line number and pattern
 responsible, so a finding points at the line to fix rather than starting a
 hunt. Anchoring, negation (`!`), nested .gitignore files and
 core.ignorecase interact in ways a hand-rolled matcher gets wrong, and a
 wrong matcher returns a confident "clean" that will be believed.

 EXEMPTIONS ARE SCOPED: each entry excuses one rule over one path scope and
 carries a written reason. An entry for the root build/ tree does not excuse
 the same unanchored rule swallowing a templates/build/ directory of source.
 The file's pinned_count is enforced against the live entry list, so an entry
 cannot be added or removed without the reviewed number moving with it.

 The non-vacuity self-test runs before every scan: a scanner that stopped
 scanning reports a clean tree, which is indistinguishable from a clean tree.

 Exit codes:
   0 = every unstaged working-tree path is a reviewed exemption
   1 = at least one publishable file is shadowed, or the self-test failed
   2 = usage error, or a missing/malformed/miscounted exemption file

.PARAMETER Repo
 Limit the scan to these repo names. Default: every framework repo in the workspace.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.PARAMETER ShowExempt
 Also print every reviewed exemption entry and its written reason.

.PARAMETER Dbg
 Enable DEBUG logging and print the python invocation before running.

.EXAMPLE
 .\ignored-source-gate.ps1
 Scan every framework repo in the workspace.

.EXAMPLE
 .\ignored-source-gate.ps1 -Repo datrix-language
 Scan only the named repo(s).

.EXAMPLE
 .\ignored-source-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.

.EXAMPLE
 .\ignored-source-gate.ps1 -ShowExempt
 Print the reviewed exemption entries with their reasons, then scan.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string[]]$Repo,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$ShowExempt,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$datrixRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)
$pythonScript = Join-Path $datrixRoot "scripts\library\test\ignored_source.py"

$commonDir = Join-Path $datrixRoot "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "Error: ignored_source.py not found at: $pythonScript"
    exit 2
}

function Invoke-Cleanup {
    Disable-DatrixVenv
}

trap {
    Write-Host ""
    Write-Warning "Interrupted by user (Ctrl-C)"
    Invoke-Cleanup
    exit 130
}

try {
    $venvActivated = Ensure-DatrixVenv
    if (-not $venvActivated) {
        Write-Error "Failed to activate virtual environment"
        exit 1
    }

    $venvPath = Get-DatrixVenvPath
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"

    $pythonArgs = @($pythonScript)
    foreach ($name in $Repo) { $pythonArgs += @("--repo", $name) }
    if ($SelfTest) { $pythonArgs += "--self-test" }
    if ($ShowExempt) { $pythonArgs += "--show-exempt" }
    if ($Dbg) { $pythonArgs += "--debug" }

    if ($Dbg) {
        Write-Host "Python executable: $pythonExe" -ForegroundColor Cyan
        Write-Host "Python script: $pythonScript" -ForegroundColor Cyan
        Write-Host ""
    }

    & $pythonExe @pythonArgs
    exit $LASTEXITCODE

} catch {
    Write-Host ""
    Write-Host "Error occurred:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Invoke-Cleanup
    exit 1
} finally {
    Invoke-Cleanup
}
