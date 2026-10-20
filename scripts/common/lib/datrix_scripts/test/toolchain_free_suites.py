"""Fail if a framework test suite compiles or executes generated output.

A ``datrix-*/tests/`` suite exists to prove that **datrix functionality** works
-- that the generator emits the right thing. Whether the emitted output then
compiles and runs in its target language belongs to the *generated* tier: the
generated project's own unit tests, and the deploy tests.

Keeping that line is not a style preference. A framework suite that shells out
to a language toolchain has to install one, so its result stops depending only
on the code under test: a cold Maven Central fetch with no timeout once wedged
a package's suite at 99% for an hour with no error text, and the same suite
runs in under a minute once the compile legs are gone.

Four shapes fail this gate:

1. **Toolchain subprocess** -- ``javac``, ``java``, ``mvn``/``mvnw``,
   ``dotnet``, ``tsc``, ``npm``/``npx``, ``node``, ``docker``, ``az``,
   ``gradle`` launched against generated output.
2. **In-process execution** -- ``exec(compile(...))``, ``runpy``, or
   ``importlib``'s ``spec_from_file_location``/``exec_module`` applied to a
   rendered template, then calling into it. No toolchain is involved; the
   principle is identical.
3. **Suite-in-suite (pytest)** -- a ``subprocess`` call spawning a nested
   pytest session against a repo test path (``pytest``/``py.test`` as argv[0],
   or the ``[sys.executable, "-m", "pytest", ...]`` module form). The suite
   already pays for that test elsewhere in the same run; spawning it again
   pays twice for work already covered.
4. **Suite-in-suite (script)** -- a ``subprocess`` call naming any script
   under ``datrix/scripts/`` (directly, or via ``powershell -File``),
   re-running a repo gate or metrics script a sibling gate already pays for.

Both new shapes carve out ``pytester``-based synthetic suites (pytest's own
plugin, which launches a nested run against a SYNTHETIC tree written to a tmp
dir -- a meta-test of a grouping/pooling primitive, never a suite re-running
this repo's own production tests): a test function taking a ``pytester``
fixture parameter, or a direct ``pytester.runpytest*(...)`` attribute call.
Use ``--shapes suite-in-suite-pytest,suite-in-suite-script`` to enforce only
the two new shapes at hard zero, independently of the pre-existing
toolchain-subprocess/in-process-execution counts.

Two shapes are allowed and must stay allowed:

- **Linters over generated text.** ``ruff``/``black`` read the emitted source;
  reading is not executing.
- **Running datrix itself.** ``sys.executable -m datrix_cli`` and the
  import-boundary probes run the framework, not its output.

Run through ``test/toolchain-free-suites-gate.ps1`` (or its ``.sh`` twin), in gate mode: the last line is the
verdict. Every run proves the detector non-vacuous before it scans; ``--self-test`` runs only that proof and the
wrapper seam checks. ``--suites`` names a suite that is not a directory, or ``--shapes`` a kind that does not
exist: a usage error (exit 2), never a scan of fewer suites or kinds than named.
"""

from __future__ import annotations

import argparse
import ast
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from datrix_scripts.framework_repos import PackageMarker, workspace_package_dirs
from datrix_scripts.gate_harness import EXIT_PASS, EXIT_VIOLATION, UsageError, expect_usage_error, run_main
from datrix_scripts.gate_log import run_as_gate
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.test import ensure_packages
from datrix_scripts.test.wrappers import run_self_test
from datrix_scripts.venv import require_packages

MODULE = "datrix_scripts.test.toolchain_free_suites"
WRAPPER = "toolchain-free-suites-gate"
GATE = "toolchain-free-suites"

#: The violation kinds, each a shape the module docstring describes (``unparseable``: a test file the scan could
#: not read, which fails rather than passes).
KIND_TOOLCHAIN_SUBPROCESS = "toolchain-subprocess"
KIND_IN_PROCESS_EXECUTION = "in-process-execution"
KIND_SUITE_IN_SUITE_PYTEST = "suite-in-suite-pytest"
KIND_SUITE_IN_SUITE_SCRIPT = "suite-in-suite-script"
KIND_UNPARSEABLE = "unparseable"
VIOLATION_KINDS: tuple[str, ...] = (
    KIND_TOOLCHAIN_SUBPROCESS,
    KIND_IN_PROCESS_EXECUTION,
    KIND_SUITE_IN_SUITE_PYTEST,
    KIND_SUITE_IN_SUITE_SCRIPT,
    KIND_UNPARSEABLE,
)

