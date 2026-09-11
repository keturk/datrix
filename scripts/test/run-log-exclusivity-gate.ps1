#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Prove two concurrent runs can never be handed the same run-log file.

.DESCRIPTION
 A run log named from a second-granularity timestamp plus a few labels is one
 name for every run that agrees on those labels. That was a real, observed
 defect: two `generate.ps1` runs started together for two different config
 profiles computed the identical `generate-results-<timestamp>-<language>.log`,
 the second run's header write truncated the first run's log, and both then
 appended into one file -- so each run pointed its caller at a log describing
 the other run's generation.

 Adding another label (the profile) does not fix that; it moves it. Two runs of
 ONE profile still collide, exactly as adding the language segment left the
 profile case open. Uniqueness has to come from claiming the name, which is what
 DatrixRunLog's New-DatrixRunLogFile does (FileMode.CreateNew: an atomic
 create-or-fail).

 This gate checks, on every run:
   1. NON-VACUITY -- the distinct-count comparator is fed names composed the way
      the defect composed them (same timestamp, same labels) and MUST see one
      name, and is fed genuinely distinct names and must see all of them. A
      comparator that cannot detect the forced collision fails the gate outright,
      before any real result is trusted.
   2. SEQUENTIAL EXCLUSIVITY -- N claims on a PINNED base name (a guaranteed
      collision, not a hoped-for one) yield N distinct files that all exist. This
      proves a name is never reused.
   3. CONCURRENT EXCLUSIVITY -- the same N claims made simultaneously yield N
      distinct files. This proves the claim is atomic; it is what fails against a
      name-only scheme.
   4. LABEL CONTAINMENT -- a label carrying separators, "..", or a drive letter
      cannot steer the log out of its results directory.
   5. WIRING -- generate.ps1's own syntax tree must actually call the claiming
      function and must not rebuild a `generate-results-<...>` name inline.
      Without this the gate would prove a library nobody calls.

 Repo-level validation SCRIPT, not a pytest suite (per the datrix showcase
 boundary -- datrix hosts no test suite of any kind).

 Exit codes:
   0 = every run gets a log file of its own, and the check is non-vacuous
   1 = a check failed (shared log file, escaping label, unwired caller, or vacuous gate)
   2 = usage error (the module or generate.ps1 not found)

.PARAMETER Racers
 How many runs to force onto one name in checks 2 and 3 (default: 8).

.EXAMPLE
 .\run-log-exclusivity-gate.ps1
#>

[CmdletBinding()]
param(
    [Parameter()]
    [ValidateRange(2, 64)]
    [int]$Racers = 8
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# scripts\test -> scripts -> datrix (the showcase repo root)
$datrixRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)
$commonDir = Join-Path $datrixRoot "scripts\common"
$modulePath = Join-Path $commonDir "DatrixRunLog.psm1"
$generateScript = Join-Path $datrixRoot "scripts\dev\generate.ps1"

$GREEN = "$([char]27)[92m"
$RED = "$([char]27)[91m"
$CYAN = "$([char]27)[96m"
$RESET = "$([char]27)[0m"

function Write-Ok {
    param([string]$Message)
    Write-Host "  [OK] $Message" -ForegroundColor Green
}

function Write-Violation {
    param([string]$Message)
    Write-Host "  [FAIL] $Message" -ForegroundColor Red
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "${CYAN}$Message${RESET}"
}

# Write-Host, not Write-Error: $ErrorActionPreference = "Stop" turns Write-Error into a
# terminating error, which would exit 1 (a gate failure) instead of the documented 2.
if (-not (Test-Path -LiteralPath $modulePath)) {
    Write-Host "Error: DatrixRunLog.psm1 not found at: $modulePath" -ForegroundColor Red
    exit 2
}
if (-not (Test-Path -LiteralPath $generateScript)) {
    Write-Host "Error: generate.ps1 not found at: $generateScript" -ForegroundColor Red
    exit 2
}

Import-Module $modulePath -Force

