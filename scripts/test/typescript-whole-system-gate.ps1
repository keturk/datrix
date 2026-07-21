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
    1. Generates the TypeScript example project TWICE, into two explicit --output
       directories (run1 / run2), via the documented generate.ps1 --source/--output
       single-project mode. Language is resolved from the example's config/system.dcfg
       (language = "typescript"); the -L flag is only the wrapper's output-path label,
       so an explicit --output dir is used to bypass it entirely.
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

.PARAMETER OutputRoot
  Root under which run1/ and run2/ are written. Default:
  d:/datrix/.test-output/ts-gate (per the repo temp-output policy).

.PARAMETER Dbg
  Forward -Dbg (debug logging) to generate.ps1.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$OutputRoot = "d:/datrix/.test-output/ts-gate",

    [Alias("Dbg")]
    [switch]$DebugLogging
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Bootstrap (venv + paths), modeled on test/dual-target.ps1.
# ---------------------------------------------------------------------------
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$datrixScriptsRoot = Split-Path -Parent $scriptDir
$commonDir = Join-Path $datrixScriptsRoot "common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

$venvActivated = Ensure-DatrixVenv
if (-not $venvActivated) {
    throw "Could not activate the Datrix Python venv; cannot run the TypeScript whole-system gate."
}

$datrixRoot = Get-DatrixRoot
$generateScript = Join-Path (Join-Path $datrixScriptsRoot "dev") "generate.ps1"
if (-not (Test-Path -LiteralPath $generateScript)) {
    throw "generate.ps1 not found at: $generateScript"
}

# The TypeScript-configured example (config/system.dcfg -> language = "typescript").
$exampleSource = Join-Path $datrixRoot "datrix/examples/04-languages/typescript-service/system.dtrx"
if (-not (Test-Path -LiteralPath $exampleSource)) {
    throw "TypeScript example not found at: $exampleSource"
}

# Directory names that are post-generation build/install artifacts, never
# deterministic generated source. Excluded from realness scan AND byte diff.
$ExcludedDirNames = @('.datrix', '.ruff_cache', '.tsc_cache', 'node_modules')

$run1 = Join-Path $OutputRoot "run1"
$run2 = Join-Path $OutputRoot "run2"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Invoke-TsGeneration {
    param(
        [Parameter(Mandatory = $true)][string]$OutputDir
    )
    if (Test-Path -LiteralPath $OutputDir) {
        Remove-Item -LiteralPath $OutputDir -Recurse -Force
    }
    # Named-parameter splat: -Language is only the wrapper's output-path label;
    # the real language is resolved from config/system.dcfg (typescript). The
    # explicit -Output dir is what the gate actually compares.
    $genArgs = @{
        Source   = $exampleSource
        Output   = $OutputDir
        Language = "typescript"
    }
    if ($DebugLogging) { $genArgs.Dbg = $true }
    & $generateScript @genArgs
    return $LASTEXITCODE
}

function Get-GeneratedSourceFiles {
    <#
      Iterative directory walk returning generated-source files under $Root,
      pruning any directory whose name is in $ExcludedDirNames and never
      descending into reparse points (symlinks -- pnpm's node_modules store).
      Returns objects with RelPath (forward-slashed, lowercased for comparison
      keys) and FullPath.
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
                        RelPath  = $rel
                        RelKey   = $rel.ToLowerInvariant()
                        FullPath = $child.FullName
                    })
            }
        }
    }
    return $results
}

function Get-PathSegments {
    param([string]$RelPath)
    return ($RelPath -split '/') | Where-Object { $_ -ne '' }
}

# ---------------------------------------------------------------------------
# 1. Generate twice
# ---------------------------------------------------------------------------
Write-Host "=== TypeScript whole-system gate ===" -ForegroundColor Cyan
Write-Host "Example : $exampleSource"
Write-Host "run1    : $run1"
Write-Host "run2    : $run2"
Write-Host ""

$failures = New-Object System.Collections.Generic.List[string]

Write-Host "Generating run1..." -ForegroundColor Cyan
$exit1 = Invoke-TsGeneration -OutputDir $run1
if ($exit1 -ne 0) {
    $failures.Add("run1 generation exited with code $exit1")
}

Write-Host "Generating run2..." -ForegroundColor Cyan
$exit2 = Invoke-TsGeneration -OutputDir $run2
if ($exit2 -ne 0) {
    $failures.Add("run2 generation exited with code $exit2")
}

