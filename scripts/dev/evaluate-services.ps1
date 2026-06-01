<#
.SYNOPSIS
    Runs /evaluate-generated-service prompts in parallel using Claude Code CLI.

.DESCRIPTION
    Finds all service-*.prompt.md files in the evaluation folder and runs them
    through Claude Code in non-interactive mode (-p), processing up to 5 services
    concurrently.

    By default uses the current directory as the evaluation folder. Pass -EvalDir
    to specify a different path.

.PARAMETER SourceDir
    Path to the project source directory (containing .dtrx files).
    Required — this is the directory Claude Code needs read access to.

.PARAMETER GeneratedDir
    Path to the generated output directory.
    Required — this is the directory Claude Code needs read access to.

.PARAMETER Parallel
    Number of parallel Claude Code processes to run. Default: 5.

.PARAMETER Model
    Model to use. Default: opus.

.PARAMETER EvalDir
    Path to the evaluation directory containing prompt files.
    If not specified, uses the current directory.

.EXAMPLE
    cd d:\datrix\eval\2026-05-16-100000-curvaero
    d:\datrix\datrix\scripts\dev\run-service-evaluations.ps1 -SourceDir "d:\datrix\datrix-projects\curvaero\curvaero-backend" -GeneratedDir "d:\datrix\.generated\python\docker\curvaero"

.EXAMPLE
    d:\datrix\datrix\scripts\dev\run-service-evaluations.ps1 -SourceDir "d:\datrix\datrix-projects\curvaero\curvaero-backend" -GeneratedDir "d:\datrix\.generated\python\docker\curvaero" -EvalDir "d:\datrix\eval\2026-05-16-100000-curvaero" -Parallel 3 -Model sonnet
#>

param(
    [Parameter(Mandatory)][string]$SourceDir,
    [Parameter(Mandatory)][string]$GeneratedDir,
    [string]$EvalDir,
    [int]$Parallel = 5,
    [string]$Model = "opus"
)

$ErrorActionPreference = "Stop"

# Validate source and generated directories
if (-not (Test-Path $SourceDir)) {
    Write-Error "Source directory not found: $SourceDir"
    exit 1
}
if (-not (Test-Path $GeneratedDir)) {
    Write-Error "Generated directory not found: $GeneratedDir"
    exit 1
}

$SourceDir = (Resolve-Path $SourceDir).Path
$GeneratedDir = (Resolve-Path $GeneratedDir).Path

# Use current directory as the evaluation folder if not specified
if (-not $EvalDir) {
    $EvalDir = (Get-Location).Path
} else {
    if (-not (Test-Path $EvalDir)) {
        Write-Error "Evaluation directory not found: $EvalDir"
        exit 1
    }
    $EvalDir = (Resolve-Path $EvalDir).Path
}

# Find all prompt files (exclude already-evaluated ones in evaluated/ subfolder)
$promptFiles = Get-ChildItem -Path $EvalDir -Filter "service-*.prompt.md" -File |
    Sort-Object Name

if ($promptFiles.Count -eq 0) {
    Write-Host "No service prompt files found in current directory: $EvalDir" -ForegroundColor Yellow
    Write-Host "Looking in evaluated/ subfolder..." -ForegroundColor Yellow
    $evaluatedDir = Join-Path $EvalDir "evaluated"
    if (Test-Path $evaluatedDir) {
        $promptFiles = Get-ChildItem -Path $evaluatedDir -Filter "service-*.prompt.md" -File |
            Sort-Object Name
    }
    if ($promptFiles.Count -eq 0) {
        Write-Error "No service-*.prompt.md files found. Run /evaluate-generated first, then cd into the evaluation folder."
        exit 1
    }
}

Write-Host ""
Write-Host "Found $($promptFiles.Count) service prompt files to evaluate:" -ForegroundColor Green
$promptFiles | ForEach-Object { Write-Host "  - $($_.Name)" -ForegroundColor Gray }
Write-Host ""
Write-Host "Parallelism: $Parallel | Model: $Model" -ForegroundColor Cyan
Write-Host "Source:    $SourceDir" -ForegroundColor Cyan
Write-Host "Generated: $GeneratedDir" -ForegroundColor Cyan
Write-Host "Eval dir:  $EvalDir" -ForegroundColor Cyan
Write-Host ""

