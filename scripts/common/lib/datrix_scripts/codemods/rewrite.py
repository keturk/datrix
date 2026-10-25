"""Rewrite the Python source of one or more Datrix projects to the idioms Ruff's UP, FURB and PERF rules ask for.

``scripts/codemods/rewrite.ps1`` (and its ``.sh`` twin) runs this module. For each selected project (names
given, or ``--all``) it runs ``ruff check --select UP,FURB,PERF --preview`` over the project's ``src/`` and
``tests/`` trees, from the project root, so the project's own ``line-length``, ``target-version``, excludes and
per-file ignores apply. ``--select`` replaces the project's own rule selection for the run, so no other rule
rewrites anything. Only Ruff's *safe* fixes are applied: a fix Ruff marks unsafe may change behaviour and is
never written. The default run is a preview (``--diff``) and writes nothing; ``--apply`` writes the fixes.

A finding Ruff cannot fix is reported but is not a failure: a project fails only when Ruff could not run on it.
``--exclude`` (repeatable) keeps matching paths out of the run, for a tree that is generated from a template and
compared byte for byte against its regeneration.

Exit codes: 0 = every project ran; 1 = a project could not be rewritten or a self-test check failed; 2 = a usage
error.

Usage (PYTHONPATH=scripts/common/lib; the wrapper sets it):
    python -m datrix_scripts.codemods.rewrite datrix-common
    python -m datrix_scripts.codemods.rewrite datrix-common datrix-cli --apply
    python -m datrix_scripts.codemods.rewrite --all --exclude "src/datrix_common/datrix_model/*"
    python -m datrix_scripts.codemods.rewrite --self-test
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from datrix_scripts.framework_repos import PackageMarker
from datrix_scripts.gate_harness import write_files
from datrix_scripts.metrics.projects import (
    EXIT_FAILED,
    EXIT_PASSED,
    SHOWCASE,
    ProjectSelectionError,
    add_project_arguments,
    print_stderr,
    print_summary,
    run_projects,
    select_projects,
)
from datrix_scripts.metrics.ruff import ProjectOutput
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import CODEMODS_SCRIPTS_DIR, module_main, run_self_test
from datrix_scripts.venv import PACKAGE_DEV_EXTRAS, missing_declared_tool

MODULE: Final = "datrix_scripts.codemods.rewrite"
WRAPPER: Final = "rewrite"
# Ruff runs as a module of this interpreter, so the shared venv's copy is the one that rewrites.
_RUFF_MODULE: Final = "ruff"
EXIT_TOOL_MISSING: Final = 2
#: The rule families that rewrite code to a newer or faster idiom: pyupgrade, refurb, perflint.
REWRITE_RULES: Final = "UP,FURB,PERF"
#: The trees of a project that hold Python source.
REWRITE_TREES: Final = (PackageMarker.SRC.value, PackageMarker.TESTS.value)
USAGE_LINES: Final = (
    "Usage: .\\rewrite.ps1 <project> [<project> ...] [-Apply] [-Exclude <pattern>] or .\\rewrite.ps1 -All [-Apply]",
)
PREVIEW_NOTICE: Final = "Preview only: nothing was written. Re-run with -Apply to write the fixes."


@dataclass(frozen=True)
class RewriteOptions:
    """What one run asks of Ruff, shared by every project."""

    apply: bool
    excludes: tuple[str, ...]


def ruff_command(trees: Sequence[str], options: RewriteOptions) -> list[str]:
    """The Ruff argument vector over the *trees* (relative to the project root) for *options*.

    ``--exit-zero`` keeps a finding Ruff cannot fix from failing the project; Ruff's own failures (a bad
    config, an unreadable file) still exit non-zero. Without ``--unsafe-fixes`` only safe fixes are applied.
    """
    command = [sys.executable, "-m", _RUFF_MODULE, "check", "--select", REWRITE_RULES, "--preview", "--exit-zero"]
    command.extend(["--output-format", "concise", "--fix" if options.apply else "--diff"])
    for pattern in options.excludes:
        command.extend(["--extend-exclude", pattern])
    command.extend(trees)
    return command


def rewrite_project(project_root: Path, options: RewriteOptions) -> ProjectOutput:
    """Ruff over the source trees of *project_root*: its exit code and its stdout then stderr; 1 when the
    project has no source tree, 2 when Ruff is not installed in this interpreter."""
    if importlib.util.find_spec(_RUFF_MODULE) is None:
        return ProjectOutput(EXIT_TOOL_MISSING, missing_declared_tool("ruff", PACKAGE_DEV_EXTRAS) + "\n", error=True)
    if not project_root.is_dir():
        return ProjectOutput(EXIT_FAILED, f"Error: project root is not a directory: {project_root}\n", error=True)
    trees = [tree for tree in REWRITE_TREES if (project_root / tree).is_dir()]
    if not trees:
        wanted = " or ".join(f"{tree}/" for tree in REWRITE_TREES)
        return ProjectOutput(EXIT_FAILED, f"Error: project has no {wanted} directory: {project_root}\n", error=True)
    result = subprocess.run(ruff_command(trees, options), cwd=str(project_root), capture_output=True, text=True)
    return ProjectOutput(result.returncode, result.stdout + result.stderr)


def _rewrite_and_show(project_root: Path, options: RewriteOptions) -> int:
    """Rewrite one project, showing what Ruff printed."""
    outcome = rewrite_project(project_root, options)
    if outcome.error:
        print_stderr(outcome.text.rstrip("\n"))
    elif outcome.text:
        print(outcome.text, end="")
    return outcome.code


def run_rewrite(args: argparse.Namespace, workspace: Path) -> int:
    """The wrapper's run over *workspace*: select, rewrite each project, summarize."""
    try:
        projects = select_projects(
            args, workspace, usage=USAGE_LINES, any_of=frozenset({PackageMarker.SRC, PackageMarker.TESTS})
        )
    except ProjectSelectionError as exc:
        for line in exc.lines:
            print(line)
        return EXIT_FAILED
    mode = "apply" if args.apply else "preview"
    print(f"Rewriting ({REWRITE_RULES}, {mode}) in: {', '.join(projects)}")
    options = RewriteOptions(apply=args.apply, excludes=tuple(args.exclude))
    results = run_projects(
        projects,
        lambda project: _rewrite_and_show(workspace / project, options),
        stop_on_error=args.stop_on_error,
        header_info=mode,
    )
    code = print_summary(f"Rewrite Summary ({mode})", results)
    if not args.apply:
        print("")
        print(PREVIEW_NOTICE)
    return code


