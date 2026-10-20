#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run tests for Datrix projects using datrix_scripts.test_project.

.DESCRIPTION
 Runs datrix_scripts.test.test in the shared venv, which runs datrix_scripts.test_project
 for one or more projects, each in its own child process.

 By default, test output is minimal (summary + link to detailed results).
 Use -VerboseOutput to see full test output in the console.

.PARAMETER Projects
 One or more project names or folder paths to test (e.g., datrix-common,
 .\datrix-common\, D:\datrix\datrix-common). Paths will be resolved and the
 project name will be extracted from the folder name.

.PARAMETER All
 Run tests for all Datrix projects.

.PARAMETER Coverage
 Generate coverage reports.

.PARAMETER VerboseOutput
 Enable verbose test output. When not specified, minimal output is shown (summary only).

.PARAMETER NoSave
 Don't save test output to log files.

.PARAMETER NoAutoInstall
 Disable automatic dependency installation (prompt instead).

.PARAMETER Unit
 Run unit tests only.

.PARAMETER Integration
 Run integration tests only.

.PARAMETER E2E
 Run end-to-end tests only.

.PARAMETER Fast
 Run fast tests only (excludes slow tests).

.PARAMETER Slow
 Run slow tests only.

.PARAMETER Specific
 Run specific test file(s) or pattern. Several files/node-IDs may be given
 comma-separated in ONE invocation (e.g. "tests/unit/a.py,tests/unit/b.py") and
 run in a single pytest session. Commas inside parametrized node IDs ("[1,2]")
 are literal, not separators.

.PARAMETER Keyword
 Run tests matching keyword expression (-k option).

.PARAMETER Tag
 Run only the tests carrying at least one of these feature tags (comma-separated,
 e.g. "gateway,identity"). A pytest test carries tags through the `tag` marker; a
 Node test through '#tag' tokens in its name. Every named tag must be carried by at
 least one test in each named package, and a tag selecting a package's whole test
 tree is refused. This is how an agent runs exactly the tests related to the code it
 changed, across every package that has them.

.PARAMETER ListTags
 Print every feature tag in each named package with its test count, and the tests
 carrying no tag. Runs no test. Exits non-zero when any test is untagged or a test
 module fails to collect. With -Specific, lists only the named files/directories.
 Then compares each package's tags with the vocabulary table in
 datrix-common/docs/contributing/test-guidelines/feature-tags.md (datrix_scripts.test.tag_vocabulary)
 and lists every tag in use the table does not name, with where it is first applied --
 report only; the exit code stays the listing's.

.PARAMETER Rerun
 Re-run tests only for projects whose latest timestamped test log reports a failure.
 Scans all projects, reads each project's .test_results directory, and runs tests
 only for those whose most recent run has failed or errored. Projects with no
 previous test results are skipped.

.PARAMETER NoDigest
 Write no failure digest. By default, after the summary, every failed package with a
 saved run gets a short digest (common/lib/datrix_scripts/run_digest.py): its failure groups with
 location and re-run command, what changed since the previous run with the same test
 selection, and a resident local model's reading of each group. The digest is written
 to digest.txt in the run directory; the console gets one "Failure digest written: <path>"
 line, never the digest itself. Model text is a lead to confirm.

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER SelfTest
 Run the module's self-test (count parsing, run-directory resolution, project selection, the
 install-check decision, and this wrapper's seam with the module). Runs no test of any package.

.EXAMPLE
 .\test.ps1 -Rerun
 Re-run tests only for projects whose latest test log reports failures.

.EXAMPLE
 .\test.ps1 datrix-common
 Run tests for datrix-common only.

.EXAMPLE
 .\test.ps1 .\datrix-common\
 Run tests using folder path (project name extracted from path).

.EXAMPLE
 .\test.ps1 -All
 Run tests for all Datrix projects.

.EXAMPLE
 .\test.ps1 datrix-common datrix-language -Coverage
 Run tests for specific projects with coverage.

.EXAMPLE
 .\test.ps1 .\datrix-common\ .\datrix-language\ -Coverage
 Run tests for specific projects using folder paths with coverage.

.EXAMPLE
 .\test.ps1 datrix-common -Unit
 Run only unit tests for datrix-common.

.EXAMPLE
 .\test.ps1 -All -Fast
 Run fast tests for all projects (excludes slow tests).

.EXAMPLE
 .\test.ps1 datrix-common -Specific "tests/unit/test_parser.py"
 Run specific test file.

.EXAMPLE
 .\test.ps1 datrix-common -Specific "tests/unit/test_parser.py,tests/unit/test_types.py"
 Run several test files in one pytest session (one runner startup, one run directory).

.EXAMPLE
 .\test.ps1 datrix-language -Keyword "test_basic"
 Run tests matching keyword expression.

.EXAMPLE
 .\test.ps1 datrix-codegen-python datrix-codegen-typescript -Tag gateway
 Run every test tagged 'gateway' in both packages.

.EXAMPLE
 .\test.ps1 datrix-codegen-python -ListTags
 List the feature tags in a package; run nothing.

#>

[CmdletBinding()]
param(
 [Parameter(Position=0, ValueFromRemainingArguments=$true)]
 [string[]]$Projects,

 [switch]$All,
 [switch]$Rerun,
 [switch]$Coverage,
 [switch]$VerboseOutput,
 [switch]$NoSave,
 [switch]$NoAutoInstall,

 # Test type filters (mutually exclusive)
 [switch]$Unit,
 [switch]$Integration,
 [switch]$E2E,
 [switch]$Fast,
 [switch]$Slow,

 # Test selection
 [string]$Specific,
 [string]$Keyword,
 [string]$Tag,
 [switch]$ListTags,

 [switch]$NoDigest,

 [Parameter()]
 [switch]$Dbg,

 [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.test.test" -Parameters $PSBoundParameters
exit $LASTEXITCODE
