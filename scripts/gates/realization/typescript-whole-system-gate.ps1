#!/usr/bin/env pwsh
<#
.SYNOPSIS
  REAL whole-system TypeScript generation gate: proves the whole-system generate
  path emits genuine TypeScript (not a hollow/failed run) and is byte-deterministic.

.DESCRIPTION
  Background: the whole-system generate path was
  hollow for TypeScript because the pipeline never attached the CodegenContext to
  the LANGUAGE generator -- Python received one only by a runtime_bootstrap
  side-effect, so TypeScriptGenerator's context stayed None and
  LanguageGenerator.generate raised "LanguageGenerator requires CodegenContext".
  With that fixed (datrix-cli pipeline/generation.py, _discover_language_and_generators)
  a real end-to-end TypeScript whole-system run is possible, and this gate proves it.

  The gate:
    1. Generates a LANGUAGE-NEUTRAL example project TWICE with -Language typescript,
       into two explicit --output directories (run1 / run2), via the documented
       generate.ps1 --source/--output single-project mode. The target language comes
       solely from that flag (generate.ps1 forwards it to generate.py as --language);
       no example pins a language, and none may -- a 'language' key in a system .dcfg
       is rejected at load time by datrix_common's system-config loader.
    2. REALNESS: asserts the run produced real TypeScript source (generated *.ts
       count > 0) AND that the SERVICE IMPLEMENTATION is TypeScript, not Python
       (no *.py under any generated `src/` tree -- the true hollow/leak guard).
    3. BYTE-STABILITY: recursively compares run1 vs run2 (sha256 per relative path).
       Any content or file-set difference fails the gate.

  WHY NOT a blanket "*.py == 0" over the whole tree: a TypeScript whole-system
  project legitimately contains a small, fixed set of LANGUAGE-AGNOSTIC Python
  artifacts, emitted by design for EVERY target language:
    - `tests/**` httpx HTTP-contract integration tests, regenerated for the
      TypeScript/NestJS target by datrix-codegen-python's
      `python_http_contract_overlay` companion generator (see that generator's
      module docstring: "runs last in the TypeScript pipeline and overwrites those
      httpx tests so JSON keys match NestJS DTOs"). These are black-box HTTP tests
      against the running service; they are not the service implementation.
    - `migration-tools/**` live-schema exporter rendered by datrix-codegen-sql
      (a DB tool that runs where the database is reachable, independent of the
      service's implementation language).
  A blanket *.py==0 would therefore FAIL on correct, intended output. This gate
  instead pins the allowed Python locations: any *.py OUTSIDE `tests/` or
  `migration-tools/` (in particular any *.py under `src/`) is treated as a
  language leak and fails the gate.

  Excluded from BOTH the realness scan and the byte diff are non-source,
  post-generation build/install artifacts whose contents embed absolute paths or
  install state and are not deterministic generated source:
    .datrix  .ruff_cache  .tsc_cache  node_modules

  The last line is the gate verdict, "[GATE] typescript-whole-system PASSED|FAILED
  exit=<n> log=<path>"; the log holds the gate's own lines (generate.ps1 keeps its own).

.PARAMETER OutputRoot
  Root under which run1/ and run2/ are written. Default:
  <workspace>/.test-output/ts-gate (per the repo temp-output policy).

.PARAMETER Dbg
  Forward -Dbg (debug logging) to generate.ps1.

.PARAMETER SelfTest
  Run only the self-test and generate nothing: the realness and byte-stability
  classifier over planted generation trees in a temp directory (a clean pair
  passes; a Python file under src/, a run with no .ts, a changed byte and a file
  only one run has each fail; differences inside an excluded directory do not),
  and Get-PathSegments over a doubled separator.

.EXAMPLE
  .\typescript-whole-system-gate.ps1
  Generate the example twice and check realness and byte-stability.

.EXAMPLE
  .\typescript-whole-system-gate.ps1 -SelfTest
  Prove the classifier on planted trees.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$OutputRoot = "",

    [Alias("Dbg")]
    [switch]$DebugLogging,

    [Parameter()]
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPaths.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$GateName = "typescript-whole-system"
$ExitPass = 0
$ExitFail = 1

# Directory names that are post-generation build/install artifacts, never
# deterministic generated source. Excluded from realness scan AND byte diff.
$ExcludedDirNames = @('.datrix', '.ruff_cache', '.tsc_cache', 'node_modules')

# Python locations every target language emits by design (see .DESCRIPTION).
$LanguageAgnosticPythonDirs = @('tests', 'migration-tools')

# Byte differences listed before the rest are summarized.
$ByteDiffListLimit = 40

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Get-GeneratedSourceFiles {
    <#
      Iterative directory walk returning generated-source files under $Root,
      pruning any directory whose name is in $ExcludedDirNames and never
      descending into reparse points (symlinks -- pnpm's node_modules store).
      Returns objects with RelPath (forward-slashed), RelKey (lowercased, the
      comparison key) and FullPath.
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
                    RelPath  = $rel
                    RelKey   = $rel.ToLowerInvariant()
                    FullPath = $child.FullName
                })
        }
    }
    return $results
}

