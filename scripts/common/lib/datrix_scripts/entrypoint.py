"""The seam between a wrapper rendered from ``common/templates/entrypoint.ps1`` and its module.

A wrapper is the template with two substitutions -- its parameter block (the comment-based help and
``param()``, which replace the template's ``# {{PARAMETER_BLOCK}}`` line) and its module (which
replaces ``{{MODULE}}``) -- and ``Invoke-DatrixEntrypoint`` (``common/DatrixPythonScript.psm1``)
passes each bound parameter to the module as ``--kebab-name``. Its POSIX twin, the ``.sh`` beside it,
is ``common/templates/entrypoint.sh`` with the module substituted. Two facts hold the seam, and a
module that has a wrapper checks both in its ``--self-test`` (``wrapper_problems``):

* the wrapper and its twin are the templates rendered: text equal after substitution
  (``rendering_problems``);
* the wrapper's parameters and the module's options are one set: every parameter's flag is an
  option of the module's parser and every option is a parameter (``flag_problems``), so a
  parameter renamed on one side fails the self-test instead of a user's run.

A module that names its wrapper in a message (a repair, a usage hint) words it with
``wrapper_command``: the ``.ps1`` and its PowerShell parameters on Windows, the ``.sh`` twin and the
module's own flags elsewhere, so the command printed is one the reader's shell runs.
"""

from __future__ import annotations

import argparse
import os
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Final

from datrix_scripts.paths import SCRIPTS_DIR
from datrix_scripts.powershell_ast import parse_scripts

TEMPLATES_DIR: Final[Path] = SCRIPTS_DIR / "common" / "templates"
PS1_TEMPLATE: Final[Path] = TEMPLATES_DIR / "entrypoint.ps1"
SH_TEMPLATE: Final[Path] = TEMPLATES_DIR / "entrypoint.sh"
PARAMETER_BLOCK_LINE: Final = "# {{PARAMETER_BLOCK}}\n"
MODULE_PLACEHOLDER: Final = "{{MODULE}}"
#: The first template line after the parameter block; a wrapper's block ends where it starts.
RENDERED_MARKER: Final = "# Rendered from scripts/common/templates/entrypoint.ps1"
SH_SUFFIX: Final = ".sh"
PS1_SUFFIX: Final = ".ps1"
#: The rule ``ConvertTo-DatrixEntrypointArgument`` (``common/DatrixPythonScript.psm1``) applies:
#: SelfTest -> self-test, IPAddress -> ip-address.
_KEBAB_BOUNDARY: Final = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_HELP_FLAG: Final = "--help"
_LONG_OPTION_PREFIX: Final = "--"
_PS_PARAMETER_PREFIX: Final = "-"
_WINDOWS: Final = os.name == "nt"


def kebab_flag(parameter: str) -> str:
    """The flag a wrapper parameter is passed as: ``SkipIfInstalled`` -> ``--skip-if-installed``."""
    return _LONG_OPTION_PREFIX + _KEBAB_BOUNDARY.sub("-", parameter).lower()


def wrapper_flag(parameter: str, *, windows: bool = _WINDOWS) -> str:
    """How a reader types wrapper *parameter* in this platform's wrapper: ``-SkipIfInstalled`` to
    the ``.ps1`` on Windows, ``--skip-if-installed`` to the ``.sh`` twin elsewhere."""
    return _PS_PARAMETER_PREFIX + parameter if windows else kebab_flag(parameter)


def wrapper_command(wrapper: str, *parameters: str, windows: bool = _WINDOWS) -> str:
    """The command that runs a rendered wrapper with *parameters* on this platform, for a message.

    *wrapper* is the wrapper's path without its suffix, ``/``-separated (``common/venv``), and
    *parameters* are its parameter names: ``common\\venv.ps1 -Ensure -EnsurePackages`` on Windows,
    ``common/venv.sh --ensure --ensure-packages`` elsewhere.
    """
    script = wrapper.replace("/", "\\") + PS1_SUFFIX if windows else wrapper + SH_SUFFIX
    return " ".join([script, *(wrapper_flag(name, windows=windows) for name in parameters)])


