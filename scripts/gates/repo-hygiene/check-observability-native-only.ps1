#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Observability native-only example-conformance guard.

.DESCRIPTION
 Scans every datrix/examples/**/config/system.dcfg for a portable
 observability provider (prometheus/datadog metrics, jaeger/zipkin tracing,
 loki logging, grafana visualization, alertmanager alerting) paired with a
 cloud deployment target (provider aws or azure) in the same resolved
 profile. The native-only platform-boundary rule forbids this pairing; this
 is the retained standing example-conformance guard against future drift.

 Exit codes:
   0 = clean (no violations), or -Warn mode
   1 = at least one violation found
   2 = usage error, missing examples root, or the automatic self-test
       step failing on a normal invocation

.PARAMETER Warn
 Warning mode: report violations but exit 0.

.PARAMETER ExamplesRoot
 Override examples root directory (default: auto-detect datrix/examples).

.PARAMETER SelfTest
 Run only the scanner's own self-test suite and exit.

.PARAMETER ShowFiles
 Print each system.dcfg being scanned (verbose mode).

.PARAMETER Dbg
 Print the interpreter and arguments before running.

.EXAMPLE
 .\check-observability-native-only.ps1
 Scan every example, fail on any cloud+portable-provider pairing.

.EXAMPLE
 .\check-observability-native-only.ps1 -ExamplesRoot D:\datrix\.tmp\obs-guard-selftest\examples
 Scan a scratch examples tree instead of the real datrix/examples.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Warn,

    [Parameter()]
    [string]$ExamplesRoot = "",

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$ShowFiles,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($Warn) { $pythonArgs += "--warn" }
if ($ExamplesRoot) { $pythonArgs += @("--examples-root", $ExamplesRoot) }
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($ShowFiles) { $pythonArgs += "--verbose" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\check_observability_native_only.py") -Arguments $pythonArgs -Gate "observability-native-only" -ShowCommand:$Dbg)
