#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Zero-environment runtime census gate -- every registered language is
 obligated to bake deployment-static values at generation time, and its
 baseline entry kind decides how its environment reads are held.

.DESCRIPTION
 The zero-environment runtime architecture bakes every deployment-static value
 into literal constants at generation time; the running service consults no
 environment variable. Every registered language is obligated to it. Each
 language plugin states, on its LanguageCapabilityDeclaration
 (zero_environment_runtime), the regular expressions that spell an
 environment read in its own templates. This gate censuses every .j2 template
 under each registered language package's src/ tree against those idioms and
 holds each language to the rule the KIND of its entry in
 scripts/config/zero-environment-runtime-baseline.json selects:

   * reviewed_exemptions -- every template that reads the environment is
     listed with a written reason; an unlisted read and a stale entry are both
     violations. A language with no entry is held to this kind with an empty
     list;
   * pinned_count -- a decrease-only count of environment-reading templates,
     for a language that delivers runtime facts through the environment by
     design; it may fall and may never rise;
   * a registered language that states no idioms fails, named, and a baseline
     entry naming an unregistered language is stale and fails.

 Language set from the installed datrix.languages entry points at runtime;
 idioms from each language's own declaration -- never a table here. Runs a
 built-in non-vacuity self-test on every invocation.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (lists every environment-reading template).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real census.

.PARAMETER UpdateBaseline
 Lower every pinned_count entry to its live census (the only writer of
 pinned_count values; it refuses to raise one). reviewed_exemptions entries are
 hand-authored and left untouched.

.EXAMPLE
 .\zero-environment-runtime-gate.ps1

.EXAMPLE
 .\zero-environment-runtime-gate.ps1 -UpdateBaseline
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$UpdateBaseline
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($Dbg) { $pythonArgs += "--debug" }
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($UpdateBaseline) { $pythonArgs += "--update-baseline" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\zero_environment_runtime_gate.py") -Arguments $pythonArgs -RequirePackages -Gate "zero-environment-runtime")
