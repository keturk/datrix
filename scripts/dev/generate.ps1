#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Generate Datrix Projects

.DESCRIPTION
 Generates Datrix projects from source files. Supports single-project or batch modes:
 1. Single project: source file (output folder optional; derived from test-projects.json when omitted)
 2. -All: all projects (test set generate-all)
 3. -Tutorial: examples/01-tutorial (tutorial-all)
 4. -NonTutorial: all examples except 01-tutorial (generate-all minus tutorial-all)
 5. -Domains: examples/02-domains

 Batch modes use the same unified generation pipeline for consistent behavior.
 Activates the datrix virtual environment and runs the generation command.
 Ensures virtual environment is deactivated even if the script is interrupted (Ctrl-C).

.PARAMETER Source
 Path to source .dtrx file (positional, required for single project mode).

.PARAMETER Output
 Output directory path (positional, optional for single project mode). When omitted, derived from test-projects.json (defaultLanguage, defaultPlatform) and the source path.

.PARAMETER All
 Generate all projects from the specified test set (switch parameter).

.PARAMETER Tutorial
 Generate only tutorial examples (examples/01-tutorial). Uses test set tutorial-all.

.PARAMETER NonTutorial
 Generate all examples except tutorial (02-domains). Uses test set non-tutorial.

.PARAMETER Domains
 Generate only domain examples (examples/02-domains). Uses test set domains.

.PARAMETER Language
 Target language for output path derivation (default: python, options: python, typescript).
 The actual language used for generation is read from config/system-config.yaml.
 Can be abbreviated as -L.

.PARAMETER Platform
 Target platform for output path derivation (default: docker).
 The actual platform used for generation is read from config/system-config.yaml.
 Can be abbreviated as -P.

.PARAMETER OutputBase
 Output base directory (default: .generated). Only used with -All parameter.

.PARAMETER TestSet
 Test set to use (default: generate-all). Only used with -All parameter.

.PARAMETER Debug
 Enable debug logging (DEBUG level instead of INFO).

.EXAMPLE
 .\generate.ps1 examples/01-tutorial/01-basic-entity/system.dtrx
 Generate a single project; output path derived from test-projects.json (e.g. .generated/python/docker/01-tutorial/01-basic-entity).

.EXAMPLE
 .\generate.ps1 examples/01-tutorial/01-basic-entity/system.dtrx .generated/python/docker/my-project
 Generate a single project with explicit output path (python, docker).

.EXAMPLE
 .\generate.ps1 examples/01-tutorial/system.dtrx .generated/typescript/kubernetes/my-project -L typescript -P kubernetes
 Generate a single project with custom language and platform.

.EXAMPLE
 .\generate.ps1 -All
 Generate all projects with default settings.

.EXAMPLE
 .\generate.ps1 -All -Language typescript -Platform kubernetes
 Generate all projects for TypeScript and Kubernetes platform.

.EXAMPLE
 .\generate.ps1 -Tutorial
 Generate only tutorial examples (01-tutorial folder).

.EXAMPLE
 .\generate.ps1 -NonTutorial
 Generate all examples except tutorial (02-domains).

.EXAMPLE
 .\generate.ps1 -Domains
 Generate only domain examples (02-domains folder).

#>

[CmdletBinding()]
param(
 [Parameter(Position=0)]
 [string]$Source,

 [Parameter(Position=1)]
 [string]$Output,

 [Parameter()]
 [switch]$All,

 [Parameter()]
 [switch]$Tutorial,

 [Parameter()]
 [switch]$NonTutorial,

 [Parameter()]
 [switch]$Domains,

 [Parameter()]
 [Alias("L")]
 [string]$Language = "python",

 [Parameter()]
 [Alias("P")]
 [string]$Platform = "docker",

 [Parameter()]
 [string]$OutputBase = ".generated",

 [Parameter()]
 [string]$TestSet = "generate-all",

 [Parameter()]
 [switch]$Dbg
)

# Error handling - ensure cleanup on exit
$ErrorActionPreference = "Stop"

# Script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Import common modules
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

# Get datrix root and workspace root
$datrixRoot = Get-DatrixRoot
$datrixWorkspaceRoot = Get-DatrixWorkspaceRoot

# Function to handle cleanup on exit
function Invoke-Cleanup {
 Disable-DatrixVenv
}

# Register cleanup on script exit
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

# Function to get log file path
function Get-LogFilePath {
 param(
 [string]$DatrixWorkspaceRoot
 )
 $logDir = Join-Path $DatrixWorkspaceRoot ".generated" | Join-Path -ChildPath ".results"
 if (-not (Test-Path $logDir)) {
 $null = New-Item -ItemType Directory -Path $logDir -Force
 }
 
 $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
 $logFileName = "generate-results-$timestamp.log"
 return Join-Path $logDir $logFileName
}