def render_ps1(parameter_block: str, module: str, template: str) -> str:
    """The wrapper text for *parameter_block* and *module* from the ``.ps1`` *template* text."""
    if PARAMETER_BLOCK_LINE not in template or MODULE_PLACEHOLDER not in template:
        raise ValueError(
            f"The wrapper template lacks {PARAMETER_BLOCK_LINE.strip()!r} or {MODULE_PLACEHOLDER!r}. "
            f"Expected both in {PS1_TEMPLATE}; restore them."
        )
    return template.replace(PARAMETER_BLOCK_LINE, parameter_block).replace(MODULE_PLACEHOLDER, module)


def render_sh(module: str, template: str) -> str:
    """The POSIX twin's text for *module* from the ``.sh`` *template* text."""
    if MODULE_PLACEHOLDER not in template:
        raise ValueError(f"The POSIX wrapper template lacks {MODULE_PLACEHOLDER!r}. Expected it in {SH_TEMPLATE}; restore it.")
    return template.replace(MODULE_PLACEHOLDER, module)


def parameter_block(wrapper_text: str) -> str | None:
    """The wrapper's own lines: from its second line up to the rendered marker. None without one."""
    first_line_end = wrapper_text.find("\n") + 1
    marker = wrapper_text.find(RENDERED_MARKER)
    if first_line_end == 0 or marker < first_line_end:
        return None
    return wrapper_text[first_line_end:marker]


def rendered_module(wrapper_text: str, template: str) -> str | None:
    """The module a wrapper rendered from *template* runs: what its copy of the template's
    ``{{MODULE}}`` line holds in that placeholder's place. None when no line of the wrapper has that shape."""
    module_line = next((line for line in template.splitlines() if MODULE_PLACEHOLDER in line), None)
    if module_line is None:
        raise ValueError(f"The wrapper template lacks {MODULE_PLACEHOLDER!r}. Expected it in {PS1_TEMPLATE}; restore it.")
    prefix, suffix = module_line.split(MODULE_PLACEHOLDER, 1)
    for line in wrapper_text.splitlines():
        if len(line) > len(prefix) + len(suffix) and line.startswith(prefix) and line.endswith(suffix):
            return line[len(prefix):len(line) - len(suffix)]
    return None


def _first_difference(actual: str, expected: str) -> str:
    for number, (got, want) in enumerate(zip(actual.splitlines(), expected.splitlines()), start=1):
        if got != want:
            return f"line {number} is {got!r}, the template renders {want!r}"
    return f"it has {len(actual.splitlines())} line(s), the template renders {len(expected.splitlines())}"


def ps1_rendering_problems(wrapper_text: str, module: str, ps1_template: str) -> list[str]:
    """Why *wrapper_text* is not the ``.ps1`` template rendered for *module*; empty when it is."""
    block = parameter_block(wrapper_text)
    if block is None:
        return [f"the wrapper has no {RENDERED_MARKER!r} line, so it was not rendered from the template"]
    expected = render_ps1(block, module, ps1_template)
    if wrapper_text != expected:
        return [f"the wrapper is not the template rendered for {module}: {_first_difference(wrapper_text, expected)}"]
    return []


def twin_rendering_problems(twin_text: str | None, module: str, sh_template: str) -> list[str]:
    """Why *twin_text* (None: no twin) is not the ``.sh`` template rendered for *module*; empty when it is."""
    if twin_text is None:
        return [f"the wrapper has no {SH_SUFFIX} twin"]
    expected = render_sh(module, sh_template)
    if twin_text != expected:
        return [f"the {SH_SUFFIX} twin is not the template rendered for {module}: {_first_difference(twin_text, expected)}"]
    return []


def text_rendering_problems(
    wrapper_text: str, twin_text: str | None, module: str, ps1_template: str, sh_template: str
) -> list[str]:
    """Why *wrapper_text* and *twin_text* are not the templates rendered for *module*; empty when they are."""
    return [
        *ps1_rendering_problems(wrapper_text, module, ps1_template),
        *twin_rendering_problems(twin_text, module, sh_template),
    ]


def rendering_problems(wrapper: Path, module: str) -> list[str]:
    """Why *wrapper* (and its ``.sh`` twin) is not the templates rendered for *module*; empty when it is."""
    twin = wrapper.with_suffix(SH_SUFFIX)
    twin_text = twin.read_text(encoding="utf-8") if twin.is_file() else None
    return text_rendering_problems(
        wrapper.read_text(encoding="utf-8-sig"),
        twin_text,
        module,
        PS1_TEMPLATE.read_text(encoding="utf-8"),
        SH_TEMPLATE.read_text(encoding="utf-8"),
    )


