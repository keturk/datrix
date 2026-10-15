<#
.SYNOPSIS
 The one way a datrix script runs Python: Invoke-DatrixPythonScript.

.DESCRIPTION
 A wrapper is its param() block, the mapping of its switches to Python flags, and

   exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\$name.py") -Arguments $pythonArgs)

 where lib\$name.py is the wrapper's own Python file beside it.

 Invoke-DatrixPythonScript activates the shared venv (Ensure-DatrixVenv, which also puts
 common\lib on PYTHONPATH), optionally checks the editable installs, runs the venv
 interpreter by absolute path, deactivates the venv in a finally block, and returns the
 child's exit code. It never calls exit itself.

 Gate mode (-Gate <name>) tees the child's output to a claimed log under
 <workspace>\.test-output\gates\<name>\<name>-<yyyyMMdd-HHmmss>[-N].log and prints exactly
 one last line:

   [GATE] <name> PASSED exit=0 log=<absolute log path>
   [GATE] <name> FAILED exit=<n> log=<absolute log path>

 That line is the seam the red-run digest hook reads (digest-red-test-run.py). A gate that
 runs no Python claims its log with New-DatrixGateLogFile, writes its lines with
 Write-DatrixGateLog, and prints the same last line with Write-DatrixGateVerdict.
#>

. (Join-Path $PSScriptRoot "venv.ps1")
# No -Force: a forced nested import unloads the caller's own import of the same module.
Import-Module (Join-Path $PSScriptRoot "DatrixPaths.psm1")
Import-Module (Join-Path $PSScriptRoot "DatrixRunLog.psm1")

$script:GateLogFolder = "gates"
$script:GateVerdictPrefix = "[GATE]"
$script:ExitUsage = 2
$script:ExitVenvUnavailable = 1

function New-DatrixGateLogFile {
 <#
 .SYNOPSIS
 Claims, and returns the absolute path of, a fresh log file for one gate run.

 .PARAMETER Gate
 The gate name; the log lives under <workspace>\.test-output\gates\<Gate>\.
 #>
 [CmdletBinding()]
 [OutputType([string])]
 param(
  [Parameter(Mandatory = $true)]
  [string]$Gate
 )

 $segment = ConvertTo-DatrixRunLogSegment -Value $Gate
 if ([string]::IsNullOrEmpty($segment)) {
  throw "Gate name '$Gate' has no letters or digits. Expected a name like 'shared-library'. Fix: pass -Gate <name>."
 }
 $directory = Join-Path (Join-Path (Join-Path (Get-DatrixWorkspaceRoot) ".test-output") $script:GateLogFolder) $segment
 $baseName = Get-DatrixRunLogBaseName -Prefix $segment
 return (New-DatrixRunLogFile -Directory $directory -BaseName $baseName)
}

function Write-DatrixGateVerdict {
 <#
 .SYNOPSIS
 Prints a gate's one verdict line: "[GATE] <name> PASSED|FAILED exit=<n> log=<path>".

 .PARAMETER Gate
 The gate name.

 .PARAMETER ExitCode
 The gate's exit code; 0 is PASSED, anything else FAILED.

 .PARAMETER LogPath
 The absolute path of the gate's log.
 #>
 [CmdletBinding()]
 param(
  [Parameter(Mandatory = $true)]
  [string]$Gate,

  [Parameter(Mandatory = $true)]
  [int]$ExitCode,

  [Parameter(Mandatory = $true)]
  [string]$LogPath
 )

 $verdict = if ($ExitCode -eq 0) { "PASSED" } else { "FAILED" }
 $color = if ($ExitCode -eq 0) { "Green" } else { "Red" }
 $absolute = [System.IO.Path]::GetFullPath($LogPath)
 Write-Host "$($script:GateVerdictPrefix) $Gate $verdict exit=$ExitCode log=$absolute" -ForegroundColor $color
}

