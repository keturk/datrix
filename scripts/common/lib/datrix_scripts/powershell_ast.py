"""Facts about PowerShell scripts, read with PowerShell's own parser.

A ``param()`` block, the commands a script calls and the parameters it passes them, and which
variables a flow-control statement assigns and which ``+=`` grows, are structure: a regex over ``.ps1`` text misreads comments, here-strings, splatting and line
continuations. So is how many lines hold code rather than comments, read from the parser's tokens. ``parse_scripts`` hands every path to ONE ``powershell -NoProfile`` child, which
parses each file with ``[System.Management.Automation.Language.Parser]::ParseFile`` and prints
one compact JSON line per script; one child per call keeps a census over hundreds of scripts to
one process start. Every value handed to ``ConvertTo-Json`` is a plain string or array: a line
read by ``Get-Content`` carries provider note properties that serialize as the whole provider
object graph.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

POWERSHELL_EXE: Final = "powershell"
_TIMEOUT_SECONDS: Final = 600
_LIST_FILE: Final = "paths.txt"
_PROGRAM_FILE: Final = "ast-facts.ps1"

_PROGRAM: Final = r"""
param([Parameter(Mandatory)][string]$ListPath)
$ErrorActionPreference = 'Stop'
$language = [System.Management.Automation.Language.Parser]
$paths = @(Get-Content -LiteralPath $ListPath -Encoding UTF8 | Where-Object { $_ } | ForEach-Object { [string]$_ })
foreach ($path in $paths) {
    $tokens = $null
    $errors = $null
    $ast = $language::ParseFile($path, [ref]$tokens, [ref]$errors)
    $parameters = @()
    if ($ast.ParamBlock) {
        foreach ($parameter in $ast.ParamBlock.Parameters) {
            $aliases = @()
            foreach ($attribute in $parameter.Attributes) {
                if ($attribute.TypeName.Name -eq 'Alias') {
                    foreach ($argument in $attribute.PositionalArguments) {
                        $aliases += [string]$argument.SafeGetValue()
                    }
                }
            }
            $parameters += [pscustomobject]@{
                name = $parameter.Name.VariablePath.UserPath
                aliases = @($aliases)
            }
        }
    }
    $commandAsts = $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.CommandAst] }, $true)
    $seen = @{}
    $commands = New-Object System.Collections.ArrayList
    foreach ($command in $commandAsts) {
        $name = [string]$command.GetCommandName()
        $passed = @(foreach ($element in $command.CommandElements) {
            if ($element -is [System.Management.Automation.Language.CommandParameterAst]) { $element.ParameterName }
        })
        $key = $name + '|' + ($passed -join ',')
        if (-not $seen.ContainsKey($key)) {
            $seen[$key] = $true
            [void]$commands.Add([pscustomobject]@{ name = $name; parameters = @($passed) })
        }
    }
    $functionAsts = $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)
    $assignmentAsts = $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.AssignmentStatementAst] }, $true)
    $statementAssignments = New-Object System.Collections.ArrayList
    $appended = New-Object System.Collections.ArrayList
    foreach ($assignment in $assignmentAsts) {
        if ($assignment.Left -isnot [System.Management.Automation.Language.VariableExpressionAst]) { continue }
        $variable = [string]$assignment.Left.VariablePath.UserPath
        $operator = [string]$assignment.Operator
        $right = $assignment.Right
        if ($operator -eq 'PlusEquals') {
            [void]$appended.Add($variable)
        } elseif ($operator -eq 'Equals' -and (
            $right -is [System.Management.Automation.Language.IfStatementAst] -or
            $right -is [System.Management.Automation.Language.LabeledStatementAst] -or
            $right -is [System.Management.Automation.Language.TryStatementAst])) {
            [void]$statementAssignments.Add([pscustomobject]@{
                variable = $variable
                line = [int]$assignment.Extent.StartLineNumber
                statement = [string]$right.GetType().Name
            })
        }
    }
    $expandableAsts = $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.ExpandableStringExpressionAst] }, $true)
    $codeLines = @{}
    foreach ($token in $tokens) {
        if (@('Comment', 'NewLine', 'LineContinuation', 'EndOfInput') -contains [string]$token.Kind) { continue }
        for ($line = $token.Extent.StartLineNumber; $line -le $token.Extent.EndLineNumber; $line++) { $codeLines[$line] = $true }
    }
    $fact = [pscustomobject]@{
        path = $path
        parse_errors = @($errors | ForEach-Object { $_.Message })
        parameters = @($parameters)
        commands = @($commands)
        functions = @($functionAsts | ForEach-Object { [string]$_.Name })
        statement_assignments = @($statementAssignments)
        appended_variables = @($appended)
        expandable_strings = @($expandableAsts | ForEach-Object { [string]$_.Extent.Text })
        code_lines = [int]$codeLines.Count
    }
    [Console]::Out.WriteLine((ConvertTo-Json -InputObject $fact -Depth 5 -Compress))
}
"""


@dataclass(frozen=True)
class ScriptParameter:
    name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class CommandCall:
    """One command invocation: the command's name and the ``-Parameter`` names passed to it."""

    name: str
    parameters: tuple[str, ...]


@dataclass(frozen=True)
class StatementAssignment:
    """``$variable = <if | switch | loop | try statement>``: the value is the statement's pipeline
    output, which PowerShell unrolls, so one emitted element binds a scalar rather than an array."""

    variable: str
    line: int
    #: The parser's node type of the right-hand side (``IfStatementAst``, ``SwitchStatementAst``, ...).
    statement: str


