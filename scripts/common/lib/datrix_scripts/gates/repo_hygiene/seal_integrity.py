"""Seal integrity: only the model seals or unseals a node.

A sealed ``Node`` refuses every attribute assignment. The flag that marks it
sealed lives in the node's own ``__dict__`` under ``_SEAL_FLAG`` (``"_sealed"``),
and exactly two methods of ``Node`` in ``datrix_common/datrix_model/base.py``
write it: ``Node.seal`` sets it, and ``Node.__deepcopy__`` builds a copy with it
off. Any other write -- a copy resealed by hand, a node unsealed to patch it --
turns sealing from a guarantee into a convention. This gate parses every
``src/`` tree of every ``datrix-*`` package on disk with ``ast`` and fails on
every write of the seal flag outside those two methods:

* ``seal-flag-dict-write`` -- ``X.__dict__[K]`` or ``vars(X)[K]`` assigned (plain,
  augmented, annotated, unpacked, a ``for`` or ``with`` target) or deleted, and
  ``__setitem__`` / ``__delitem__`` / ``pop`` / ``setdefault`` with key K, or
  ``update`` carrying K, called on ``X.__dict__`` or ``vars(X)``;
* ``seal-flag-attribute-write`` -- ``X._sealed`` assigned or deleted, and
  ``setattr`` / ``delattr`` / ``__setattr__`` / ``__delattr__`` called with key K;

where K is the literal ``"_sealed"``, the name ``_SEAL_FLAG`` (or a name it is
imported as, or a module-level name bound to ``"_sealed"``), or an attribute
``<module>._SEAL_FLAG``.

The terminal state is zero: there is no baseline. The real scan must find the
write in ``Node.seal``, or it cannot tell a clean tree from a matcher that
stopped matching.

Built-in non-vacuity self-test, every invocation: a planted ``src/`` tree must be
reported at exactly the planted lines, its two permitted writes recognised as
permitted, and its clean shapes and its ``tests/`` tree not reported at all.

Run it through ``gates/repo-hygiene/seal-integrity-gate.ps1`` or its ``.sh`` twin; it runs in gate mode
(``datrix_scripts.gate_log.run_as_gate``) and prints the
``[GATE] seal-integrity PASSED|FAILED exit=<n> log=<path>`` verdict last.
"""

from __future__ import annotations

import argparse
import ast
import logging
import sys
import tempfile
import textwrap
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from datrix_scripts.framework_repos import PackageMarker, workspace_package_dirs
from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.gates.repo_hygiene.gate_options import (
    check_requested_roots_split_on_commas,
    report_by_printing,
    requested_roots,
    roots_gate_parser,
)
from datrix_scripts.paths import TMP_DIR, WORKSPACE_DIR
from datrix_scripts.test import wrappers

logger = logging.getLogger(__name__)

GATE: Final = "seal-integrity"
MODULE: Final = "datrix_scripts.gates.repo_hygiene.seal_integrity"
WRAPPER: Final = "seal-integrity-gate"

_EXIT_OK: Final[int] = 0
_EXIT_FINDINGS: Final[int] = 1
_EXIT_GATE_BROKEN: Final[int] = 2

#: The ``__dict__`` key that marks a node sealed.
SEAL_FLAG_VALUE: Final[str] = "_sealed"

#: The model's name for that key.
SEAL_FLAG_NAME: Final[str] = "_SEAL_FLAG"

#: The trailing path parts of the one file allowed to write the flag.
SEAL_OWNER_FILE: Final[tuple[str, ...]] = ("datrix_common", "datrix_model", "base.py")

#: The class whose methods may write the flag.
SEAL_OWNER_CLASS: Final[str] = "Node"

#: The method that sets the flag; the real scan must find its write.
SEALING_METHOD: Final[str] = "seal"

#: The methods of the owner class allowed to write the flag.
SEAL_WRITERS: Final[frozenset[str]] = frozenset({SEALING_METHOD, "__deepcopy__"})

#: Scope depth of a method defined directly in a top-level class: the class, then the method.
_WRITER_DEPTH: Final[int] = 2

#: Package subtree the gate scans.
SOURCE_SUBTREE: Final[str] = "src"

#: Directories under a source tree that hold no framework source.
SKIP_DIRS: Final[frozenset[str]] = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", "node_modules"})

#: An object's attribute dictionary.
_INSTANCE_DICT: Final[str] = "__dict__"

