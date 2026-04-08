<#
.SYNOPSIS
    Run all visualization and documentation scripts for a project.

.DESCRIPTION
    Orchestrates the full visualization pipeline for one or more .dtrx projects:
      1. Mermaid diagrams (all types)
      2. OpenAPI / AsyncAPI specs
      3. Documentation status report

    All output is written next to the .dtrx source files (language-agnostic).
    Each step runs independently - a failure in one step is reported but does not
    block subsequent steps.

.PARAMETER Source
    Path to .dtrx file or directory (single project mode).

.PARAMETER All
    Process all projects from test-projects.json.

.PARAMETER Tutorial
    Tutorial examples only.

.PARAMETER Domains
    Domain examples only.

.PARAMETER TestSet
    Named test set from test-projects.json (default: generate-all).

.PARAMETER Profile
    Config profile to resolve (default: test).

.PARAMETER Dbg
    Enable debug logging.

.EXAMPLE
    .\all-reports.ps1 examples\02-domains\ecommerce\system.dtrx
    Run all reports for the ecommerce example.

.EXAMPLE
    .\all-reports.ps1 -Tutorial
    Run all reports for tutorial examples.

.EXAMPLE
    .\all-reports.ps1 -All -Dbg
    Run all reports for every project with debug logging.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Source,

    [switch]$All,
    [switch]$Tutorial,
    [switch]$Domains,
    [string]$TestSet = "generate-all",
    [string]$Profile = "test",
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Validate that at least one mode is specified
if (-not $Source -and -not $All -and -not $Tutorial -and -not $Domains) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\all-reports.ps1 <source.dtrx>               Single project" -ForegroundColor White
    Write-Host "  .\all-reports.ps1 -All                         All projects" -ForegroundColor White
    Write-Host "  .\all-reports.ps1 -Tutorial                    Tutorial examples" -ForegroundColor White
    Write-Host "  .\all-reports.ps1 -Domains                     Domain examples" -ForegroundColor White
    Write-Host ""
    Write-Host "Use Get-Help .\all-reports.ps1 -Full for detailed help." -ForegroundColor Yellow
    exit 1
}

# Build common arguments that get forwarded to every sub-script (hashtable splatting)
$commonArgs = @{}
if ($Source)   { $commonArgs.Source = $Source }
if ($All)      { $commonArgs.All = $true }
if ($Tutorial) { $commonArgs.Tutorial = $true }
if ($Domains)  { $commonArgs.Domains = $true }
if ($TestSet -ne "generate-all") { $commonArgs.TestSet = $TestSet }
if ($Profile -ne "test") { $commonArgs.Profile = $Profile }
if ($Dbg) { $commonArgs.Dbg = $true }

$steps = @(
    @{
        Name   = "Mermaid Diagrams"
        Script = Join-Path $scriptDir "visualize.ps1"
    },
    @{
        Name   = "OpenAPI / AsyncAPI Specs"
        Script = Join-Path $scriptDir "openapi-gen.ps1"
    },
    @{
        Name   = "Documentation Status"
        Script = Join-Path $scriptDir "status-docs.ps1"
    }
)

$totalSteps = $steps.Count
$passed = 0
$failed = 0

Write-Host ""
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  Datrix Visualization - All Reports" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

for ($i = 0; $i -lt $totalSteps; $i++) {
    $step = $steps[$i]
    $stepNum = $i + 1
    $stepScript = $step.Script

    Write-Host "---------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "  Step $stepNum/$totalSteps : $($step.Name)" -ForegroundColor Cyan
    Write-Host "---------------------------------------------------" -ForegroundColor DarkGray

    if (-not (Test-Path $stepScript)) {
        Write-Host "  SKIPPED - script not found: $stepScript" -ForegroundColor Yellow
        $failed++
        continue
    }

    try {
        & $stepScript @commonArgs
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  -> OK" -ForegroundColor Green
            $passed++
        } else {
            Write-Host "  -> FAILED (exit code $LASTEXITCODE)" -ForegroundColor Red
            $failed++
        }
    } catch {
        Write-Host "  -> ERROR: $_" -ForegroundColor Red
        $failed++
    }
    Write-Host ""
}

# Summary
$summaryColor = "Green"
if ($failed -gt 0) { $summaryColor = "Yellow" }

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  Summary: $passed passed, $failed failed (out of $totalSteps steps)" -ForegroundColor $summaryColor
Write-Host "===================================================" -ForegroundColor Cyan

if ($failed -gt 0) { exit 1 } else { exit 0 }
