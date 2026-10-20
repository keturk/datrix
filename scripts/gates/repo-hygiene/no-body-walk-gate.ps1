#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate: a datrix-codegen-* function walks a model body only where the allowlist says so.

.DESCRIPTION
 Runs datrix_scripts.gates.repo_hygiene.no_body_walk_gate in the shared venv. It parses every
 *.py under every datrix-codegen-*/src (globbed from the workspace root, so a new target repo is
 covered the moment it exists) with Python ast and flags, by innermost enclosing function, a call
 of a walk function (iter_tree, iter_expressions, walk_expression, expression_children,
 find_call_nodes, iter_ast_walk_edges, iter_body_nodes), a walk method (.walk(), .child_nodes(),
 .children(), .child_expressions(), .child_statements(), except on the bare receivers ast and os),
 or getattr(<x>, "<walk method>").

 The flagged set must equal scripts\config\no_body_walk_allowlist.json exactly: an unlisted
 function fails, and so does an entry whose function no longer walks (the list only shrinks). Each
 difference is printed as path::function with the flagged call forms and their lines.

 WHY IT EXISTS: analysis records what every body reads, calls, writes and resolves; a generator
 reads those facts instead of walking the body again. The allowlist names the few deliberate
 walks (render traversal, local emission syntax, transpiler decisions, literal searches, code
 analysis records no facts on). guard-code-standards.py refuses the same thing on the edit.

 A built-in self-test runs before every scan: an embedded source with one call of every flagged
 form, plus ast.walk and os.walk, must flag exactly the former.

 Exit codes:
   0 = flagged set equals the allowlist (or the self-test passed, with -SelfTest)
   1 = at least one unlisted function or stale entry
   2 = the gate cannot judge: a failed self-test, a malformed allowlist, or a source file that
       does not parse or cannot be read

.PARAMETER SelfTest
 Run only the self-test and the wrapper seam checks, and skip the real scan.

.PARAMETER Dbg
 Print the python invocation before running.

.EXAMPLE
 .\no-body-walk-gate.ps1
 Compare every flagged function with the allowlist.

.EXAMPLE
 .\no-body-walk-gate.ps1 -SelfTest
 Run only the self-test.
#>
[CmdletBinding()]
param(
 [switch]$SelfTest, [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.repo_hygiene.no_body_walk_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
