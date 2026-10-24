"""Run a numbered Bowler codemod recipe from ``scripts/codemods/lib/``.

The module behind ``codemods/run-codemod.ps1`` (and its ``.sh`` twin). Finds the recipe
``<NN>_<name>.py`` and runs ``python -m bowler run <recipe> -- <args>`` in the shared venv; every
argument after the recipe name goes to the recipe unchanged (e.g. ``OLD_NAME NEW_NAME`` and the
paths to rewrite). Bowler comes from the ``scripts`` dependency group of ``datrix/pyproject.toml``,
which the shared venv installs. Only a numbered recipe in that folder runs: a name holding a path
is refused. A recipe previews its rewrite as a diff; ``--write`` sets ``DATRIX_CODEMOD_WRITE=1``, on
which the recipes' shared ``finish`` (``codemods/lib/_shared.py``) writes it instead.

Exit codes: Bowler's own; 1 = no such recipe; 2 = no recipe named.

Usage:
    python -m datrix_scripts.codemods.run_codemod 01_rename_function old_name new_name datrix-language/src
    python -m datrix_scripts.codemods.run_codemod --codemod-name=01_rename_function --codemod-args=old_name ...
    python -m datrix_scripts.codemods.run_codemod --write 01_rename_function old_name new_name datrix-language/src
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import UsageError, expect_usage_error
from datrix_scripts.paths import LIB_DIR_NAME, SCRIPTS_DIR, script_env
from datrix_scripts.test.wrappers import CODEMODS_SCRIPTS_DIR, module_main, run_self_test
from datrix_scripts.venv import get_venv_python

MODULE: Final = "datrix_scripts.codemods.run_codemod"
WRAPPER: Final = "run-codemod"
# The numbered recipes are files Bowler loads by path (``01_*.py`` is no importable module name).
CODEMODS_DIR: Final = SCRIPTS_DIR / "codemods" / LIB_DIR_NAME
CODEMOD_GLOB: Final = "[0-9][0-9]_*.py"
CODEMOD_NAME: Final = re.compile(r"^[0-9]{2}_[A-Za-z0-9_]+$")
PY_SUFFIX: Final = ".py"
EXIT_NOT_FOUND: Final = 1
# Read by ``finish`` in ``codemods/lib/_shared.py`` (its ``WRITE_ENV``): "1" writes the rewrite.
WRITE_ENV: Final = "DATRIX_CODEMOD_WRITE"
PYTHONPATH_ENV: Final = "PYTHONPATH"


def find_codemod_script(name: str) -> Path:
    """The recipe *name* names (``.py`` optional).

    Raises:
        FileNotFoundError: *name* is not a numbered recipe in the codemods folder; the message lists them.
    """
    stem = name.removesuffix(PY_SUFFIX)
    path = CODEMODS_DIR / f"{stem}{PY_SUFFIX}"
    if not CODEMOD_NAME.match(stem) or not path.is_file():
        raise FileNotFoundError(
            f"Codemod script not found: {path}. "
            f"Available in {CODEMODS_DIR}: "
            f"{', '.join(p.name for p in sorted(CODEMODS_DIR.glob(CODEMOD_GLOB)))}"
        )
    return path


def codemod_command(script: Path, codemod_args: Sequence[str]) -> list[str]:
    """The Bowler argument vector that runs *script* with *codemod_args*."""
    return [str(get_venv_python()), "-m", "bowler", "run", str(script), "--", *codemod_args]


def codemod_env(write: bool) -> dict[str, str]:
    """The recipe's environment: the scripts' own, the recipes folder first on ``PYTHONPATH`` (Bowler loads a
    recipe by path, so ``from _shared import ...`` resolves only through it), and ``WRITE_ENV=1`` exactly when
    *write*."""
    env = script_env()
    env[PYTHONPATH_ENV] = os.pathsep.join(filter(None, (str(CODEMODS_DIR), env.get(PYTHONPATH_ENV))))
    env.pop(WRITE_ENV, None)
    if write:
        env[WRITE_ENV] = "1"
    return env


def requested(args: argparse.Namespace) -> tuple[str, list[str]]:
    """The recipe name and its arguments: ``--codemod-name`` / ``--codemod-args``, or the positional words.

    Raises:
        UsageError: No recipe is named, or it is named twice.
    """
    words = list(args.words)
    if args.codemod_name and words:
        return args.codemod_name, [*args.codemod_args, *words]
    if args.codemod_name:
        return args.codemod_name, list(args.codemod_args)
    if not words:
        raise UsageError(f"-CodemodName is required: one of {CODEMOD_GLOB} in {CODEMODS_DIR}, without .py.")
    if args.codemod_args:
        raise UsageError("-CodemodArgs needs -CodemodName; name the recipe first.")
    return words[0], words[1:]


def run_codemod(name: str, codemod_args: Sequence[str], *, write: bool = False) -> int:
    try:
        script = find_codemod_script(name)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_NOT_FOUND
    return subprocess.run(codemod_command(script, codemod_args), env=codemod_env(write), check=False).returncode


def build_parser() -> argparse.ArgumentParser:
    """The options of ``codemods/run-codemod.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("words", nargs="*", metavar="WORD",
                        help="The recipe name, then its arguments (as --codemod-name and --codemod-args).")
    parser.add_argument("--codemod-name", help="The recipe without .py (e.g. 01_rename_function).")
    parser.add_argument("--codemod-args", action="append", default=[],
                        help="An argument for the recipe (repeatable, in order).")
    parser.add_argument("--write", action="store_true",
                        help="Write the rewrite to the files instead of printing its diff.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: a recipe previews and writes a planted rename, and the "
                             "refusals.")
    parser.set_defaults(debug=False)
    return parser


