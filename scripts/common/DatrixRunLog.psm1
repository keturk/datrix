<#
.SYNOPSIS
 Run-log file naming and exclusive claiming for datrix scripts.

.DESCRIPTION
 Two runs that start in the same second compute the same timestamped log name.
 Naming alone cannot keep them apart: whatever discriminants a name carries
 (language, config profile, target), two runs that agree on all of them compute
 one name, and the second run's header write truncates the first run's log while
 both keep appending into it.

 So here a name is a LABEL and the claim is the uniqueness mechanism.
 New-DatrixRunLogFile creates each candidate with FileMode.CreateNew -- an
 atomic create-or-fail -- so of two runs racing on one candidate exactly one
 creates it and the other moves to the next candidate. The path it returns is
 owned by that run alone.

 This is the file-level twin of TeeLogger._claim_run_dir in
 datrix/scripts/library/shared/logging_utils.py, which enforces the same
 invariant for test run DIRECTORIES.

 Held by datrix/scripts/test/run-log-exclusivity-gate.ps1.
#>

# How many candidate names New-DatrixRunLogFile tries before failing (base name,
# then base-2 ... base-N). Runs colliding on one timestamped name are the
# concurrency case this bounds; N is far above any plausible number of
# same-second runs writing into one results directory.
$script:DatrixRunLogMaxClaimAttempts = 1000

# Timestamp format for run-log base names. Second granularity, leading in the
# name, so sorting the results directory by name stays chronological for the
# consumers that glob for these logs.
$script:DatrixRunLogTimestampFormat = "yyyyMMdd-HHmmss"

# What a caller-supplied label may contribute to a file name. Everything else --
# path separators, drive colons, "..", spaces, wildcards -- collapses to a single
# dash, so a label taken from a command line (a language, a config profile) can
# never steer the log out of its results directory or name a file the caller did
# not intend.
$script:DatrixRunLogSegmentPattern = '[^A-Za-z0-9]+'

function ConvertTo-DatrixRunLogSegment {
 <#
 .SYNOPSIS
 Reduces one label to the characters a run-log file name may carry.

 .DESCRIPTION
 Collapses every run of non-alphanumeric characters to a single dash and trims
 leading/trailing dashes. Returns an empty string when nothing survives, which
 callers drop rather than emit as an empty name segment.

 .PARAMETER Value
 The raw label (e.g. a language name or a config profile name).

 .EXAMPLE
 ConvertTo-DatrixRunLogSegment -Value "../../etc/passwd"
 Returns "etc-passwd" -- no separator survives, so the name cannot traverse.
 #>
 [CmdletBinding()]
 [OutputType([string])]
 param(
 [Parameter(Mandatory = $true)]
 [AllowEmptyString()]
 [string]$Value
 )

 return ($Value -replace $script:DatrixRunLogSegmentPattern, '-').Trim('-')
}

function Get-DatrixRunLogBaseName {
 <#
 .SYNOPSIS
 Composes the preferred (extension-less) base name for a run log.

 .DESCRIPTION
 Produces "<prefix>-<timestamp>[-<segment>...]". The segments are labels that
 say which run a log belongs to; they are NOT what makes the name unique --
 New-DatrixRunLogFile is. Labels that sanitize away to nothing are dropped.

 .PARAMETER Prefix
 Leading name component, e.g. "generate-results". Consumers glob on it.

 .PARAMETER Segment
 Zero or more labels appended after the timestamp, in order.

 .PARAMETER Timestamp
 The moment to stamp into the name. Defaults to now; pass an explicit value to
 make the composed name deterministic (the exclusivity gate pins it).

 .EXAMPLE
 Get-DatrixRunLogBaseName -Prefix "generate-results" -Segment @("python", "pilot")
 #>
 [CmdletBinding()]
 [OutputType([string])]
 param(
 [Parameter(Mandatory = $true)]
 [string]$Prefix,

 [Parameter()]
 [AllowEmptyCollection()]
 [string[]]$Segment = @(),

 [Parameter()]
 [datetime]$Timestamp = (Get-Date)
 )

 $parts = [System.Collections.Generic.List[string]]::new()
 $parts.Add((ConvertTo-DatrixRunLogSegment -Value $Prefix))
 $parts.Add($Timestamp.ToString($script:DatrixRunLogTimestampFormat))
 foreach ($label in $Segment) {
 $clean = ConvertTo-DatrixRunLogSegment -Value $label
 if (-not [string]::IsNullOrEmpty($clean)) {
 $parts.Add($clean)
 }
 }

 return ($parts -join "-")
}

