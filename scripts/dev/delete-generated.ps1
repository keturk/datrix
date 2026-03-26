#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Rename .generated and delete the renamed tree (background by default).

.DESCRIPTION
    Renames <BaseDir>/.generated to .generated_old, or .generated_old_01 through .generated_old_99
    if those names already exist. Then removes the renamed folder. By default deletion runs in a
    Start-Job so the script returns right after the rename. Background jobs stop if the PowerShell
    session exits; use -Wait for synchronous deletion.

.PARAMETER BaseDir
    Monorepo root (default: three parents above this script directory).

.PARAMETER Wait
    Block until Remove-Item finishes on the renamed folder.

.EXAMPLE
    .\delete-generated.ps1

.EXAMPLE
    .\delete-generated.ps1 -Wait

.EXAMPLE
    .\delete-generated.ps1 -BaseDir D:\other\repo
#>

[CmdletBinding()]
param(
    [string]$BaseDir = (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))),
    [switch]$Wait
)

$ErrorActionPreference = "Stop"

$MAX_NUMERIC_SUFFIX = 99
$OLD_FOLDER_BASE_NAME = ".generated_old"
$GENERATED_FOLDER_NAME = ".generated"

$generatedPath = Join-Path $BaseDir $GENERATED_FOLDER_NAME

if (-not (Test-Path -LiteralPath $generatedPath)) {
    Write-Host "Nothing to do: not found: $generatedPath" -ForegroundColor Yellow
    exit 0
}

$candidatePaths = @((Join-Path $BaseDir $OLD_FOLDER_BASE_NAME))
for ($i = 1; $i -le $MAX_NUMERIC_SUFFIX; $i++) {
    $suffix = "{0:D2}" -f $i
    $candidatePaths += @(Join-Path $BaseDir ($OLD_FOLDER_BASE_NAME + "_" + $suffix))
}

$targetPath = $null
foreach ($candidate in $candidatePaths) {
    if (-not (Test-Path -LiteralPath $candidate)) {
        $targetPath = $candidate
        break
    }
}

if ($null -eq $targetPath) {
    $lastSuffix = "{0:D2}" -f $MAX_NUMERIC_SUFFIX
    $msg = (
        "No free name for old generated folder. Tried '$OLD_FOLDER_BASE_NAME' and " +
        "'${OLD_FOLDER_BASE_NAME}_01' through '${OLD_FOLDER_BASE_NAME}_$lastSuffix'."
    )
    Write-Error $msg
    exit 1
}

$newLeafName = Split-Path -Leaf $targetPath
Write-Host "Renaming '$generatedPath' -> '$newLeafName' ..." -ForegroundColor Cyan
Rename-Item -LiteralPath $generatedPath -NewName $newLeafName

if ($Wait) {
    Write-Host "Removing '$targetPath' (waiting) ..." -ForegroundColor Cyan
    Remove-Item -LiteralPath $targetPath -Recurse -Force
    Write-Host "Done." -ForegroundColor Green
    exit 0
}

$job = Start-Job -ScriptBlock {
    param($PathToRemove)
    $ErrorActionPreference = "Stop"
    Remove-Item -LiteralPath $PathToRemove -Recurse -Force
} -ArgumentList $targetPath

Write-Host "Started background job Id=$($job.Id) to remove '$targetPath'." -ForegroundColor Green
Write-Host "Check status: Get-Job -Id $($job.Id); output/errors: Receive-Job -Id $($job.Id) -Keep" -ForegroundColor Gray
Write-Host "For synchronous deletion next time, use -Wait." -ForegroundColor Gray

exit 0