function Get-PathSegments {
    param([string]$RelPath)
    return @(($RelPath -split '/') | Where-Object { $_ -ne '' })
}

function Get-LanguageLeaks {
    <#
      The generated *.py files that are a language leak: any under a `src/`
      segment, or outside the language-agnostic Python locations.
    #>
    param([Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$PyFiles)

    $leaked = New-Object System.Collections.Generic.List[string]
    foreach ($py in $PyFiles) {
        $segs = Get-PathSegments -RelPath $py.RelKey
        $underSrc = $segs -contains 'src'
        $allowed = @($segs | Where-Object { $LanguageAgnosticPythonDirs -contains $_ }).Count -gt 0
        if ($underSrc -or (-not $allowed)) { $leaked.Add($py.RelPath) }
    }
    return , $leaked
}

function Get-ByteDifferences {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$Run1Files,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$Run2Files
    )

    $map1 = @{}
    foreach ($f in $Run1Files) { $map1[$f.RelKey] = $f.FullPath }
    $map2 = @{}
    foreach ($f in $Run2Files) { $map2[$f.RelKey] = $f.FullPath }

    $diffs = New-Object System.Collections.Generic.List[string]
    foreach ($k in ($map1.Keys | Sort-Object)) {
        if (-not $map2.ContainsKey($k)) { $diffs.Add("only in run1: $k"); continue }
        $h1 = (Get-FileHash -LiteralPath $map1[$k] -Algorithm SHA256).Hash
        $h2 = (Get-FileHash -LiteralPath $map2[$k] -Algorithm SHA256).Hash
        if ($h1 -ne $h2) { $diffs.Add("content differs: $k") }
    }
    foreach ($k in ($map2.Keys | Sort-Object)) {
        if (-not $map1.ContainsKey($k)) { $diffs.Add("only in run2: $k") }
    }
    return , $diffs
}

function Get-GenerationVerdict {
    <#
      The failure classifier: realness over run1, byte-stability run1 vs run2.
      Returns Failures (a list of messages) and the summary counts.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Run1,
        [Parameter(Mandatory = $true)][string]$Run2
    )

    $failures = New-Object System.Collections.Generic.List[string]
    $run1Files = @(Get-GeneratedSourceFiles -Root $Run1)
    $tsFiles = @($run1Files | Where-Object { $_.RelKey.EndsWith('.ts') })
    $pyFiles = @($run1Files | Where-Object { $_.RelKey.EndsWith('.py') })

    if ($tsFiles.Count -le 0) {
        $failures.Add("REALNESS: expected generated *.ts files > 0, found $($tsFiles.Count) (hollow TypeScript output).")
    }
    $leaked = Get-LanguageLeaks -PyFiles $pyFiles
    if ($leaked.Count -gt 0) {
        $failures.Add("REALNESS: $($leaked.Count) Python file(s) leaked into the TypeScript service (expected only $($LanguageAgnosticPythonDirs -join '/ + ')/): $($leaked -join ', ')")
    }

    $byteDiffs = Get-ByteDifferences -Run1Files $run1Files -Run2Files @(Get-GeneratedSourceFiles -Root $Run2)
    foreach ($d in ($byteDiffs | Select-Object -First $ByteDiffListLimit)) { $failures.Add("BYTE-STABILITY: $d") }
    if ($byteDiffs.Count -gt $ByteDiffListLimit) {
        $failures.Add("BYTE-STABILITY: ... and $($byteDiffs.Count - $ByteDiffListLimit) more differences")
    }

    return [PSCustomObject]@{
        Failures      = $failures
        TsCount       = $tsFiles.Count
        PyCount       = $pyFiles.Count
        ComparedCount = $run1Files.Count
        ByteDiffCount = $byteDiffs.Count
    }
}

