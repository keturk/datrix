"""Thin-entrypoint gate: every ``.ps1`` under ``datrix/scripts`` is a thin wrapper rendered from the template.

A script's behaviour lives in a ``datrix_scripts`` module; its ``.ps1`` is ``common/templates/entrypoint.ps1``
rendered with its parameter block and module, beside a ``.sh`` twin rendered from
``common/templates/entrypoint.sh``. Four rules over every ``.ps1`` below ``scripts/`` (the template itself
excepted), read with PowerShell's own parser (``datrix_scripts.powershell_ast``) and the rendering seam
(``datrix_scripts.entrypoint``), each a hard zero with no baseline:

1. ``code-lines`` -- at most ``MAX_WRAPPER_CODE_LINES`` lines carry a token other than a comment. The
   comment-based help is the wrapper's documentation and does not count; the ``param()`` block and the
   template's lines do.
2. ``not-rendered`` -- the wrapper (and its twin, when there is one) is the template rendered: equal text
   after substituting its parameter block and the module it runs. A byte-order mark is a difference (the
   template has none, and one before ``#!`` breaks the shebang). Line endings are the checkout's (``.ps1``
   is ``eol=crlf`` in the working tree, LF in the index); the line-ending gate holds them.
3. ``missing-twin`` -- a ``.sh`` twin sits beside the wrapper.
4. ``parse-error`` -- PowerShell parses the wrapper, so the line count above is read from a sound token stream.

Run it through ``gates/repo-hygiene/thin-entrypoint-gate.ps1`` or its ``.sh`` twin; it runs in gate mode
(``datrix_scripts.gate_log.run_as_gate``) and prints the
``[GATE] thin-entrypoint PASSED|FAILED exit=<n> log=<path>`` verdict last.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from datrix_scripts.entrypoint import (
    PS1_SUFFIX,
    PS1_TEMPLATE,
    SH_SUFFIX,
    SH_TEMPLATE,
    ps1_rendering_problems,
    render_ps1,
    render_sh,
    rendered_module,
    twin_rendering_problems,
)
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, NamedCheck, check_list_main, check_list_parser, write_files
from datrix_scripts.gate_log import run_as_gate
from datrix_scripts.paths import SCRIPTS_DIR
from datrix_scripts.powershell_ast import parse_scripts
from datrix_scripts.test import wrappers

GATE: Final = "thin-entrypoint"
MODULE: Final = "datrix_scripts.gates.repo_hygiene.thin_entrypoint_gate"
WRAPPER: Final = "thin-entrypoint-gate"

#: The most lines of code (comment-based help excluded) a wrapper may hold.
MAX_WRAPPER_CODE_LINES: Final = 40
#: The templates, relative to the scripts tree: the ``.ps1`` one is no wrapper, and both are what a wrapper renders.
PS1_TEMPLATE_PATH: Final = PS1_TEMPLATE.relative_to(SCRIPTS_DIR)
SH_TEMPLATE_PATH: Final = SH_TEMPLATE.relative_to(SCRIPTS_DIR)
_SKIP_DIRS: Final = frozenset({"__pycache__", ".pytest_cache", "node_modules"})
#: Plain UTF-8 for the wrappers too: ``utf-8-sig`` would drop a byte-order mark the template does not carry.
_ENCODING: Final = "utf-8"
_BYTE_ORDER_MARK: Final = "﻿"


class Rule(StrEnum):
    CODE_LINES = "code-lines"
    NOT_RENDERED = "not-rendered"
    MISSING_TWIN = "missing-twin"
    PARSE_ERROR = "parse-error"


@dataclass(frozen=True)
class Hit:
    rule: Rule
    location: str
    detail: str

    def render(self) -> str:
        return f"[{self.rule}] {self.location}: {self.detail}"


def wrappers_under(scripts_dir: Path) -> list[Path]:
    """Every ``.ps1`` below *scripts_dir*, the ``.ps1`` template excepted, sorted."""
    template = (scripts_dir / PS1_TEMPLATE_PATH).resolve()
    return sorted(
        path for path in scripts_dir.rglob(f"*{PS1_SUFFIX}")
        if not _SKIP_DIRS.intersection(path.relative_to(scripts_dir).parts) and path.resolve() != template
    )


def _rendering_hits(wrapper: Path, location: str, ps1_template: str, sh_template: str) -> list[Hit]:
    twin = wrapper.with_suffix(SH_SUFFIX)
    twin_text = twin.read_text(encoding=_ENCODING) if twin.is_file() else None
    hits: list[Hit] = []
    if twin_text is None:
        hits.append(Hit(Rule.MISSING_TWIN, location, f"no {twin.name} beside it; render one from {SH_TEMPLATE_PATH.as_posix()}"))
    wrapper_text = wrapper.read_text(encoding=_ENCODING)
    module = rendered_module(wrapper_text, ps1_template)
    if module is None:
        detail = (f"no line runs a module as {PS1_TEMPLATE_PATH.as_posix()} does; move the behaviour into a "
                  "datrix_scripts module and render the wrapper from the template")
        return [*hits, Hit(Rule.NOT_RENDERED, location, detail)]
    problems = ps1_rendering_problems(wrapper_text, module, ps1_template)
    if twin_text is not None:
        problems.extend(twin_rendering_problems(twin_text, module, sh_template))
    return [*hits, *(Hit(Rule.NOT_RENDERED, location, problem) for problem in problems)]


def thin_entrypoint_hits(scripts_dir: Path) -> list[Hit]:
    """Every rule's hits over the wrappers below *scripts_dir*, rendered against the templates in it.

    Raises:
        PowerShellParseError: PowerShell could not report facts for the wrappers (the gate fails closed).
    """
    ps1_template = (scripts_dir / PS1_TEMPLATE_PATH).read_text(encoding=_ENCODING)
    sh_template = (scripts_dir / SH_TEMPLATE_PATH).read_text(encoding=_ENCODING)
    found = wrappers_under(scripts_dir)
    facts = parse_scripts(found)
    hits: list[Hit] = []
    for wrapper in found:
        location = wrapper.relative_to(scripts_dir).as_posix()
        fact = facts[wrapper.resolve()]
        hits.extend(Hit(Rule.PARSE_ERROR, location, message) for message in fact.parse_errors)
        if fact.code_lines > MAX_WRAPPER_CODE_LINES:
            detail = (f"{fact.code_lines} lines of code, at most {MAX_WRAPPER_CODE_LINES} allowed (comment-based "
                      "help does not count); move the logic into its datrix_scripts module")
            hits.append(Hit(Rule.CODE_LINES, location, detail))
        hits.extend(_rendering_hits(wrapper, location, ps1_template, sh_template))
    return hits


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

_PLANTED_MODULE: Final = "datrix_scripts.planted"
#: Lines of a wrapper whose ``param()`` block declares no parameter that carry code besides that block's.
_FRAME_BLOCK: Final = "[CmdletBinding()]\nparam(\n)\n"
#: Help long enough that the wrapper has more physical lines than the limit, though few lines of code.
_HELP_HEAVY_BLOCK: Final = (
    "<#\n.SYNOPSIS\n Planted.\n"
    + "".join(f"\n.PARAMETER P{number}\n Switch {number}.\n" for number in range(MAX_WRAPPER_CODE_LINES))
    + "#>\n[CmdletBinding()]\nparam([switch]$SelfTest)\n"
)
_HANDMADE: Final = "[CmdletBinding()]\nparam([switch]$SelfTest)\nWrite-Output 'behaviour in the wrapper'\n"


def _switches_block(count: int) -> str:
    return "[CmdletBinding()]\nparam(\n" + "".join(f" [switch]$P{number},\n" for number in range(count)) + " [switch]$Last\n)\n"


def _templates() -> tuple[str, str]:
    return PS1_TEMPLATE.read_text(encoding=_ENCODING), SH_TEMPLATE.read_text(encoding=_ENCODING)


def _rendered_pair(name: str, block: str, ps1_template: str, sh_template: str) -> dict[str, str]:
    return {f"{name}{PS1_SUFFIX}": render_ps1(block, _PLANTED_MODULE, ps1_template),
            f"{name}{SH_SUFFIX}": render_sh(_PLANTED_MODULE, sh_template)}


def _frame_code_lines(root: Path, ps1_template: str) -> int:
    """The code lines of a rendered wrapper declaring no parameter, as the parser counts them."""
    frame = write_files(root / "frame", {f"frame{PS1_SUFFIX}": render_ps1(_FRAME_BLOCK, _PLANTED_MODULE, ps1_template)})[0]
    return parse_scripts([frame])[frame.resolve()].code_lines


def _planted_tree(root: Path, *, defects: bool) -> Path:
    """A scripts tree holding both templates and sound wrappers (a help-heavy one, one at the limit); with
    *defects*, one wrapper over the limit, a hand-written one, one without a twin, one with a drifted twin and
    one whose rendering is preceded by a byte-order mark."""
    ps1_template, sh_template = _templates()
    # _switches_block(n) holds the frame's code lines, n switch lines and the last parameter's line.
    at_limit = MAX_WRAPPER_CODE_LINES - _frame_code_lines(root, ps1_template) - 1
    scripts_dir = root / "scripts"
    files = {PS1_TEMPLATE_PATH.as_posix(): ps1_template, SH_TEMPLATE_PATH.as_posix(): sh_template}
    files |= _rendered_pair("a/help-heavy", _HELP_HEAVY_BLOCK, ps1_template, sh_template)
    files |= _rendered_pair("a/at-limit", _switches_block(at_limit), ps1_template, sh_template)
    if defects:
        files |= _rendered_pair("b/over-limit", _switches_block(at_limit + 1), ps1_template, sh_template)
        files |= {f"b/handmade{PS1_SUFFIX}": _HANDMADE, f"b/handmade{SH_SUFFIX}": render_sh(_PLANTED_MODULE, sh_template)}
        files |= {f"b/lonely{PS1_SUFFIX}": render_ps1(_FRAME_BLOCK, _PLANTED_MODULE, ps1_template)}
        files |= {f"b/drifted{PS1_SUFFIX}": render_ps1(_FRAME_BLOCK, _PLANTED_MODULE, ps1_template),
                  f"b/drifted{SH_SUFFIX}": render_sh("datrix_scripts.other", sh_template)}
        files |= {f"b/marked{PS1_SUFFIX}": _BYTE_ORDER_MARK + render_ps1(_FRAME_BLOCK, _PLANTED_MODULE, ps1_template),
                  f"b/marked{SH_SUFFIX}": render_sh(_PLANTED_MODULE, sh_template)}
    write_files(scripts_dir, files)
    return scripts_dir


def _check_a_clean_tree_has_no_hit() -> None:
    with TemporaryDirectory(prefix="thin-entrypoint-") as temp:
        scripts_dir = _planted_tree(Path(temp), defects=False)
        help_heavy_lines = len((scripts_dir / "a" / f"help-heavy{PS1_SUFFIX}").read_text(encoding=_ENCODING).splitlines())
        hits = thin_entrypoint_hits(scripts_dir)
    assert help_heavy_lines > MAX_WRAPPER_CODE_LINES, f"the help-heavy plant has only {help_heavy_lines} lines"
    assert hits == [], [hit.render() for hit in hits]


def _check_every_rule_reports_its_planted_defect() -> None:
    with TemporaryDirectory(prefix="thin-entrypoint-") as temp:
        hits = thin_entrypoint_hits(_planted_tree(Path(temp), defects=True))
    found = {(hit.rule, hit.location) for hit in hits}
    expected = {
        (Rule.CODE_LINES, f"b/over-limit{PS1_SUFFIX}"),
        (Rule.NOT_RENDERED, f"b/handmade{PS1_SUFFIX}"),
        (Rule.MISSING_TWIN, f"b/lonely{PS1_SUFFIX}"),
        (Rule.NOT_RENDERED, f"b/drifted{PS1_SUFFIX}"),
        (Rule.NOT_RENDERED, f"b/marked{PS1_SUFFIX}"),
    }
    assert found == expected and len(hits) == len(expected), [hit.render() for hit in hits]


def _check_every_wrapper_but_the_template_is_censused() -> None:
    with TemporaryDirectory(prefix="thin-entrypoint-") as temp:
        scripts_dir = _planted_tree(Path(temp), defects=True)
        found = [path.relative_to(scripts_dir).as_posix() for path in wrappers_under(scripts_dir)]
    expected = [f"a/{name}{PS1_SUFFIX}" for name in ("at-limit", "help-heavy")]
    expected += [f"b/{name}{PS1_SUFFIX}" for name in ("drifted", "handmade", "lonely", "marked", "over-limit")]
    assert found == expected, found


def _check_scripts_tree_wrappers_are_thin() -> None:
    count = len(wrappers_under(SCRIPTS_DIR))
    assert count > 0, f"no .ps1 found under {SCRIPTS_DIR}; the census read nothing"
    hits = thin_entrypoint_hits(SCRIPTS_DIR)
    assert not hits, f"{len(hits)} hit(s) over {count} wrapper(s):\n" + "\n".join(hit.render() for hit in hits)


_SELF_TEST: Final = [
    NamedCheck("a_clean_tree_has_no_hit", _check_a_clean_tree_has_no_hit),
    NamedCheck("every_rule_reports_its_planted_defect", _check_every_rule_reports_its_planted_defect),
    NamedCheck("every_wrapper_but_the_template_is_censused", _check_every_wrapper_but_the_template_is_censused),
]
_CHECKS: Final = [*_SELF_TEST, NamedCheck("scripts_tree_wrappers_are_thin", _check_scripts_tree_wrappers_are_thin)]


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/repo-hygiene/thin-entrypoint-gate.ps1``: one per wrapper parameter, spelled exactly."""
    parser = check_list_parser(
        "Thin entrypoints: every scripts .ps1 is the wrapper template rendered, at most "
        f"{MAX_WRAPPER_CODE_LINES} lines of code, with its .sh twin.",
        debug_flag=WRAPPER_DEBUG_FLAG,
        allow_abbrev=False,
        harness_self_test_flag=False,
    )
    parser.prog = WRAPPER
    return parser


def _gate(argv: Sequence[str] | None) -> int:
    # --self-test: the checks over planted trees pass, and the wrapper is the template rendered with this
    # parser's options.
    parser = build_parser()
    return check_list_main(
        parser.description or "",
        GATE,
        _CHECKS,
        self_test=[
            *_SELF_TEST,
            *wrappers.seam_checks(
                wrapper=WRAPPER, module=MODULE, parser=parser, folder=wrappers.REPO_HYGIENE_GATES_DIR
            ),
        ],
        argv=argv,
        parser=parser,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, _gate, argv)


if __name__ == "__main__":
    sys.exit(main())