function Write-DatrixGateLog {
 <#
 .SYNOPSIS
 Shows one line of a gate that runs no Python and appends it to the gate's claimed log.

 .PARAMETER LogPath
 The log New-DatrixGateLogFile claimed.

 .PARAMETER Message
 The line.

 .PARAMETER Color
 The console colour (the log carries the text only).
 #>
 [CmdletBinding()]
 param(
  [Parameter(Mandatory = $true)]
  [string]$LogPath,

  [Parameter(Mandatory = $true)]
  [AllowEmptyString()]
  [string]$Message,

  [Parameter()]
  [System.ConsoleColor]$Color = [System.ConsoleColor]::Gray
 )

 Write-Host $Message -ForegroundColor $Color
 [System.IO.File]::AppendAllText($LogPath, $Message + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding $false))
}

function Invoke-DatrixPythonChild {
 # Runs the interpreter and returns the child's exit code. Every output line (stdout and
 # stderr, as a string) goes to exactly one place: shown and appended to the log, fed to the
 # caller's steppable pipeline, added to the caller's list, or -- with none of those -- the
 # console.
 param(
  [string]$PythonExe,
  [string[]]$ChildArguments,
  [string]$LogPath,
  [System.Management.Automation.SteppablePipeline]$OutputPipeline,
  [System.Collections.Generic.List[string]]$OutputLines
 )

 if (-not $LogPath -and -not $OutputPipeline -and $null -eq $OutputLines) {
  & $PythonExe @ChildArguments | Out-Host
  return $LASTEXITCODE
 }

 $writer = if ($LogPath) { New-Object System.IO.StreamWriter($LogPath, $true, (New-Object System.Text.UTF8Encoding $false)) } else { $null }
 $previousPreference = $ErrorActionPreference
 $ErrorActionPreference = "Continue"
 try {
  if ($OutputPipeline) { $OutputPipeline.Begin($true) }
  & $PythonExe @ChildArguments 2>&1 | ForEach-Object {
   $line = if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.Exception.Message } else { [string]$_ }
   if ($OutputPipeline) { $null = $OutputPipeline.Process($line) }
   elseif ($null -ne $OutputLines) { $OutputLines.Add($line) }
   else {
    $writer.WriteLine($line)
    Write-Host $line
   }
  }
  return $LASTEXITCODE
 }
 finally {
  $ErrorActionPreference = $previousPreference
  if ($OutputPipeline) { $null = $OutputPipeline.End(); $OutputPipeline.Dispose() }
  if ($writer) { $writer.Dispose() }
 }
}

