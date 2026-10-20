#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Enforce the I5 docs-conformance gate across Datrix architecture docs.

.DESCRIPTION
 Runs datrix_scripts.gates.repo_hygiene.check_docs_conformance in the shared venv.

 Extracts repo-relative path references and Python module references from the
 curated 38-file architecture-doc set and fails if any reference does not
 resolve to a real file/directory/module in the tree, unless it is recorded
 in the committed exceptions baseline at
 scripts/config/docs-conformance-exceptions.json.

 It also holds the overview's dependency graph to the edges the package
 manifests declare (both directions), fails on any numeric package or
 repository count in an architecture doc, and fails on a Code Quality tool
 that no scripts quick-reference documents.

 Exit codes:
   0 = clean (no unresolved references), or -Warn mode
   1 = at least one unresolved, non-excepted reference found
   2 = usage error, missing exceptions baseline, or a doc in
       ARCHITECTURE_DOC_FILES that no longer exists

.PARAMETER Warn
 Warning mode: report unresolved references but exit 0.

.PARAMETER ShowFiles
 Print each architecture doc file being scanned (verbose mode).

.PARAMETER BaseDir
 Monorepo root directory (default: auto-detect).

.PARAMETER SelfTest
 Run only the self-test suite (plain-Python edge-case checks on the scanner's
 own functions) and exit -- skips the real docs scan. The same self-test also
 runs automatically, unconditionally, as step 1 of every normal invocation
 (with or without this switch).

.PARAMETER Dbg
 Print the interpreter and arguments before running.

.EXAMPLE
 .\check-docs-conformance.ps1
 Scan all 38 architecture docs, fail on unresolved references (self-test runs first, automatically).

.EXAMPLE
 .\check-docs-conformance.ps1 -SelfTest
 Run only the scanner's own self-test suite.

.EXAMPLE
 .\check-docs-conformance.ps1 -Warn
 Report unresolved references but exit 0.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Warn,

    [Parameter()]
    [switch]$ShowFiles,

    [Parameter()]
    [string]$BaseDir = "",

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
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.repo_hygiene.check_docs_conformance" -Parameters $PSBoundParameters
exit $LASTEXITCODE
