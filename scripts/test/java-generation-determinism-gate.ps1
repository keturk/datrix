#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Java generation-pipeline determinism gate: the SAME source tree, generated
  N times in a row via the documented single-project generate.ps1 path, must
  never produce two different outcomes.

.DESCRIPTION
  Background: a bless sweep for the java parity baseline found that running
  the IDENTICAL command against an UNCHANGED tree three times in a row
  produced THREE DIFFERENT outcomes -- once failing inside the "generate:java"
  pipeline stage itself (a struct-test planner unable to resolve a struct from
  the Application it was planned against), twice failing later at `mvnw
  compile` with a set of Java compiler errors. Same input, same invocation,
  different output: every java parity baseline is only provisionally
  trustworthy until this class of regression is caught automatically.

  Each run is its OWN `generate.ps1` process (a fresh `python.exe`
  invocation), so this gate also exercises PYTHONHASHSEED-driven ordering
  bugs that a single long-lived process would never surface -- a `set`
  iterated without a deterministic sort produces different orderings across
  separate Python processes by default, but always the same ordering within
  one process. `dev\byte-identity-generate.ps1` diffs a "before" code state
  against the current tree (proving a CODE CHANGE is output-neutral); it does
  NOT run the same code twice, so it cannot catch this class of bug. This
  gate closes that hole: same code, N runs, N outcomes compared to each
  other.

  The gate:
    1. Generates the reference example N times (default 5, matching the
       investigation's own repro loop), into N explicit --output directories,
       via the documented generate.ps1 --source/--output single-project mode.
    2. Each run is classified SUCCESS (generation + post-processing exited 0)
       or FAILED (non-zero exit), and a normalized fingerprint is computed:
         - SUCCESS: a per-relative-path sha256 manifest of the generated
           source tree, excluding `.datrix` (its own audit log / snapshot /
           manifest `generated_at` timestamp are expected to differ every
           run by design -- they record WHEN generation ran, not WHAT it
           produced).
         - FAILED: the generation log's error section, with the run's own
           output directory path replaced by a fixed placeholder (so two
           runs failing for the identical reason in different --output
           directories fingerprint identically instead of spuriously
           differing on the run-specific path embedded in every compiler
           error line).
    3. All N runs must be the SAME classification, and all N fingerprints
       must be IDENTICAL. Any run whose classification or fingerprint differs
       from run 1 fails the gate and is reported by name.

  This gate does not require generation to currently SUCCEED for the
  reference example -- a consistent, reproducible FAILURE (same stage, same
  error, every run) is a passing outcome. The property under test is
  determinism, not correctness of the generated Java; unrelated, already
  tracked codegen defects are out of this gate's scope.

.PARAMETER OutputRoot
  Root under which run1/ .. runN/ are written. Default:
  d:/datrix/.test-output/java-determinism-gate (per the repo temp-output
  policy).

.PARAMETER Runs
  Number of repeated generations to compare. Default 5 (the investigation's
  own repro-loop size). Must be >= 2.

.PARAMETER Dbg
  Forward -Dbg (debug logging) to generate.ps1.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$OutputRoot = "d:/datrix/.test-output/java-determinism-gate",

    [Parameter()]
    [int]$Runs = 5,

    [Alias("Dbg")]
    [switch]$DebugLogging
)

$ErrorActionPreference = "Stop"

if ($Runs -lt 2) {
    throw "Runs must be >= 2 (need at least two outcomes to compare); got $Runs."
}

# ---------------------------------------------------------------------------
# Bootstrap (venv + paths), modeled on test/typescript-whole-system-gate.ps1.
# ---------------------------------------------------------------------------
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$datrixScriptsRoot = Split-Path -Parent $scriptDir
$commonDir = Join-Path $datrixScriptsRoot "common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

$venvActivated = Ensure-DatrixVenv
if (-not $venvActivated) {
    throw "Could not activate the Datrix Python venv; cannot run the java generation determinism gate."
}

$datrixRoot = Get-DatrixRoot
$generateScript = Join-Path (Join-Path $datrixScriptsRoot "dev") "generate.ps1"
if (-not (Test-Path -LiteralPath $generateScript)) {
    throw "generate.ps1 not found at: $generateScript"
}

