#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Set up the line-edit MCP server (datrix-edit) that agents read and edit files through by line.

.DESCRIPTION
 Runs datrix_scripts.dev.line_edit in the shared venv. The datrix-edit server
 (datrix_scripts.dev.line_edit_mcp, logic in datrix_scripts.line_edits) gives agents read_lines,
 which shows every line numbered and hashed, and edit_lines, which replaces or inserts line ranges
 -- many at once, across files -- naming the old lines by number and hash instead of re-sending
 their text. Every edit_lines call is judged by the Write/Edit guards through the
 route-line-edits.py hook. Only existing UTF-8 text files under the workspace are read or written.

 Exit codes:
   0 = done
   1 = the request could not be carried out (the message says why)

.PARAMETER Setup
 Set this machine up: write the datrix-edit MCP server into <workspace>\.mcp.json with this
 machine's paths (other servers in the file are kept), approve it for this machine in
 .claude\settings.local.json (gitignored), and remove any older local-scope registration that
 would shadow it. Run once on each development machine, then restart Claude Code. Safe to re-run.

.PARAMETER SelfTest
 Run only the self-test: -Setup is required, the server module it registers exists, and this
 wrapper is the template rendered with the module's options.

.EXAMPLE
 .\line-edit.ps1 -Setup
#>
[CmdletBinding()]
param(
 [switch]$Setup, [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.line_edit" -Parameters $PSBoundParameters
exit $LASTEXITCODE
