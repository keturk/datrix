"""What the realization gates that generate share: their common options and ``main``, the walk over a generated
tree, and one single-project generation.

Each such gate takes ``--output-root`` (where its generations write; a default under
``<workspace>/.test-output``), ``--debug-logging`` (the wrapper's ``-DebugLogging``/``-Dbg``, forwarded to every
generation) and ``--self-test`` (its checks over planted inputs; nothing is generated), and its ``main`` runs it
in gate mode (``datrix_scripts.gate_log.run_as_gate`` over ``gate_log.gate_child``): its whole output is kept in a claimed
log and the last line is the ``[GATE] <name> PASSED|FAILED exit=<n> log=<path>`` verdict.

The walk lists every file under a generated project's root except those inside a directory whose name is
excluded (post-generation metadata, build caches, installed dependencies, matched case-insensitively), and it
never enters a symbolic link or junction (pnpm's ``node_modules`` store links anywhere). Each file carries its
root-relative path with ``/`` separators, and its comparison key is that path lower-cased, so two runs into
different directories compare file by file.

A generation is ``datrix_scripts.dev.generate`` (the module ``dev/generate.ps1`` runs) in its single-project
mode, as a child process of its own: a fresh interpreter each time, so an ordering that depends on the
per-process hash seed shows up across runs. Its output directory is emptied first, a link there refused.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.cleanup_utils import is_link, plant_directory_link, remove_tree
from datrix_scripts.dev.generate import MODULE as GENERATE_MODULE
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, CheckFunc, NamedCheck, write_files
from datrix_scripts.generation.tree_hash import file_digest
from datrix_scripts.paths import SHOWCASE_DIR, WORKSPACE_DIR, script_env
from datrix_scripts.test.wrappers import REALIZATION_GATES_DIR, run_self_test

EXAMPLES_DIR: Final = SHOWCASE_DIR / "examples"
TEST_OUTPUT_DIR: Final = WORKSPACE_DIR / ".test-output"
SYSTEM_SOURCE: Final = "system.dtrx"
#: The run-directory name of a gate's n-th generation: run1, run2, ...
RUN_DIR_PREFIX: Final = "run"
DEBUG_LOGGING_FLAG: Final = "--debug-logging"
OUTPUT_ROOT_FLAG: Final = "--output-root"
SELF_TEST_FLAG: Final = "--self-test"


class GeneratedTreeError(Exception):
    """A generated tree a gate compares is not on disk; the message names it and how to fix it."""


@dataclass(frozen=True)
class GeneratedFile:
    """One file of a generated tree: its root-relative ``/`` path and where it is."""

    rel_path: str
    full_path: Path

    @property
    def rel_key(self) -> str:
        """The comparison key: the relative path lower-cased."""
        return self.rel_path.lower()

    def digest(self) -> str:
        """The SHA-256 of the file's bytes, hex."""
        return file_digest(self.full_path)


# ---------------------------------------------------------------------------
# Options and main
# ---------------------------------------------------------------------------


def gate_parser(wrapper: str, description: str) -> argparse.ArgumentParser:
    """A generating gate's parser with the options every one takes (``args.debug`` holds ``--debug-logging``).

    It accepts only exact spellings, so the options are exactly the wrapper's parameters.
    """
    parser = argparse.ArgumentParser(prog=wrapper, description=description, allow_abbrev=False)
    parser.add_argument(
        OUTPUT_ROOT_FLAG, default="", help="Root the gate's generations write under (default: under .test-output)."
    )
    parser.add_argument(
        DEBUG_LOGGING_FLAG, dest="debug", action="store_true", help="Debug logging here and in every generation."
    )
    parser.add_argument(
        SELF_TEST_FLAG, action="store_true", help="Run only the checks over planted inputs; generate nothing."
    )
    return parser


def output_root(value: str, default: Path) -> Path:
    """The absolute output root: *value* when given, else *default*."""
    return Path(os.path.abspath(value)) if value else default


def gate_self_test(
    checks: Sequence[CheckFunc | NamedCheck], *, wrapper: str, module: str, parser: argparse.ArgumentParser
) -> int:
    """Run *checks* and the seam checks of ``gates/realization/<wrapper>.ps1`` against *module*'s *parser*."""
    return run_self_test(checks, wrapper=wrapper, module=module, parser=parser, folder=REALIZATION_GATES_DIR)


