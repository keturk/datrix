#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Author a package's diagnostics fixtures from the diagnostic catalog (draft, plan, scaffold, verify), inventory what every package's tests read and need, or draft the shared fixture corpus to hold it.

.DESCRIPTION
 The behaviour is datrix_scripts.dev.fixture_author.cli.

 needs inventories every workspace package holding tests\ (or the one -Package names): the inputs each
 test module reads (fixture file names, inline .dtrx/.dcfg literals, FIXTURE_SYSTEM_* names, conftest pair
 fixtures), found statically, and per test function the declarations its assertions depend on, read by a
 local model. It writes .tmp\fixture-author\needs.json, rows sorted by module path and byte-identical on an
 unchanged tree, only when every module found has its row, and prints per package the modules, inputs,
 declarations, distinct paths and local tests, then the declaration kinds per block family.
 Exit: 0 written, 1 a module found is not inventoried (nothing is written), a tree reader moved or a test
 module cannot be parsed, 2 usage error or a tree the inventory reads is missing, 3 no local model can read
 (nothing is written).

 library drafts the shared fixture corpus (datrix-testing's fixtures_data\corpus) to hold what needs.json
 needs: per block family a local model writes or extends services\<family>.dtrx and its owner configs
 (each importing the datasource templates), and per new entry its system, round by round; each round
 analyzes every entry under every profile it runs, and a unit passes when needed - provided is empty and
 nothing errs. A draft holding a secret-looking literal is queued and never written; a unit still failing
 after 4 rounds is written to .tmp\fixture-author\queue\library-<unit>.md; a rename keeping two colliding
 needs apart is recorded in .tmp\fixture-author\renames.json. Only units that pass are written to the corpus.
 Exit: 0 every unit landed or was provided, 1 a unit was queued or the inventory cannot be read, 2 usage
 error or needs.json missing, 3 no local model can draft (nothing is written).

 repoint rewrites the test modules needs.json lists for -Package so their tests read the shared corpus:
 per module a local model is given the module, its needs, the corpus entry that provides them and
 renames.json. The module is saved to .tmp\fixture-author\undo\ and written; the rewrite is kept only when
 every test and every assertion (assert plus pytest.raises blocks) stays, the module reads no input but one
 whose first line is // @local <reason>, a module holding a test with no local reason reads its corpus entry
 (corpus_project or corpus_project_copy), and test.ps1 -Specific over it (over the test modules depending
 on a conftest or helper) passes. Otherwise it is written back byte for byte, and after 4 rounds queued in
 .tmp\fixture-author\queue\repoint-<package>--<module>.md. A draft adding a secret-looking literal is queued
 and never written. The run ends on inventoried - rewritten - local, computed from the code.
 Exit: 0 that remainder is empty, 1 a module is not done or the inventory cannot be read, 2 usage error
 (no -Package, a diagnostics switch, needs.json missing), 3 no local model can rewrite.

 repoint -Prune deletes the fixture files of -Package nothing reads any more, and is refused while
 .tmp\fixture-author\queue\ holds a module of the package. A file needs discovery names, a directory a module
 reads whole, the diagnostics harness tree and what a kept file reaches are kept. Each deleted file is saved
 to .tmp\fixture-author\undo\ first; a deletion leaving a model with no contract sample, or changing the
 package's semantic baseline other than by the deleted keys leaving and the corpus keys arriving, refuses
 the run and every file is written back byte for byte. An accepted run regenerates the package's semantic
 manifest and runs fixture-budget-gate.ps1 -UpdateBaseline.
 Exit: 0 pruned and the budget banked, 1 refused or the baseline not tightened, 2 usage error.

 diagnostics loads the package's case session, reads the
 catalog variants its diagnostics fixtures must provoke (the target-check variants for the package that
 registers the target checks, every other variant for the rest, less those its census proves by a code
 test), and plans one area project per code family (<family>-halt for a code that ends analysis, a seeded
 <area>/ directory for a code read off seed documents, one targets area for target checks, declaring
 // @analysis targets and naming no language: it is one input per registered backend language, and a
 variant must fire under each). With no action switch it drafts each planned area not on disk: a local model writes
 one fragment per variant, the area is analyzed once per round, a cascade or a variant not provoked goes
 back to the model, at most 4 rounds; a variant still failing is written to
 .tmp\fixture-author\queue\<area>.md for a person to finish. A draft holding a secret-looking literal is
 queued and never written. -Verify analyzes each area as its whole-analysis case does and prints what it
 reports and does not annotate (a cascade) and what it annotates and does not report.

 Exit of diagnostics: 0 done (every drafted variant landed; every verified area reports exactly what it
 annotates), 1 a variant was queued, an area failed or the package's state refuses the run, 2 usage
 error, 3 no local model can draft (nothing is written).

.PARAMETER Kind
 diagnostics (author the diagnostics fixtures), needs (inventory what the tests read and need), library
 (draft the shared fixture corpus from the inventory) or repoint (rewrite a package's test modules to read
 the corpus).

.PARAMETER Package
 The package directory name, e.g. datrix-semantic. Required by diagnostics and repoint; needs defaults to every package holding tests\; library takes none.

.PARAMETER Area
 One planned area; default every planned area (diagnostics only).

.PARAMETER Plan
 Print the needs and the planned areas (with -Area, that area's variants).

.PARAMETER Scaffold
 Copy the corpus system configuration and datasource templates into each project root lacking them.

.PARAMETER Verify
 Compare each area's reported variants with its annotated ones.

.PARAMETER Prune
 With repoint: delete the package's fixture files nothing reads, once its queue is empty.

.PARAMETER LocalMachines
 Machines (host name or IP) whose Ollama server drafts or reads, in preference order.

.PARAMETER LlmModel
 Use only these models, best first. Default: any model already in memory.

.PARAMETER LlmTimeout
 Timeout in seconds for each request to a ready model. Default: 300.

.PARAMETER Dbg
 Debug logging.

.PARAMETER SelfTest
 Run only the module's self-test: needs, area plan, scaffold, verification, and drafting over a loopback model server; the needs inventory on planted inputs and on the real tree over a loopback model server; the corpus library plan and check, and library drafting over a loopback model server on copies of the corpus; repointing a planted package over a loopback model server; pruning planted packages.

.EXAMPLE
 .\dev\fixture-author.ps1 needs
 Inventory what every package's tests read and need into .tmp\fixture-author\needs.json.

.EXAMPLE
 .\dev\fixture-author.ps1 needs -Package datrix-testing
 Inventory one package.

.EXAMPLE
 .\dev\fixture-author.ps1 library
 Draft the shared fixture corpus to hold what .tmp\fixture-author\needs.json needs, and queue what still fails.

.EXAMPLE
 .\dev\fixture-author.ps1 repoint -Package datrix-common
 Rewrite datrix-common's inventoried test modules to read the shared corpus, and queue what still fails.

.EXAMPLE
 .\dev\fixture-author.ps1 repoint -Package datrix-common -Prune
 Delete datrix-common's fixture files nothing reads any more, and bank the fixture budget.

.EXAMPLE
 .\dev\fixture-author.ps1 diagnostics -Package datrix-semantic -Area svc
 Draft the area svc with a local model and queue what still fails.

.EXAMPLE
 .\dev\fixture-author.ps1 diagnostics -Package datrix-semantic -Plan
 Print the needs and every planned area.

.EXAMPLE
 .\dev\fixture-author.ps1 diagnostics -Package datrix-semantic -Area svc -Verify
 Verify the area project svc.dtrx.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Mandatory = $true, Position = 0, ParameterSetName = "Run")][ValidateSet("diagnostics", "library", "needs", "repoint")][string]$Kind,
 [Parameter(ParameterSetName = "Run")][string]$Package,
 [Parameter(ParameterSetName = "Run")][string]$Area,
 [Parameter(ParameterSetName = "Run")][switch]$Plan,
 [Parameter(ParameterSetName = "Run")][switch]$Scaffold,
 [Parameter(ParameterSetName = "Run")][switch]$Verify,
 [Parameter(ParameterSetName = "Run")][switch]$Prune,
 [Parameter(ParameterSetName = "Run")][string[]]$LocalMachines,
 [Parameter(ParameterSetName = "Run")][string[]]$LlmModel,
 [Parameter(ParameterSetName = "Run")][int]$LlmTimeout,
 [switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.fixture_author.cli" -Parameters $PSBoundParameters
exit $LASTEXITCODE
