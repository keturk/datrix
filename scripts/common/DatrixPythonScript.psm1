<#
.SYNOPSIS
 The one way a datrix script runs Python: Invoke-DatrixPythonScript.

.DESCRIPTION
 A wrapper is its param() block, the mapping of its switches to Python flags, and

   exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\$name.py") -Arguments $pythonArgs)

 where lib\$name.py is the wrapper's own Python file beside it.

 Invoke-DatrixPythonScript has the shared venv checked (common\venv.ps1's -Ensure, and with
 -RequirePackages its -EnsurePackages -SkipIfInstalled), points the child's environment at the venv
 (common\lib first on PYTHONPATH, the bytecode cache outside the source trees, VIRTUAL_ENV and
 the venv's Scripts first on PATH), runs the venv interpreter by absolute path, restores this
 process's environment in a finally block, and returns the child's exit code. It never calls
 exit itself.

 Invoke-DatrixEntrypoint is the body of every wrapper rendered from
 common\templates\entrypoint.ps1: it runs one datrix_scripts module with the wrapper's bound
 parameters as --kebab-name arguments, in an argument vector, and leaves the module's exit code in
 $LASTEXITCODE for the wrapper's "exit $LASTEXITCODE". When the venv has no interpreter yet it
 first creates it (python -m datrix_scripts.venv --ensure under any Python on the machine; the
 module picks the native base interpreter).

 Gate mode (-Gate <name>) tees the child's output to a claimed log under
 <workspace>\.test-output\gates\<name>\<name>-<yyyyMMdd-HHmmss>[-N].log and prints exactly
 one last line:

   [GATE] <name> PASSED exit=0 log=<absolute log path>
   [GATE] <name> FAILED exit=<n> log=<absolute log path>

 That line is the seam the red-run digest hook reads (digest-red-test-run.py). A gate that
 runs no Python claims its log with New-DatrixGateLogFile, writes its lines with
 Write-DatrixGateLog, and prints the same last line with Write-DatrixGateVerdict.
#>

# -Force: without it, a copy an earlier command loaded into this session is reused even after the
# file changed on disk (a pull), so a function added since is missing. -Global: a forced import
# replaces the session's copy, and importing the new one into the global scope keeps a caller that
# imported the same module itself working.
Import-Module (Join-Path $PSScriptRoot "DatrixPaths.psm1") -Force -Global
Import-Module (Join-Path $PSScriptRoot "DatrixRunLog.psm1") -Force -Global

$script:GateLogFolder = "gates"
$script:GateVerdictPrefix = "[GATE]"
$script:ExitUsage = 2
$script:ExitVenvUnavailable = 1
# The functions from here to Invoke-DatrixEntrypoint keep their constants local: a wrapper script
# runs them, and $script: in a function names the scope of the script being run when that script
# runs in this module's session state, not this module's own scope.

function Enter-DatrixVenvEnvironment {
 # Points this process's environment at the shared venv for a Python child and returns the values
 # it replaced, for Exit-DatrixVenvEnvironment: common\lib first on PYTHONPATH, the bytecode cache
 # under <workspace>\.pycache-verify (never beside the sources), VIRTUAL_ENV and the venv's Scripts
 # first on PATH. PYTHONHOME is cleared, as a venv's activation does.
 $names = @("PYTHONPATH", "PYTHONPYCACHEPREFIX", "PYTHONHOME", "VIRTUAL_ENV", "PATH")
 $cacheFolder = ".pycache-verify"
 $lib = Get-DatrixScriptsPythonPath
 if (-not (Test-Path -LiteralPath (Join-Path $lib "datrix_scripts"))) {
  throw "The shared scripts package is missing: expected $lib\datrix_scripts. Restore it from the datrix repository."
 }
 $saved = @{}
 foreach ($name in $names) { $saved[$name] = [Environment]::GetEnvironmentVariable($name) }
 $separator = [System.IO.Path]::PathSeparator
 $inherited = @("$($saved['PYTHONPATH'])" -split [regex]::Escape($separator) | Where-Object { $_ -and ($_ -ne $lib) })
 $env:PYTHONPATH = (@($lib) + $inherited) -join $separator
 if ([string]::IsNullOrWhiteSpace($saved["PYTHONPYCACHEPREFIX"])) {
  $env:PYTHONPYCACHEPREFIX = Join-Path (Get-DatrixWorkspaceRoot) $cacheFolder
 }
 [Environment]::SetEnvironmentVariable("PYTHONHOME", $null)
 $env:VIRTUAL_ENV = Get-DatrixVenvPath
 $env:PATH = (Join-Path $env:VIRTUAL_ENV "Scripts") + $separator + $saved["PATH"]
 return $saved
}

function Exit-DatrixVenvEnvironment {
 # Restores what Enter-DatrixVenvEnvironment replaced; a variable that was unset is removed.
 param([Parameter(Mandatory = $true)][hashtable]$Saved)
 foreach ($name in $Saved.Keys) { [Environment]::SetEnvironmentVariable($name, $Saved[$name]) }
}

function ConvertTo-DatrixEntrypointArgument {
 # A wrapper's bound parameters as an argument vector: a present switch is --kebab-name, every
 # other value --kebab-name=<value> (one per element of an array). PowerShell's common parameters
 # (-Verbose, -ErrorAction, ...) belong to the wrapper and are not passed.
 param([Parameter(Mandatory = $true)][AllowEmptyCollection()][System.Collections.IDictionary]$Parameters)
 # A word boundary is a lower-case letter or digit before an upper-case one (SelfTest -> self-test),
 # or an upper-case letter before an upper-case one that starts a word (IPAddress -> ip-address).
 # datrix_scripts.entrypoint.kebab_flag applies the same rule when it compares a wrapper's
 # parameters with its module's options.
 $kebabBoundary = '(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])'
 $common = @([System.Management.Automation.Cmdlet]::CommonParameters) + @([System.Management.Automation.Cmdlet]::OptionalCommonParameters)
 $arguments = New-Object System.Collections.Generic.List[string]
 foreach ($name in $Parameters.Keys) {
  if ($common -contains $name) { continue }
  $flag = "--" + ($name -creplace $kebabBoundary, "-").ToLowerInvariant()
  $value = $Parameters[$name]
  if ($value -is [System.Management.Automation.SwitchParameter]) {
   if ($value.IsPresent) { $arguments.Add($flag) }
   continue
  }
  foreach ($item in @($value)) { $arguments.Add("$flag=$item") }
 }
 return ,$arguments.ToArray()
}

function Get-DatrixBootstrapPython {
 # Any Python that can run datrix_scripts.venv --ensure, which picks the native base interpreter
 # itself: DATRIX_PYTHON, else the first of py, python, python3 on PATH (Store aliases excluded).
 $launchers = @("py", "python", "python3")
 if (-not [string]::IsNullOrWhiteSpace($env:DATRIX_PYTHON)) { return $env:DATRIX_PYTHON }
 foreach ($name in $launchers) {
  $found = @(Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue |
   Where-Object { $_.Source -notmatch '\\WindowsApps\\' })
  if ($found.Count -gt 0) { return $found[0].Source }
 }
 throw ("No Python was found to create the shared venv at $(Get-DatrixVenvPath). Expected DATRIX_PYTHON or one of " +
  "$($launchers -join ', ') on PATH. Fix: install a CPython built for this machine's CPU, " +
  "or set DATRIX_PYTHON to one, then retry.")
}

function Invoke-DatrixEntrypoint {
 <#
 .SYNOPSIS
 Runs one datrix_scripts module in the shared venv with a wrapper's bound parameters; the body of
 every wrapper rendered from common\templates\entrypoint.ps1.

 .DESCRIPTION
 The module's output goes to the caller's pipeline (a caller may capture it) and its exit code is
 left in $LASTEXITCODE. When the venv has no interpreter yet, the venv is created first with
 "python -m datrix_scripts.venv --ensure" under Get-DatrixBootstrapPython; a failed creation
 leaves its exit code in $LASTEXITCODE and runs nothing else.

 .PARAMETER Module
 The dotted module to run with -m, e.g. datrix_scripts.venv.

 .PARAMETER Parameters
 The wrapper's $PSBoundParameters.
 #>
 [CmdletBinding()]
 param(
  [Parameter(Mandatory = $true)]
  [string]$Module,

  [Parameter(Mandatory = $true)]
  [AllowEmptyCollection()]
  [System.Collections.IDictionary]$Parameters
 )

 # Continue, not the caller's Stop: under a caller's 2>&1, Windows PowerShell turns each stderr
 # line of a native command into an error record, and Stop would end the run on the first one.
 $previousPreference = $ErrorActionPreference
 $ErrorActionPreference = "Continue"
 $saved = Enter-DatrixVenvEnvironment
 try {
  $python = Get-DatrixVenvPython
  if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
   & (Get-DatrixBootstrapPython) -m datrix_scripts.venv --ensure
   if ($LASTEXITCODE -ne 0) { return }
  }
  $arguments = @("-m", $Module) + @(ConvertTo-DatrixEntrypointArgument -Parameters $Parameters)
  & $python @arguments
 }
 finally {
  Exit-DatrixVenvEnvironment -Saved $saved
  $ErrorActionPreference = $previousPreference
 }
}

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
 Check the editable installs first (common\venv.ps1 -EnsurePackages -SkipIfInstalled).

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
 $saved = $null
 try {
  # The venv check is common\venv.ps1's own call, made here directly: a script run from inside this
  # module would run in the module's session state, where $script: names that script's scope and
  # not this module's. Out-Host keeps the check's diagnostics out of this function's return value.
  $check = @{ Ensure = [switch]$true }
  if ($RequirePackages) {
   $check["EnsurePackages"] = [switch]$true
   $check["SkipIfInstalled"] = [switch]$true
  }
  Invoke-DatrixEntrypoint -Module "datrix_scripts.venv" -Parameters $check | Out-Host
  if ($LASTEXITCODE -ne 0) {
   $checked = if ($RequirePackages) { "the shared venv at $(Get-DatrixVenvPath) and its package installs" } else { "the shared venv at $(Get-DatrixVenvPath)" }
   Write-Host "Error: $checked failed the check above (exit $LASTEXITCODE). Fix what it names, then re-run (set DATRIX_VENV_VERBOSE=1 to see each step of common\venv.ps1)." -ForegroundColor Red
   return $exitCode
  }
  $saved = Enter-DatrixVenvEnvironment
  $pythonExe = Get-DatrixVenvPython
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
  if ($null -ne $saved) { Exit-DatrixVenvEnvironment -Saved $saved }
  if ($Gate) {
   Write-DatrixGateVerdict -Gate $Gate -ExitCode $exitCode -LogPath $logPath
  }
 }
}

Export-ModuleMember -Function Invoke-DatrixPythonScript, Invoke-DatrixEntrypoint, Enter-DatrixVenvEnvironment, Exit-DatrixVenvEnvironment, New-DatrixGateLogFile, Write-DatrixGateLog, Write-DatrixGateVerdict
