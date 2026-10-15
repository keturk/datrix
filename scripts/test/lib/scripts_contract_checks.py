"""Shared-library gate checks for the scripts tree's shared contracts.

Run by ``shared_library_gate.py`` beside its module checks:

* ``datrix_scripts.gate_harness`` -- the one check loop, its non-vacuity proof, the shared flags
  and the fixture writer;
* ``datrix_scripts.count_ratchet`` -- the two ratchet semantics and the fail-closed baseline
  reader;
* the scripts-tree censuses (``scripts_tree_census``): each reports a planted copy, and the real
  tree stays at or under its baseline;
* every ``datrix_scripts`` module imports as the first import of a fresh interpreter, and every
  module a hook imports is exercised by a gate (``consumed - covered`` is empty). Hooks fail
  open, so a broken import would disable a hook silently.
"""

from __future__ import annotations

import ast
import contextlib
import io
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

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
from datrix_scripts.dead_code_report import _parse_line, finding_order, format_finding
from datrix_scripts.gate_harness import (
    NamedCheck,
    gate_argument_parser,
    harness_self_test,
    run_checks,
    write_file,
    write_files,
)
from datrix_scripts.hook_modules import DIGEST_HOOK_MODULE, load_hook_module
from datrix_scripts.paths import PACKAGE_DIR, PYTHONPATH_ROOT, SCRIPTS_DIR, SHOWCASE_DIR
from run_complete import _generated_projects
from scripts_tree_census import census_failures, python_modules, python_root_resolvers, run_censuses
from scripts_tree_census import self_test_checks as census_self_test_checks

HOOKS_DIR: Final = SHOWCASE_DIR / "claude-config" / ".claude" / "hooks"
_SHARED_PACKAGE: Final = "datrix_scripts"
_HOOK_TEST_PREFIX: Final = "test-"
_GATE_OWNER_FOLDERS: Final = ("test", "dev", "skill", "tasks", "git", "review")
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
    relative = path.relative_to(scripts_dir).parts
    if relative[0] == "gates" and len(relative) >= 3 and relative[2] == "lib":
        return True
    return relative[0] in _GATE_OWNER_FOLDERS and "gate" in path.stem


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
    consumed = hook_consumed_modules(HOOKS_DIR)
    assert consumed, f"no hook under {HOOKS_DIR} imports a shared module; the census reads nothing"
    uncovered = _uncovered(consumed, gate_covered_modules(SCRIPTS_DIR))
    assert not uncovered, (
        f"shared modules a hook imports that no gate exercises: {uncovered}. Hooks fail open, so a "
        "break in one would disable the hook silently. Fix: import the module in a gate check, or "
        "give it a top-level self_test."
    )


_RUNNER_WITH_DEPLOY = "param(\n    [switch]$Unit,\n    [switch]$Deploy\n)\n"
_RUNNER_WITHOUT_DEPLOY = "param(\n    [switch]$Unit\n)\n"


def check_run_complete_discovers_projects_by_their_test_runner() -> None:
    """Steps 3 and 4 find a generated project by its emitted tests/run-tests.ps1, whatever language
    generated it: both planted projects for unit tests, only the one whose runner declares
    -Deploy for deploy tests."""
    with TemporaryDirectory(prefix="run-complete-projects-") as tmp:
        generated = Path(tmp) / ".generated"
        write_files(
            generated,
            {
                "lang-a/docker/local/shop/tests/run-tests.ps1": _RUNNER_WITH_DEPLOY,
                "lang-b/docker/local/catalog/tests/run-tests.ps1": _RUNNER_WITHOUT_DEPLOY,
                "lang-b/docker/local/catalog/scripts/run-tests.ps1": _RUNNER_WITH_DEPLOY,
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


def checks() -> list[NamedCheck]:
    """Every check of this module, the census self-tests included, in run order."""
    module_checks = [
        check_gate_harness_reports_each_check_and_the_overall_verdict,
        check_gate_harness_lets_a_non_assertion_error_propagate,
        check_gate_harness_self_test_detects_a_failure,
        check_gate_harness_argument_parser_carries_the_shared_flags,
        check_gate_harness_writes_planted_files,
        check_count_ratchet_tighten_only,
        check_count_ratchet_exact_pin,
        check_count_ratchet_reader_fails_closed,
        check_run_complete_discovers_projects_by_their_test_runner,
        check_dead_code_report_reads_and_orders_vulture_sizes,
    ]
    real_tree = [
        check_scripts_tree_censuses_are_zero,
        check_hooks_name_no_retired_root_resolver,
        check_every_shared_module_imports_in_a_fresh_interpreter,
        check_every_hook_consumed_shared_module_is_exercised_by_a_gate,
        check_runner_gate_verdict_is_the_line_the_digest_hook_parses,
    ]
    return [
        *(NamedCheck(check.__name__, check) for check in module_checks),
        *(NamedCheck(f"check_{check.name}", check.run) for check in census_self_test_checks()),
        *(NamedCheck(check.__name__, check) for check in real_tree),
    ]