# Function to clean up old log files
function Remove-OldLogFiles {
 param(
 [string]$DatrixWorkspaceRoot,
 [int]$KeepCount = 7
 )
 $logDir = Join-Path $DatrixWorkspaceRoot ".generated" | Join-Path -ChildPath ".results"
 if (-not (Test-Path $logDir)) {
 return
 }
 
 # Get all generate-results-*.log files, sorted by last write time (newest first)
 $logFiles = Get-ChildItem -Path $logDir -Filter "generate-results-*.log" | 
 Sort-Object LastWriteTime -Descending
 
 # Delete files beyond the keep count
 if ($logFiles.Count -gt $KeepCount) {
 $filesToDelete = $logFiles | Select-Object -Skip $KeepCount
 foreach ($file in $filesToDelete) {
 try {
 Remove-Item -Path $file.FullName -Force -ErrorAction Stop
 } catch {
 # Ignore errors during cleanup to avoid breaking the script
 }
 }
 }
}

# Function to show help message
function Show-HelpMessage {
 Write-Host ""
 Write-Host "Usage:" -ForegroundColor Yellow
 Write-Host " Generate single project:" -ForegroundColor Cyan
 Write-Host " .\generate.ps1 <Source> [Output] [-Language <lang>] [-Platform <platform>] [-Dbg]" -ForegroundColor White
 Write-Host "   (Output optional; derived from test-projects.json when omitted)" -ForegroundColor Gray
 Write-Host ""
 Write-Host " Generate all projects:" -ForegroundColor Cyan
 Write-Host " .\generate.ps1 -All [-Language <lang>] [-Platform <platform>] [-OutputBase <dir>] [-TestSet <set>] [-Dbg]" -ForegroundColor White
 Write-Host " Generate by example folder:" -ForegroundColor Cyan
 Write-Host " .\generate.ps1 -Tutorial | -NonTutorial | -Domains [-Language <lang>] [-Platform <platform>] [-Dbg]" -ForegroundColor White
 Write-Host ""
 Write-Host "Examples:" -ForegroundColor Yellow
 Write-Host " .\generate.ps1 examples/01-tutorial/system.dtrx .generated/python/docker/my-project" -ForegroundColor Gray
 Write-Host " .\generate.ps1 -All" -ForegroundColor Gray
 Write-Host " .\generate.ps1 -Tutorial" -ForegroundColor Gray
 Write-Host " .\generate.ps1 -NonTutorial" -ForegroundColor Gray
 Write-Host " .\generate.ps1 -Domains" -ForegroundColor Gray
 Write-Host " .\generate.ps1 -All -Language typescript -Platform kubernetes -Dbg" -ForegroundColor Gray
 Write-Host ""
 Write-Host "Use Get-Help .\generate.ps1 -Full for detailed help." -ForegroundColor Yellow
 Write-Host ""
}