function Invoke-TsGeneration {
    param(
        [Parameter(Mandatory = $true)][string]$GenerateScript,
        [Parameter(Mandatory = $true)][string]$ExampleSource,
        [Parameter(Mandatory = $true)][string]$OutputDir
    )
    if (Test-Path -LiteralPath $OutputDir) {
        Remove-Item -LiteralPath $OutputDir -Recurse -Force
    }
    # Named-parameter splat: -Language IS the target selector (generate.ps1
    # forwards it as --language). The explicit -Output dir is what the gate
    # actually compares.
    $genArgs = @{
        Source   = $ExampleSource
        Output   = $OutputDir
        Language = "typescript"
    }
    if ($DebugLogging) { $genArgs.Dbg = $true }
    & $GenerateScript @genArgs | Out-Host
    return $LASTEXITCODE
}

# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

function New-PlantedFile {
    param([string]$Root, [string]$RelPath, [string]$Content)
    $path = Join-Path $Root $RelPath
    New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force | Out-Null
    [System.IO.File]::WriteAllText($path, $Content)
}

function New-PlantedPair {
    <# A clean run1/run2 pair under $Root: identical source, allowed Python, a differing excluded dir. #>
    param([string]$Root)
    foreach ($run in @("run1", "run2")) {
        $dir = Join-Path $Root $run
        New-PlantedFile -Root $dir -RelPath "service/src/app.ts" -Content "export const app = 1;"
        New-PlantedFile -Root $dir -RelPath "service/tests/test_contract.py" -Content "def test_contract(): ..."
        New-PlantedFile -Root $dir -RelPath "service/migration-tools/export.py" -Content "print('export')"
        New-PlantedFile -Root $dir -RelPath "service/node_modules/pkg/index.js" -Content "$run"
    }
    return [PSCustomObject]@{ Run1 = (Join-Path $Root "run1"); Run2 = (Join-Path $Root "run2") }
}

function Test-SelfTestCase {
    <# Plants a pair, lets $Plant break it, and checks the classifier's failures against $ExpectedPrefix ("" = no failure). #>
    param([string]$Root, [string]$Name, [scriptblock]$Plant, [string]$ExpectedPrefix, [string]$LogPath)
    $pair = New-PlantedPair -Root (Join-Path $Root $Name)
    & $Plant $pair
    $failures = (Get-GenerationVerdict -Run1 $pair.Run1 -Run2 $pair.Run2).Failures
    $ok = if ($ExpectedPrefix) {
        $failures.Count -eq 1 -and $failures[0].StartsWith($ExpectedPrefix)
    }
    else {
        $failures.Count -eq 0
    }
    $status = if ($ok) { "OK" } else { "FAIL" }
    Write-DatrixGateLog -LogPath $LogPath -Message "  [$status] $Name$(if (-not $ok) { " -- got: $($failures -join ' | ')" })"
    return $ok
}

