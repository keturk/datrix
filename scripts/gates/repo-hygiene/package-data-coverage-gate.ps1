#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate: every runtime resource a package loads ships in its wheel.

.DESCRIPTION
 For every datrix-* package in the workspace with a [tool.setuptools.package-data]
 table, expands each glob exactly as setuptools expands it and requires every
 Jinja2 template (*.j2) and DAL generator definition (*.dal) under the package to
 be matched. An editable install reads the source tree directly, so a missing
 glob is invisible locally; the loss only appears after installing the built
 wheel, as a package that cannot render a file.

 The non-vacuity self-test runs before every scan.

 Exit codes:
   0 = every runtime resource ships
   1 = at least one runtime resource ships with no glob, or the self-test failed
   2 = usage error (an unknown -Package name)

.PARAMETER Package
 Limit the scan to these repo names. Default: every datrix-* package in the workspace.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.PARAMETER Dbg
 Enable DEBUG logging.

.EXAMPLE
 .\package-data-coverage-gate.ps1
 Scan every package in the workspace.

.EXAMPLE
 .\package-data-coverage-gate.ps1 -Package datrix-codegen-python
 Scan only the named package(s).

.EXAMPLE
 .\package-data-coverage-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string[]]$Package,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
foreach ($name in $Package) { $pythonArgs += @("--package", $name) }
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\package_data_coverage.py") -Arguments $pythonArgs -Gate "package-data-coverage")
