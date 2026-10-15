#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Generation-pipeline determinism gate: the SAME source tree, generated N times
  in a row for one registered language via the documented single-project
  generate.ps1 path, must never produce two different outcomes.

.DESCRIPTION
  Background: a corpus generation sweep once found that running the IDENTICAL
  command against an UNCHANGED tree three times in a row produced THREE
  DIFFERENT outcomes -- once failing inside the language's own "generate:<lang>"
  pipeline stage (a struct-test planner unable to resolve a struct from the
  Application it was planned against), twice failing later at the generated
  project's compile step with a set of compiler errors. Same input, same
  invocation, different output: no conclusion drawn from one generation is
  trustworthy until this class of regression is caught automatically.

  Each run is its OWN `generate.ps1` process (a fresh `python.exe`
  invocation), so this gate also exercises PYTHONHASHSEED-driven ordering
  bugs that a single long-lived process would never surface -- a `set`
  iterated without a deterministic sort produces different orderings across
  separate Python processes by default, but always the same ordering within
  one process. No before/after comparison of two code states can catch this
  class of bug, because it never runs the same code twice. This gate does:
  same code, N runs, N outcomes compared to each other.

  The gate:
    1. Generates the reference example N times (default 5) for -Language,
       into N explicit --output directories, via the documented generate.ps1
       --source/--output single-project mode.
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
  determinism, not correctness of the generated code; unrelated, already
  tracked codegen defects are out of this gate's scope.

  The last line is the gate verdict, "[GATE] generation-determinism
  PASSED|FAILED exit=<n> log=<path>"; the log holds the per-run outcomes and the
  findings (generate.ps1 keeps its own logs).

.PARAMETER Language
  Required unless -SelfTest. The registered `datrix.languages` name to generate
  for (passed to generate.ps1 as -Language). There is no default: the gate never
  assumes which languages are installed.

.PARAMETER OutputRoot
  Root under which run1/ .. runN/ are written. Default:
  <workspace>/.test-output/generation-determinism-gate/<Language> (per the repo
  temp-output policy).

.PARAMETER Runs
  Number of repeated generations to compare. Default 5. Must be >= 2.

.PARAMETER Dbg
  Forward -Dbg (debug logging) to generate.ps1.

.PARAMETER SelfTest
  Run only the self-test and generate nothing: the success manifest and the
  failure fingerprint over planted trees and logs (one changed byte differs,
  identical twins and a different --output path do not), and the outcome
  comparison (a changed classification or fingerprint fails, agreement passes).

.EXAMPLE
  .\generation-determinism-gate.ps1 -Language python
  Generate the reference example five times for python and compare the outcomes.

.EXAMPLE
  .\generation-determinism-gate.ps1 -SelfTest
  Prove the fingerprints and the comparison on planted inputs.
#>

