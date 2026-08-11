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

Two shapes fail this gate:

1. **Toolchain subprocess** -- ``javac``, ``java``, ``mvn``/``mvnw``,
   ``dotnet``, ``tsc``, ``npm``/``npx``, ``node``, ``docker``, ``az``,
   ``gradle`` launched against generated output.
2. **In-process execution** -- ``exec(compile(...))``, ``runpy``, or
   ``importlib``'s ``spec_from_file_location``/``exec_module`` applied to a
   rendered template, then calling into it. No toolchain is involved; the
   principle is identical.

Two shapes are allowed and must stay allowed:

- **Linters over generated text.** ``ruff``/``black`` read the emitted source;
  reading is not executing.
- **Running datrix itself.** ``sys.executable -m datrix_cli`` and the
  import-boundary probes run the framework, not its output.

Run with ``--self-test`` to prove the detector is non-vacuous.
"""

from __future__ import annotations

import argparse
import ast
import sys
import tempfile
from pathlib import Path

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
        return [Violation(path, exc.lineno or 1, "unparseable", str(exc))]

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
            violations.append(Violation(path, node.lineno, "toolchain-subprocess", detail))
            continue
        hit, detail = _is_in_process_execution(node, scope_of.get(node))
        if hit:
            violations.append(Violation(path, node.lineno, "in-process-execution", detail))
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


def self_test() -> int:
    """Prove the detector fires on each forbidden shape and stays quiet otherwise."""
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, body, expect in (
            ("offender.py", _OFFENDER, "toolchain-subprocess"),
            ("in_process.py", _IN_PROCESS_OFFENDER, "in-process-execution"),
            ("allowed.py", _ALLOWED, None),
        ):
            target = root / name
            target.write_text(body, encoding="utf-8")
            found = scan_source(target)
            kinds = {v.kind for v in found}
            if expect is None and found:
                failures.append(f"{name}: expected no violation, got {[str(v) for v in found]}")
            elif expect is not None and expect not in kinds:
                failures.append(f"{name}: expected a {expect} violation, got {sorted(kinds)}")

    if failures:
        print("SELF-TEST FAILED -- the detector is not trustworthy:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print("Self-test passed: detector fires on both forbidden shapes and spares the allowed ones.")
    return 0


def default_suites(repo_root: Path) -> list[Path]:
    return sorted(
        package / "tests"
        for package in repo_root.iterdir()
        if package.is_dir()
        and package.name.startswith("datrix")
        and (package / "tests").is_dir()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "suites", nargs="*", type=Path,
        help="tests/ directories to scan (default: every datrix-* package's suite)",
    )
    parser.add_argument("--self-test", action="store_true", help="run only the self-test")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if self_test() != 0:
        return 1

    suites = args.suites or default_suites(Path(__file__).resolve().parents[4])
    if not suites:
        print("No test suites found to scan.", file=sys.stderr)
        return 1

    violations: list[Violation] = []
    for suite in suites:
        if not suite.is_dir():
            print(f"Not a directory, skipping: {suite}", file=sys.stderr)
            continue
        violations.extend(scan_suite(suite))

    if violations:
        print(
            f"\n{len(violations)} framework test(s) compile or execute generated output.\n"
            "That belongs to the generated project's own tests and the deploy tests --\n"
            "assert on the emitted source instead.\n",
            file=sys.stderr,
        )
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        return 1

    print(f"No toolchain or in-process execution in {len(suites)} suite(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