if ($failures.Count -gt 0) {
    Write-Host ""
    Write-Host "GATE FAILED (generation did not complete):" -ForegroundColor Red
    foreach ($f in $failures) { Write-Host "  - $f" -ForegroundColor Red }
    exit 1
}

# ---------------------------------------------------------------------------
# 2. Realness assertions (against run1)
# ---------------------------------------------------------------------------
$run1Files = Get-GeneratedSourceFiles -Root $run1

$tsFiles = @($run1Files | Where-Object { $_.RelPath.ToLowerInvariant().EndsWith('.ts') })
$pyFiles = @($run1Files | Where-Object { $_.RelPath.ToLowerInvariant().EndsWith('.py') })

$tsCount = $tsFiles.Count
$pyCount = $pyFiles.Count

# Positive realness: the TypeScript language generator emitted real .ts source.
if ($tsCount -le 0) {
    $failures.Add("REALNESS: expected generated *.ts files > 0, found $tsCount (hollow TypeScript output).")
}

# Negative leak guard: the SERVICE IMPLEMENTATION must be TypeScript, not Python.
# Any *.py under a `src/` segment, or outside the allowed language-agnostic
# locations (tests/, migration-tools/), is a language leak.
$leakedPy = New-Object System.Collections.Generic.List[string]
foreach ($py in $pyFiles) {
    $segs = Get-PathSegments -RelPath $py.RelKey
    $underSrc = $segs -contains 'src'
    $allowed = ($segs -contains 'tests') -or ($segs -contains 'migration-tools')
    if ($underSrc -or (-not $allowed)) {
        $leakedPy.Add($py.RelPath)
    }
}
if ($leakedPy.Count -gt 0) {
    $failures.Add("REALNESS: $($leakedPy.Count) Python file(s) leaked into the TypeScript service (expected only tests/ + migration-tools/): $($leakedPy -join ', ')")
}

# ---------------------------------------------------------------------------
# 3. Byte-stability (run1 vs run2)
# ---------------------------------------------------------------------------
$run2Files = Get-GeneratedSourceFiles -Root $run2

$map1 = @{}
foreach ($f in $run1Files) { $map1[$f.RelKey] = $f.FullPath }
$map2 = @{}
foreach ($f in $run2Files) { $map2[$f.RelKey] = $f.FullPath }

$byteDiffs = New-Object System.Collections.Generic.List[string]

$onlyIn1 = @($map1.Keys | Where-Object { -not $map2.ContainsKey($_) })
$onlyIn2 = @($map2.Keys | Where-Object { -not $map1.ContainsKey($_) })
foreach ($k in $onlyIn1) { $byteDiffs.Add("only in run1: $k") }
foreach ($k in $onlyIn2) { $byteDiffs.Add("only in run2: $k") }

foreach ($k in $map1.Keys) {
    if (-not $map2.ContainsKey($k)) { continue }
    $h1 = (Get-FileHash -LiteralPath $map1[$k] -Algorithm SHA256).Hash
    $h2 = (Get-FileHash -LiteralPath $map2[$k] -Algorithm SHA256).Hash
    if ($h1 -ne $h2) { $byteDiffs.Add("content differs: $k") }
}

if ($byteDiffs.Count -gt 0) {
    $shown = $byteDiffs | Select-Object -First 40
    foreach ($d in $shown) { $failures.Add("BYTE-STABILITY: $d") }
    if ($byteDiffs.Count -gt 40) {
        $failures.Add("BYTE-STABILITY: ... and $($byteDiffs.Count - 40) more differences")
    }
}

# ---------------------------------------------------------------------------
# 4. Summary + exit
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "Generated TypeScript source files (*.ts, excl. build artifacts): $tsCount"
Write-Host "Language-agnostic Python artifacts (tests/ + migration-tools/):  $pyCount"
Write-Host "Compared source files run1 vs run2:                              $($map1.Count)"
Write-Host "Byte differences (excl. .datrix/.ruff_cache/.tsc_cache/node_modules): $($byteDiffs.Count)"
Write-Host ""

if ($failures.Count -gt 0) {
    Write-Host "GATE FAILED:" -ForegroundColor Red
    foreach ($f in $failures) { Write-Host "  - $f" -ForegroundColor Red }
    exit 1
}

Write-Host "GATE PASSED: real TypeScript whole-system output, byte-stable across two runs." -ForegroundColor Green
exit 0
