#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Hard-zero gate: every Jinja template a framework package ships is named by
 something that can render it.

.DESCRIPTION
 Discovers every .j2 file below a templates/ directory of every datrix-*/src
 tree on disk and fails on any that nothing names: no Python string constant,
 f-string or concatenation in any framework package's src/ (docstrings
 excluded), no static Jinja include/import/from/extends, and no compiled DAL generator
 FileDefinition template name of any registered generator target. A DAL generator
 template name that matches no template on disk fails the gate too.

 A template nothing names is dead output: reviewed, kept in sync and shipped,
 yet never rendered. Two cache-access templates once sat beside the live one
 that way.

 The self-test runs first on every invocation: a planted workspace must yield
 exactly its docstring-only and unnamed templates, and the live DAL generator walk must
 find template names -- so the matcher is proven, never vacuous.

 An unnamed template a declared contract requires to exist is listed, with a
 written reason, in datrix/scripts/config/template-reachability-exemptions.json;
 an entry whose template is named or gone is stale and fails the gate.

 Exit codes:
   0 = every template is named, or a successful -SelfTest run
   1 = an unnamed template, a dangling DAL generator template name or a stale exemption
   2 = usage error, a template that does not parse, a malformed exemptions file,
       or the self-test failed

.PARAMETER BaseDir
 Workspace root directory (default: auto-detect).

.PARAMETER SelfTest
 Run only the self-test and exit, skipping the real scan.

.PARAMETER Dbg
 Print the python invocation.

.EXAMPLE
 .\template-reachability-gate.ps1
 Scan every framework package, fail on any template nothing names.

.EXAMPLE
 .\template-reachability-gate.ps1 -SelfTest
 Prove the matcher on a planted workspace and the DAL generator walk on the real one.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$BaseDir = "",

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($BaseDir) { $pythonArgs += @("--base-dir", $BaseDir) }
if ($SelfTest) { $pythonArgs += "--self-test" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\template_reachability.py") -Arguments $pythonArgs -Gate "template-reachability" -ShowCommand:$Dbg)