# Confirmation
$confirm = Read-Host "Proceed? (y/N)"
if ($confirm -ne 'y' -and $confirm -ne 'Y') {
    Write-Host "Aborted." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Starting evaluations..." -ForegroundColor Green
Write-Host "=" * 60

# Track results
$results = @()
$startTime = Get-Date
$completed = 0
$failed = 0

# Process in batches of $Parallel
$batches = [System.Collections.ArrayList]@()
for ($i = 0; $i -lt $promptFiles.Count; $i += $Parallel) {
    $batch = $promptFiles[$i..([Math]::Min($i + $Parallel - 1, $promptFiles.Count - 1))]
    [void]$batches.Add($batch)
}

Write-Host "Processing $($promptFiles.Count) services in $($batches.Count) batch(es) of up to $Parallel..." -ForegroundColor Cyan
Write-Host ""

$batchNum = 0
foreach ($batch in $batches) {
    $batchNum++
    Write-Host "--- Batch $batchNum/$($batches.Count) ($($batch.Count) services) ---" -ForegroundColor Magenta

    $jobs = @()
    foreach ($promptFile in $batch) {
        $serviceName = $promptFile.Name -replace '^service-' -replace '\.prompt\.md$'
        $promptPath = $promptFile.FullName

        Write-Host "  Starting: $serviceName" -ForegroundColor White

        # Build the prompt that invokes the skill
        $prompt = @"
/evaluate-generated-service

PROMPT_FILE: $promptPath
"@

        # Launch Claude Code in non-interactive mode as a background job
        # Working dir = EvalDir (where prompts live and reports are written)
        # --add-dir grants read access to source and generated directories
        $job = Start-Job -Name $serviceName -ScriptBlock {
            param($prompt, $model, $sourceDir, $generatedDir, $evalDir)
            Set-Location $evalDir
            $env:NO_COLOR = "1"
            $result = & claude -p $prompt --model $model `
                --allowedTools "Read" "Glob" "Grep" "Write" "Task" "WebSearch" "TodoWrite" `
                --add-dir $sourceDir --add-dir $generatedDir 2>&1
            @{
                Output   = ($result -join "`n")
                ExitCode = $LASTEXITCODE
            }
        } -ArgumentList $prompt, $Model, $SourceDir, $GeneratedDir, $EvalDir

        $jobs += @{
            Job         = $job
            ServiceName = $serviceName
            PromptFile  = $promptPath
            StartTime   = Get-Date
        }
    }

    # Wait for all jobs in this batch to complete
    Write-Host ""
    Write-Host "  Waiting for batch $batchNum to complete..." -ForegroundColor DarkGray

    $jobs | ForEach-Object {
        $jobInfo = $_
        $job = $jobInfo.Job
        $job | Wait-Job | Out-Null
        $elapsed = (Get-Date) - $jobInfo.StartTime
        $jobResult = Receive-Job -Job $job

        if ($job.State -eq 'Failed' -or $jobResult.ExitCode -ne 0) {
            $failed++
            Write-Host "  FAILED: $($jobInfo.ServiceName) ($([math]::Round($elapsed.TotalMinutes, 1)) min)" -ForegroundColor Red
            $status = "FAILED"
        } else {
            $completed++
            Write-Host "  DONE:   $($jobInfo.ServiceName) ($([math]::Round($elapsed.TotalMinutes, 1)) min)" -ForegroundColor Green
            $status = "OK"
        }

        $results += @{
            Service  = $jobInfo.ServiceName
            Status   = $status
            Duration = $elapsed
            Output   = $jobResult.Output
        }

        Remove-Job -Job $job
    }

    Write-Host ""
}

# Summary
$totalElapsed = (Get-Date) - $startTime
Write-Host "=" * 60
Write-Host "EVALUATION COMPLETE" -ForegroundColor Green
Write-Host "=" * 60
Write-Host ""
Write-Host "Total services: $($promptFiles.Count)" -ForegroundColor White
Write-Host "Completed:      $completed" -ForegroundColor Green
Write-Host "Failed:         $failed" -ForegroundColor $(if ($failed -gt 0) { "Red" } else { "Gray" })
Write-Host "Total time:     $([math]::Round($totalElapsed.TotalMinutes, 1)) minutes" -ForegroundColor Cyan
Write-Host ""

# Write summary log
$logPath = Join-Path $EvalDir "evaluation-run.log"
$logContent = @"
Evaluation Run Summary
======================
Date:       $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Directory:  $EvalDir
Model:      $Model
Parallel:   $Parallel
Total:      $($promptFiles.Count)
Completed:  $completed
Failed:     $failed
Duration:   $([math]::Round($totalElapsed.TotalMinutes, 1)) minutes

Results:
"@

foreach ($r in $results) {
    $logContent += "`n  [$($r.Status)] $($r.Service) - $([math]::Round($r.Duration.TotalMinutes, 1)) min"
}

if ($failed -gt 0) {
    $logContent += "`n`nFailed Services Output:`n"
    foreach ($r in $results | Where-Object { $_.Status -eq "FAILED" }) {
        $logContent += "`n--- $($r.Service) ---`n$($r.Output)`n"
    }
}

$logContent | Out-File -FilePath $logPath -Encoding utf8
Write-Host "Log written to: $logPath" -ForegroundColor DarkGray

if ($failed -gt 0) {
    Write-Host ""
    Write-Host "Failed services:" -ForegroundColor Red
    $results | Where-Object { $_.Status -eq "FAILED" } | ForEach-Object {
        Write-Host "  - $($_.Service)" -ForegroundColor Red
    }
    exit 1
}