# The example this class of non-determinism was originally found against.
$exampleSource = Join-Path $datrixRoot "datrix/examples/02-features/03-infrastructure-blocks/nosql/system.dtrx"
if (-not (Test-Path -LiteralPath $exampleSource)) {
    throw "Reference example not found at: $exampleSource"
}

# `.datrix` holds the run's own audit log / snapshot / manifest generated_at
# timestamp -- expected to differ every invocation by design. Excluded from
# both the success manifest and (implicitly, via log-only scanning) the
# failure fingerprint.
$ExcludedDirNames = @('.datrix')

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Invoke-JavaGeneration {
    param(
        [Parameter(Mandatory = $true)][string]$OutputDir
    )
    if (Test-Path -LiteralPath $OutputDir) {
        Remove-Item -LiteralPath $OutputDir -Recurse -Force
    }
    $genArgs = @{
        Source   = $exampleSource
        Output   = $OutputDir
        Language = "java"
    }
    if ($DebugLogging) { $genArgs.Dbg = $true }
    $resultsDir = Join-Path $datrixRoot ".generated/.results"
    $logBefore = Get-ChildItem -LiteralPath $resultsDir -Filter "generate-results-*.log" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    & $generateScript @genArgs | Out-Null
    $exitCode = $LASTEXITCODE
    $logAfter = Get-ChildItem -LiteralPath $resultsDir -Filter "generate-results-*.log" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $logPath = $null
    if ($null -ne $logAfter -and ($null -eq $logBefore -or $logAfter.FullName -ne $logBefore.FullName)) {
        $logPath = $logAfter.FullName
    }
    return [PSCustomObject]@{
        ExitCode = $exitCode
        LogPath  = $logPath
    }
}