#: Executables whose presence in argv[0] means a language/platform toolchain is
#: being driven. Matched on the basename, so an absolute path still trips it.
TOOLCHAIN_EXECUTABLES: frozenset[str] = frozenset({
    "javac", "java", "jar", "mvn", "mvnw", "mvnw.cmd", "gradle", "gradlew",
    "dotnet", "csc", "msbuild",
    "tsc", "tsx", "npm", "npx", "node", "yarn", "pnpm",
    "docker", "docker-compose", "podman",
    "az", "aws", "gcloud", "kubectl", "terraform", "bicep",
})

#: Tools that only READ generated text. Never a violation.
READ_ONLY_TOOLS: frozenset[str] = frozenset({"ruff", "black", "isort", "mypy"})

#: Callables that execute source in this process.
IN_PROCESS_EXECUTORS: frozenset[str] = frozenset({
    "exec", "exec_module", "spec_from_file_location", "run_path", "run_module",
})

#: `subprocess` entry points.
SUBPROCESS_RUNNERS: frozenset[str] = frozenset({
    "run", "Popen", "call", "check_call", "check_output",
})

#: The repo-path segment identifying a `datrix/scripts/...` invocation, forward-
#: slash form (argv text is normalized to forward slashes before this is matched).
_REPO_SCRIPTS_SEGMENT: str = "datrix/scripts/"

#: pytest's own CLI spellings this gate treats as "running pytest itself".
_PYTEST_INVOCATION_NAMES: frozenset[str] = frozenset({"pytest", "py.test"})

#: Module prefixes that identify datrix's own code. A `sys.executable` call
#: that runs one of these is running the framework, not generated output.
DATRIX_MODULE_PREFIXES: tuple[str, ...] = ("datrix", "tests.")


class Violation:
    """One offending call site."""

    def __init__(self, path: Path, line: int, kind: str, detail: str) -> None:
        self.path = path
        self.line = line
        self.kind = kind
        self.detail = detail

    def __str__(self) -> str:
        return f"{self.path.as_posix()}:{self.line}: {self.kind} -- {self.detail}"