# A fixed moment, so every composed base name in this gate is identical by
# construction. The collision these checks survive is guaranteed, not scheduled.
$PinnedTimestamp = [datetime]::new(2026, 1, 2, 3, 4, 5)

function Test-NonVacuity {
    Write-Step "Step 1/5: non-vacuity (the comparator must see a forced collision)"
    $ok = $true

    $colliding = 1..$Racers | ForEach-Object {
        Get-DatrixRunLogBaseName -Prefix "generate-results" -Segment @("python", "pilot") -Timestamp $PinnedTimestamp
    }
    $distinctColliding = ($colliding | Sort-Object -Unique).Count
    if ($distinctColliding -ne 1) {
        Write-Violation ("$Racers names composed from one timestamp and one label set produced " +
            "$distinctColliding distinct names, expected 1. The gate cannot force the collision it " +
            "exists to survive, so its later steps prove nothing.")
        $ok = $false
    } else {
        Write-Ok "$Racers same-input compositions -> 1 name (the collision is real and visible)"
    }

    $varied = 1..$Racers | ForEach-Object {
        Get-DatrixRunLogBaseName -Prefix "generate-results" -Segment @("python", "profile$_") -Timestamp $PinnedTimestamp
    }
    $distinctVaried = ($varied | Sort-Object -Unique).Count
    if ($distinctVaried -ne $Racers) {
        Write-Violation ("$Racers names composed from $Racers different label sets produced " +
            "$distinctVaried distinct names, expected $Racers. The comparator reports sameness that " +
            "is not there, so a passing exclusivity step would be meaningless.")
        $ok = $false
    } else {
        Write-Ok "$Racers distinct-input compositions -> $Racers names (no false collisions)"
    }

    return $ok
}

function Test-SequentialExclusivity {
    param([string]$Root)

    Write-Step "Step 2/5: sequential exclusivity (pinned base name, claimed $Racers times)"
    $dir = Join-Path $Root "sequential"
    $base = Get-DatrixRunLogBaseName -Prefix "generate-results" -Segment @("python", "pilot") -Timestamp $PinnedTimestamp

    $claimed = 1..$Racers | ForEach-Object { New-DatrixRunLogFile -Directory $dir -BaseName $base }
    $distinct = ($claimed | Sort-Object -Unique).Count
    if ($distinct -ne $Racers) {
        Write-Violation ("$Racers sequential runs wanting the same log name got $distinct distinct " +
            "files, expected $Racers. A reused log file means the later run truncates the earlier " +
            "run's log and both append into one file.")
        return $false
    }

    $missing = @($claimed | Where-Object { -not (Test-Path -LiteralPath $_) })
    if ($missing.Count -gt 0) {
        Write-Violation ("$($missing.Count) claimed path(s) do not exist: $($missing -join ', '). " +
            "A claim that does not create the file reserves nothing.")
        return $false
    }

    Write-Ok "$Racers sequential claims -> $Racers distinct files, all created"
    return $true
}

function Test-ConcurrentExclusivity {
    param([string]$Root)

    Write-Step "Step 3/5: concurrent exclusivity (the same claims made simultaneously)"
    $dir = Join-Path $Root "concurrent"
    $base = Get-DatrixRunLogBaseName -Prefix "generate-results" -Segment @("python", "pilot") -Timestamp $PinnedTimestamp
    $null = New-Item -ItemType Directory -Path $dir -Force

    $module = $modulePath
    $claimed = 1..$Racers | ForEach-Object -ThrottleLimit $Racers -Parallel {
        Import-Module $using:module -Force
        New-DatrixRunLogFile -Directory $using:dir -BaseName $using:base
    }

    $distinct = ($claimed | Sort-Object -Unique).Count
    if ($distinct -ne $Racers) {
        Write-Violation ("$Racers CONCURRENT runs wanting the same log name got $distinct distinct " +
            "files, expected $Racers -- the claim is not atomic, so two runs both believe they own " +
            "one log file.")
        return $false
    }

    Write-Ok "$Racers concurrent claims -> $Racers distinct files"
    return $true
}