#: The builtin that returns an object's attribute dictionary.
_VARS: Final[str] = "vars"

#: Dictionary methods whose first argument is the key they write or remove.
_DICT_KEY_MUTATORS: Final[frozenset[str]] = frozenset({"__setitem__", "__delitem__", "pop", "setdefault"})

#: The dictionary method that writes every key it is given.
_DICT_UPDATE: Final[str] = "update"

#: Calls that write or remove an attribute named by one of their first two arguments.
_ATTRIBUTE_MUTATORS: Final[frozenset[str]] = frozenset({"setattr", "delattr", "__setattr__", "__delattr__"})

#: How many leading positional arguments of an attribute mutator may name the attribute:
#: ``setattr(obj, name, value)`` names it second, a bound ``obj.__setattr__(name, value)`` first.
_ATTRIBUTE_NAME_POSITIONS: Final[int] = 2

#: Kind label of a write through the node's attribute dictionary.
KIND_DICT_WRITE: Final[str] = "seal-flag-dict-write"
#: Kind label of a write through attribute assignment.
KIND_ATTRIBUTE_WRITE: Final[str] = "seal-flag-attribute-write"

_REMEDY: Final[str] = (
    "only Node.seal() and Node.__deepcopy__ in datrix_common/datrix_model/base.py write the seal flag; "
    "seal a tree with seal(), copy one with copy.deepcopy(), and never unseal a node to change it"
)


class GateInputError(Exception):
    """A source file the gate must read cannot be parsed."""


@dataclass(frozen=True, slots=True)
class Finding:
    """One write of the seal flag outside the model."""

    path: Path
    line: int
    kind: str
    detail: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.kind}: {self.detail}"


@dataclass(frozen=True, slots=True)
class PermittedWrite:
    """One write of the seal flag by a method allowed to make it."""

    path: Path
    line: int
    method: str


@dataclass(slots=True)
class ScanResult:
    """What a scan read and found."""

    files: int = 0
    findings: list[Finding] = field(default_factory=list)
    permitted: list[PermittedWrite] = field(default_factory=list)


def _is_flag_literal(expression: ast.expr | None) -> bool:
    return isinstance(expression, ast.Constant) and expression.value == SEAL_FLAG_VALUE


def _seal_names(tree: ast.Module) -> frozenset[str]:
    """The names that hold the seal key in *tree*: the model's own, its import aliases, module-level copies."""
    names = {SEAL_FLAG_NAME}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.asname for alias in node.names if alias.name == SEAL_FLAG_NAME and alias.asname)
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and _is_flag_literal(statement.value):
            names.update(target.id for target in statement.targets if isinstance(target, ast.Name))
        elif isinstance(statement, ast.AnnAssign) and _is_flag_literal(statement.value):
            if isinstance(statement.target, ast.Name):
                names.add(statement.target.id)
    return frozenset(names)


def _is_seal_key(expression: ast.expr, names: frozenset[str]) -> bool:
    if _is_flag_literal(expression):
        return True
    if isinstance(expression, ast.Name):
        return expression.id in names
    return isinstance(expression, ast.Attribute) and expression.attr == SEAL_FLAG_NAME


def _is_instance_dict(expression: ast.expr) -> bool:
    """True for ``X.__dict__`` and ``vars(X)``."""
    if isinstance(expression, ast.Attribute):
        return expression.attr == _INSTANCE_DICT
    return (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Name)
        and expression.func.id == _VARS
        and len(expression.args) == 1
    )


def _flattened(target: ast.expr) -> Iterator[ast.expr]:
    if isinstance(target, (ast.Tuple, ast.List)):
        for element in target.elts:
            yield from _flattened(element)
    elif isinstance(target, ast.Starred):
        yield from _flattened(target.value)
    else:
        yield target


def _statement_targets(statement: ast.stmt) -> Iterator[ast.expr]:
    """Every expression *statement* assigns or deletes."""
    targets: list[ast.expr] = []
    if isinstance(statement, (ast.Assign, ast.Delete)):
        targets = list(statement.targets)
    elif isinstance(statement, (ast.AugAssign, ast.AnnAssign, ast.For, ast.AsyncFor)):
        targets = [statement.target]
    elif isinstance(statement, (ast.With, ast.AsyncWith)):
        targets = [item.optional_vars for item in statement.items if item.optional_vars is not None]
    for target in targets:
        yield from _flattened(target)


