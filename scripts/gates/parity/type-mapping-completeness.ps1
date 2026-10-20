#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Validate type mapping completeness for specified languages.

.DESCRIPTION
 Runs type mapping completeness validation for one or more language generators.
 Ensures all canonical types in the TypeRegistry have mappings in each language.

.PARAMETER Languages
 Comma-separated list of languages to check for the CANONICAL-TYPE completeness
 leg only (e.g., "python,typescript"). When omitted, every registered
 datrix.languages target is checked (discovered at runtime -- never a
 hardcoded python/typescript list). Does NOT restrict the extension-map
 completeness leg, which always runs unconditionally over every
 registered language plus sql, regardless of this parameter.

.PARAMETER SelfTest
 Run only the extension-map comparator's non-vacuity self-test and skip both
 real checks.

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.EXAMPLE
 .\type-mapping-completeness.ps1
 Run both checks: canonical-type completeness for every registered language,
 and extension-map completeness for every registered language plus sql.

.EXAMPLE
 .\type-mapping-completeness.ps1 -Languages python,typescript
 Restrict the canonical-type leg to Python and TypeScript; the extension-map
 leg still covers every registered language plus sql.

.EXAMPLE
 .\type-mapping-completeness.ps1 -SelfTest
 Run only the extension-map comparator's non-vacuity self-test.

.EXAMPLE
 .\type-mapping-completeness.ps1 -Languages python -Dbg
 Check Python type mappings with debug logging.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$Languages = "",

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.parity.type_mapping_completeness" -Parameters $PSBoundParameters
exit $LASTEXITCODE