[CmdletBinding(DefaultParameterSetName = "Gate")]
param(
    [Parameter(Mandatory = $true, ParameterSetName = "Gate")]
    [string]$Language,

    [Parameter(ParameterSetName = "Gate")]
    [string]$OutputRoot,

    [Parameter(ParameterSetName = "Gate")]
    [int]$Runs = 5,

    [Parameter(ParameterSetName = "Gate")]
    [Alias("Dbg")]
    [switch]$DebugLogging,

    [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")]
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPaths.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$GateName = "generation-determinism"
$ExitPass = 0
$ExitFail = 1
$MinimumRuns = 2

# `.datrix` holds the run's own audit log / snapshot / manifest generated_at
# timestamp -- expected to differ every invocation by design. Excluded from
# both the success manifest and (implicitly, via log-only scanning) the
# failure fingerprint.
$ExcludedDirNames = @('.datrix')

# Preamble lines of a generate-results log that carry the run's own time or path.
$RunSpecificLogLinePatterns = @('^Timestamp:', '^Log file:', '^Log saved to:')

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Get-Sha256Hex {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $sha256.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($Text))
        return [System.BitConverter]::ToString($hashBytes).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $sha256.Dispose()
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
        foreach ($child in (Get-ChildItem -LiteralPath $dir -Force)) {
            $isReparse = ($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
            if ($isReparse) { continue }
            if ($child.PSIsContainer) {
                if ($ExcludedDirNames -notcontains $child.Name) { $stack.Push($child.FullName) }
                continue
            }
            $rel = $child.FullName.Substring($rootLen).TrimStart('\', '/') -replace '\\', '/'
            $results.Add([PSCustomObject]@{
                    RelKey   = $rel.ToLowerInvariant()
                    FullPath = $child.FullName
                })
        }
    }
    return $results
}

function Get-SuccessManifestHash {
    param([Parameter(Mandatory = $true)][string]$Root)
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($f in (Get-GeneratedSourceFiles -Root $Root | Sort-Object RelKey)) {
        $lines.Add("$($f.RelKey):$((Get-FileHash -LiteralPath $f.FullPath -Algorithm SHA256).Hash)")
    }
    return Get-Sha256Hex -Text ([string]::Join("`n", $lines))
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
        $line = $_
        @($RunSpecificLogLinePatterns | Where-Object { $line -match $_ }).Count -eq 0
    }
    return Get-Sha256Hex -Text ([string]::Join("`n", $normalizedLines))
}

function Get-DeterminismFailures {
    <# Every outcome whose classification or fingerprint differs from the first. #>
    param([Parameter(Mandatory = $true)][object[]]$Outcomes)

    $reference = $Outcomes[0]
    $failures = New-Object System.Collections.Generic.List[string]
    foreach ($o in ($Outcomes | Select-Object -Skip 1)) {
        if ($o.Success -ne $reference.Success) {
            $failures.Add("run$($o.Run) classification ($(if ($o.Success) { 'SUCCESS' } else { 'FAILED' })) differs from run1 ($(if ($reference.Success) { 'SUCCESS' } else { 'FAILED' }))")
        }
        elseif ($o.Fingerprint -ne $reference.Fingerprint) {
            $failures.Add("run$($o.Run) fingerprint ($($o.Fingerprint)) differs from run1 ($($reference.Fingerprint))")
        }
    }
    return , $failures
}

function Invoke-LanguageGeneration {
    param(
        [Parameter(Mandatory = $true)][string]$GenerateScript,
        [Parameter(Mandatory = $true)][string]$ExampleSource,
        [Parameter(Mandatory = $true)][string]$ResultsDir,
        [Parameter(Mandatory = $true)][string]$OutputDir
    )
    if (Test-Path -LiteralPath $OutputDir) {
        Remove-Item -LiteralPath $OutputDir -Recurse -Force
    }
    $genArgs = @{
        Source   = $ExampleSource
        Output   = $OutputDir
        Language = $Language
    }
    if ($DebugLogging) { $genArgs.Dbg = $true }
    $logBefore = Get-ChildItem -LiteralPath $ResultsDir -Filter "generate-results-*.log" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    & $GenerateScript @genArgs | Out-Null
    $exitCode = $LASTEXITCODE
    $logAfter = Get-ChildItem -LiteralPath $ResultsDir -Filter "generate-results-*.log" -ErrorAction SilentlyContinue |
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

# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

function New-PlantedFile {
    param([string]$Path, [string]$Content)
    New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force | Out-Null
    [System.IO.File]::WriteAllText($Path, $Content)
}

function Write-SelfTestResult {
    param([string]$LogPath, [string]$Name, [bool]$Ok)
    Write-DatrixGateLog -LogPath $LogPath -Message "  [$(if ($Ok) { 'OK' } else { 'FAIL' })] $Name"
    return $Ok
}

function Invoke-SelfTest {
    param([string]$LogPath)
    $root = Join-Path ([System.IO.Path]::GetTempPath()) "$GateName-selftest-$([guid]::NewGuid().ToString('N'))"
    New-Item -ItemType Directory -Path $root -Force | Out-Null
    Write-DatrixGateLog -LogPath $LogPath -Message "$GateName self-test:"
    try {
        foreach ($tree in @("a", "b", "c")) {
            New-PlantedFile -Path (Join-Path $root "$tree\src\app.py") -Content "x = 1"
            New-PlantedFile -Path (Join-Path $root "$tree\.datrix\manifest.json") -Content "{`"generated_at`": `"$tree`"}"
        }
        New-PlantedFile -Path (Join-Path $root "c\src\app.py") -Content "x = 2"

        $runA = Join-Path $root "run-a"; $runB = Join-Path $root "run-b"
        New-Item -ItemType Directory -Path $runA, $runB -Force | Out-Null
        $logA = Join-Path $root "a.log"; $logB = Join-Path $root "b.log"; $logC = Join-Path $root "c.log"
        New-PlantedFile -Path $logA -Content "Timestamp: 1`nerror in $runA\src\app.ts: TS2304`n"
        New-PlantedFile -Path $logB -Content "Timestamp: 2`nerror in $runB\src\app.ts: TS2304`n"
        New-PlantedFile -Path $logC -Content "Timestamp: 3`nerror in $runB\src\app.ts: TS2551`n"

        $same = @(
            [PSCustomObject]@{ Run = 1; Success = $true; Fingerprint = "f" },
            [PSCustomObject]@{ Run = 2; Success = $true; Fingerprint = "f" }
        )
        $reclassified = @($same[0], [PSCustomObject]@{ Run = 2; Success = $false; Fingerprint = "f" })
        $refingerprinted = @($same[0], [PSCustomObject]@{ Run = 2; Success = $true; Fingerprint = "g" })

        $results = @(
            (Write-SelfTestResult -LogPath $LogPath -Name "manifest_identical_trees_agree_despite_datrix_metadata" -Ok ((Get-SuccessManifestHash -Root (Join-Path $root "a")) -eq (Get-SuccessManifestHash -Root (Join-Path $root "b")))),
            (Write-SelfTestResult -LogPath $LogPath -Name "manifest_one_changed_byte_differs" -Ok ((Get-SuccessManifestHash -Root (Join-Path $root "a")) -ne (Get-SuccessManifestHash -Root (Join-Path $root "c")))),
            (Write-SelfTestResult -LogPath $LogPath -Name "fingerprint_same_failure_in_another_output_dir_agrees" -Ok ((Get-FailureFingerprint -LogPath $logA -OutputDir $runA) -eq (Get-FailureFingerprint -LogPath $logB -OutputDir $runB))),
            (Write-SelfTestResult -LogPath $LogPath -Name "fingerprint_different_error_differs" -Ok ((Get-FailureFingerprint -LogPath $logB -OutputDir $runB) -ne (Get-FailureFingerprint -LogPath $logC -OutputDir $runB))),
            (Write-SelfTestResult -LogPath $LogPath -Name "comparison_agreeing_runs_pass" -Ok ((Get-DeterminismFailures -Outcomes $same).Count -eq 0)),
            (Write-SelfTestResult -LogPath $LogPath -Name "comparison_changed_classification_fails" -Ok ((Get-DeterminismFailures -Outcomes $reclassified).Count -eq 1)),
            (Write-SelfTestResult -LogPath $LogPath -Name "comparison_changed_fingerprint_fails" -Ok ((Get-DeterminismFailures -Outcomes $refingerprinted).Count -eq 1))
        )
        $failed = @($results | Where-Object { -not $_ }).Count
        if ($failed -gt 0) {
            Write-DatrixGateLog -LogPath $LogPath -Message "SELF-TEST FAILED: $failed of $($results.Count) check(s) failed." -Color Red
            return $ExitFail
        }
        Write-DatrixGateLog -LogPath $LogPath -Message "SELF-TEST PASSED: $($results.Count) check(s)." -Color Green
        return $ExitPass
    }
    finally {
        Remove-Item -LiteralPath $root -Recurse -Force
    }
}

# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------

function Invoke-Gate {
    param([string]$LogPath)

    if ($Runs -lt $MinimumRuns) {
        Write-DatrixGateLog -LogPath $LogPath -Message "Runs must be >= $MinimumRuns (need at least two outcomes to compare); got $Runs. Fix: pass -Runs $MinimumRuns or more." -Color Red
        return $ExitFail
    }
    $workspace = Get-DatrixWorkspaceRoot
    $root = if ($OutputRoot) { $OutputRoot } else { Join-Path $workspace ".test-output\generation-determinism-gate\$Language" }
    $generateScript = Join-Path $PSScriptRoot "..\..\dev\generate.ps1"
    $resultsDir = Join-Path $workspace ".generated\.results"
    # The example this class of non-determinism was originally found against.
    $exampleSource = Join-Path $workspace "datrix\examples\02-features\03-infrastructure-blocks\nosql\system.dtrx"
    if (-not (Test-Path -LiteralPath $exampleSource)) {
        Write-DatrixGateLog -LogPath $LogPath -Message "Reference example not found at: $exampleSource. Fix: restore it." -Color Red
        return $ExitFail
    }

    Write-DatrixGateLog -LogPath $LogPath -Message "=== Generation determinism gate: $Language ($Runs runs) ===" -Color Cyan
    Write-DatrixGateLog -LogPath $LogPath -Message "Example : $exampleSource"

    $outcomes = New-Object System.Collections.Generic.List[object]
    for ($i = 1; $i -le $Runs; $i++) {
        $runDir = Join-Path $root "run$i"
        Write-Host "Generating run$i..." -ForegroundColor Cyan
        $gen = Invoke-LanguageGeneration -GenerateScript $generateScript -ExampleSource $exampleSource -ResultsDir $resultsDir -OutputDir $runDir
        if ($gen.ExitCode -eq 0) {
            $hash = Get-SuccessManifestHash -Root $runDir
            $outcomes.Add([PSCustomObject]@{ Run = $i; Success = $true; Fingerprint = $hash; Detail = "SUCCESS manifest sha256=$hash" })
        }
        elseif ($null -eq $gen.LogPath) {
            $outcomes.Add([PSCustomObject]@{ Run = $i; Success = $false; Fingerprint = "NO_LOG_FOUND"; Detail = "FAILED (exit $($gen.ExitCode)) -- no new generate-results log was found" })
        }
        else {
            $fp = Get-FailureFingerprint -LogPath $gen.LogPath -OutputDir $runDir
            $outcomes.Add([PSCustomObject]@{ Run = $i; Success = $false; Fingerprint = $fp; Detail = "FAILED (exit $($gen.ExitCode)) fingerprint=$fp log=$($gen.LogPath)" })
        }
        Write-DatrixGateLog -LogPath $LogPath -Message "  run$($i): $($outcomes[$i - 1].Detail)"
    }

    $failures = Get-DeterminismFailures -Outcomes $outcomes.ToArray()
    if ($failures.Count -gt 0) {
        Write-DatrixGateLog -LogPath $LogPath -Message "GATE FAILED (non-deterministic generation detected):" -Color Red
        foreach ($f in $failures) { Write-DatrixGateLog -LogPath $LogPath -Message "  - $f" -Color Red }
        return $ExitFail
    }
    $kind = if ($outcomes[0].Success) { "byte-identical SUCCESS" } else { "identical FAILURE" }
    Write-DatrixGateLog -LogPath $LogPath -Message "GATE PASSED: all $Runs runs produced $kind (fingerprint $($outcomes[0].Fingerprint))." -Color Green
    return $ExitPass
}

$logPath = New-DatrixGateLogFile -Gate $GateName
$exitCode = $ExitFail
try {
    $exitCode = if ($SelfTest) { Invoke-SelfTest -LogPath $logPath } else { Invoke-Gate -LogPath $logPath }
}
finally {
    Write-DatrixGateVerdict -Gate $GateName -ExitCode $exitCode -LogPath $logPath
}
exit $exitCode