def _target_kind(target: ast.expr, names: frozenset[str]) -> str:
    if isinstance(target, ast.Subscript) and _is_instance_dict(target.value) and _is_seal_key(target.slice, names):
        return KIND_DICT_WRITE
    if isinstance(target, ast.Attribute) and target.attr == SEAL_FLAG_VALUE:
        return KIND_ATTRIBUTE_WRITE
    return ""


def _update_carries_key(call: ast.Call, names: frozenset[str]) -> bool:
    if any(keyword.arg == SEAL_FLAG_VALUE for keyword in call.keywords):
        return True
    return any(
        isinstance(argument, ast.Dict) and any(key is not None and _is_seal_key(key, names) for key in argument.keys)
        for argument in call.args
    )


def _dict_call_writes(func: ast.Attribute, call: ast.Call, names: frozenset[str]) -> bool:
    if func.attr in _DICT_KEY_MUTATORS:
        return bool(call.args) and _is_seal_key(call.args[0], names)
    return func.attr == _DICT_UPDATE and _update_carries_key(call, names)


def _call_kind(call: ast.Call, names: frozenset[str]) -> str:
    func = call.func
    if isinstance(func, ast.Attribute) and _is_instance_dict(func.value):
        return KIND_DICT_WRITE if _dict_call_writes(func, call, names) else ""
    callee = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
    if callee not in _ATTRIBUTE_MUTATORS:
        return ""
    named = call.args[:_ATTRIBUTE_NAME_POSITIONS]
    return KIND_ATTRIBUTE_WRITE if any(_is_seal_key(argument, names) for argument in named) else ""