function Test-LabelContainment {
    param([string]$Root)

    Write-Step "Step 4/5: label containment (a hostile label cannot leave the results directory)"
    $dir = Join-Path $Root "containment"
    $null = New-Item -ItemType Directory -Path $dir -Force
    $resolvedDir = (Resolve-Path -LiteralPath $dir).Path
    $ok = $true

    $hostileLabels = @(
        "../../escaped",
        "..\..\escaped",
        "C:\Windows\System32\log",
        "nested/deep/name",
        "with spaces and *wildcards?"
    )

    foreach ($label in $hostileLabels) {
        $base = Get-DatrixRunLogBaseName -Prefix "generate-results" -Segment @("python", $label) -Timestamp $PinnedTimestamp
        if ($base -match '[\\/:*?"<>|]') {
            Write-Violation "Composed base name '$base' still carries a path or wildcard character from label '$label'."
            $ok = $false
            continue
        }
        $claimed = New-DatrixRunLogFile -Directory $dir -BaseName $base
        $parent = (Resolve-Path -LiteralPath (Split-Path -Parent $claimed)).Path
        if ($parent -ne $resolvedDir) {
            Write-Violation "Label '$label' produced a log at '$claimed', outside '$resolvedDir'."
            $ok = $false
        }
    }

    if ($ok) {
        Write-Ok "$($hostileLabels.Count) hostile labels -> $($hostileLabels.Count) logs, all inside the results directory"
    }
    return $ok
}

function Test-CallerWiring {
    Write-Step "Step 5/5: wiring (generate.ps1 must actually claim, not compose)"
    $ok = $true

    $tokens = $null
    $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($generateScript, [ref]$tokens, [ref]$errors)
    if ($errors -and $errors.Count -gt 0) {
        Write-Violation "generate.ps1 does not parse: $($errors[0].Message)"
        return $false
    }

    $claimCalls = $ast.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "New-DatrixRunLogFile"
    }, $true)
    if ($claimCalls.Count -lt 1) {
        Write-Violation ("generate.ps1 never calls New-DatrixRunLogFile, so its log path is not " +
            "claimed and two concurrent runs can still share one file. Fix: build the name with " +
            "Get-DatrixRunLogBaseName and claim it with New-DatrixRunLogFile.")
        $ok = $false
    } else {
        Write-Ok "generate.ps1 claims its log file ($($claimCalls.Count) call site)"
    }

    # An interpolated `generate-results-...` literal is the composed-name shape the
    # defect had; the claiming function takes the prefix as a plain constant.
    $composedNames = $ast.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.ExpandableStringExpressionAst] -and
        $node.Value -match 'generate-results-'
    }, $true)
    if ($composedNames.Count -gt 0) {
        Write-Violation ("generate.ps1 still composes a log name inline: " +
            "$($composedNames[0].Extent.Text). A name built from a timestamp is one name for every " +
            "run that shares that second.")
        $ok = $false
    } else {
        Write-Ok "generate.ps1 composes no generate-results-* name inline"
    }

    return $ok
}

$scratchRoot = Join-Path ([System.IO.Path]::GetTempPath()) "datrix-run-log-gate-$([guid]::NewGuid())"
$results = @()
try {
    $null = New-Item -ItemType Directory -Path $scratchRoot -Force
    $results += Test-NonVacuity
    $results += Test-SequentialExclusivity -Root $scratchRoot
    $results += Test-ConcurrentExclusivity -Root $scratchRoot
    $results += Test-LabelContainment -Root $scratchRoot
    $results += Test-CallerWiring
} finally {
    if (Test-Path -LiteralPath $scratchRoot) {
        Remove-Item -LiteralPath $scratchRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
if ($results -contains $false) {
    Write-Host "${RED}GATE FAILED${RESET}: see the violations above."
    exit 1
}
Write-Host "${GREEN}GATE PASSED${RESET}: every run gets a log file of its own, and the check is non-vacuous."
exit 0
