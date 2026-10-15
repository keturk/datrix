"""Seam censuses over the scripts tree, run by the shared-library gate.

Each census names one fact that has exactly one home and reports every place that copies it:

``harness-ownership``
    No module other than ``datrix_scripts/gate_harness.py`` defines a top-level
    ``run_checks``, ``run_self_test_checks``, ``harness_self_test``, ``_ok``, ``_fail``,
    ``_step``, ``_assert``, ``configure_logging`` or ``_configure_logging``.
``runner-adoption``
    No ``.ps1`` other than ``common/venv.ps1`` calls ``Ensure-DatrixVenv`` (a wrapper runs its
    Python through ``Invoke-DatrixPythonScript``), and every gate wrapper reports one verdict
    line: it passes ``-Gate`` to ``Invoke-DatrixPythonScript`` or calls
    ``Write-DatrixGateVerdict``.
``package-discovery``
    No module other than ``datrix_scripts/framework_repos.py`` loops over ``<dir>.iterdir()``
    testing a ``datrix`` name prefix.
``sys-path``
    No production script inserts into ``sys.path``; the exceptions are the self-test fixtures
    that plant synthetic distributions, and ``hook_modules.py`` (the hooks directory is not a
    package).
``identical-bodies``
    No function body of three or more statements (docstring stripped) is AST-identical to one in
    another file.
``gate-self-test``
    Every gate wrapper (``*-gate.ps1``, ``*ratchet*.ps1``, ``type-mapping-completeness.ps1``)
    declares a ``SelfTest`` switch.
``root-resolvers``
    No ``.py``, ``.ps1`` or ``.psm1`` defines, imports or calls a retired workspace-root resolver
    (``RETIRED_PY_ROOT_RESOLVERS``, ``RETIRED_PS_ROOT_RESOLVERS``); the root is
    ``Get-DatrixWorkspaceRoot`` and ``datrix_scripts.paths.WORKSPACE_DIR``.

The censuses parse structure (Python ``ast``; PowerShell's own parser through
``datrix_scripts.powershell_ast``), never text.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from datrix_scripts.gate_harness import NamedCheck, write_files
from datrix_scripts.powershell_ast import ScriptFacts, parse_scripts

HARNESS_NAMES: Final = frozenset(
    {
        "run_checks", "run_self_test_checks", "harness_self_test", "_ok", "_fail", "_step",
        "_assert", "configure_logging", "_configure_logging",
    }
)
HARNESS_HOME: Final = "common/lib/datrix_scripts/gate_harness.py"
DISCOVERY_HOME: Final = "common/lib/datrix_scripts/framework_repos.py"
VENV_HOME: Final = "common/venv.ps1"
SYS_PATH_ALLOWED: Final = frozenset(
    {
        "common/lib/datrix_scripts/suite_inputs.py",
        "gates/parity/lib/behaviour_parity.py",
        "test/lib/affected_gate.py",
        "common/lib/datrix_scripts/hook_modules.py",
    }
)
_SYS_PATH_MUTATORS: Final = frozenset({"insert", "append", "extend"})
_DATRIX_NAME: Final = "datrix"
_PREFIX_CONSTANT: Final = "FRAMEWORK_REPO_PREFIX"
MIN_BODY_STATEMENTS: Final = 3

ENSURE_VENV: Final = "Ensure-DatrixVenv"
RUNNER: Final = "Invoke-DatrixPythonScript"
VERDICT_WRITER: Final = "Write-DatrixGateVerdict"
GATE_PARAMETER: Final = "Gate"
SELF_TEST_PARAMETER: Final = "SelfTest"
_TYPE_MAPPING_GATE: Final = "type-mapping-completeness.ps1"
#: Retired workspace-root resolvers: the root is ``Get-DatrixWorkspaceRoot`` (PowerShell) and
#: ``datrix_scripts.paths.WORKSPACE_DIR`` (Python).
RETIRED_PS_ROOT_RESOLVERS: Final = frozenset({"Get-DatrixRoot", "Get-DatrixWorkspaceRootFromScript"})
RETIRED_PY_ROOT_RESOLVERS: Final = frozenset({"get_datrix_root"})
_SKIP_DIRS: Final = frozenset({"__pycache__", ".pytest_cache", "node_modules"})


class Census(StrEnum):
    HARNESS = "harness-ownership"
    RUNNER = "runner-adoption"
    DISCOVERY = "package-discovery"
    SYS_PATH = "sys-path"
    IDENTICAL_BODIES = "identical-bodies"
    SELF_TEST = "gate-self-test"
    ROOT_RESOLVERS = "root-resolvers"


@dataclass(frozen=True)
class CensusHit:
    census: Census
    location: str
    detail: str

    def render(self) -> str:
        return f"[{self.census}] {self.location}: {self.detail}"


def _relative(path: Path, scripts_dir: Path) -> str:
    return path.relative_to(scripts_dir).as_posix()


def _files(scripts_dir: Path, pattern: str) -> list[Path]:
    return sorted(
        path for path in scripts_dir.rglob(pattern)
        if not any(part in _SKIP_DIRS for part in path.parts)
    )


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return None


def python_modules(scripts_dir: Path) -> Iterator[tuple[str, ast.Module]]:
    """(scripts-relative path, parsed module) for every parseable ``.py`` under ``scripts_dir``."""
    for path in _files(scripts_dir, "*.py"):
        tree = _parse(path)
        if tree is not None:
            yield _relative(path, scripts_dir), tree


# ---------------------------------------------------------------- Python censuses


def harness_ownership(modules: list[tuple[str, ast.Module]]) -> list[CensusHit]:
    hits: list[CensusHit] = []
    for relative, tree in modules:
        if relative == HARNESS_HOME:
            continue
        for node in tree.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name in HARNESS_NAMES:
                hits.append(
                    CensusHit(
                        Census.HARNESS,
                        f"{relative}:{node.lineno}",
                        f"defines {node.name}; import it from datrix_scripts.gate_harness",
                    )
                )
    return hits


def _is_datrix_prefix_text(value: object) -> bool:
    """A package-directory prefix: ``datrix`` itself or anything starting ``datrix-``.

    ``datrix_`` (an import-name prefix, matched inside a ``src/`` tree) is not one.
    """
    return isinstance(value, str) and (value == _DATRIX_NAME or value.startswith(f"{_DATRIX_NAME}-"))


def _prefix_constants(tree: ast.Module) -> frozenset[str]:
    """Module-level names bound to a string starting ``datrix`` (``_PACKAGE_PREFIX = "datrix-"``)."""
    names: set[str] = {_PREFIX_CONSTANT}
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        if isinstance(value, ast.Constant) and _is_datrix_prefix_text(value.value):
            names.update(target.id for target in targets if isinstance(target, ast.Name))
    return frozenset(names)


def _names_datrix_prefix(argument: ast.expr, constants: frozenset[str]) -> bool:
    if isinstance(argument, ast.Constant):
        return _is_datrix_prefix_text(argument.value)
    if isinstance(argument, ast.Name | ast.Attribute):
        name = argument.id if isinstance(argument, ast.Name) else argument.attr
        return name in constants
    if isinstance(argument, ast.Tuple):
        return any(_names_datrix_prefix(element, constants) for element in argument.elts)
    return False


def _tests_datrix_prefix(node: ast.AST, constants: frozenset[str]) -> bool:
    for inner in ast.walk(node):
        if (
            isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Attribute)
            and inner.func.attr == "startswith"
            and any(_names_datrix_prefix(argument, constants) for argument in inner.args)
        ):
            return True
    return False


def _iterates_a_directory(iterable: ast.expr) -> bool:
    return any(
        isinstance(inner, ast.Call)
        and isinstance(inner.func, ast.Attribute)
        and inner.func.attr == "iterdir"
        for inner in ast.walk(iterable)
    )


def _discovery_loops(tree: ast.Module) -> Iterator[ast.AST]:
    constants = _prefix_constants(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.For | ast.AsyncFor) and _iterates_a_directory(node.iter):
            if _tests_datrix_prefix(node, constants):
                yield node
        elif isinstance(node, ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp):
            if any(_iterates_a_directory(gen.iter) for gen in node.generators) and _tests_datrix_prefix(
                node, constants
            ):
                yield node


def package_discovery(modules: list[tuple[str, ast.Module]]) -> list[CensusHit]:
    hits: list[CensusHit] = []
    for relative, tree in modules:
        if relative == DISCOVERY_HOME:
            continue
        for node in _discovery_loops(tree):
            hits.append(
                CensusHit(
                    Census.DISCOVERY,
                    f"{relative}:{getattr(node, 'lineno', 0)}",
                    "enumerates datrix-* directories itself; call "
                    "datrix_scripts.framework_repos.workspace_package_dirs",
                )
            )
    return hits


def _is_sys_path_mutation(node: ast.AST) -> bool:
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
        return False
    if node.func.attr not in _SYS_PATH_MUTATORS:
        return False
    receiver = node.func.value
    return (
        isinstance(receiver, ast.Attribute)
        and receiver.attr == "path"
        and isinstance(receiver.value, ast.Name)
        and receiver.value.id == "sys"
    )


def sys_path_inserts(modules: list[tuple[str, ast.Module]]) -> list[CensusHit]:
    hits: list[CensusHit] = []
    for relative, tree in modules:
        if relative in SYS_PATH_ALLOWED:
            continue
        for node in ast.walk(tree):
            if _is_sys_path_mutation(node):
                hits.append(
                    CensusHit(
                        Census.SYS_PATH,
                        f"{relative}:{getattr(node, 'lineno', 0)}",
                        "mutates sys.path; the venv's editable installs are the only import path",
                    )
                )
    return hits


def _body_without_docstring(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    body = list(node.body)
    first = body[0] if body else None
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        return body[1:]
    return body


def _body_key(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    body = _body_without_docstring(node)
    if len(body) < MIN_BODY_STATEMENTS:
        return None
    return ast.dump(node.args) + "\n" + "\n".join(ast.dump(statement) for statement in body)


def identical_bodies(modules: list[tuple[str, ast.Module]]) -> list[CensusHit]:
    groups: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
    for relative, tree in modules:
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                key = _body_key(node)
                if key is not None:
                    groups[key].append((relative, node.name, node.lineno))
    hits: list[CensusHit] = []
    for members in groups.values():
        files = {relative for relative, _, _ in members}
        if len(files) < 2:
            continue
        rendered = ", ".join(f"{relative}:{line} {name}" for relative, name, line in sorted(members))
        hits.append(
            CensusHit(
                Census.IDENTICAL_BODIES,
                members[0][0],
                f"identical function bodies in {len(files)} files ({rendered}); give the body one home",
            )
        )
    return sorted(hits, key=lambda hit: hit.detail)


def _python_root_resolver_name(node: ast.AST) -> str | None:
    """The retired resolver ``node`` defines, imports or names, if it is one."""
    names: list[str] = []
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        names.append(node.name)
    elif isinstance(node, ast.Name):
        names.append(node.id)
    elif isinstance(node, ast.Attribute):
        names.append(node.attr)
    elif isinstance(node, ast.ImportFrom):
        names.extend(alias.name for alias in node.names)
    return next((name for name in names if name in RETIRED_PY_ROOT_RESOLVERS), None)


def python_root_resolvers(modules: list[tuple[str, ast.Module]]) -> list[CensusHit]:
    """Every definition, import or use of a retired Python workspace-root resolver."""
    hits: list[CensusHit] = []
    for relative, tree in modules:
        for node in ast.walk(tree):
            name = _python_root_resolver_name(node)
            if name is not None:
                hits.append(
                    CensusHit(
                        Census.ROOT_RESOLVERS,
                        f"{relative}:{getattr(node, 'lineno', 0)}",
                        f"names {name}; import WORKSPACE_DIR from datrix_scripts.paths",
                    )
                )
    return hits


# ---------------------------------------------------------------- PowerShell censuses


def is_gate_wrapper(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith("-gate.ps1") or ("ratchet" in name and name.endswith(".ps1")) or name == _TYPE_MAPPING_GATE


def _reports_verdict(facts: ScriptFacts) -> bool:
    runner_with_gate = any(
        GATE_PARAMETER.lower() in (parameter.lower() for parameter in call.parameters)
        for call in facts.calls(RUNNER)
    )
    return runner_with_gate or bool(facts.calls(VERDICT_WRITER))


def runner_adoption(scripts_dir: Path, facts: dict[Path, ScriptFacts]) -> list[CensusHit]:
    hits: list[CensusHit] = []
    for path, script in sorted(facts.items()):
        relative = _relative(path, scripts_dir)
        if relative != VENV_HOME and script.calls(ENSURE_VENV):
            hits.append(
                CensusHit(
                    Census.RUNNER,
                    relative,
                    f"calls {ENSURE_VENV}; run the Python through {RUNNER} (common/DatrixPythonScript.psm1)",
                )
            )
        if is_gate_wrapper(path) and not _reports_verdict(script):
            hits.append(
                CensusHit(
                    Census.RUNNER,
                    relative,
                    f"gate wrapper prints no verdict line; pass -{GATE_PARAMETER} <name> to {RUNNER} "
                    f"or call {VERDICT_WRITER}",
                )
            )
    return hits


def gate_self_tests(scripts_dir: Path, facts: dict[Path, ScriptFacts]) -> list[CensusHit]:
    return [
        CensusHit(
            Census.SELF_TEST,
            _relative(path, scripts_dir),
            f"gate wrapper declares no -{SELF_TEST_PARAMETER} switch; add one that runs only the "
            "gate's non-vacuity proof over planted inputs",
        )
        for path, script in sorted(facts.items())
        if is_gate_wrapper(path) and not script.declares(SELF_TEST_PARAMETER)
    ]


def powershell_root_resolvers(scripts_dir: Path, facts: dict[Path, ScriptFacts]) -> list[CensusHit]:
    """Every definition or call of a retired PowerShell workspace-root resolver."""
    hits: list[CensusHit] = []
    for path, script in sorted(facts.items()):
        for name in sorted(RETIRED_PS_ROOT_RESOLVERS):
            if script.defines(name) or script.calls(name):
                hits.append(
                    CensusHit(
                        Census.ROOT_RESOLVERS,
                        _relative(path, scripts_dir),
                        f"defines or calls {name}; call Get-DatrixWorkspaceRoot (common/DatrixPaths.psm1)",
                    )
                )
    return hits


def parse_errors(scripts_dir: Path, facts: dict[Path, ScriptFacts]) -> list[str]:
    return [
        f"{_relative(path, scripts_dir)}: {script.parse_errors[0]}"
        for path, script in sorted(facts.items())
        if script.parse_errors
    ]


# ---------------------------------------------------------------- the whole tree


def run_censuses(scripts_dir: Path) -> dict[Census, list[CensusHit]]:
    """Every census over ``scripts_dir``; PowerShell is parsed by one child for all of them.

    Raises:
        datrix_scripts.powershell_ast.PowerShellParseError: PowerShell could not report facts.
        ValueError: a ``.ps1`` does not parse (named), since its census would read nothing.
    """
    modules = list(python_modules(scripts_dir))
    facts = parse_scripts([*_files(scripts_dir, "*.ps1"), *_files(scripts_dir, "*.psm1")])
    broken = parse_errors(scripts_dir, facts)
    if broken:
        raise ValueError(f"PowerShell parse errors, so no census can read them: {broken}")
    # Runner adoption and gate self-tests are facts about scripts; the modules (the runner
    # itself among them) are read only for root resolvers.
    scripts = {path: script for path, script in facts.items() if path.suffix.lower() == ".ps1"}
    python_censuses: dict[Census, Callable[[list[tuple[str, ast.Module]]], list[CensusHit]]] = {
        Census.HARNESS: harness_ownership,
        Census.DISCOVERY: package_discovery,
        Census.SYS_PATH: sys_path_inserts,
        Census.IDENTICAL_BODIES: identical_bodies,
    }
    results = {census: run(modules) for census, run in python_censuses.items()}
    results[Census.RUNNER] = runner_adoption(scripts_dir, scripts)
    results[Census.SELF_TEST] = gate_self_tests(scripts_dir, scripts)
    results[Census.ROOT_RESOLVERS] = [
        *python_root_resolvers(modules),
        *powershell_root_resolvers(scripts_dir, facts),
    ]
    return results


def census_failures(results: dict[Census, list[CensusHit]]) -> list[str]:
    """One message per census with any hit: every census is a hard zero, with no baseline."""
    messages: list[str] = []
    for census, hits in results.items():
        if not hits:
            continue
        listing = "\n    ".join(hit.render() for hit in hits)
        messages.append(
            f"census {census.value}: {len(hits)} hit(s). Expected none: each fact has exactly one "
            f"home. Fix: move each copy to its home (or delete it). Hits:\n    {listing}"
        )
    return messages


# ---------------------------------------------------------------- self-test


def _planted_counts(files: dict[str, str]) -> dict[Census, int]:
    with TemporaryDirectory(prefix="scripts-census-") as tmp:
        root = Path(tmp) / "scripts"
        write_files(root, files)
        return {census: len(hits) for census, hits in run_censuses(root).items()}


_HARNESS_COPY: Final = "def _ok(message: str) -> None:\n    print(message)\n"
_DISCOVERY_COPY: Final = (
    "from pathlib import Path\n\n"
    "def packages(root: Path) -> list[Path]:\n"
    "    return [p for p in root.iterdir() if p.name.startswith('datrix-')]\n"
)
_DISCOVERY_COPY_VIA_CONSTANT: Final = (
    "from pathlib import Path\n\n"
    "_PREFIX = 'datrix-'\n\n"
    "def packages(root: Path) -> list[Path]:\n"
    "    found = []\n"
    "    for p in sorted(root.iterdir()):\n"
    "        if p.name.startswith(_PREFIX):\n"
    "            found.append(p)\n"
    "    return found\n"
)
_SYS_PATH_COPY: Final = "import sys\nsys.path.insert(0, 'x')\n"
_BODY: Final = "def helper(a: int) -> int:\n    b = a + 1\n    c = b * 2\n    return c\n"
_OTHER_BODY: Final = "def helper(a: int) -> int:\n    b = a + 2\n    c = b * 2\n    return c\n"
_VENV_WRAPPER: Final = "Ensure-DatrixVenv\n"
_GATE_WITHOUT_VERDICT: Final = "param([switch]$SelfTest)\nWrite-Host 'x'\n"
_GATE_WITH_VERDICT: Final = (
    "param([switch]$SelfTest)\nexit (Invoke-DatrixPythonScript -Script 'a.py' -Gate 'demo')\n"
)
_GATE_WITHOUT_SELF_TEST: Final = "param([switch]$Dbg)\nexit (Invoke-DatrixPythonScript -Script 'a.py' -Gate 'demo')\n"


#: Planted script paths, built from parts so the scripts-reference check does not read them as
#: references to real scripts.
_PLANTED_WRAPPER: Final = Path("dev", "run-thing.ps1").as_posix()
_PLANTED_GATE: Final = Path("gates", "demo", "demo-gate.ps1").as_posix()
_PLANTED_MODULE: Final = Path("common", "Rooted.psm1").as_posix()

#: The retired resolvers' names are built from parts, so this module is not itself a hit.
_PY_RESOLVER: Final = "_".join(("get", "datrix", "root"))
_PS_RESOLVER: Final = "-".join(("Get", "DatrixRoot"))
_PY_ROOT_RESOLVER_USE: Final = f"from datrix_scripts.venv import {_PY_RESOLVER}\n\nROOT = {_PY_RESOLVER}()\n"
_PY_ROOT_CLEAN: Final = "from datrix_scripts.paths import WORKSPACE_DIR\n\nROOT = WORKSPACE_DIR\n"
_PS_ROOT_RESOLVER_CALL: Final = f"$root = {_PS_RESOLVER}\n"
_PS_ROOT_RESOLVER_DEFINITION: Final = f"function {_PS_RESOLVER} {{ return 'x' }}\n"
_PS_ROOT_CLEAN: Final = "$root = Get-DatrixWorkspaceRoot\n"


def _expect(files: dict[str, str], census: Census, expected: int) -> None:
    got = _planted_counts(files)[census]
    if got != expected:
        raise AssertionError(f"census {census} over planted files {sorted(files)}: {got} hit(s), expected {expected}")


def _check_harness_ownership() -> None:
    _expect({"dev/lib/a_gate.py": _HARNESS_COPY}, Census.HARNESS, 1)
    _expect({HARNESS_HOME: _HARNESS_COPY}, Census.HARNESS, 0)


def _check_package_discovery() -> None:
    _expect({"dev/lib/finder.py": _DISCOVERY_COPY}, Census.DISCOVERY, 1)
    _expect({"dev/lib/finder.py": _DISCOVERY_COPY_VIA_CONSTANT}, Census.DISCOVERY, 1)
    _expect({DISCOVERY_HOME: _DISCOVERY_COPY}, Census.DISCOVERY, 0)


def _check_sys_path() -> None:
    _expect({"dev/lib/importer.py": _SYS_PATH_COPY}, Census.SYS_PATH, 1)
    _expect({"common/lib/datrix_scripts/hook_modules.py": _SYS_PATH_COPY}, Census.SYS_PATH, 0)


def _check_identical_bodies() -> None:
    _expect({"dev/lib/a.py": _BODY, "test/lib/b.py": _BODY}, Census.IDENTICAL_BODIES, 1)
    _expect({"dev/lib/a.py": _BODY, "test/lib/b.py": _OTHER_BODY}, Census.IDENTICAL_BODIES, 0)


def _check_runner_adoption() -> None:
    _expect({_PLANTED_WRAPPER: _VENV_WRAPPER}, Census.RUNNER, 1)
    _expect({VENV_HOME: _VENV_WRAPPER}, Census.RUNNER, 0)
    _expect({_PLANTED_GATE: _GATE_WITHOUT_VERDICT}, Census.RUNNER, 1)
    _expect({_PLANTED_GATE: _GATE_WITH_VERDICT}, Census.RUNNER, 0)


def _check_gate_self_test() -> None:
    _expect({_PLANTED_GATE: _GATE_WITHOUT_SELF_TEST}, Census.SELF_TEST, 1)
    _expect({_PLANTED_GATE: _GATE_WITH_VERDICT}, Census.SELF_TEST, 0)


def _check_root_resolvers() -> None:
    _expect({"dev/lib/rooted.py": _PY_ROOT_RESOLVER_USE}, Census.ROOT_RESOLVERS, 2)
    _expect({"dev/lib/rooted.py": _PY_ROOT_CLEAN}, Census.ROOT_RESOLVERS, 0)
    _expect({_PLANTED_WRAPPER: _PS_ROOT_RESOLVER_CALL}, Census.ROOT_RESOLVERS, 1)
    _expect({_PLANTED_MODULE: _PS_ROOT_RESOLVER_DEFINITION}, Census.ROOT_RESOLVERS, 1)
    _expect({_PLANTED_WRAPPER: _PS_ROOT_CLEAN}, Census.ROOT_RESOLVERS, 0)


def self_test_checks() -> list[NamedCheck]:
    """Each census reports a planted copy and passes its clean twin."""
    return [
        NamedCheck("census_harness_ownership_reports_a_planted_copy", _check_harness_ownership),
        NamedCheck("census_package_discovery_reports_a_planted_scan", _check_package_discovery),
        NamedCheck("census_sys_path_reports_a_planted_insert", _check_sys_path),
        NamedCheck("census_identical_bodies_reports_a_planted_pair", _check_identical_bodies),
        NamedCheck("census_runner_adoption_reports_planted_wrappers", _check_runner_adoption),
        NamedCheck("census_gate_self_test_reports_a_planted_gate", _check_gate_self_test),
        NamedCheck("census_root_resolvers_reports_planted_definitions_and_uses", _check_root_resolvers),
    ]
