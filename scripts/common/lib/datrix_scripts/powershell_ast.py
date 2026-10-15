"""Facts about PowerShell scripts, read with PowerShell's own parser.

A ``param()`` block, the commands a script calls and the parameters it passes them are
structure: a regex over ``.ps1`` text misreads comments, here-strings, splatting and line
continuations. ``parse_scripts`` hands every path to ONE ``powershell -NoProfile`` child, which
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
    $fact = [pscustomobject]@{
        path = $path
        parse_errors = @($errors | ForEach-Object { $_.Message })
        parameters = @($parameters)
        commands = @($commands)
        functions = @($functionAsts | ForEach-Object { [string]$_.Name })
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
class ScriptFacts:
    path: Path
    parse_errors: tuple[str, ...]
    parameters: tuple[ScriptParameter, ...]
    commands: tuple[CommandCall, ...]
    #: The names of the functions the script defines, at any depth.
    functions: tuple[str, ...]

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
    return ScriptFacts(
        path=Path(str(entry["path"])),
        parse_errors=tuple(str(message) for message in _as_list(entry.get("parse_errors"))),
        parameters=parameters,
        commands=commands,
        functions=tuple(str(name) for name in _as_list(entry.get("functions"))),
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