def _literal_strings(node: ast.AST) -> list[str]:
    return [
        n.value for n in ast.walk(node)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


def _argv0(call: ast.Call) -> str | None:
    """Return argv[0] as a basename when it is a literal, else None."""
    if not call.args:
        return None
    first = call.args[0]
    if isinstance(first, (ast.List, ast.Tuple)):
        if not first.elts:
            return None
        first = first.elts[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return Path(first.value.lstrip("./")).name.lower()
    return None


def _uses_pytester_fixture(enclosing: ast.AST | None) -> bool:
    """True when the enclosing test function declares a ``pytester`` parameter.

    ``pytester`` (pytest's own plugin, enabled in ``datrix-common/conftest.py``)
    spins up a nested, IN-PROCESS-launched pytest run against a synthetic tree
    written to a tmp dir -- it is a meta-test of a grouping/pooling primitive,
    never a suite re-running THIS repo's own production tests. Its subprocess
    variant (``runpytest_subprocess``) still launches a real child process, so
    it must be told apart from a bare ``subprocess.run([..., "pytest", ...])``
    by the ENCLOSING FUNCTION's own parameter list, not by the call shape.
    """
    if not isinstance(enclosing, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    return any(arg.arg == "pytester" for arg in enclosing.args.args)


def _is_pytester_method_call(call: ast.Call) -> bool:
    """True for ``pytester.runpytest_subprocess(...)``/``pytester.runpytest(...)``
    -- the attribute-call shape ``pytester``'s own API uses, told apart from a
    bare ``subprocess.run([..., "pytest", ...])`` by the receiver name."""
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr in ("runpytest_subprocess", "runpytest", "runpytest_inprocess")
        and isinstance(func.value, ast.Name)
        and func.value.id == "pytester"
    )


#: The path segments a subprocess argv must name -- as one joined literal
#: (``"datrix/scripts/..."``) OR as their own separate literals (the shape a
#: ``Path(...) / "datrix" / "scripts" / ... / "x.ps1"`` join produces, one
#: ``ast.Constant`` per segment) -- alongside a script-shaped literal, to
#: count as naming a repo script.
_REPO_SCRIPTS_SEGMENTS: frozenset[str] = frozenset({"datrix", "scripts"})


def _argv_names_repo_script(call: ast.Call) -> str | None:
    """Return the repo-relative script path a subprocess argv names, or None.

    Matches when the call's own literals -- taken together, since a path is
    as often assembled as ``Path(...) / "datrix" / "scripts" / ... /
    "x.ps1"`` (one string constant per path segment) as written as a single
    joined string -- name BOTH a script file (a literal ending in ``.ps1`` or
    ``.py``) and the ``datrix``/``scripts`` segments, either joined in one
    literal (``"datrix/scripts/..."``/``"datrix\\scripts\\..."``) or present
    as their own separate literals. This stays Call-node-local -- every
    literal considered comes from this same subprocess call's own argument
    expression, never a variable resolved from a prior statement. Never
    matches a bare tool name (``pytest``, ``ruff``) with no such path.
    """
    literals = _literal_strings(call)
    normalized = [text.replace("\\", "/") for text in literals]
    script_literal = next(
        (raw for raw, norm in zip(literals, normalized) if norm.lower().endswith((".ps1", ".py"))),
        None,
    )
    if script_literal is None:
        return None
    joined_hit = any(_REPO_SCRIPTS_SEGMENT in norm.lower() for norm in normalized)
    segments_present = {norm.lower() for norm in normalized} >= _REPO_SCRIPTS_SEGMENTS
    if joined_hit or segments_present:
        return script_literal
    return None


def _argv_runs_pytest(call: ast.Call) -> bool:
    """True when a subprocess argv runs pytest against a real invocation
    shape: ``["pytest", ...]``/``["py.test", ...]`` as argv[0], OR
    ``[sys.executable, "-m", "pytest", ...]`` (the interpreter-module form)."""
    argv0 = _argv0(call)
    if argv0 in _PYTEST_INVOCATION_NAMES:
        return True
    literals = _literal_strings(call)
    return "-m" in literals and any(name in literals for name in _PYTEST_INVOCATION_NAMES)


def _is_suite_in_suite(call: ast.Call, enclosing: ast.AST | None) -> tuple[bool, str, str]:
    """Detect a test spawning another pytest session or a repo gate/metrics script.

    Returns ``(hit, kind, detail)``. ``pytester``-based synthetic suites (the
    fixture-parameter shape OR the attribute-call shape) are explicitly out of
    scope -- see ``_uses_pytester_fixture``/``_is_pytester_method_call``.
    """
    func = call.func
    is_subprocess_call = (
        isinstance(func, ast.Attribute)
        and func.attr in SUBPROCESS_RUNNERS
        and isinstance(func.value, ast.Name)
        and func.value.id == "subprocess"
    )
    if _is_pytester_method_call(call):
        return False, "", ""
    if is_subprocess_call and _uses_pytester_fixture(enclosing):
        return False, "", ""
    if not is_subprocess_call:
        return False, "", ""

    script_path = _argv_names_repo_script(call)
    if script_path is not None:
        return True, KIND_SUITE_IN_SUITE_SCRIPT, f"subprocess runs repo script '{script_path}'"
    if _argv_runs_pytest(call):
        return True, KIND_SUITE_IN_SUITE_PYTEST, "subprocess runs a nested pytest session"
    return False, "", ""


def _runs_datrix_itself(call: ast.Call) -> bool:
    """True when the command runs a datrix module through this interpreter."""
    argv = call.args[0] if call.args else None
    if not isinstance(argv, (ast.List, ast.Tuple)):
        return False
    head = argv.elts[0] if argv.elts else None
    is_interpreter = (
        isinstance(head, ast.Attribute) and head.attr == "executable"
    ) or (
        isinstance(head, ast.Constant)
        and isinstance(head.value, str)
        and Path(head.value).name.lower().startswith("python")
    )
    if not is_interpreter:
        return False
    return any(
        text.startswith(DATRIX_MODULE_PREFIXES) or "import datrix" in text
        for text in _literal_strings(argv)
    )


def _is_toolchain_subprocess(call: ast.Call) -> tuple[bool, str]:
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr not in SUBPROCESS_RUNNERS:
        return False, ""
    if not (isinstance(func.value, ast.Name) and func.value.id == "subprocess"):
        return False, ""
    if _runs_datrix_itself(call):
        return False, ""

    argv0 = _argv0(call)
    if argv0 is None:
        # A computed command (`[str(mvnw), ...]`, `[dotnet_executable(), ...]`)
        # is the usual shape once a helper resolves the tool, so fall back to
        # the literals anywhere in the call.
        for text in _literal_strings(call):
            name = Path(text.lstrip("./")).name.lower()
            if name in READ_ONLY_TOOLS:
                return False, ""
            if name in TOOLCHAIN_EXECUTABLES:
                return True, f"subprocess runs '{text}'"
        return False, ""
    if argv0 in READ_ONLY_TOOLS:
        return False, ""
    if argv0 in TOOLCHAIN_EXECUTABLES:
        return True, f"subprocess runs '{argv0}'"
    return False, ""


def _is_in_process_execution(call: ast.Call, enclosing: ast.AST | None) -> tuple[bool, str]:
    func = call.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    if name not in IN_PROCESS_EXECUTORS:
        return False, ""
    if enclosing is not None and _loads_a_peer_test_module(enclosing):
        # Importing a sibling `test_*.py` for a shared harness is loading THIS
        # suite's own code, not generated output.
        return False, ""
    return True, f"{name}() executes source in this process"


def _loads_a_peer_test_module(scope: ast.AST) -> bool:
    return any(
        Path(text).name.startswith("test_") and text.endswith(".py")
        for text in _literal_strings(scope)
    )


def scan_source(path: Path) -> list[Violation]:
    """Return every violation in *path*."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except SyntaxError as exc:
        return [Violation(path, exc.lineno or 1, KIND_UNPARSEABLE, str(exc))]

    scope_of: dict[ast.Call, ast.AST] = {}
    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(scope):
            if isinstance(inner, ast.Call):
                scope_of.setdefault(inner, scope)

    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        hit, detail = _is_toolchain_subprocess(node)
        if hit:
            violations.append(Violation(path, node.lineno, KIND_TOOLCHAIN_SUBPROCESS, detail))
            continue
        hit, kind, detail = _is_suite_in_suite(node, scope_of.get(node))
        if hit:
            violations.append(Violation(path, node.lineno, kind, detail))
            continue
        hit, detail = _is_in_process_execution(node, scope_of.get(node))
        if hit:
            violations.append(Violation(path, node.lineno, KIND_IN_PROCESS_EXECUTION, detail))
    return violations


def scan_suite(tests_dir: Path) -> list[Violation]:
    violations: list[Violation] = []
    for source in sorted(tests_dir.rglob("*.py")):
        violations.extend(scan_source(source))
    return violations


_OFFENDER = '''\
import subprocess
subprocess.run(["javac", "-d", "out", "Thing.java"], check=True)
'''

_IN_PROCESS_OFFENDER = '''\
namespace = {}
exec(compile(open("generated.py").read(), "generated.py", "exec"), namespace)
'''

_ALLOWED = '''\
import subprocess
import sys
subprocess.run([sys.executable, "-m", "datrix_cli", "--help"], check=True)
subprocess.run(["ruff", "check", "generated/"], check=True)
'''

_SUITE_IN_SUITE_PYTEST_OFFENDER = '''\
import subprocess
import sys

def test_census_still_passes():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/unit/test_sibling.py"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
'''

_SUITE_IN_SUITE_SCRIPT_OFFENDER = '''\
import subprocess

def test_gate_self_test_still_passes():
    result = subprocess.run(
        ["powershell", "-File", "d:/datrix/datrix/scripts/gates/parity/behaviour-parity-gate.ps1", "-SelfTest"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
'''

_PYTESTER_FIXTURE_ALLOWED = '''\
def test_xdist_pooling_under_real_dist_loadgroup(pytester):
    result = pytester.runpytest_subprocess("-n", "2", "--dist", "loadgroup")
    result.assert_outcomes(passed=4)
'''

_PYTESTER_METHOD_ALLOWED = '''\
import pytest

def test_inline_pooling_proof():
    pytester = pytest.Pytester(None, None, None)  # illustrative receiver name only
    result = pytester.runpytest("-p", "no:cacheprovider")
    assert result.ret == 0
'''


#: Each planted file, its body and the kind the detector must report on it (None: it must report nothing).
_DETECTOR_CASES: tuple[tuple[str, str, str | None], ...] = (
    ("offender.py", _OFFENDER, KIND_TOOLCHAIN_SUBPROCESS),
    ("in_process.py", _IN_PROCESS_OFFENDER, KIND_IN_PROCESS_EXECUTION),
    ("allowed.py", _ALLOWED, None),
    ("suite_in_suite_pytest.py", _SUITE_IN_SUITE_PYTEST_OFFENDER, KIND_SUITE_IN_SUITE_PYTEST),
    ("suite_in_suite_script.py", _SUITE_IN_SUITE_SCRIPT_OFFENDER, KIND_SUITE_IN_SUITE_SCRIPT),
    ("pytester_fixture_allowed.py", _PYTESTER_FIXTURE_ALLOWED, None),
    ("pytester_method_allowed.py", _PYTESTER_METHOD_ALLOWED, None),
)

_DETECTOR_PASSED = (
    "Self-test passed: detector fires on toolchain-subprocess, in-process-execution, "
    "suite-in-suite-pytest and suite-in-suite-script, and spares pytester-based synthetic suites."
)


def detector_failures() -> list[str]:
    """Each planted case the detector gets wrong: a forbidden shape it misses, or an allowed one it reports."""
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, body, expect in _DETECTOR_CASES:
            target = root / name
            target.write_text(body, encoding="utf-8")
            found = scan_source(target)
            kinds = {v.kind for v in found}
            if expect is None and found:
                failures.append(f"{name}: expected no violation, got {[str(v) for v in found]}")
            elif expect is not None and expect not in kinds:
                failures.append(f"{name}: expected a {expect} violation, got {sorted(kinds)}")
    return failures


def _check_detector_classifies_every_shape() -> None:
    failures = detector_failures()
    assert not failures, f"the detector is not trustworthy: {'; '.join(failures)}"


def _check_suites_and_shapes_name_what_exists() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        suite = Path(tmp)
        missing = suite / "no-such-tests"
        assert requested_suites(f" {suite} ,") == [suite], "a named directory must be scanned"
        expect_usage_error(lambda: requested_suites(f"{suite},{missing}"), str(missing))
    assert requested_shapes(None) is None and requested_shapes(" , ") is None, "no shape named means every kind"
    assert requested_shapes(KIND_SUITE_IN_SUITE_PYTEST) == {KIND_SUITE_IN_SUITE_PYTEST}
    expect_usage_error(lambda: requested_shapes(f"{KIND_UNPARSEABLE},suite-in-suite"), "suite-in-suite.")


def default_suites(repo_root: Path) -> list[Path]:
    return [
        package / PackageMarker.TESTS.value
        for package in workspace_package_dirs(
            repo_root, any_of=frozenset({PackageMarker.TESTS}), include_showcase=True
        )
        if (package / PackageMarker.TESTS.value).is_dir()
    ]


def _comma_items(text: str | None) -> list[str]:
    return [item.strip() for item in (text or "").split(",") if item.strip()]


def requested_suites(text: str | None) -> list[Path]:
    """The ``tests/`` directories *text* names (comma-separated); empty when it names none.

    Raises:
        UsageError: an entry is not a directory (a scan of fewer suites than named would pass unseen).
    """
    suites = [Path(item) for item in _comma_items(text)]
    missing = [str(suite) for suite in suites if not suite.is_dir()]
    if missing:
        raise UsageError(f"--suites names {len(missing)} path(s) that are not directories: {', '.join(missing)}. "
                         "Expected comma-separated tests/ directories, e.g. D:/datrix/datrix-codegen-typescript/tests; "
                         "omit --suites to scan every package suite.")
    return suites


def requested_shapes(text: str | None) -> frozenset[str] | None:
    """The violation kinds *text* names (comma-separated), or None for every kind.

    Raises:
        UsageError: an entry is not a violation kind (a filter naming nothing would pass every scan).
    """
    shapes = frozenset(_comma_items(text))
    if not shapes:
        return None
    unknown = sorted(shapes.difference(VIOLATION_KINDS))
    if unknown:
        raise UsageError(f"--shapes names unknown kind(s): {', '.join(unknown)}. "
                         f"Valid kinds: {', '.join(VIOLATION_KINDS)}. Pass a comma-separated subset, or omit --shapes "
                         "for all of them.")
    return shapes


def _filter_by_shapes(
    violations: list[Violation], allowed_kinds: frozenset[str] | None
) -> list[Violation]:
    """Narrow *violations* to *allowed_kinds*, printing a per-kind count
    census first (including kinds excluded by the filter) so a filtered run
    still shows what exists outside its own scope."""
    if allowed_kinds is None:
        return violations
    by_kind: dict[str, int] = {}
    for v in violations:
        by_kind[v.kind] = by_kind.get(v.kind, 0) + 1
    for kind in sorted(by_kind):
        marker = "" if kind in allowed_kinds else "  [not enforced by --shapes]"
        print(f"  ({kind}: {by_kind[kind]} occurrence(s)){marker}")
    return [v for v in violations if v.kind in allowed_kinds]


def build_parser() -> argparse.ArgumentParser:
    """The options of ``test/toolchain-free-suites-gate.ps1``: one per wrapper parameter, spelled exactly (it has no
    debug parameter)."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER,
        description="Fail if a framework test suite compiles or executes generated output, or re-runs another "
        "suite or gate.",
        allow_abbrev=False,
    )
    parser.set_defaults(debug=False)
    parser.add_argument(
        "--suites",
        metavar="DIRS",
        help="Comma-separated tests/ directories to scan (default: every datrix-* package's suite).",
    )
    parser.add_argument(
        "--shapes",
        metavar="KINDS",
        help=(
            f"Comma-separated violation kinds to report (default: all; valid: {', '.join(VIOLATION_KINDS)}). "
            "E.g. --shapes suite-in-suite-pytest,suite-in-suite-script to enforce "
            "the new shapes at hard zero independently of the pre-existing, still-red "
            "in-process-execution/toolchain-subprocess counts."
        ),
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the detector's non-vacuity proof and the wrapper seam checks.",
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test(
            [_check_detector_classifies_every_shape, _check_suites_and_shapes_name_what_exists],
            wrapper=WRAPPER,
            module=MODULE,
            parser=build_parser(),
        )
    named_suites = requested_suites(args.suites)
    allowed_kinds = requested_shapes(args.shapes)
    if not ensure_packages(os.environ, require_packages):
        return EXIT_VIOLATION
    failures = detector_failures()
    if failures:
        print("SELF-TEST FAILED -- the detector is not trustworthy:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return EXIT_VIOLATION
    print(_DETECTOR_PASSED)

    suites = named_suites or default_suites(WORKSPACE_DIR)
    if not suites:
        print("No test suites found to scan.", file=sys.stderr)
        return EXIT_VIOLATION
    violations = _filter_by_shapes([v for suite in suites for v in scan_suite(suite)], allowed_kinds)
    return _report(violations, allowed_kinds, len(suites))


def _report(violations: list[Violation], allowed_kinds: frozenset[str] | None, suite_count: int) -> int:
    if violations:
        print(
            f"\n{len(violations)} framework test(s) compile or execute generated output, "
            "or re-run another suite/gate.\n"
            "That belongs to the generated project's own tests and the deploy tests, "
            "or is already paid for by the suite/gate being re-run -- "
            "assert on the emitted source in-process instead.\n",
            file=sys.stderr,
        )
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        return EXIT_VIOLATION

    scope_label = ", ".join(sorted(allowed_kinds)) if allowed_kinds is not None else "all shapes"
    print(f"No violations ({scope_label}) in {suite_count} suite(s).")
    return EXIT_PASS


def _gate(argv: Sequence[str] | None) -> int:
    parser = build_parser()
    return run_main(lambda: parser.parse_args(argv), _run)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the verdict, in gate mode."""
    return run_as_gate(GATE, MODULE, _gate, argv)


if __name__ == "__main__":
    sys.exit(main())
