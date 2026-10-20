"""Shared-library gate checks for the scripts tree's shared contracts.

Run by ``shared_library_gate.py`` beside its module checks:

* ``datrix_scripts.gate_harness`` -- the one check loop, its non-vacuity proof, the shared flags
  and the fixture writer;
* ``datrix_scripts.gate_log`` and ``datrix_scripts.run_log`` -- gate mode's claimed log and the
  verdict line the red-run digest hook reads, and the contained, exclusive run-log names;
* ``datrix_scripts.count_ratchet`` -- the two ratchet semantics and the fail-closed baseline
  reader;
* the scripts-tree censuses (``scripts_tree_census``): each reports a planted copy, and the real
  tree stays at or under its baseline;
* every ``datrix_scripts`` module imports as the first import of a fresh interpreter, and every
  module a hook imports is exercised by a gate (``consumed - covered`` is empty). Hooks fail
  open, so a broken import would disable a hook silently;
* the held-clean script modules (the ``import_boundaries`` scanner package, ``run_complete`` and
  the ``checklist`` and ``guard-predeploy-analysis`` hooks) keep every function at or under the
  cognitive-complexity limit, and the measurement reports a planted function over it.
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Final

from datrix_codegen_kernel.generation.test_runner_entry_point import (
    PARALLEL_ARGUMENT,
    RESULTS_DIR_ARGUMENT,
    TEST_RUNNER_ENTRY_POINT,
    ProjectTestRunner,
    build_test_runner_entry_point,
)

from datrix_scripts.count_ratchet import (
    RatchetDelta,
    RatchetMode,
    compare,
    load_counts_json,
    load_counts_toml,
    read_counts,
    write_counts_json,
    write_counts_toml,
)
from datrix_scripts.metrics.complexity import DEFAULT_MAX_COMPLEXITY, run_check_cognitive
from datrix_scripts.metrics.dead_code_report import _parse_line, finding_order, format_finding
from datrix_scripts.gate_harness import (
    WRAPPER_DEBUG_FLAG,
    NamedCheck,
    check_list_parser,
    gate_argument_parser,
    harness_self_test,
    run_checks,
    write_file,
    write_files,
)
from datrix_scripts.gate_log import GATE_CHILD_ENV, gate_log_directory, verdict_line
from datrix_scripts.run_log import MAX_CLAIM_ATTEMPTS, claim_run_log_file, run_log_base_name, run_log_segment
from datrix_scripts.hook_modules import DIGEST_HOOK_MODULE, load_hook_module
from datrix_scripts.paths import PACKAGE_DIR, PYTHONPATH_ROOT, SCRIPTS_DIR, SHOWCASE_DIR
from datrix_scripts.venv import get_venv_python
from datrix_scripts.test.run_complete import (
    _generated_projects,
    _run_single_project_deploy_tests,
    _run_single_project_unit_tests,
    get_paths,
)
from datrix_scripts.test.scripts_tree_census import (
    census_failures,
    python_modules,
    python_root_resolvers,
    run_censuses,
)
from datrix_scripts.test.scripts_tree_census import self_test_checks as census_self_test_checks

HOOKS_DIR: Final = SHOWCASE_DIR / "claude-config" / ".claude" / "hooks"
_SHARED_PACKAGE: Final = "datrix_scripts"
_HOOK_TEST_PREFIX: Final = "test-"
_GATE_OWNER_FOLDERS: Final = ("test", "dev", "skill", "tasks", "git", "review")
_SHARED_PACKAGE_PARTS: Final = ("common", "lib", _SHARED_PACKAGE)
_SELF_TEST_NAMES: Final = frozenset({"self_test", "run_self_test"})
_IMPORT_TIMEOUT_SECONDS: Final = 180
_IMPORT_WORKERS: Final = 8
_IMPORT_PROGRAM: Final = (
    "import importlib, sys; sys.path[0:0] = sys.argv[2:]; importlib.import_module(sys.argv[1])"
)


# ---------------------------------------------------------------- gate_harness


def _captured(action: Callable[[], object]) -> tuple[object, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = action()
    return result, buffer.getvalue()


def _passing() -> None:
    return None


def _failing() -> None:
    raise AssertionError("planted failure")


def _raising_value_error() -> None:
    raise ValueError("a defect in the gate, not a failed check")


def check_gate_harness_reports_each_check_and_the_overall_verdict() -> None:
    """run_checks prints [OK]/[FAIL] per check, by function name or NamedCheck name, and returns
    False when one failed; a list of passing checks returns True."""
    passed, output = _captured(lambda: run_checks([_passing, NamedCheck("named_case", _failing)]))
    assert passed is False, "a failing check must make run_checks return False"
    assert "[OK]" in output and "_passing" in output, f"the passing check was not reported: {output!r}"
    assert "[FAIL]" in output and "named_case: planted failure" in output, (
        f"the NamedCheck failure was not reported by its name: {output!r}"
    )
    all_passed, _ = _captured(lambda: run_checks([_passing]))
    assert all_passed is True, "only passing checks must return True"


def check_gate_harness_lets_a_non_assertion_error_propagate() -> None:
    """Only AssertionError is a failed check; any other exception is a gate defect and propagates."""
    try:
        _captured(lambda: run_checks([_raising_value_error]))
    except ValueError:
        return
    raise AssertionError("a ValueError raised inside a check was swallowed by run_checks")


def check_gate_harness_self_test_detects_a_failure() -> None:
    """harness_self_test returns True only because its deliberate failure was reported FAILED."""
    result, output = _captured(harness_self_test)
    assert result is True, f"harness_self_test did not prove the loop reports a failure: {output!r}"
    assert "[FAIL]" in output, "the deliberately failing check was not printed as FAILED"


def check_gate_harness_argument_parser_carries_the_shared_flags() -> None:
    """--debug, --self-test and --harness-self-test always; --update-baseline only when asked."""
    plain = gate_argument_parser("demo").parse_args(["--debug", "--self-test", "--harness-self-test"])
    assert plain.debug and plain.self_test and plain.harness_self_test, "a shared flag was not parsed"
    assert not hasattr(plain, "update_baseline"), "--update-baseline must exist only when requested"
    with_baseline = gate_argument_parser("demo", update_baseline=True).parse_args(["--update-baseline"])
    assert with_baseline.update_baseline is True, "--update-baseline was not parsed when requested"


def check_gate_harness_debug_flag_follows_the_wrapper() -> None:
    """A template-wrapped gate takes ``--dbg`` (its wrapper's ``-Dbg``) or no debug flag at all, and
    refuses abbreviations; the check-list parser adds ``--only``."""
    wrapped = check_list_parser("demo", debug_flag=WRAPPER_DEBUG_FLAG, allow_abbrev=False)
    parsed = wrapped.parse_args(["--dbg", "--only=x"])
    assert parsed.debug and parsed.only == "x", f"--dbg/--only were not parsed: {parsed}"
    silent = gate_argument_parser("demo", debug_flag=None, allow_abbrev=False)
    assert silent.parse_args([]).debug is False, "a parser without a debug flag must still answer args.debug"
    unharnessed = check_list_parser("demo", debug_flag=WRAPPER_DEBUG_FLAG, allow_abbrev=False,
                                    harness_self_test_flag=False)
    assert unharnessed.parse_args([]).harness_self_test is False, (
        "a parser without --harness-self-test must still answer args.harness_self_test"
    )
    for parser, refused in (
        (wrapped, ["--debug"]), (wrapped, ["--self"]), (silent, ["--dbg"]), (unharnessed, ["--harness-self-test"])
    ):
        try:
            with contextlib.redirect_stderr(io.StringIO()):  # argparse's usage text for a case refused on purpose.
                parser.parse_args(refused)
        except SystemExit:
            continue
        raise AssertionError(f"{refused} was accepted by a template-wrapped gate parser")


def check_gate_harness_writes_planted_files() -> None:
    """write_files creates parents and writes UTF-8 text; write_file writes one file."""
    with TemporaryDirectory(prefix="gate-harness-") as tmp:
        root = Path(tmp)
        written = write_files(root, {"a/b/c.txt": "ä", "d.txt": "x"})
        assert [path.relative_to(root).as_posix() for path in written] == ["a/b/c.txt", "d.txt"]
        assert (root / "a" / "b" / "c.txt").read_text(encoding="utf-8") == "ä"
        single = write_file(root / "e" / "f.txt", "y")
        assert single.read_text(encoding="utf-8") == "y"


# ---------------------------------------------------------------- count_ratchet


def check_count_ratchet_tighten_only() -> None:
    """An increase fails, a decrease passes, a key the baseline lacks is pinned at zero."""
    baseline = {"a": 3, "b": 2}
    assert compare({"a": 4, "b": 1}, baseline, RatchetMode.TIGHTEN_ONLY) == [RatchetDelta("a", 3, 4)]
    assert compare({"a": 3, "b": 0}, baseline, RatchetMode.TIGHTEN_ONLY) == []
    assert compare({"new": 1}, baseline, RatchetMode.TIGHTEN_ONLY) == [RatchetDelta("new", 0, 1)]
    keyed = compare({}, baseline, RatchetMode.TIGHTEN_ONLY, keys=frozenset({"a"}))
    assert keyed == [], f"a key with no live count reads as zero, which tightens: {keyed}"


def check_count_ratchet_exact_pin() -> None:
    """Any difference fails, including an unbanked decrease; a baseline key outside the
    registered key set is stale."""
    baseline = {"python": 2, "gone": 1}
    deltas = compare({"python": 1}, baseline, RatchetMode.EXACT_PIN, keys=frozenset({"python"}))
    assert deltas == [RatchetDelta("python", 2, 1), RatchetDelta("gone", 1, 0, stale=True)], deltas
    assert deltas[0].decreased and not deltas[0].increased
    assert compare({"python": 2}, {"python": 2}, RatchetMode.EXACT_PIN, keys=frozenset({"python"})) == []


def check_count_ratchet_reader_fails_closed() -> None:
    """A missing baseline, a non-table, a bool, a negative and a non-integer count are each a
    ValueError naming the file; a written JSON and TOML table read back unchanged."""
    with TemporaryDirectory(prefix="count-ratchet-") as tmp:
        root = Path(tmp)
        for loader, name in ((load_counts_json, "missing.json"), (load_counts_toml, "missing.toml")):
            try:
                loader(root / name, table_key="counts")
            except ValueError as exc:
                assert name in str(exc), f"the missing-file error does not name the file: {exc}"
            else:
                raise AssertionError(f"a missing baseline {name} read as empty instead of failing")
        for bad in ([1], {"k": True}, {"k": -1}, {"k": "3"}):
            try:
                read_counts(bad, source=root / "b.toml", table_name="counts")
            except ValueError as exc:
                assert "b.toml" in str(exc), f"the error does not name the source file: {exc}"
            else:
                raise AssertionError(f"read_counts accepted {bad!r}")
        counts = {"x-y": 2, "a": 0}
        write_counts_json(root / "c.json", counts, comment="demo", table_key="baseline")
        assert load_counts_json(root / "c.json", table_key="baseline") == counts
        write_counts_toml(root / "c.toml", counts, header="demo\nheader", table_key="counts")
        assert load_counts_toml(root / "c.toml", table_key="counts") == counts


# ---------------------------------------------------------------- censuses


def check_scripts_tree_censuses_are_zero() -> None:
    """No census over the real scripts tree reports a hit."""
    failures = census_failures(run_censuses(SCRIPTS_DIR))
    assert not failures, "\n".join(failures)


def check_hooks_name_no_retired_root_resolver() -> None:
    """No hook defines, imports or calls a retired workspace-root resolver."""
    assert HOOKS_DIR.is_dir(), f"hooks directory {HOOKS_DIR} is missing; the census would read nothing"
    hits = python_root_resolvers(list(python_modules(HOOKS_DIR)))
    assert not hits, "\n".join(hit.render() for hit in hits)


# ---------------------------------------------------------------- shared-module coverage


def _module_name_under(path: Path, root: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def shared_modules(package_dir: Path = PACKAGE_DIR) -> list[str]:
    """Dotted names of every module of the shared package."""
    return sorted(
        _module_name_under(path, package_dir.parent)
        for path in package_dir.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _import_failure(module: str, search_root: Path) -> str | None:
    completed = subprocess.run(
        [sys.executable, "-I", "-c", _IMPORT_PROGRAM, module, str(search_root)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False, timeout=_IMPORT_TIMEOUT_SECONDS,
    )
    if completed.returncode == 0:
        return None
    lines = completed.stderr.strip().splitlines()
    return f"{module} (exit {completed.returncode}): {lines[-1] if lines else 'no stderr'}"


def import_failures(modules: list[str], search_root: Path) -> list[str]:
    with ThreadPoolExecutor(max_workers=_IMPORT_WORKERS) as pool:
        results = pool.map(lambda module: _import_failure(module, search_root), modules)
    return [failure for failure in results if failure is not None]


def check_every_shared_module_imports_in_a_fresh_interpreter() -> None:
    """Every module under common/lib/datrix_scripts imports as the first import of an isolated
    (-I) venv interpreter with only common/lib on sys.path. A planted module with a syntax error
    is reported."""
    with TemporaryDirectory(prefix="import-census-") as tmp:
        root = Path(tmp)
        write_files(root, {"planted_pkg/__init__.py": "", "planted_pkg/broken.py": "def (:\n"})
        planted = import_failures(["planted_pkg.broken"], root)
        assert planted and "SyntaxError" in planted[0], f"the planted syntax error was not reported: {planted}"
    modules = shared_modules()
    assert len(modules) > 50, f"the census found only {len(modules)} shared modules; the walk is broken"
    failures = import_failures(modules, PYTHONPATH_ROOT)
    assert not failures, (
        "shared modules that do not import in a fresh interpreter (a syntax error, a missing "
        f"dependency, or an import cycle): {failures}. Fix the module; a hook importing it fails open."
    )


def _shared_imports(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if node.module == _SHARED_PACKAGE:
                found.update(f"{_SHARED_PACKAGE}.{alias.name}" for alias in node.names)
            elif node.module.startswith(f"{_SHARED_PACKAGE}."):
                found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names if alias.name.startswith(f"{_SHARED_PACKAGE}."))
    return found


def _parsed(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return None


def hook_consumed_modules(hooks_dir: Path) -> set[str]:
    """``datrix_scripts`` modules imported by the hooks (their ``test-*.py`` files excluded)."""
    consumed: set[str] = set()
    for path in sorted(hooks_dir.glob("*.py")):
        if path.name.startswith(_HOOK_TEST_PREFIX):
            continue
        tree = _parsed(path)
        if tree is not None:
            consumed |= _shared_imports(tree)
    return consumed


def _is_gate_module(path: Path, scripts_dir: Path) -> bool:
    """A gate's module: under ``gates/<family>/lib/``, or a ``*gate*`` module of a gate-owning scripts folder,
    kept in that folder or in its package ``common/lib/datrix_scripts/<folder>/``."""
    relative = path.relative_to(scripts_dir).parts
    if relative[0] == "gates" and len(relative) >= 3 and relative[2] == "lib":
        return True
    in_package = relative[:len(_SHARED_PACKAGE_PARTS)] == _SHARED_PACKAGE_PARTS
    owner = relative[len(_SHARED_PACKAGE_PARTS)] if in_package and len(relative) > len(_SHARED_PACKAGE_PARTS) + 1 \
        else relative[0]
    return owner in _GATE_OWNER_FOLDERS and "gate" in path.stem


def _defines_self_test(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.FunctionDef) and node.name in _SELF_TEST_NAMES for node in tree.body
    )


def gate_covered_modules(scripts_dir: Path) -> set[str]:
    """Shared modules a gate module imports, or that define a top-level self-test."""
    covered: set[str] = set()
    package_dir = scripts_dir / "common" / "lib" / _SHARED_PACKAGE
    for path in sorted(scripts_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = _parsed(path)
        if tree is None:
            continue
        if _is_gate_module(path, scripts_dir):
            covered |= _shared_imports(tree)
        if package_dir in path.parents and _defines_self_test(tree):
            covered.add(_module_name_under(path, scripts_dir / "common" / "lib"))
    return covered


def _uncovered(consumed: set[str], covered: set[str]) -> list[str]:
    """Consumed modules no gate covers; a module counts as covered when it or a parent package is."""
    return sorted(
        module for module in consumed
        if not any(module == name or module.startswith(f"{name}.") for name in covered)
    )


def check_every_hook_consumed_shared_module_is_exercised_by_a_gate() -> None:
    """consumed - covered is empty: each datrix_scripts module a hook imports is imported by a gate
    module or carries its own top-level self-test. A planted hook importing an uncovered module
    is reported."""
    with TemporaryDirectory(prefix="hook-census-") as tmp:
        hooks = Path(tmp) / "hooks"
        write_files(
            hooks,
            {
                "guard-demo.py": "from datrix_scripts.zz_uncovered import thing\n",
                "test-guard-demo.py": "from datrix_scripts.zz_test_only import thing\n",
            },
        )
        planted = _uncovered(hook_consumed_modules(hooks), gate_covered_modules(SCRIPTS_DIR))
        assert planted == ["datrix_scripts.zz_uncovered"], f"the planted hook import was not isolated: {planted}"
    package_gate = SCRIPTS_DIR.joinpath(*_SHARED_PACKAGE_PARTS, "tasks", "demo_gate.py")
    package_module = SCRIPTS_DIR.joinpath(*_SHARED_PACKAGE_PARTS, "tasks", "demo.py")
    assert _is_gate_module(package_gate, SCRIPTS_DIR) and not _is_gate_module(package_module, SCRIPTS_DIR), (
        "a gate module in a gate-owning folder's package was not told apart from its other modules"
    )
    consumed = hook_consumed_modules(HOOKS_DIR)
    assert consumed, f"no hook under {HOOKS_DIR} imports a shared module; the census reads nothing"
    uncovered = _uncovered(consumed, gate_covered_modules(SCRIPTS_DIR))
    assert not uncovered, (
        f"shared modules a hook imports that no gate exercises: {uncovered}. Hooks fail open, so a "
        "break in one would disable the hook silently. Fix: import the module in a gate check, or "
        "give it a top-level self_test."
    )


#: Stub runners for planted projects: each records what it was started with, then exits.
_UNIT_STUB: Final = ProjectTestRunner("python", PurePosixPath("tests/unit_stub.py"))
_DEPLOY_STUB: Final = ProjectTestRunner("python", PurePosixPath("tests/deploy_stub.py"))
_STUB_RECORD_SUFFIX: Final = ".seen.json"
_STUB_PROGRAM: Final = (
    "import json, os, sys\n"
    "from pathlib import Path\n"
    "record = {'argv': sys.argv[1:], 'cwd': os.getcwd(), 'executable': sys.executable}\n"
    "Path(sys.argv[0] + '" + _STUB_RECORD_SUFFIX + "').write_text(json.dumps(record), encoding='utf-8')\n"
    "sys.exit(int(Path(sys.argv[0] + '.exit').read_text(encoding='utf-8')))\n"
)


def _entry_point_text(*, with_deploy: bool) -> str:
    """The entry point every language emits, built by the kernel over the stub runners."""
    return build_test_runner_entry_point(unit=_UNIT_STUB, deploy=_DEPLOY_STUB if with_deploy else None).content


def _plant_project(project: Path, *, with_deploy: bool, exit_code: int) -> None:
    files = {str(TEST_RUNNER_ENTRY_POINT): _entry_point_text(with_deploy=with_deploy)}
    for stub in (_UNIT_STUB, _DEPLOY_STUB):
        files[str(stub.script)] = _STUB_PROGRAM
        files[f"{stub.script}.exit"] = str(exit_code)
    write_files(project, files)


def _stub_record(project: Path, stub: ProjectTestRunner) -> dict[str, object] | None:
    record = project / f"{stub.script}{_STUB_RECORD_SUFFIX}"
    return json.loads(record.read_text(encoding="utf-8")) if record.is_file() else None


def check_run_complete_discovers_projects_by_their_test_runner() -> None:
    """Steps 3 and 4 find a generated project by its emitted tests/run-tests.ps1, whatever language
    generated it: both planted projects for unit tests, only the one whose runner declares
    -Deploy for deploy tests."""
    with TemporaryDirectory(prefix="run-complete-projects-") as tmp:
        generated = Path(tmp) / ".generated"
        write_files(
            generated,
            {
                "lang-a/docker/local/shop/tests/run-tests.ps1": _entry_point_text(with_deploy=True),
                "lang-b/docker/local/catalog/tests/run-tests.ps1": _entry_point_text(with_deploy=False),
                "lang-b/docker/local/catalog/scripts/run-tests.ps1": _entry_point_text(with_deploy=True),
            },
        )
        shop = generated / "lang-a" / "docker" / "local" / "shop"
        catalog = generated / "lang-b" / "docker" / "local" / "catalog"
        unit = _generated_projects(generated, None, "unused", "unused", deploy=False)
        assert unit == [shop, catalog], f"unit discovery found {unit}, expected both projects once"
        deploy = _generated_projects(generated, None, "unused", "unused", deploy=True)
        assert deploy == [shop], f"deploy discovery found {deploy}, expected only the -Deploy runner"
        missing = _generated_projects(Path(tmp) / "absent", None, "unused", "unused", deploy=False)
        assert missing == [], f"an absent .generated tree must yield no project: {missing}"


def check_run_complete_runs_every_project_through_its_test_entry_point() -> None:
    """Steps 3 and 4 run a project's tests only through tests/run-tests.ps1, whatever language
    generated it: -Unit with --parallel, -Deploy with --results-dir, from the project root, in the
    activated workspace venv; a failing runner fails the project, a project without -Deploy has no
    deploy step, and a project without the entry point is a failure, never a silent skip."""
    paths = get_paths()
    venv_python = get_venv_python().resolve()
    with TemporaryDirectory(prefix="run-complete-entry-point-") as tmp:
        generated = Path(tmp) / ".generated"
        passing = generated / "lang-x" / "docker" / "local" / "shop"
        failing = generated / "lang-x" / "docker" / "local" / "ledger"
        unit_only = generated / "lang-y" / "docker" / "local" / "catalog"
        bare = generated / "lang-z" / "docker" / "local" / "bare"
        _plant_project(passing, with_deploy=True, exit_code=0)
        _plant_project(failing, with_deploy=True, exit_code=1)
        _plant_project(unit_only, with_deploy=False, exit_code=0)
        write_file(bare / "tests" / "unit_stub.py", _STUB_PROGRAM)

        unit = _run_single_project_unit_tests(passing, generated, "lang-x")
        assert unit["success"] is True, f"a passing unit runner must pass the project: {unit}"
        seen = _stub_record(passing, _UNIT_STUB)
        assert seen is not None, "the unit runner never ran through the entry point"
        assert seen["argv"] == [PARALLEL_ARGUMENT], f"the unit runner got {seen['argv']}"
        assert Path(str(seen["cwd"])).resolve() == passing.resolve(), f"the unit runner ran in {seen['cwd']}"
        assert Path(str(seen["executable"])).resolve() == venv_python, (
            f"the unit runner ran under {seen['executable']}, not the workspace venv's {venv_python}"
        )
        assert _stub_record(passing, _DEPLOY_STUB) is None, "-Unit started the deploy runner"

        failed = _run_single_project_unit_tests(failing, generated, "lang-x")
        assert failed["success"] is False, f"a failing unit runner must fail the project: {failed}"

        timestamp = "20000101-000000"
        deploy = _run_single_project_deploy_tests(passing, "shop", paths, timestamp, "lang-x")
        assert deploy is not None and deploy["success"] is True, f"deploy run: {deploy}"
        seen = _stub_record(passing, _DEPLOY_STUB)
        results_dir = passing / ".test_results" / f"deploy-test-{timestamp}"
        assert seen is not None and seen["argv"] == [RESULTS_DIR_ARGUMENT, str(results_dir)], (
            f"the deploy runner got {seen and seen['argv']}"
        )
        failed_deploy = _run_single_project_deploy_tests(failing, "ledger", paths, timestamp, "lang-x")
        assert failed_deploy is not None and failed_deploy["success"] is False, f"deploy run: {failed_deploy}"
        assert _run_single_project_deploy_tests(unit_only, "catalog", paths, timestamp, "lang-y") is None, (
            "a project whose entry point declares no -Deploy must have no deploy step"
        )

        for result in (
            _run_single_project_unit_tests(bare, generated, "lang-z"),
            _run_single_project_deploy_tests(bare, "bare", paths, timestamp, "lang-z"),
        ):
            assert result is not None and result["success"] is False and result["errors"] == 1, (
                f"a project without {TEST_RUNNER_ENTRY_POINT} must fail, not skip: {result}"
            )
        assert _stub_record(bare, _UNIT_STUB) is None, "a runner was started without the entry point"


def check_dead_code_report_reads_and_orders_vulture_sizes() -> None:
    """``--sort-by-size`` lines carry ``, N lines``; they parse, and order largest first."""
    small = _parse_line("pkg/a.py:3: unused function 'tiny' (60% confidence, 4 lines)")
    large = _parse_line("pkg/b.py:9: unused class 'Huge' (60% confidence, 38 lines)")
    plain = _parse_line("pkg/c.py:1: unused import 'os' (90% confidence)")
    assert small is not None and large is not None and plain is not None, "every Vulture line shape must parse"
    assert (small.size, large.size, plain.size) == (4, 38, 0), (small, large, plain)
    assert sorted([small, plain, large], key=finding_order(True)) == [large, small, plain]
    assert sorted([large, small], key=finding_order(False)) == [small, large], "default order is file, line"
    assert format_finding(large).endswith("(60% confidence, 38 lines)"), format_finding(large)


_VERDICT_SEAM_GATE: Final = "shared-library-verdict-seam"
_PLANTED_GATE_EXIT: Final = 3
_PLANTED_GATE_OUTPUT: Final = "planted gate check failed: boom"
_POWERSHELL_TIMEOUT_SECONDS: Final = 180


def _run_through_the_runner(script: Path) -> tuple[int, str]:
    """(exit code, console) of ``script`` run by ``Invoke-DatrixPythonScript -Gate``."""
    runner = SCRIPTS_DIR / "common" / "DatrixPythonScript.psm1"
    command = (
        f"Import-Module '{runner}'; "
        f"exit (Invoke-DatrixPythonScript -Script '{script}' -Gate '{_VERDICT_SEAM_GATE}')"
    )
    process = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        timeout=_POWERSHELL_TIMEOUT_SECONDS,
        check=False,
    )
    return process.returncode, process.stdout


def check_runner_gate_verdict_is_the_line_the_digest_hook_parses() -> None:
    """The verdict line the runner prints in gate mode is the one the red-run digest hook reads:
    a failing gate's line names its claimed log (holding the child's output), a passing gate's
    line names none."""
    digest_hook = load_hook_module(DIGEST_HOOK_MODULE)
    with TemporaryDirectory(prefix="verdict-seam-") as tmp:
        failing = write_file(
            Path(tmp) / "failing_gate.py",
            f"import sys\nprint({_PLANTED_GATE_OUTPUT!r})\nsys.exit({_PLANTED_GATE_EXIT})\n",
        )
        passing = write_file(Path(tmp) / "passing_gate.py", "print('all checks passed')\n")
        failed_code, failed_console = _run_through_the_runner(failing)
        passed_code, passed_console = _run_through_the_runner(passing)
    failed_logs = [red_log.log for red_log in digest_hook.failed_gate_logs(failed_console)]
    passed_logs = digest_hook.failed_gate_logs(passed_console)
    claimed = [Path(line.rsplit("log=", 1)[1].strip()) for line in (failed_console + passed_console).splitlines()
               if line.startswith(f"[GATE] {_VERDICT_SEAM_GATE} ")]
    try:
        assert failed_code == _PLANTED_GATE_EXIT, f"the runner returned {failed_code}, expected the child's exit"
        assert len(failed_logs) == 1, f"the hook read {failed_logs} from the failing gate's console:\n{failed_console}"
        log_text = failed_logs[0].read_text(encoding="utf-8")
        assert _PLANTED_GATE_OUTPUT in log_text, f"the claimed log {failed_logs[0]} lacks the child's output"
        assert passed_code == 0 and passed_logs == [], (
            f"a passing gate (exit {passed_code}) must give the hook no log to digest: {passed_logs}"
        )
    finally:
        for log in claimed:
            log.unlink(missing_ok=True)


# ---------------------------------------------------------------- gate_log / run_log


_PLANTED_GATE_MODULE: Final = "planted_gate_mode"
_PLANTED_GATE_PROGRAM: Final = (
    "import sys\n"
    "from datrix_scripts.gate_log import run_as_gate\n"
    "def run(argv):\n"
    "    args = list(sys.argv[1:] if argv is None else argv)\n"
    "    print('planted gate output', *args)\n"
    "    print('planted stderr line', file=sys.stderr)\n"
    "    if args == ['crash']:\n"
    "        raise RuntimeError('planted crash')\n"
    "    return int(args[0]) if args else 0\n"
    f"sys.exit(run_as_gate({_VERDICT_SEAM_GATE!r}, {_PLANTED_GATE_MODULE!r}, run))\n"
)
_PINNED_RUN_LOG_TIME: Final = datetime(2026, 1, 2, 3, 4, 5)
_HOSTILE_LABEL: Final = "..\\a b:/c*"
_CLAIM_RACERS: Final = 16


def _run_planted_gate(package_root: Path, *arguments: str) -> tuple[int, str]:
    """(exit code, console) of the planted gate module run with ``-m`` like a rendered wrapper runs it."""
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join([str(package_root), str(PYTHONPATH_ROOT)])}
    environment.pop(GATE_CHILD_ENV, None)
    process = subprocess.run(
        [sys.executable, "-m", _PLANTED_GATE_MODULE, *arguments],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=_POWERSHELL_TIMEOUT_SECONDS,
        check=False,
    )
    return process.returncode, process.stdout


def _verdict_logs(console: str) -> list[Path]:
    return [Path(line.rsplit("log=", 1)[1].strip()) for line in console.splitlines()
            if line.startswith(f"[GATE] {_VERDICT_SEAM_GATE} ")]


def check_gate_mode_verdict_is_the_line_the_digest_hook_parses() -> None:
    """A module run in gate mode (``gate_log.run_as_gate``) relays its output, stdout and stderr, to
    the console and a claimed log under ``.test-output/gates/<gate>/``, and ends on the verdict line
    the red-run digest hook reads: FAILED with the child's exit code (a crash included), PASSED for
    exit 0, which gives the hook no log to digest."""
    digest_hook = load_hook_module(DIGEST_HOOK_MODULE)
    with TemporaryDirectory(prefix="gate-mode-") as tmp:
        write_file(Path(tmp) / f"{_PLANTED_GATE_MODULE}.py", _PLANTED_GATE_PROGRAM)
        runs = {label: _run_planted_gate(Path(tmp), *arguments)
                for label, arguments in (("failing", (str(_PLANTED_GATE_EXIT),)), ("crashing", ("crash",)), ("passing", ()))}
    claimed = [log for _code, console in runs.values() for log in _verdict_logs(console)]
    try:
        failed_code, failed_console = runs["failing"]
        assert failed_code == _PLANTED_GATE_EXIT, f"gate mode returned {failed_code}, expected the child's exit:\n{failed_console}"
        assert failed_console.rstrip().splitlines()[-1].startswith(f"[GATE] {_VERDICT_SEAM_GATE} FAILED exit={_PLANTED_GATE_EXIT} log="), (
            f"the verdict line is not the last line of the failing run:\n{failed_console}"
        )
        failed_logs = [red_log.log for red_log in digest_hook.failed_gate_logs(failed_console)]
        assert len(failed_logs) == 1, f"the hook read {failed_logs} from the failing gate's console:\n{failed_console}"
        assert failed_logs[0].parent == gate_log_directory(_VERDICT_SEAM_GATE).resolve(), (
            f"the log {failed_logs[0]} is not under {gate_log_directory(_VERDICT_SEAM_GATE)}"
        )
        log_text = failed_logs[0].read_text(encoding="utf-8")
        assert "planted gate output" in log_text and "planted stderr line" in log_text, (
            f"the claimed log {failed_logs[0]} lacks the child's stdout or stderr:\n{log_text}"
        )
        crash_code, crash_console = runs["crashing"]
        assert crash_code != 0 and len(digest_hook.failed_gate_logs(crash_console)) == 1, (
            f"a crashing gate (exit {crash_code}) must end on a FAILED verdict line:\n{crash_console}"
        )
        passed_code, passed_console = runs["passing"]
        assert passed_code == 0 and digest_hook.failed_gate_logs(passed_console) == [], (
            f"a passing gate (exit {passed_code}) must give the hook no log to digest:\n{passed_console}"
        )
        assert f"[GATE] {_VERDICT_SEAM_GATE} PASSED exit=0 log=" in passed_console, (
            f"a passing gate printed no PASSED verdict line:\n{passed_console}"
        )
    finally:
        for log in claimed:
            log.unlink(missing_ok=True)


def check_gate_log_verdict_and_directory_refuse_nothing_silently() -> None:
    """``verdict_line`` says PASSED for exit 0 only; a gate name with no letter or digit is refused."""
    log = Path("x.log")
    assert verdict_line("g", 0, log).startswith("[GATE] g PASSED exit=0 log="), verdict_line("g", 0, log)
    assert verdict_line("g", -1, log).startswith("[GATE] g FAILED exit=-1 log="), verdict_line("g", -1, log)
    try:
        gate_log_directory("..\\")
    except ValueError:
        return
    raise AssertionError("gate_log_directory accepted a gate name with no letter or digit")


def check_run_log_names_are_contained_and_ordered() -> None:
    """A run-log name is ``prefix-<yyyyMMdd-HHmmss>[-segment...]``; a hostile label collapses to dashes
    (no separator, colon, dot-dot or wildcard survives) and an empty segment is dropped."""
    name = run_log_base_name("unit", [_HOSTILE_LABEL, "", "?"], timestamp=_PINNED_RUN_LOG_TIME)
    assert name == "unit-20260102-030405-a-b-c", f"run_log_base_name gave {name!r}"
    assert run_log_segment(_HOSTILE_LABEL) == "a-b-c", run_log_segment(_HOSTILE_LABEL)


def check_run_log_claims_are_exclusive_under_a_race() -> None:
    """Racing claims of one base name each get a different file (base, base-2, ...); an existing file
    is never handed out again; when every name is taken the claim raises instead of reusing one."""
    with TemporaryDirectory(prefix="run-log-claim-") as tmp:
        directory = Path(tmp) / "nested"
        with ThreadPoolExecutor(max_workers=_CLAIM_RACERS) as pool:
            claims = list(pool.map(lambda _index: claim_run_log_file(directory, "race"), range(_CLAIM_RACERS)))
        expected = {"race.log", *(f"race-{attempt}.log" for attempt in range(2, _CLAIM_RACERS + 1))}
        assert {claim.name for claim in claims} == expected, f"racing claims gave {sorted(c.name for c in claims)}"
        full = Path(tmp) / "full"
        full.mkdir()
        for attempt in range(1, MAX_CLAIM_ATTEMPTS + 1):
            (full / (f"taken{'' if attempt == 1 else f'-{attempt}'}.log")).touch()
        try:
            claim_run_log_file(full, "taken")
        except RuntimeError:
            return
    raise AssertionError("claim_run_log_file reused a name when every candidate was taken")


# ---------------------------------------------------------------- cognitive complexity


_IMPORT_BOUNDARIES_DIR: Final = PYTHONPATH_ROOT / "datrix_scripts" / "scan" / "import_boundaries"
_HELD_CLEAN_SINGLE_MODULES: Final = (
    PYTHONPATH_ROOT / "datrix_scripts" / "test" / "run_complete.py",
    HOOKS_DIR / "checklist.py",
    HOOKS_DIR / "guard-predeploy-analysis.py",
)
_PLANTED_OVER_LIMIT_FUNCTION: Final = "planted_branchy"


def _held_clean_modules() -> list[Path]:
    """The script modules held at or under the cognitive-complexity limit, every one present."""
    package_modules = sorted(_IMPORT_BOUNDARIES_DIR.glob("*.py"))
    assert package_modules, f"no modules found under {_IMPORT_BOUNDARIES_DIR}"
    held = [*package_modules, *_HELD_CLEAN_SINGLE_MODULES]
    missing = [str(path) for path in held if not path.is_file()]
    assert not missing, f"held-clean modules are missing (moved or renamed?): {missing}"
    return held


def _over_limit(files: list[Path]) -> list[tuple[str, str, int, int]]:
    """Every function over the limit in ``files``; a file that does not parse fails the check,
    since the measurement skips it silently."""
    for path in files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return run_check_cognitive(None, DEFAULT_MAX_COMPLEXITY, (), False, files=files)


def check_held_clean_modules_stay_within_cognitive_complexity() -> None:
    """No function of the held-clean script modules exceeds the cognitive-complexity limit."""
    violations = _over_limit(_held_clean_modules())
    assert not violations, (
        f"functions over cognitive complexity {DEFAULT_MAX_COMPLEXITY}; split them into named "
        "helpers: " + "; ".join(f"{path}:{line} {name} ({score})" for path, name, line, score in violations)
    )


def check_cognitive_complexity_check_reports_a_planted_function() -> None:
    """The measurement the held-clean check relies on reports a planted function over the limit."""
    nested = "".join(
        f"{'    ' * (depth + 1)}if value > {depth}:\n" for depth in range(DEFAULT_MAX_COMPLEXITY)
    )
    body = f"{nested}{'    ' * (DEFAULT_MAX_COMPLEXITY + 1)}return value\n    return 0\n"
    with TemporaryDirectory(prefix="cognitive-complexity-") as tmp:
        planted = write_file(
            Path(tmp) / "planted.py", f"def {_PLANTED_OVER_LIMIT_FUNCTION}(value: int) -> int:\n{body}"
        )
        violations = _over_limit([planted])
    names = [name for _path, name, _line, _score in violations]
    assert names == [_PLANTED_OVER_LIMIT_FUNCTION], f"the planted function was not reported: {violations}"


def checks() -> list[NamedCheck]:
    """Every check of this module, the census self-tests included, in run order."""
    module_checks = [
        check_gate_harness_reports_each_check_and_the_overall_verdict,
        check_gate_harness_lets_a_non_assertion_error_propagate,
        check_gate_harness_self_test_detects_a_failure,
        check_gate_harness_argument_parser_carries_the_shared_flags,
        check_gate_harness_writes_planted_files,
        check_gate_harness_debug_flag_follows_the_wrapper,
        check_gate_log_verdict_and_directory_refuse_nothing_silently,
        check_run_log_names_are_contained_and_ordered,
        check_run_log_claims_are_exclusive_under_a_race,
        check_count_ratchet_tighten_only,
        check_count_ratchet_exact_pin,
        check_count_ratchet_reader_fails_closed,
        check_run_complete_discovers_projects_by_their_test_runner,
        check_run_complete_runs_every_project_through_its_test_entry_point,
        check_dead_code_report_reads_and_orders_vulture_sizes,
        check_cognitive_complexity_check_reports_a_planted_function,
    ]
    real_tree = [
        check_scripts_tree_censuses_are_zero,
        check_hooks_name_no_retired_root_resolver,
        check_every_shared_module_imports_in_a_fresh_interpreter,
        check_every_hook_consumed_shared_module_is_exercised_by_a_gate,
        check_runner_gate_verdict_is_the_line_the_digest_hook_parses,
        check_gate_mode_verdict_is_the_line_the_digest_hook_parses,
        check_held_clean_modules_stay_within_cognitive_complexity,
    ]
    return [
        *(NamedCheck(check.__name__, check) for check in module_checks),
        *(NamedCheck(f"check_{check.name}", check.run) for check in census_self_test_checks()),
        *(NamedCheck(check.__name__, check) for check in real_tree),
    ]
