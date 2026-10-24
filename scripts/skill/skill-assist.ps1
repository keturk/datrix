#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Skill assists: the mechanical phases of agent skills, done by scripts and local models.

.DESCRIPTION
 The behaviour is datrix_scripts.skill.skill_assist, which runs one command of the assists' command
 line (datrix_scripts.skill.assist_cli) in-process. Each command takes over one phase a skill used to
 spend a Claude model on, and writes its output under <workspace>\.tmp\assist\, printing the path and a
 one-line summary. Exact checks are exact; anything a local model wrote is checked against its inputs
 (citations, quotes, set comparisons) and marked as a lead. A verdict is never delegated: the skill
 still decides.

   context-digest     --phase N                  shared-context digest for a phase's implementers
   readiness          --phase N [--no-model]     readiness-audit evidence (missing edges, stale names,
                                                 already-satisfied leads)
   findings-index     [--dir D]                  atomic-finding index of the findings inbox
   findings-check     --delete F... [--dir D]    would deleting F lose a citation or leave a dangling
                      [--keep-raw]               Related pointer? (--keep-raw: raw files may remain)
   findings-redundant [--dir D] [--no-model]     findings files another file already covers: plan JSON +
                                                 review view (model verdict on exact candidates, checked)
   findings-redundant-delete [--plan P] [--dir D] delete the plan's proposals still marked delete, when every
                                                 proof holds
   findings-plan      [--dir D] [--no-model]     theme plan for the findings inbox: plan JSON + review view
   findings-assemble  [--plan P] [--apply]       write the theme files from the plan, carrying every unit
                                                 verbatim; --apply writes, checks, deletes the sources
   finding-select     [--count N] [--dir D]      the first N findings files by name (/implement-finding)
   finding-close      --finding F                delete F unless another findings file names it;
                      [--session-log L]          with L (a step's .stream.jsonl), also unless its
                                                 last test.ps1 run failed or it ran none
   checklist          --design PATH              conformance checklist draft for a design
   absorb-transfer    --design PATH --target T.. is each design section present in the target docs?
   absorb-references  --design PATH [--also P..] every line that still names the design
   absorb-delete      --design PATH              delete the design when its deletion licence holds
                      [--verified V |            (V ends PROVEN and names it; else its Status reads
                       --knowledge-only]         Implemented) and no line names it
                      [--also P..]
   bug-resolution     --report R --repo P.. ...  the Resolution section for a fixed bug report
   design-inventory   [--dir D] [--design-dir DD] registered targets, existing designs, numbering and the
                                                 unconverted consolidated sections (/consolidate-to-design)
   design-verify      [--dir D] [--no-model]     does each consolidated defect still hold? (model leads)
   design-plan        [--dir D] [--design-dir DD] fix shapes for the consolidated sections: plan JSON +
                      [--no-model]               review view
   design-check       [--design-dir DD]          is the design folder well formed (size, order, references,
                                                 guideline answers, target consistency)?
   design-xref        [--design-dir DD]          cross-design index: decision references, name allocations
                                                 and every design naming each name (/verify-design)
   design-close       --finding F.. [--fixed ID..] delete converted consolidated files when the designs pass
                      [--apply]                  and carry every cited file
   rule-names         --site PATH:LINE.. [--sites-file F]  names for unnamed validate rules (model leads,
                      [--apply]                  checked; --apply writes the names that passed)

 Lines carrying a registered customer term are withheld before anything is sent to a model, and
 without the term corpus nothing is sent.

 Exit codes:
   0 = done (or a passing -SelfTest)
   1 = the request could not be carried out (the message says what to pass instead), or a self-test
       check failed
   2 = the check found something the skill must act on, or a command line the wrapper cannot read
   3 = no local model answered: the skill does this phase itself, as it did before the assist

.PARAMETER Command
 The assist to run (see the list above).

.PARAMETER Arguments
 The command's own arguments, passed through (python style: --phase 12).

.PARAMETER LocalMachines
 Machines to search for model servers, in preference order. Omit for the default list in
 common/lib/datrix_scripts/local_llm.py.

.PARAMETER LlmModel
 Models to use, best first. Omit and readiness, findings-redundant, findings-plan, absorb-transfer,
 bug-resolution and design-plan use nemotron-3-super:120b, then
 qwen3-coder:30b-ctx32k (QUALITY_MODEL_PREFERENCE in local_llm.py): they wait for the most
 capable machine. The other model commands use any model already in memory.

.PARAMETER LlmTimeout
 Request timeout in seconds. Default: 600.

.PARAMETER SelfTest
 Run only the module's self-test (the wrapper commands are exactly the assist commands, the model
 commands get the local-model flags, the command-line cases) and the wrapper seam checks.

.EXAMPLE
 .\skill\skill-assist.ps1 context-digest --phase 12

.EXAMPLE
 .\skill\skill-assist.ps1 checklist --design "D:\datrix\design\<the design file>.md"

.EXAMPLE
 .\skill\skill-assist.ps1 findings-check --delete 20261005-002142-x.md 20261005-002143-y.md
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Position=0, Mandatory=$true, ParameterSetName="Run")]
 [ValidateSet("context-digest", "readiness", "findings-index", "findings-check", "findings-redundant",
  "findings-redundant-delete", "findings-plan", "findings-assemble", "finding-select", "finding-close",
  "checklist", "absorb-transfer", "absorb-references", "absorb-delete", "bug-resolution", "design-inventory",
  "design-verify", "design-plan", "design-check", "design-xref", "design-close", "rule-names")]
 [string]$Command,

 [Parameter(Position=1, ValueFromRemainingArguments=$true, ParameterSetName="Run")]
 [string[]]$Arguments,

 [Parameter(ParameterSetName="Run")][string[]]$LocalMachines,
 [Parameter(ParameterSetName="Run")][string[]]$LlmModel,
 [Parameter(ParameterSetName="Run")][int]$LlmTimeout,

 [Parameter(Mandatory=$true, ParameterSetName="SelfTest")]
 [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.skill.skill_assist" -Parameters $PSBoundParameters
exit $LASTEXITCODE