function Invoke-DatrixPythonScript {
 <#
 .SYNOPSIS
 Runs a Python file or module in the shared venv and returns its exit code.

 .PARAMETER Script
 Path of the .py file to run. Exactly one of -Script and -Module.

 .PARAMETER Module
 Dotted module name to run with -m (e.g. datrix_scripts.affected_set).

 .PARAMETER Arguments
 Arguments passed to the Python program.

 .PARAMETER RequirePackages
 Check the editable installs first (Ensure-DatrixPackagesInstalled -SkipIfInstalled).

 .PARAMETER Gate
 Gate mode: tee the output to a claimed log and print one verdict line (see the module help).

 .PARAMETER TeePath
 Show the output and also append every line to this file (stdout and stderr), for a caller
 that parses what the child printed. Not with -Gate, which tees to the gate's own log.

 .PARAMETER OutputPipeline
 A steppable pipeline the caller built -- e.g. { Write-TeeOutput -LogFilePath $log }.GetSteppablePipeline(),
 so its command and arguments resolve in the caller's own scope -- that receives the child's
 output lines (stdout and stderr, as strings) as they arrive, in place of the console: for a
 caller that filters or reformats what the child prints. The runner begins, feeds and ends it.

 .PARAMETER OutputLines
 A list that receives the child's output lines (stdout and stderr, as strings) in place of
 the console: for a caller that reads what the child printed.

 At most one of -Gate, -TeePath, -OutputPipeline and -OutputLines.

 .PARAMETER ShowCommand
 Print the interpreter and arguments before running (a wrapper's -Dbg).

 .EXAMPLE
 exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\$name_gate.py") -Arguments $pythonArgs -Gate $name)
 #>
 [CmdletBinding(DefaultParameterSetName = "Script")]
 [OutputType([int])]
 param(
  [Parameter(Mandatory = $true, ParameterSetName = "Script")]
  [string]$Script,

  [Parameter(Mandatory = $true, ParameterSetName = "Module")]
  [string]$Module,

  [Parameter()]
  [AllowEmptyCollection()]
  [string[]]$Arguments = @(),

  [Parameter()]
  [switch]$RequirePackages,

  [Parameter()]
  [string]$Gate = "",

  [Parameter()]
  [string]$TeePath = "",

  [Parameter()]
  [System.Management.Automation.SteppablePipeline]$OutputPipeline,

  [Parameter()]
  [System.Collections.Generic.List[string]]$OutputLines,

  [Parameter()]
  [switch]$ShowCommand
 )

 if ($PSCmdlet.ParameterSetName -eq "Script" -and -not (Test-Path -LiteralPath $Script -PathType Leaf)) {
  Write-Host "Error: Python script not found: $Script. Expected the file beside its wrapper in lib\. Fix: restore it or correct the wrapper." -ForegroundColor Red
  return $script:ExitUsage
 }
 $destinations = @([bool]$Gate, [bool]$TeePath, ($null -ne $OutputPipeline), ($null -ne $OutputLines)) | Where-Object { $_ }
 if (@($destinations).Count -gt 1) {
  Write-Host "Error: more than one of -Gate, -TeePath, -OutputPipeline and -OutputLines was given. Expected at most one: each decides where the child's output goes. Fix: keep the one this call needs." -ForegroundColor Red
  return $script:ExitUsage
 }

 $logPath = $TeePath
 if ($Gate) {
  $logPath = New-DatrixGateLogFile -Gate $Gate
 }

 $exitCode = $script:ExitVenvUnavailable
 try {
  $activated = Ensure-DatrixVenv
  if (-not $activated) {
   Write-Host "Error: could not activate the shared venv at $(Get-DatrixVenvPath). Fix: run common\venv.ps1 setup, then re-run." -ForegroundColor Red
   return $exitCode
  }
  if ($RequirePackages) {
   $installed = Ensure-DatrixPackagesInstalled -SkipIfInstalled
   if (-not $installed) {
    Write-Host "Error: the datrix packages are not installed in the shared venv. Fix: run common\venv.ps1 setup, then re-run." -ForegroundColor Red
    return $exitCode
   }
  }
  $pythonExe = Join-Path (Get-DatrixVenvPath) "Scripts\python.exe"
  $target = if ($PSCmdlet.ParameterSetName -eq "Module") { @("-m", $Module) } else { @($Script) }
  $childArguments = @($target) + @($Arguments)
  if ($ShowCommand) {
   Write-Host "Python executable: $pythonExe" -ForegroundColor Cyan
   Write-Host "Arguments: $($childArguments -join ' ')" -ForegroundColor Cyan
  }
  $exitCode = Invoke-DatrixPythonChild -PythonExe $pythonExe -ChildArguments $childArguments -LogPath $logPath -OutputPipeline $OutputPipeline -OutputLines $OutputLines
  return $exitCode
 }
 finally {
  Disable-DatrixVenv | Out-Null
  if ($Gate) {
   Write-DatrixGateVerdict -Gate $Gate -ExitCode $exitCode -LogPath $logPath
  }
 }
}

Export-ModuleMember -Function Invoke-DatrixPythonScript, New-DatrixGateLogFile, Write-DatrixGateLog, Write-DatrixGateVerdict