def parser_flags(parser: argparse.ArgumentParser) -> frozenset[str]:
    """The long option of every optional argument of *parser*, ``--help`` excluded."""
    flags: set[str] = set()
    for action in parser._actions:
        flags.update(option for option in action.option_strings if option.startswith(_LONG_OPTION_PREFIX))
    return frozenset(flags - {_HELP_FLAG})


def flag_problems(parameters: Iterable[str], parser: argparse.ArgumentParser) -> list[str]:
    """Why the wrapper *parameters* and *parser*'s options are not one set; empty when they are."""
    passed = {kebab_flag(name): name for name in parameters}
    accepted = parser_flags(parser)
    problems = [
        f"the wrapper parameter -{name} is passed as {flag}, which the module does not accept"
        for flag, name in sorted(passed.items()) if flag not in accepted
    ]
    problems.extend(
        f"the module option {flag} has no wrapper parameter, so the wrapper can never pass it"
        for flag in sorted(accepted - set(passed))
    )
    return problems


def wrapper_problems(wrapper: Path, module: str, parser: argparse.ArgumentParser) -> list[str]:
    """Both seam facts for *wrapper*: rendered from the templates, and its parameters equal *parser*'s options.

    Raises:
        PowerShellParseError: PowerShell could not parse the wrapper (the check fails closed).
    """
    facts = parse_scripts([wrapper])[wrapper.resolve()]
    problems = [f"PowerShell cannot parse it: {message}" for message in facts.parse_errors]
    problems.extend(rendering_problems(wrapper, module))
    problems.extend(flag_problems((parameter.name for parameter in facts.parameters), parser))
    return [f"{wrapper.name}: {problem}" for problem in problems]


def self_test_problems() -> list[str]:
    """The seam checks proven on planted wrappers: each finds the drift planted for it, and none
    reports a sound rendering. Returns the failures; empty when every case holds."""
    failures: list[str] = []
    for parameter, flag in (("SelfTest", "--self-test"), ("IPAddress", "--ip-address"), ("Dbg", "--dbg"), ("NoDev", "--no-dev")):
        if kebab_flag(parameter) != flag:
            failures.append(f"kebab_flag({parameter!r}) is {kebab_flag(parameter)!r}, expected {flag!r}")
    for windows, command in ((True, "common\\venv.ps1 -Ensure -EnsurePackages"), (False, "common/venv.sh --ensure --ensure-packages")):
        worded = wrapper_command("common/venv", "Ensure", "EnsurePackages", windows=windows)
        if worded != command:
            failures.append(f"wrapper_command(windows={windows}) is {worded!r}, expected {command!r}")
    ps1_template = PS1_TEMPLATE.read_text(encoding="utf-8")
    sh_template = SH_TEMPLATE.read_text(encoding="utf-8")
    block = "<#\n.SYNOPSIS\n Planted.\n#>\n[CmdletBinding()]\nparam([switch]$SelfTest)\n"
    module = "datrix_scripts.planted"
    sound = render_ps1(block, module, ps1_template)
    twin = render_sh(module, sh_template)
    cases = (
        ("a sound rendering", sound, twin, False),
        ("an edited template line", sound.replace("exit $LASTEXITCODE", "exit 0"), twin, True),
        ("another module", sound, render_sh("datrix_scripts.other", sh_template), True),
        ("a missing twin", sound, None, True),
        ("no rendered marker", block, twin, True),
    )
    if rendered_module(sound, ps1_template) != module or rendered_module(block, ps1_template) is not None:
        failures.append(f"rendered_module did not read {module!r} from a sound rendering, or read one from no rendering")
    for label, wrapper_text, twin_text, drifts in cases:
        found = bool(text_rendering_problems(wrapper_text, twin_text, module, ps1_template, sh_template))
        if found != drifts:
            failures.append(f"rendering check on {label}: reported drift={found}, expected {drifts}")
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    if flag_problems(["SelfTest"], parser):
        failures.append(f"flag check reported drift on matching sets: {flag_problems(['SelfTest'], parser)}")
    if len(flag_problems(["SelfTest", "Extra"], parser)) != 1 or len(flag_problems([], parser)) != 1:
        failures.append("flag check missed a parameter the module lacks or an option the wrapper lacks")
    return failures