function Get-GeneratedSourceFiles {
    <#
      Iterative directory walk returning generated-source files under $Root,
      pruning any directory whose name is in $ExcludedDirNames and never
      descending into reparse points.
    #>
    param([Parameter(Mandatory = $true)][string]$Root)

    $rootFull = (Resolve-Path -LiteralPath $Root).Path
    $rootLen = $rootFull.Length
    $results = New-Object System.Collections.Generic.List[object]
    $stack = New-Object System.Collections.Generic.Stack[string]
    $stack.Push($rootFull)

    while ($stack.Count -gt 0) {
        $dir = $stack.Pop()
        $children = Get-ChildItem -LiteralPath $dir -Force -ErrorAction SilentlyContinue
        foreach ($child in $children) {
            $isReparse = ($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
            if ($child.PSIsContainer) {
                if ($ExcludedDirNames -contains $child.Name) { continue }
                if ($isReparse) { continue }
                $stack.Push($child.FullName)
            }
            else {
                if ($isReparse) { continue }
                $rel = $child.FullName.Substring($rootLen).TrimStart('\', '/') -replace '\\', '/'
                $results.Add([PSCustomObject]@{
                        RelKey   = $rel.ToLowerInvariant()
                        FullPath = $child.FullName
                    })
            }
        }
    }
    return $results
}

function Get-SuccessManifestHash {
    param([Parameter(Mandatory = $true)][string]$Root)
    $files = Get-GeneratedSourceFiles -Root $Root | Sort-Object RelKey
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($f in $files) {
        $fileHash = (Get-FileHash -LiteralPath $f.FullPath -Algorithm SHA256).Hash
        $lines.Add("$($f.RelKey):$fileHash")
    }
    $joined = [string]::Join("`n", $lines)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($joined)
    $hashBytes = $sha256.ComputeHash($bytes)
    return [System.BitConverter]::ToString($hashBytes).Replace('-', '').ToLowerInvariant()
}

function Get-FailureFingerprint {
    <#
      Normalizes a generation-results log into a stable failure signature:
      strips the run-specific timestamp/log-path preamble lines and replaces
      every occurrence of the run's own --output directory (which is embedded
      verbatim in every compiler error line) with a fixed placeholder, then
      hashes what remains. Two runs failing for the identical underlying
      reason in different --output directories must fingerprint identically.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$LogPath,
        [Parameter(Mandatory = $true)][string]$OutputDir
    )
    if (-not (Test-Path -LiteralPath $LogPath)) {
        return "MISSING_LOG:$LogPath"
    }
    $text = Get-Content -LiteralPath $LogPath -Raw
    $outputDirFull = (Resolve-Path -LiteralPath $OutputDir).Path
    # Cover both path separator styles the log may contain.
    $text = $text.Replace($outputDirFull, "<OUTPUT_DIR>")
    $text = $text.Replace($outputDirFull.Replace('\', '/'), "<OUTPUT_DIR>")
    $normalizedLines = ($text -split "`r?`n") | Where-Object {
        ($_ -notmatch '^Timestamp:') -and ($_ -notmatch '^Log file:') -and ($_ -notmatch '^Log saved to:')
    }
    $normalized = [string]::Join("`n", $normalizedLines)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($normalized)
    $hashBytes = $sha256.ComputeHash($bytes)
    $digest = [System.BitConverter]::ToString($hashBytes).Replace('-', '').ToLowerInvariant()
    return @{ Digest = $digest; Normalized = $normalized }
}

# ---------------------------------------------------------------------------
# 1. Generate N times
# ---------------------------------------------------------------------------
Write-Host "=== Java generation determinism gate ($Runs runs) ===" -ForegroundColor Cyan
Write-Host "Example : $exampleSource"
Write-Host ""

$outcomes = New-Object System.Collections.Generic.List[object]

for ($i = 1; $i -le $Runs; $i++) {
    $runDir = Join-Path $OutputRoot "run$i"
    Write-Host "Generating run$i..." -ForegroundColor Cyan
    $gen = Invoke-JavaGeneration -OutputDir $runDir
    if ($gen.ExitCode -eq 0) {
        $hash = Get-SuccessManifestHash -Root $runDir
        $outcomes.Add([PSCustomObject]@{
                Run          = $i
                Success      = $true
                Fingerprint  = $hash
                Detail       = "SUCCESS manifest sha256=$hash"
            })
    }
    else {
        if ($null -eq $gen.LogPath) {
            $outcomes.Add([PSCustomObject]@{
                    Run         = $i
                    Success     = $false
                    Fingerprint = "NO_LOG_FOUND"
                    Detail      = "FAILED (exit $($gen.ExitCode)) -- no new generate-results log was found"
                })
        }
        else {
            $fp = Get-FailureFingerprint -LogPath $gen.LogPath -OutputDir $runDir
            $outcomes.Add([PSCustomObject]@{
                    Run         = $i
                    Success     = $false
                    Fingerprint = $fp.Digest
                    Detail      = "FAILED (exit $($gen.ExitCode)) fingerprint=$($fp.Digest) log=$($gen.LogPath)"
                })
        }
    }
    Write-Host "  $($outcomes[$i - 1].Detail)"
}

# ---------------------------------------------------------------------------
# 2. All N outcomes must agree: same classification, same fingerprint.
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan

$reference = $outcomes[0]
$failures = New-Object System.Collections.Generic.List[string]

for ($i = 1; $i -lt $outcomes.Count; $i++) {
    $o = $outcomes[$i]
    if ($o.Success -ne $reference.Success) {
        $failures.Add("run$($o.Run) classification (" + $(if ($o.Success) { "SUCCESS" } else { "FAILED" }) + ") differs from run1 (" + $(if ($reference.Success) { "SUCCESS" } else { "FAILED" }) + ")")
    }
    elseif ($o.Fingerprint -ne $reference.Fingerprint) {
        $failures.Add("run$($o.Run) fingerprint ($($o.Fingerprint)) differs from run1 ($($reference.Fingerprint))")
    }
}

foreach ($o in $outcomes) {
    Write-Host "  run$($o.Run): $($o.Detail)"
}
Write-Host ""

if ($failures.Count -gt 0) {
    Write-Host "GATE FAILED (non-deterministic generation detected):" -ForegroundColor Red
    foreach ($f in $failures) { Write-Host "  - $f" -ForegroundColor Red }
    exit 1
}

$kind = if ($reference.Success) { "byte-identical SUCCESS" } else { "identical FAILURE" }
Write-Host "GATE PASSED: all $Runs runs produced $kind (fingerprint $($reference.Fingerprint))." -ForegroundColor Green
exit 0