_PLANTED_SOURCE: Final = "def old_func(value: int) -> int:\n    return value + 1\n\n\ndef caller() -> int:\n    return old_func(1)\n"


def _check_a_recipe_previews_a_planted_rename() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        planted = Path(tmp) / "sample.py"
        planted.write_text(_PLANTED_SOURCE, encoding="utf-8")
        name, codemod_args = requested(build_parser().parse_args(
            ["--codemod-name=01_rename_function", "--codemod-args=old_func", "--codemod-args=new_func", f"--codemod-args={tmp}"]
        ))
        result = subprocess.run(codemod_command(find_codemod_script(name), codemod_args), env=codemod_env(False),
                                capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "+    return new_func(1)" in result.stdout, result.stdout + result.stderr
        assert planted.read_text(encoding="utf-8") == _PLANTED_SOURCE, "a preview rewrote the file"


def _check_write_rewrites_the_planted_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        planted = Path(tmp) / "sample.py"
        planted.write_text(_PLANTED_SOURCE, encoding="utf-8")
        args = build_parser().parse_args(["--write", "01_rename_function", "old_func", "new_func", tmp])
        assert args.write, "--write did not parse"
        status = run_codemod(*requested(args), write=args.write)
        assert status == 0, f"run-codemod --write exited {status}"
        assert planted.read_text(encoding="utf-8") == _PLANTED_SOURCE.replace("old_func", "new_func"), (
            f"--write left {planted.read_text(encoding='utf-8')!r}; expected every old_func renamed")


def _check_unknown_or_path_names_are_refused() -> None:
    for name in ("99_no_such", "../codemods/lib/01_rename_function", "_shared", "01_rename_function/../_shared"):
        try:
            find_codemod_script(name)
        except FileNotFoundError as exc:
            assert "01_rename_function.py" in str(exc), str(exc)
            continue
        raise AssertionError(f"{name!r} resolved to a recipe instead of being refused")
    assert find_codemod_script("02_rename_class.py").name == "02_rename_class.py"
    expect_usage_error(lambda: requested(build_parser().parse_args([])), "-CodemodName")
    assert requested(build_parser().parse_args(["01_rename_function", "a", "b"])) == ("01_rename_function", ["a", "b"])


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_a_recipe_previews_a_planted_rename, _check_write_rewrites_the_planted_file,
                  _check_unknown_or_path_names_are_refused]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(),
                             folder=CODEMODS_SCRIPTS_DIR)
    return run_codemod(*requested(args), write=args.write)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
