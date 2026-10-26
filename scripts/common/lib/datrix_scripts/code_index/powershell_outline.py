"""What each PowerShell file defines, read with PowerShell's own parser.

``run_outline`` hands many files to ONE PowerShell 7 (``pwsh``) child: the program below reads a JSON
array of ``{path, text}`` on stdin and writes a JSON array on stdout, one entry per input file in the
same order: ``{error, synopsis, symbols}``. Each symbol is ``{name, qualname, kind, line, end_line,
doc}``; a file the parser reports errors for has an error and no symbols. Windows PowerShell 5.1 lacks
the parser APIs' JSON shape, so the child is ``pwsh``.

The program is this module's data, written to a fresh temporary directory for each run (as
``datrix_scripts.powershell_ast`` does), never a script of the scripts tree: every ``.ps1`` there is a
wrapper rendered from the entrypoint template. ``datrix_scripts.code_index.formats`` turns each entry
into the index's file facts.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

POWERSHELL_EXECUTABLE: Final = "pwsh"
FILES_PER_PROCESS: Final = 200
TIMEOUT_SECONDS: Final = 300
PROGRAM_NAME: Final = "powershell-outline.ps1"

_PROGRAM: Final = r"""
$ErrorActionPreference = 'Stop'
$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8

function New-Symbol {
    param(
        [string]$Name,
        [string]$Qualname,
        [string]$Kind,
        [System.Management.Automation.Language.IScriptExtent]$Extent,
        [string]$Doc,
        # The line that names the definition, when it is not the first line of its extent
        # (a parameter's attributes come before its name).
        [int]$NameLine = 0
    )
    [pscustomobject]@{
        name     = $Name
        qualname = $Qualname
        kind     = $Kind
        line     = if ($NameLine -gt 0) { $NameLine } else { $Extent.StartLineNumber }
        end_line = $Extent.EndLineNumber
        doc      = $Doc
    }
}

function Get-ParameterSymbols {
    param(
        [System.Management.Automation.Language.ParameterAst[]]$Parameters,
        [string]$Prefix,
        [System.Management.Automation.Language.CommentHelpInfo]$Help
    )
    foreach ($parameter in $Parameters) {
        $name = $parameter.Name.VariablePath.UserPath
        $doc = ''
        if ($null -ne $Help -and $Help.Parameters.ContainsKey($name.ToUpperInvariant())) {
            $doc = $Help.Parameters[$name.ToUpperInvariant()]
        }
        New-Symbol -Name $name -Qualname "$Prefix$name" -Kind 'parameter' -Extent $parameter.Extent -Doc $doc `
            -NameLine $parameter.Name.Extent.StartLineNumber
    }
}

function Get-FunctionSymbols {
    param([System.Management.Automation.Language.FunctionDefinitionAst]$Function)
    $help = $Function.GetHelpContent()
    $synopsis = if ($null -ne $help) { $help.Synopsis } else { '' }
    New-Symbol -Name $Function.Name -Qualname $Function.Name -Kind 'function' -Extent $Function.Extent -Doc $synopsis
    $parameters = @($Function.Parameters) + @($Function.Body.ParamBlock.Parameters) | Where-Object { $null -ne $_ }
    Get-ParameterSymbols -Parameters $parameters -Prefix "$($Function.Name)." -Help $help
}

function Get-FileOutline {
    param([string]$Path, [string]$Text)
    $tokens = $null
    $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseInput($Text, $Path, [ref]$tokens, [ref]$errors)
    if ($errors.Count -gt 0) {
        $first = $errors[0]
        return [pscustomobject]@{
            error    = "ParseError: line $($first.Extent.StartLineNumber): $($first.Message)"
            synopsis = ''
            symbols  = @()
        }
    }
    $help = $ast.GetHelpContent()
    $symbols = [System.Collections.Generic.List[object]]::new()
    if ($null -ne $ast.ParamBlock) {
        foreach ($symbol in Get-ParameterSymbols -Parameters $ast.ParamBlock.Parameters -Prefix '' -Help $help) {
            $symbols.Add($symbol)
        }
    }
    $isFunction = { param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] }
    foreach ($function in $ast.FindAll($isFunction, $true)) {
        foreach ($symbol in Get-FunctionSymbols -Function $function) {
            $symbols.Add($symbol)
        }
    }
    [pscustomobject]@{
        error    = ''
        synopsis = if ($null -ne $help) { $help.Synopsis } else { '' }
        symbols  = $symbols.ToArray()
    }
}

$files = @([Console]::In.ReadToEnd() | ConvertFrom-Json)
$outlines = foreach ($file in $files) { Get-FileOutline -Path $file.path -Text $file.text }
ConvertTo-Json -InputObject @($outlines) -Depth 5 -Compress
"""


def run_outline(files: Sequence[tuple[str, str]]) -> list[dict[str, object]] | str:
    """The outline of each ``(path, text)``, in order, from one ``pwsh`` child; or the reason none could
    be read (``ToolError: ...``)."""
    executable = shutil.which(POWERSHELL_EXECUTABLE)
    if executable is None:
        return (f"ToolError: PowerShell 7 ('{POWERSHELL_EXECUTABLE}') is not on PATH; install it to index "
                f"PowerShell files.")
    payload = json.dumps([{"path": path, "text": text} for path, text in files])
    with TemporaryDirectory(prefix="ps-outline-") as tmp:
        program = Path(tmp) / PROGRAM_NAME
        program.write_text(_PROGRAM, encoding="utf-8-sig")
        command = [executable, "-NoProfile", "-NonInteractive", "-File", str(program)]
        try:
            result = subprocess.run(command, input=payload.encode("utf-8"), capture_output=True,
                                    timeout=TIMEOUT_SECONDS, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f"ToolError: running {PROGRAM_NAME} failed: {exc}"
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        return f"ToolError: {PROGRAM_NAME} exited {result.returncode}: {detail}"
    outlines = json.loads(result.stdout.decode("utf-8-sig"))
    if not isinstance(outlines, list) or len(outlines) != len(files):
        return f"ToolError: {PROGRAM_NAME} returned {outlines!r} for {len(files)} files"
    return outlines