class _Scanner(ast.NodeVisitor):
    """Collect every seal-flag write in one module, with the class and function scope it sits in."""

    def __init__(self, path: Path, names: frozenset[str], result: ScanResult) -> None:
        self._path = path
        self._names = names
        self._result = result
        self._owner_file = path.parts[-len(SEAL_OWNER_FILE):] == SEAL_OWNER_FILE
        self._scope: list[tuple[type[ast.AST], str]] = []

    def visit(self, node: ast.AST) -> None:
        if isinstance(node, ast.stmt):
            for target in _statement_targets(node):
                kind = _target_kind(target, self._names)
                if kind:
                    self._record(node.lineno, kind, ast.unparse(target))
        if isinstance(node, ast.Call):
            kind = _call_kind(node, self._names)
            if kind:
                self._record(node.lineno, kind, ast.unparse(node))
        super().visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._enter(ast.ClassDef, node.name, node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._enter(ast.FunctionDef, node.name, node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._enter(ast.FunctionDef, node.name, node)

    def _enter(self, kind: type[ast.AST], name: str, node: ast.AST) -> None:
        self._scope.append((kind, name))
        self.generic_visit(node)
        self._scope.pop()

    def _permitted_method(self) -> str:
        """The writer method this scope is directly inside, or ``""`` outside one."""
        if not self._owner_file or len(self._scope) != _WRITER_DEPTH:
            return ""
        (outer_kind, outer_name), (inner_kind, inner_name) = self._scope
        if outer_kind is ast.ClassDef and outer_name == SEAL_OWNER_CLASS and inner_kind is ast.FunctionDef:
            return inner_name if inner_name in SEAL_WRITERS else ""
        return ""

    def _record(self, line: int, kind: str, source: str) -> None:
        method = self._permitted_method()
        if method:
            self._result.permitted.append(PermittedWrite(self._path, line, method))
            return
        self._result.findings.append(Finding(self._path, line, kind, f"{source} writes the seal flag; {_REMEDY}"))


def _python_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
        if not SKIP_DIRS.intersection(path.relative_to(root).parts):
            yield path


def _parse(path: Path) -> ast.Module:
    """Parse *path*.

    Raises:
        GateInputError: The file is not valid Python or not UTF-8.
    """
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as error:
        raise GateInputError(
            f"Cannot parse {path}: {error}. Expected: a UTF-8 Python source file. "
            f"Fix: correct the file, since the gate never skips a file it cannot read."
        ) from error


def default_roots(workspace: Path) -> list[Path]:
    """The ``src/`` tree of every ``datrix-*`` package on disk."""
    return [
        package / SOURCE_SUBTREE
        for package in workspace_package_dirs(workspace, any_of=frozenset({PackageMarker.SRC}))
    ]


def scan(roots: Sequence[Path]) -> ScanResult:
    """Every seal-flag write under *roots*, split into findings and permitted writes."""
    result = ScanResult()
    for root in roots:
        for path in _python_files(root):
            tree = _parse(path)
            _Scanner(path, _seal_names(tree), result).visit(tree)
            result.files += 1
    result.findings.sort(key=lambda finding: (str(finding.path), finding.line))
    return result


_PLANTED_MODEL: Final[str] = textwrap.dedent(
    """\
    _SEAL_FLAG = "_sealed"


    class Node:
        def seal(self):
            self.__dict__[_SEAL_FLAG] = True

            def reseal_later():
                self.__dict__[_SEAL_FLAG] = True

            return reseal_later

        def __deepcopy__(self, memo):
            copy_obj = object.__new__(type(self))
            copy_obj.__dict__[_SEAL_FLAG] = False
            return copy_obj

        def unseal(self):
            self.__dict__.pop(_SEAL_FLAG)


    class Other:
        def seal(self):
            self.__dict__[_SEAL_FLAG] = True
    """
)

_PLANTED_TARGET: Final[str] = textwrap.dedent(
    """\
    import copy
    from datrix_common.datrix_model import base
    from datrix_common.datrix_model.base import _SEAL_FLAG
    from datrix_common.datrix_model.base import _SEAL_FLAG as FLAG

    SEALED_KEY = "_sealed"


    def reseal(node, pairs):
        node.__dict__[_SEAL_FLAG] = True
        node.__dict__["_sealed"] = True
        vars(node)[FLAG] = True
        node.__dict__[base._SEAL_FLAG] = True
        node.__dict__[SEALED_KEY] |= True
        node.__dict__[_SEAL_FLAG]: bool = True
        other, node.__dict__[_SEAL_FLAG] = 1, True
        del node.__dict__[_SEAL_FLAG]
        node.__dict__.pop(_SEAL_FLAG)
        node.__dict__.setdefault(_SEAL_FLAG, True)
        node.__dict__.__setitem__(_SEAL_FLAG, True)
        vars(node).__delitem__("_sealed")
        node.__dict__.update({_SEAL_FLAG: True})
        vars(node).update(_sealed=False)
        for node.__dict__[_SEAL_FLAG] in pairs:
            break
        with pairs as node.__dict__[_SEAL_FLAG]:
            node._sealed = True
        del node._sealed
        setattr(node, "_sealed", True)
        object.__setattr__(node, _SEAL_FLAG, True)
        delattr(node, FLAG)
        object.__delattr__(node, base._SEAL_FLAG)
        node.__setattr__(SEALED_KEY, True)
        return other


    def clean(node, flags):
        sealed = node.__dict__.get(_SEAL_FLAG, False)
        node.__dict__["name"] = sealed
        node.__dict__[sealed] = True
        flags[_SEAL_FLAG] = True
        node.__dict__.update({"name": sealed})
        setattr(node, "name", _SEAL_FLAG)
        node.sealed = True
        return copy.deepcopy(node).is_sealed


    class Node:
        def seal(self):
            self.__dict__[_SEAL_FLAG] = True
    """
)

#: Name of the planted model file and of the planted target file.
_MODEL_FILE: Final[str] = SEAL_OWNER_FILE[-1]
_TARGET_FILE: Final[str] = "module.py"

#: ``(file name, line, kind)`` of every finding the planted tree must yield: in the model, a write
#: nested inside ``Node.seal``, a third ``Node`` method, and ``seal`` on another class; in the
#: target, every reported shape, and a ``Node.seal`` outside the model's file.
_PLANTED_EXPECTED: Final[frozenset[tuple[str, int, str]]] = frozenset(
    {
        (_MODEL_FILE, 9, KIND_DICT_WRITE),
        (_MODEL_FILE, 19, KIND_DICT_WRITE),
        (_MODEL_FILE, 24, KIND_DICT_WRITE),
        *((_TARGET_FILE, line, KIND_DICT_WRITE) for line in range(10, 25)),
        (_TARGET_FILE, 26, KIND_DICT_WRITE),
        *((_TARGET_FILE, line, KIND_ATTRIBUTE_WRITE) for line in range(27, 34)),
        (_TARGET_FILE, 50, KIND_DICT_WRITE),
    }
)

#: ``(line, method)`` of the planted model's two permitted writes.
_PLANTED_PERMITTED: Final[frozenset[tuple[int, str]]] = frozenset({(6, SEALING_METHOD), (15, "__deepcopy__")})

#: Source files the planted tree holds under ``src/``: the model and the target.
_PLANTED_FILES: Final[int] = 2


def _plant(scratch: Path) -> tuple[Path, Path]:
    """Write the planted model and target packages (and a tests copy); return the two source files."""
    model = scratch / "datrix-common" / SOURCE_SUBTREE / Path(*SEAL_OWNER_FILE)
    target_package = scratch / "datrix-planted"
    target = target_package / SOURCE_SUBTREE / "planted" / _TARGET_FILE
    files = {
        model: _PLANTED_MODEL,
        target: _PLANTED_TARGET,
        target_package / "tests" / "test_module.py": _PLANTED_TARGET,
    }
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return model, target


def self_test() -> bool:
    """The gate reports every planted write at its line, permits the model's two, and reports nothing else."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TMP_DIR, prefix="seal-integrity-") as scratch:
        model, target = _plant(Path(scratch))
        result = scan(default_roots(Path(scratch)))
    found = {(finding.path.name, finding.line, finding.kind) for finding in result.findings}
    permitted = {(write.line, write.method) for write in result.permitted if write.path == model}
    misplaced = [finding.render() for finding in result.findings if finding.path not in (model, target)]
    if result.files != _PLANTED_FILES or misplaced or len(permitted) != len(result.permitted):
        logger.error("self_test_failed files=%d misplaced=%s permitted=%s", result.files, misplaced, result.permitted)
        return False
    if found != _PLANTED_EXPECTED or len(result.findings) != len(_PLANTED_EXPECTED) or permitted != _PLANTED_PERMITTED:
        logger.error(
            "self_test_failed missed=%s unexpected=%s count=%d permitted=%s",
            sorted(_PLANTED_EXPECTED - found),
            sorted(found - _PLANTED_EXPECTED),
            len(result.findings),
            sorted(permitted),
        )
        return False
    logger.info("self_test_passed findings=%d permitted=%d", len(result.findings), len(permitted))
    return True


def run_gate(roots: Sequence[Path]) -> int:
    """Scan *roots*; print each finding and a count."""
    try:
        result = scan(roots)
    except GateInputError as error:
        print(f"FAIL {error}")
        return _EXIT_GATE_BROKEN
    if not any(write.method == SEALING_METHOD for write in result.permitted):
        print(
            f"FAIL no seal-flag write found in {SEAL_OWNER_CLASS}.{SEALING_METHOD} under {len(roots)} src tree(s); "
            f"expected one in {'/'.join(SEAL_OWNER_FILE)}. Fix: include datrix-common's src among the roots, "
            "or repair the matcher if the model still seals through its __dict__"
        )
        return _EXIT_GATE_BROKEN
    for finding in result.findings:
        print(f"FAIL {finding.render()}")
    print(
        f"{result.files} file(s) under {len(roots)} src tree(s), {len(result.permitted)} permitted seal-flag "
        f"write(s), {len(result.findings)} seal-flag write(s) outside the model"
    )
    return _EXIT_FINDINGS if result.findings else _EXIT_OK


def _check_planted_seal_flag_writes_are_reported_exactly() -> None:
    assert self_test(), "the scan did not report exactly the planted seal-flag writes (see the self_test_failed record)"


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/repo-hygiene/seal-integrity-gate.ps1``: one per wrapper parameter, spelled
    exactly."""
    return roots_gate_parser(
        WRAPPER, "Fail if any code outside Node.seal and Node.__deepcopy__ writes a node's seal flag.", debug=True
    )


def _run(args: argparse.Namespace) -> int:
    report_by_printing(args.debug)
    if args.self_test:
        return wrappers.run_self_test(
            [_check_planted_seal_flag_writes_are_reported_exactly, check_requested_roots_split_on_commas],
            wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=wrappers.REPO_HYGIENE_GATES_DIR,
        )
    if not self_test():
        print("Seal-integrity gate self-test failed: the gate cannot tell a seal-flag write from clean code.")
        return _EXIT_GATE_BROKEN
    requested = requested_roots(args.roots)
    return run_gate([Path(root) for root in requested] if requested else default_roots(WORKSPACE_DIR))


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