# Function to write to both console and log file
function Write-TeeHost {
 param(
 [object]$Object,
 [string]$ForegroundColor = "White",
 [string]$BackgroundColor,
 [switch]$NoNewline,
 [string]$LogFilePath
 )
 $message = if ($Object) { $Object.ToString() } else { "" }
 
 # Build Write-Host parameters conditionally
 $writeHostParams = @{
 Object = $message
 ForegroundColor = $ForegroundColor
 NoNewline = $NoNewline
 }
 if ($BackgroundColor) {
 $writeHostParams['BackgroundColor'] = $BackgroundColor
 }
 Write-Host @writeHostParams
 
 if ($LogFilePath) {
 # Strip ANSI color codes for log file
 $plainMessage = $message -replace '\x1b\[[0-9;]*m', ''
 # Use UTF-8 encoding and FileShare.ReadWrite to allow concurrent access
 $utf8Encoding = New-Object System.Text.UTF8Encoding($false)
 $retryCount = 0
 $maxRetries = 3
 $written = $false

 while (-not $written -and $retryCount -lt $maxRetries) {
 try {
 $stream = [System.IO.File]::Open($LogFilePath, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
 $writer = New-Object System.IO.StreamWriter($stream, $utf8Encoding)
 try {
 if ($NoNewline) {
 $writer.Write($plainMessage)
 } else {
 $writer.WriteLine($plainMessage)
 }
 $written = $true
 } finally {
 $writer.Close()
 $stream.Close()
 }
 } catch {
 $retryCount++
 if ($retryCount -lt $maxRetries) {
 Start-Sleep -Milliseconds 100
 }
 }
 }
 }
}

# Long ERROR/Pipeline error lines are split on "; " for readability (threshold chars)
$MAX_LINE_LENGTH_BEFORE_SPLIT = 200

# Function to write pipeline output to both console and log file (UTF-8).
# Long lines containing "; " (e.g. ERROR / Pipeline error) are split so each error is on its own line.
function Write-TeeOutput {
 param(
 [Parameter(ValueFromPipeline=$true)]
 [object]$InputObject,
 [string]$LogFilePath
 )
 begin {
 $utf8Encoding = New-Object System.Text.UTF8Encoding($false)
 $logStream = $null
 if ($LogFilePath) {
 try {
 $logStream = [System.IO.File]::Open($LogFilePath, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
 $logWriter = New-Object System.IO.StreamWriter($logStream, $utf8Encoding)
 $logWriter.AutoFlush = $true
 } catch {
 Write-Warning "Could not open log file for writing: $_"
 }
 }
 }
 process {
 if ($null -ne $InputObject) {
 $line = $InputObject.ToString()
 # Use same plain text for both console and log (strip ANSI so log and console match)
 $plainLine = $line -replace '\x1b\[[0-9;]*m', ''
 # Split long ERROR / Pipeline error lines on "; " so each error is on its own line
 if ($plainLine.Length -gt $MAX_LINE_LENGTH_BEFORE_SPLIT -and $plainLine -match ';\s') {
 $segments = $plainLine -split ';\s*'
 $first = $true
 foreach ($seg in $segments) {
 $seg = $seg.Trim()
 if ($seg.Length -eq 0) { continue }
 $outLine = if ($first) { $seg } else { "  " + $seg }
 Write-Host $outLine
 if ($logWriter) {
 try { $logWriter.WriteLine($outLine) } catch { }
 }
 $first = $false
 }
 } else {
 Write-Host $plainLine
 if ($logWriter) {
 try { $logWriter.WriteLine($plainLine) } catch { }
 }
 }
 }
 }
 end {
 if ($logWriter) {
 $logWriter.Close()
 $logStream.Close()
 }
 }
}

# Maximum error-detail lines to include per failed project in the Errors section
$MAX_ERROR_LINES_PER_PROJECT = 5

# Function to append Errors section and Generation Summary to the log file
function Write-GenerationSummaryToLog {
 param(
 [Parameter(Mandatory = $true)]
 [string]$LogFilePath
 )
 $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
 try {
 $lines = [System.IO.File]::ReadAllLines($LogFilePath, $utf8NoBom)
 } catch {
 Write-Warning "Could not read log file for summary: $_"
 return
 }

 # Match result lines: [N/M] project-name: Success|Failed OR [N/M] Failed: project-name (exception path)
 $resultPatternNormal = '^\s*\[(\d+)/(\d+)\]\s+(.+?):\s+(Success|Failed)\s*\r?$'
 $resultPatternFailedAlt = '^\s*\[(\d+)/(\d+)\]\s+Failed:\s+(.+?)\s*\r?$'
 $results = @()
 for ($i = 0; $i -lt $lines.Count; $i++) {
  $line = $lines[$i]
  if ($line -match $resultPatternNormal) {
   $results += [PSCustomObject]@{ Index = [int]$Matches[1]; Total = [int]$Matches[2]; Name = $Matches[3].Trim(); Status = $Matches[4]; LineIndex = $i }
  } elseif ($line -match $resultPatternFailedAlt) {
   $results += [PSCustomObject]@{ Index = [int]$Matches[1]; Total = [int]$Matches[2]; Name = $Matches[3].Trim(); Status = 'Failed'; LineIndex = $i }
  }
 }

 $totalProjects = 0
 $successCount = 0
 $failCount = 0
 $failedProjects = @()
 $projectErrors = @{}

 if ($results.Count -gt 0) {
 $totalProjects = $results[0].Total
 $successCount = ($results | Where-Object { $_.Status -eq 'Success' }).Count
 $failCount = ($results | Where-Object { $_.Status -eq 'Failed' }).Count
 # Force array so one failed project does not become scalar (Name would then -join as characters)
 $failedProjects = @(($results | Where-Object { $_.Status -eq 'Failed' }) | ForEach-Object { $_.Name })

 foreach ($r in $results) {
 if ($r.Status -ne 'Failed') { continue }
 $blockStart = 0
 $prev = $results | Where-Object { $_.LineIndex -lt $r.LineIndex } | Sort-Object LineIndex -Descending | Select-Object -First 1
 if ($prev) { $blockStart = $prev.LineIndex + 1 }
 $blockEnd = $r.LineIndex - 1
 $errorLines = @()
 for ($j = $blockStart; $j -le $blockEnd -and $j -lt $lines.Count; $j++) {
 $ln = $lines[$j]
 if ($ln -match 'ERROR\s|Pipeline error:|Pipeline failed') {
 $errorLines += $ln.Trim()
 if ($errorLines.Count -ge $MAX_ERROR_LINES_PER_PROJECT) { break }
 }
 }
 if ($errorLines.Count -gt 0) {
 $projectErrors[$r.Name] = $errorLines
 }
 }
 }

 $sep = "=" * 80
 $report = "`n$sep`n"
 if ($failCount -gt 0 -and $projectErrors.Count -gt 0) {
 $report += "Errors`n"
 $report += "$sep`n"
 foreach ($name in $failedProjects) {
 $errs = $projectErrors[$name]
 if ($errs) {
 $report += "  $name`:`n"
 foreach ($e in $errs) {
 $report += "    $e`n"
 }
 }
 }
 }
 $report += "Generation Summary`n"
 $report += "$sep`n"
 if ($results.Count -eq 0) {
 $report += "  No project results found.`n"
 } else {
 $report += "  Total projects: $totalProjects`n"
 $report += "  Successful:     $successCount`n"
 $report += "  Failed:         $failCount`n"
 if ($failCount -gt 0) {
 $report += "  Failed projects: $($failedProjects -join ', ')`n"
 }
 }
 $report += "$sep`n"

 try {
 [System.IO.File]::AppendAllText($LogFilePath, $report, $utf8NoBom)
 Write-Host $report
 } catch {
 Write-Warning "Could not append generation summary to log: $_"
 }
}

# Main execution with proper error handling
$logFilePath = $null
try {
 # Clean up old log files before creating new one (keep only last 7)
 Remove-OldLogFiles -DatrixWorkspaceRoot $datrixWorkspaceRoot -KeepCount 7
 
 # Set up logging
 $logFilePath = Get-LogFilePath -DatrixWorkspaceRoot $datrixWorkspaceRoot
 
 # Write header to log file (UTF-8)
 $header = @"
Generate Results Log
Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
$("=" * 80)

"@
 $utf8Encoding = New-Object System.Text.UTF8Encoding($false)
 [System.IO.File]::WriteAllText($logFilePath, $header, $utf8Encoding)
 
 Write-TeeHost "Log file: $logFilePath" -ForegroundColor Cyan -LogFilePath $logFilePath
 Write-TeeHost "" -LogFilePath $logFilePath
 
 # Determine which mode to use
 $libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
 $pythonScript = Join-Path $libraryDir "dev\generate.py"
 
 # Check if Python script exists
 if (-not (Test-Path $pythonScript)) {
 Write-Error "Error: generate.py not found at: $pythonScript"
 exit 1
 }

 # Activate virtual environment
 $venvActivated = Ensure-DatrixVenv
 if (-not $venvActivated) {
 Write-Error "Failed to activate virtual environment"
 exit 1
 }

 # Ensure all packages are installed and up-to-date
 # Use SkipIfInstalled to avoid mid-run reinstalls that could break concurrent operations
 # Only triggers full reinstall if packages are not importable
 $packagesInstalled = Ensure-DatrixPackagesInstalled -SkipIfInstalled
 if (-not $packagesInstalled) {
 Write-Error "Failed to install/update packages"
 exit 1
 }

 # Verify datrix command works (console script entry point)
 # This catches cases where module imports work but entry point is broken
 if (-not (Test-DatrixCommand)) {
 # Only attempt reinstall if explicitly needed - use locking to prevent concurrent installs
 Write-TeeHost "datrix command verification failed, attempting reinstall of datrix-cli..." -ForegroundColor Yellow -LogFilePath $logFilePath
 $reinstalled = Install-DatrixPackage -PackageName "datrix-cli" -NoDev
 if (-not $reinstalled) {
 Write-Error "Failed to reinstall datrix-cli"
 exit 1
 }
 # Verify again after reinstall
 if (-not (Test-DatrixCommand)) {
 Write-Error "datrix command still not working after reinstall"
 exit 1
 }
 Write-TeeHost "datrix command verified successfully" -ForegroundColor Green -LogFilePath $logFilePath
 }

 # Get Python executable from venv
 $venvPath = Get-DatrixVenvPath
 $pythonExe = Join-Path $venvPath "Scripts\python.exe"

 # Build arguments for Python script
 $pythonArgs = @($pythonScript)
 
 $batchMode = $All -or $Tutorial -or $NonTutorial -or $Domains -or ($TestSet -ne "generate-all")
 if ($batchMode) {
 # Batch mode: folder switches take precedence over -All for test set
 $effectiveTestSet = if ($Tutorial) { "tutorial-all" }
 elseif ($NonTutorial) { "non-tutorial" }
 elseif ($Domains) { "domains" }
 else { $TestSet }
 if ($Language -ne "python") {
 $pythonArgs += "--language"
 $pythonArgs += $Language
 }
 if ($Platform -ne "docker") {
 $pythonArgs += "--platform"
 $pythonArgs += $Platform
 }
 if ($OutputBase -ne ".generated") {
 $pythonArgs += "--output-base"
 $pythonArgs += $OutputBase
 }
 if ($effectiveTestSet -ne "generate-all") {
 $pythonArgs += "--test-set"
 $pythonArgs += $effectiveTestSet
 }
 if ($Dbg) {
 $pythonArgs += "--debug"
 }

 # Run the Python script
 $batchLabel = if ($Tutorial) { "tutorial" }
 elseif ($NonTutorial) { "non-tutorial" }
 elseif ($Domains) { "domains" }
 else { "all" }
 Write-TeeHost "Running generate $batchLabel..." -ForegroundColor Cyan -LogFilePath $logFilePath
 Write-TeeHost "" -LogFilePath $logFilePath
 } elseif ($Source) {
 # Single project mode: Generate single project (output path optional; generate.py derives from test-projects.json when omitted)
 # Resolve source path to absolute
 try {
 $sourcePath = (Resolve-Path -Path $Source -ErrorAction Stop).Path
 } catch {
 $sourcePath = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Source))
 }

 # Validate source file or directory exists
 if (-not (Test-Path $sourcePath)) {
 Write-Error "Error: Source file or directory not found: $sourcePath"
 exit 1
 }

 # Build arguments for single project mode
 $pythonArgs += "--source"
 $pythonArgs += $sourcePath
 if (-not [string]::IsNullOrWhiteSpace($Output)) {
 # Ensure output directory exists or can be created when explicitly provided
 $null = New-Item -ItemType Directory -Path $Output -Force -ErrorAction Stop
 $pythonArgs += "--output"
 $pythonArgs += $Output
 }
 
 if ($Language -ne "python") {
 $pythonArgs += "--language"
 $pythonArgs += $Language
 }
 if ($Platform -ne "docker") {
 $pythonArgs += "--platform"
 $pythonArgs += $Platform
 }
 if ($Dbg) {
 $pythonArgs += "--debug"
 }

 # Run the generation command
 # Note: The Python script will print the generation details, so we don't duplicate them here
 } else {
 # Neither mode specified - show help
 Write-Host "Error: Either -All, -Tutorial, -NonTutorial, -Domains, -TestSet <set>, or both Source and Output parameters must be provided." -ForegroundColor Red
 Show-HelpMessage
 exit 1
 }

 # Disable Python script's own logging (PowerShell handles it)
 $env:DATRIX_DISABLE_LOG = "1"
 try {
 # Capture output to both console and log file (ASCII) - stream in real-time
 & $pythonExe @pythonArgs 2>&1 | Write-TeeOutput -LogFilePath $logFilePath
 $exitCode = $LASTEXITCODE
 } finally {
 Remove-Item env:DATRIX_DISABLE_LOG -ErrorAction SilentlyContinue
 }

 # Append Errors section and Generation Summary to the log file
 if ($logFilePath) {
 Write-GenerationSummaryToLog -LogFilePath $logFilePath
 }

 # Exit with the same code as the Python script
 exit $exitCode

} catch {
 $errorMsg = @"

Error occurred: $($_.Exception.Message)
"@
 if ($_.Exception.InnerException) {
 $errorMsg += @"

Inner exception: $($_.Exception.InnerException.Message)

"@
 }
 Write-TeeHost $errorMsg -ForegroundColor Red -LogFilePath $logFilePath

 # Attempt to write generation summary even on error so the log is complete
 if ($logFilePath) {
 try { Write-GenerationSummaryToLog -LogFilePath $logFilePath } catch { }
 }

 Invoke-Cleanup
 exit 1
} finally {
 # Ensure virtual environment is deactivated even on Ctrl-C
 Invoke-Cleanup
 
 # Clean up old log files (keep only last 7)
 if ($logFilePath) {
 Write-Host "`nLog saved to: $logFilePath" -ForegroundColor Cyan
 Remove-OldLogFiles -DatrixWorkspaceRoot $datrixWorkspaceRoot -KeepCount 7
 }
}