@dataclass(frozen=True)
class ScriptFacts:
    path: Path
    parse_errors: tuple[str, ...]
    parameters: tuple[ScriptParameter, ...]
    commands: tuple[CommandCall, ...]
    #: The names of the functions the script defines, at any depth.
    functions: tuple[str, ...]
    #: Every plain ``=`` whose right-hand side is a flow-control statement, at any depth.
    statement_assignments: tuple[StatementAssignment, ...]
    #: The variable of every ``+=``, at any depth (repeats kept).
    appended_variables: tuple[str, ...]
    #: The source text of every expandable (interpolating, double-quoted) string, at any depth.
    expandable_strings: tuple[str, ...]
    #: How many lines carry a token other than a comment: blank lines, comment lines and the
    #: comment-based help block do not count; a token spanning lines (a here-string) counts each.
    code_lines: int

    def unrolled_then_appended(self) -> list[StatementAssignment]:
        """The statement assignments whose variable the script also grows with ``+=``: when the
        statement emits one element the variable holds a scalar, and ``+=`` concatenates onto it
        instead of appending. Variable names compare case-insensitively, as PowerShell does."""
        appended = {variable.lower() for variable in self.appended_variables}
        return [
            assignment for assignment in self.statement_assignments
            if assignment.variable.lower() in appended
        ]

    def defines(self, function: str) -> bool:
        """True when the script defines a function named ``function``, case-insensitively."""
        wanted = function.lower()
        return any(name.lower() == wanted for name in self.functions)

    def declares(self, name: str) -> bool:
        """True when the ``param()`` block declares ``name`` (or an alias of it), case-insensitively."""
        wanted = name.lower()
        return any(
            parameter.name.lower() == wanted or wanted in (alias.lower() for alias in parameter.aliases)
            for parameter in self.parameters
        )

    def calls(self, command: str) -> list[CommandCall]:
        wanted = command.lower()
        return [call for call in self.commands if call.name.lower() == wanted]


class PowerShellParseError(RuntimeError):
    """The PowerShell child could not report facts for the given scripts."""


def _as_list(value: object) -> list[object]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _facts(entry: dict[str, object]) -> ScriptFacts:
    parameters = tuple(
        ScriptParameter(
            name=str(item["name"]),
            aliases=tuple(str(alias) for alias in _as_list(item.get("aliases"))),
        )
        for item in _as_list(entry.get("parameters"))
        if isinstance(item, dict)
    )
    commands = tuple(
        CommandCall(
            name=str(item.get("name") or ""),
            parameters=tuple(str(name) for name in _as_list(item.get("parameters"))),
        )
        for item in _as_list(entry.get("commands"))
        if isinstance(item, dict)
    )
    statement_assignments = tuple(
        StatementAssignment(
            variable=str(item["variable"]),
            line=int(str(item["line"])),
            statement=str(item["statement"]),
        )
        for item in _as_list(entry.get("statement_assignments"))
        if isinstance(item, dict)
    )
    return ScriptFacts(
        path=Path(str(entry["path"])),
        parse_errors=tuple(str(message) for message in _as_list(entry.get("parse_errors"))),
        parameters=parameters,
        commands=commands,
        functions=tuple(str(name) for name in _as_list(entry.get("functions"))),
        statement_assignments=statement_assignments,
        appended_variables=tuple(str(name) for name in _as_list(entry.get("appended_variables"))),
        expandable_strings=tuple(str(text) for text in _as_list(entry.get("expandable_strings"))),
        code_lines=int(str(entry["code_lines"])),
    )


def parse_scripts(paths: Sequence[Path]) -> dict[Path, ScriptFacts]:
    """Parse every script in ``paths`` in one PowerShell child; keyed by the resolved path.

    Raises:
        PowerShellParseError: PowerShell is not on PATH, the child failed, or its output is not
            the expected JSON -- the census then fails closed rather than reading nothing.
    """
    if not paths:
        return {}
    resolved = [path.resolve() for path in paths]
    with TemporaryDirectory(prefix="ps-ast-") as tmp:
        list_path = Path(tmp) / _LIST_FILE
        program_path = Path(tmp) / _PROGRAM_FILE
        list_path.write_text("\n".join(str(path) for path in resolved) + "\n", encoding="utf-8")
        program_path.write_text(_PROGRAM, encoding="utf-8-sig")
        command = [
            POWERSHELL_EXE, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(program_path), "-ListPath", str(list_path),
        ]
        try:
            completed = subprocess.run(
                command, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=_TIMEOUT_SECONDS, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PowerShellParseError(
                f"could not run {POWERSHELL_EXE} to parse {len(resolved)} script(s): {exc}. "
                "Expected Windows PowerShell on PATH."
            ) from exc
    if completed.returncode != 0:
        raise PowerShellParseError(
            f"{POWERSHELL_EXE} exited {completed.returncode} parsing {len(resolved)} script(s): "
            f"{completed.stderr.strip()[:2000]}"
        )
    facts: list[ScriptFacts] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PowerShellParseError(
                f"{POWERSHELL_EXE} printed a line that is not JSON: {exc}; line began {line[:300]!r}"
            ) from exc
        if isinstance(entry, dict):
            facts.append(_facts(entry))
    by_path = {fact.path.resolve(): fact for fact in facts}
    missing = [str(path) for path in resolved if path not in by_path]
    if missing:
        raise PowerShellParseError(
            f"{POWERSHELL_EXE} reported no facts for {len(missing)} script(s): {missing[:5]}"
        )
    return by_path