function Invoke-SelfTest {
    param([string]$LogPath)
    $root = Join-Path ([System.IO.Path]::GetTempPath()) "$GateName-selftest-$([guid]::NewGuid().ToString('N'))"
    New-Item -ItemType Directory -Path $root -Force | Out-Null
    Write-DatrixGateLog -LogPath $LogPath -Message "$GateName self-test:"
    try {
        $cases = @(
            @{ Name = "clean_pair_passes"; Expected = ""; Plant = { param($p) } },
            @{ Name = "python_under_src_is_a_leak"; Expected = "REALNESS: 1 Python file(s) leaked"; Plant = {
                    param($p)
                    foreach ($run in @($p.Run1, $p.Run2)) { New-PlantedFile -Root $run -RelPath "service/src/handler.py" -Content "x = 1" }
                } },
            @{ Name = "no_typescript_is_hollow"; Expected = "REALNESS: expected generated *.ts"; Plant = {
                    param($p)
                    foreach ($run in @($p.Run1, $p.Run2)) { Remove-Item -LiteralPath (Join-Path $run "service/src/app.ts") }
                } },
            @{ Name = "changed_byte_is_unstable"; Expected = "BYTE-STABILITY: content differs"; Plant = {
                    param($p)
                    New-PlantedFile -Root $p.Run2 -RelPath "service/src/app.ts" -Content "export const app = 2;"
                } },
            @{ Name = "file_in_one_run_is_unstable"; Expected = "BYTE-STABILITY: only in run2"; Plant = {
                    param($p)
                    New-PlantedFile -Root $p.Run2 -RelPath "service/src/extra.ts" -Content "export {};"
                } }
        )
        $passed = 0
        foreach ($case in $cases) {
            if (Test-SelfTestCase -Root $root -Name $case.Name -Plant $case.Plant -ExpectedPrefix $case.Expected -LogPath $LogPath) { $passed += 1 }
        }
        $segments = Get-PathSegments -RelPath "service//src/app.ts"
        $segmentsOk = ($segments -join '|') -eq "service|src|app.ts"
        Write-DatrixGateLog -LogPath $LogPath -Message "  [$(if ($segmentsOk) { 'OK' } else { 'FAIL' })] path_segments_drop_empty_parts"
        if ($segmentsOk) { $passed += 1 }

        $total = $cases.Count + 1
        if ($passed -ne $total) {
            Write-DatrixGateLog -LogPath $LogPath -Message "SELF-TEST FAILED: $($total - $passed) of $total check(s) failed." -Color Red
            return $ExitFail
        }
        Write-DatrixGateLog -LogPath $LogPath -Message "SELF-TEST PASSED: $total check(s)." -Color Green
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

    $workspace = Get-DatrixWorkspaceRoot
    $root = if ($OutputRoot) { $OutputRoot } else { Join-Path $workspace ".test-output\ts-gate" }
    $generateScript = Join-Path $PSScriptRoot "..\..\dev\generate.ps1"
    # A language-NEUTRAL example. Datrix has no language-specific examples: every
    # example models domain content only, and the generation target is chosen by the
    # caller. 01-foundation is used because it is the one example known to generate
    # cleanly in every registered language (the same reason the reference-example
    # parity gate holds it as its corpus).
    $exampleSource = Join-Path $workspace "datrix\examples\01-foundation\system.dtrx"
    if (-not (Test-Path -LiteralPath $exampleSource)) {
        Write-DatrixGateLog -LogPath $LogPath -Message "Gate example not found at: $exampleSource. Expected the 01-foundation example. Fix: restore it." -Color Red
        return $ExitFail
    }

    $run1 = Join-Path $root "run1"
    $run2 = Join-Path $root "run2"
    Write-DatrixGateLog -LogPath $LogPath -Message "=== TypeScript whole-system gate ===" -Color Cyan
    Write-DatrixGateLog -LogPath $LogPath -Message "Example : $exampleSource"
    Write-DatrixGateLog -LogPath $LogPath -Message "run1    : $run1"
    Write-DatrixGateLog -LogPath $LogPath -Message "run2    : $run2"

    $generationFailures = New-Object System.Collections.Generic.List[string]
    foreach ($run in @($run1, $run2)) {
        Write-DatrixGateLog -LogPath $LogPath -Message "Generating $(Split-Path -Leaf $run)..." -Color Cyan
        $exitCode = Invoke-TsGeneration -GenerateScript $generateScript -ExampleSource $exampleSource -OutputDir $run
        if ($exitCode -ne 0) { $generationFailures.Add("$(Split-Path -Leaf $run) generation exited with code $exitCode") }
    }
    if ($generationFailures.Count -gt 0) {
        Write-DatrixGateLog -LogPath $LogPath -Message "GATE FAILED (generation did not complete):" -Color Red
        foreach ($f in $generationFailures) { Write-DatrixGateLog -LogPath $LogPath -Message "  - $f" -Color Red }
        return $ExitFail
    }

    $verdict = Get-GenerationVerdict -Run1 $run1 -Run2 $run2
    Write-DatrixGateLog -LogPath $LogPath -Message "=== Summary ===" -Color Cyan
    Write-DatrixGateLog -LogPath $LogPath -Message "Generated TypeScript source files (*.ts, excl. build artifacts): $($verdict.TsCount)"
    Write-DatrixGateLog -LogPath $LogPath -Message "Language-agnostic Python artifacts (tests/ + migration-tools/):  $($verdict.PyCount)"
    Write-DatrixGateLog -LogPath $LogPath -Message "Compared source files run1 vs run2:                              $($verdict.ComparedCount)"
    Write-DatrixGateLog -LogPath $LogPath -Message "Byte differences (excl. $($ExcludedDirNames -join '/')): $($verdict.ByteDiffCount)"

    if ($verdict.Failures.Count -gt 0) {
        Write-DatrixGateLog -LogPath $LogPath -Message "GATE FAILED:" -Color Red
        foreach ($f in $verdict.Failures) { Write-DatrixGateLog -LogPath $LogPath -Message "  - $f" -Color Red }
        return $ExitFail
    }
    Write-DatrixGateLog -LogPath $LogPath -Message "GATE PASSED: real TypeScript whole-system output, byte-stable across two runs." -Color Green
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