def build_parser() -> argparse.ArgumentParser:
    """The options of ``codemods/rewrite.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER,
        description=f"Rewrite Datrix projects to the idioms of Ruff's {REWRITE_RULES} rules (safe fixes only).",
        allow_abbrev=False,
    )
    add_project_arguments(parser)
    parser.add_argument("--apply", action="store_true", help="Write the fixes; without it, show the diff only.")
    parser.add_argument(
        "--exclude", action="append", default=[], metavar="PATTERN",
        help="A path or glob, relative to the project root, to leave out; repeatable.",
    )
    parser.add_argument("--stop-on-error", action="store_true", help="Stop on the first project that fails.")
    parser.add_argument("--self-test", action="store_true", help="Run only the self-test over planted projects.")
    parser.set_defaults(debug=False)
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test(
            SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=CODEMODS_SCRIPTS_DIR
        )
    return run_rewrite(args, WORKSPACE_DIR)


# ---------------------------------------------------------------------------
# Self-test: planted projects in a temporary workspace, rewritten by the real Ruff.
# ---------------------------------------------------------------------------

#: ``Optional[...]`` is the pyupgrade rewrite (to ``X | None``) on a project targeting Python 3.11.
_OLD_IDIOM: Final = "from typing import Optional\n\n\ndef first(value: Optional[int]) -> Optional[int]:\n    return value\n"
#: What the rewrite leaves: the annotations changed; the import it made unused stays (F401 is not a rewrite rule).
_REWRITTEN: Final = _OLD_IDIOM.replace("Optional[int]", "int | None")
_CLEAN: Final = "def first(value: int | None) -> int | None:\n    return value\n"
_CONFIG: Final = "[project]\nname = '{name}'\n\n[tool.ruff]\ntarget-version = 'py311'\n"
#: ``a if a else b`` is the refurb rewrite (to ``a or b``); the project's own ``select`` never names FURB.
_REFURB_SOURCE: Final = "def pick(a: str, b: str) -> str:\n    return a if a else b\n"
_REFURB_FIXED: Final = "def pick(a: str, b: str) -> str:\n    return a or b\n"


def _plant(root: Path) -> Path:
    """``datrix-old`` (old idioms in src/ and tests/, a generated tree), ``datrix-clean``, ``datrix-bare`` (no
    source tree), ``datrix-refurb`` (selects only F, so its own config never asks for FURB) and the showcase."""
    files = {
        "datrix-old/src/pkg/module.py": _OLD_IDIOM,
        "datrix-old/src/pkg/generated/node.py": _OLD_IDIOM,
        "datrix-old/tests/test_module.py": _OLD_IDIOM,
        "datrix-clean/src/module.py": _CLEAN,
        "datrix-bare/pyproject.toml": _CONFIG.format(name="datrix-bare"),
        "datrix-refurb/src/module.py": _REFURB_SOURCE,
    }
    write_files(root, files)
    for name in ("datrix-old", "datrix-clean", "datrix-refurb"):
        extra = "\n[tool.ruff.lint]\nselect = ['F']\n" if name == "datrix-refurb" else ""
        (root / name / PackageMarker.PYPROJECT.value).write_text(_CONFIG.format(name=name) + extra, encoding="utf-8")
    (root / SHOWCASE).mkdir()
    return root


def _report(argv: Sequence[str], files: tuple[str, ...] = ()) -> tuple[int, str, str, dict[str, str]]:
    """Exit code, stdout, stderr and the text of the named *files* (relative to the workspace) after a run
    over a planted workspace."""
    out, err = io.StringIO(), io.StringIO()
    with TemporaryDirectory() as raw:
        workspace = _plant(Path(raw) / "ws")
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = run_rewrite(build_parser().parse_args(list(argv)), workspace)
        texts = {name: (workspace / name).read_text(encoding="utf-8") for name in files}
    return code, out.getvalue(), err.getvalue(), texts


_OLD_MODULE: Final = "datrix-old/src/pkg/module.py"
_OLD_GENERATED: Final = "datrix-old/src/pkg/generated/node.py"
_OLD_TEST: Final = "datrix-old/tests/test_module.py"


def _check_preview_shows_the_diff_and_writes_nothing() -> None:
    code, out, _, texts = _report(["datrix-old"], (_OLD_MODULE, _OLD_TEST))
    assert code == EXIT_PASSED, (code, out)
    assert "UP045" in out or "UP007" in out or "Would fix" in out, out
    assert texts == {_OLD_MODULE: _OLD_IDIOM, _OLD_TEST: _OLD_IDIOM}, texts
    assert PREVIEW_NOTICE in out and "======== datrix-old (preview) ========" in out, out


def _check_apply_rewrites_src_and_tests() -> None:
    code, out, _, texts = _report(["datrix-old", "--apply"], (_OLD_MODULE, _OLD_TEST))
    assert code == EXIT_PASSED and PREVIEW_NOTICE not in out, (code, out)
    assert texts == {_OLD_MODULE: _REWRITTEN, _OLD_TEST: _REWRITTEN}, texts


def _check_apply_adds_rules_the_project_did_not_select() -> None:
    code, out, _, texts = _report(["datrix-refurb", "--apply"], ("datrix-refurb/src/module.py",))
    assert code == EXIT_PASSED, (code, out)
    assert texts["datrix-refurb/src/module.py"] == _REFURB_FIXED, texts


def _check_several_projects_run_in_one_call() -> None:
    code, out, _, _ = _report(["datrix-old", "datrix-clean", "datrix-refurb"])
    assert code == EXIT_PASSED, (code, out)
    for name in ("datrix-old", "datrix-clean", "datrix-refurb"):
        assert f" [PASS] : {name}" in out, out


def _check_exclude_leaves_a_generated_tree_alone() -> None:
    code, out, _, texts = _report(
        ["datrix-old", "--apply", "--exclude", "src/pkg/generated/*"], (_OLD_MODULE, _OLD_GENERATED)
    )
    assert code == EXIT_PASSED, (code, out)
    assert texts == {_OLD_MODULE: _REWRITTEN, _OLD_GENERATED: _OLD_IDIOM}, texts


def _check_a_project_without_source_fails() -> None:
    code, out, err, _ = _report(["datrix-bare", "datrix-clean"])
    assert code == EXIT_FAILED, (code, out)
    assert "Error: project has no src/ or tests/ directory:" in err, err
    assert " [FAIL] : datrix-bare" in out and " [PASS] : datrix-clean" in out, out


def _check_command_carries_every_flag() -> None:
    command = ruff_command(["src", "tests"], RewriteOptions(apply=False, excludes=("a/*", "b.py")))
    expected = [
        "check", "--select", REWRITE_RULES, "--preview", "--exit-zero", "--output-format", "concise", "--diff",
        "--extend-exclude", "a/*", "--extend-exclude", "b.py", "src", "tests",
    ]
    assert command[3:] == expected, command
    assert ruff_command(["src"], RewriteOptions(apply=True, excludes=()))[-2:] == ["--fix", "src"]
    assert "--unsafe-fixes" not in command


def _check_refusals_print_the_usage() -> None:
    code, out, _, _ = _report([SHOWCASE])
    assert code == EXIT_FAILED and out.splitlines() == ["ERROR: No valid projects (datrix excluded)."], (code, out)
    code, out, _, _ = _report([])
    assert code == EXIT_FAILED and USAGE_LINES[0] in out.splitlines(), (code, out)


SELF_TEST_CHECKS: Final[tuple[Callable[[], None], ...]] = (
    _check_preview_shows_the_diff_and_writes_nothing,
    _check_apply_rewrites_src_and_tests,
    _check_apply_adds_rules_the_project_did_not_select,
    _check_several_projects_run_in_one_call,
    _check_exclude_leaves_a_generated_tree_alone,
    _check_a_project_without_source_fails,
    _check_command_carries_every_flag,
    _check_refusals_print_the_usage,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