function New-DatrixRunLogFile {
 <#
 .SYNOPSIS
 Creates, and returns the path of, a run-log file no other run owns.

 .DESCRIPTION
 Tries "<BaseName><Extension>" first, then "<BaseName>-2<Extension>",
 "<BaseName>-3<Extension>", ... Each attempt opens the candidate with
 FileMode.CreateNew, which is an atomic create-or-fail: of two processes racing
 on one candidate name, exactly one creates the file and the other sees the
 name taken and tries the next candidate.

 The returned file exists and is empty, so the caller may write its header
 straight into it -- the name can no longer be claimed by anyone else.

 NEVER relax CreateNew to Create or OpenOrCreate: both succeed on an existing
 file, which is exactly how two runs end up truncating and interleaving one log.

 .PARAMETER Directory
 Directory the log is created in. Created if missing.

 .PARAMETER BaseName
 Preferred name without extension, normally from Get-DatrixRunLogBaseName.

 .PARAMETER Extension
 File extension including the dot (default ".log").

 .EXAMPLE
 $base = Get-DatrixRunLogBaseName -Prefix "generate-results" -Segment @("python")
 $log = New-DatrixRunLogFile -Directory $resultsDir -BaseName $base
 #>
 [CmdletBinding()]
 [OutputType([string])]
 param(
 [Parameter(Mandatory = $true)]
 [string]$Directory,

 [Parameter(Mandatory = $true)]
 [string]$BaseName,

 [Parameter()]
 [string]$Extension = ".log"
 )

 if (-not (Test-Path -LiteralPath $Directory)) {
 $null = New-Item -ItemType Directory -Path $Directory -Force
 }

 for ($attempt = 1; $attempt -le $script:DatrixRunLogMaxClaimAttempts; $attempt++) {
 $candidateName = if ($attempt -eq 1) { "$BaseName$Extension" } else { "$BaseName-$attempt$Extension" }
 $candidate = Join-Path $Directory $candidateName
 $claimed = $false
 try {
 $stream = [System.IO.File]::Open(
 $candidate,
 [System.IO.FileMode]::CreateNew,
 [System.IO.FileAccess]::Write,
 [System.IO.FileShare]::None)
 $stream.Dispose()
 $claimed = $true
 } catch {
 # The name being taken is the collision this loop exists for, and it is
 # exactly the case where the candidate now exists. Any other failure (an
 # unwritable directory, a directory that vanished, an invalid path) is a
 # real problem: rethrow it with its own message rather than retrying it
 # 1000 times and reporting "all names taken", which it is not.
 if (-not (Test-Path -LiteralPath $candidate)) { throw }
 }
 if ($claimed) { return $candidate }
 }

 throw (
 "Could not claim a private run-log file under '$Directory': the names " +
 "'$BaseName$Extension' through '$BaseName-$($script:DatrixRunLogMaxClaimAttempts)$Extension' " +
 "are all taken. Expected at least one free name. This run cannot proceed, because " +
 "sharing a log file with another run truncates that run's log and interleaves both " +
 "runs' output into one file. Fix: delete stale logs from '$Directory' and re-run."
 )
}

Export-ModuleMember -Function ConvertTo-DatrixRunLogSegment, Get-DatrixRunLogBaseName, New-DatrixRunLogFile