# ---------------------------------------------------------------------------
# Generated trees
# ---------------------------------------------------------------------------


def example_source(example: str) -> Path:
    """The ``system.dtrx`` of the showcase example at *example* (``/``-separated, under ``datrix/examples``)."""
    return EXAMPLES_DIR.joinpath(*example.split("/"), SYSTEM_SOURCE)


def run_dir(root: Path, number: int) -> Path:
    """``<root>/run<number>``, where a gate's *number*-th generation writes."""
    return root / f"{RUN_DIR_PREFIX}{number}"


def generated_files(root: Path, excluded_dir_names: frozenset[str]) -> list[GeneratedFile]:
    """Every file under *root* outside the directories named in *excluded_dir_names* (lower-case), no link entered.

    Raises:
        GeneratedTreeError: *root* is not a directory.
    """
    if not root.is_dir():
        raise GeneratedTreeError(
            f"Generated tree not found: {root}. Expected the --output directory a generation wrote. "
            "Fix: check the generation's own log for why it wrote nothing there."
        )
    files: list[GeneratedFile] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        for entry in directory.iterdir():
            if is_link(entry):
                continue
            if entry.is_dir():
                if entry.name.lower() not in excluded_dir_names:
                    pending.append(entry)
                continue
            files.append(GeneratedFile(entry.relative_to(root).as_posix(), entry))
    return files


def generation_command(source: Path, output: Path, language: str, *, debug: bool) -> list[str]:
    """The argument vector that generates *source* for *language* into *output*."""
    command = [
        sys.executable,
        "-m",
        GENERATE_MODULE,
        f"--source={source}",
        f"--output={output}",
        f"--language={language}",
    ]
    if debug:
        command.append(WRAPPER_DEBUG_FLAG)
    return command


def run_generation(source: Path, output: Path, language: str, *, debug: bool, quiet: bool) -> int:
    """Empty *output*, generate *source* for *language* into it, and return the generation's exit code.

    With *quiet* the generation's standard output is dropped (its log keeps it); otherwise it reaches the
    console. Raises ``OSError`` when *output* cannot be emptied (a link there is refused, never followed).
    """
    if output.exists():
        remove_tree(output)
    completed = subprocess.run(
        generation_command(source, output, language, debug=debug),
        env=script_env(),
        stdout=subprocess.DEVNULL if quiet else None,
        check=False,
    )
    return completed.returncode


# ---------------------------------------------------------------------------
# Self-test checks, run by every gate that uses what they cover
# ---------------------------------------------------------------------------


def check_walk_skips_excluded_directories_and_links() -> None:
    """The walk keeps source files, prunes an excluded directory in any case, and never enters a link."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        root = base / "tree"
        outside = base / "outside"
        write_files(root, {"src/app.py": "x = 1", "src/.DATRIX/manifest.json": "{}", "docs/readme.md": "r"})
        write_files(outside, {"leaked.py": "y = 2"})
        plant_directory_link(root / "linked", outside)
        keys = sorted(item.rel_key for item in generated_files(root, frozenset({".datrix"})))
        assert keys == ["docs/readme.md", "src/app.py"], keys
        try:
            generated_files(base / "absent", frozenset())
        except GeneratedTreeError as error:
            assert "Generated tree not found" in str(error), error
        else:
            raise AssertionError("a missing tree was walked")


def check_generation_command_is_an_argument_vector() -> None:
    """The generation runs the generate module with one ``--name=value`` per option, ``--dbg`` only on request."""
    source, output = Path("examples") / SYSTEM_SOURCE, Path("out") / "run1"
    command = generation_command(source, output, "lang-a", debug=True)
    assert command == [
        sys.executable, "-m", GENERATE_MODULE, f"--source={source}", f"--output={output}", "--language=lang-a",
        WRAPPER_DEBUG_FLAG,
    ], command
    assert WRAPPER_DEBUG_FLAG not in generation_command(source, output, "lang-a", debug=False)
    assert example_source("01-foundation") == EXAMPLES_DIR / "01-foundation" / SYSTEM_SOURCE
    assert run_dir(Path("root"), 3) == Path("root") / "run3"
    assert output_root("", Path("default")) == Path("default")
    assert output_root("given", Path("default")) == Path(os.path.abspath("given"))
