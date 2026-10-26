"""Stateless generators: no generator attribute is assigned after construction.

A generator is a function of ``(Application, CodegenContext, output_dir)``. One
that keeps run state on itself -- a context assigned before ``generate`` runs, a
cache filled by an earlier run -- answers a second run with the first run's facts.
This gate keeps that shape from coming back, over every ``src/`` tree of every
``datrix-*`` package on disk, parsed with ``ast``:

* the ``Generator`` subclasses are found from the class graph of every scanned
  module, each base resolved through the module's imports (re-exports followed),
  rooted at the kernel's ``Generator``;
* inside a method of such a class other than ``__init__``, any assignment to an
  attribute of ``self`` (or ``cls``): ``=``, augmented, annotated, ``for`` and
  ``with`` targets, tuple unpacking, ``setattr`` / ``object.__setattr__`` and
  ``self.__dict__[...] =``;
* anywhere, an assignment to an attribute of a name typed as a ``Generator``
  subclass (a parameter or variable annotation naming one, or a ``for`` target
  iterating such a name);
* a parameter of such a class's ``__init__`` typed ``CodegenContext``: a context
  is a ``generate`` argument, never construction state.

The terminal state is zero: there is no baseline and no allowlist.

Built-in non-vacuity self-test, every invocation: a planted ``src/`` tree must be
reported at exactly the planted lines, and its clean shapes and its ``tests/`` tree
not at all.

Run it through ``gates/repo-hygiene/stateless-generator-gate.ps1`` or its ``.sh`` twin; it runs in gate
mode (``datrix_scripts.gate_log.run_as_gate``) and prints the
``[GATE] stateless-generator PASSED|FAILED exit=<n> log=<path>`` verdict last.
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

GATE: Final = "stateless-generator"
MODULE: Final = "datrix_scripts.gates.repo_hygiene.stateless_generator"
WRAPPER: Final = "stateless-generator-gate"

_EXIT_OK: Final[int] = 0
_EXIT_FINDINGS: Final[int] = 1
_EXIT_GATE_BROKEN: Final[int] = 2

#: The qualified name of the base class every generator subclasses.
GENERATOR_ROOT: Final[str] = "datrix_codegen_kernel.generation.generator.Generator"

#: The qualified name of the run context a generator receives as a ``generate`` argument.
CODEGEN_CONTEXT: Final[str] = "datrix_common.config.codegen_context.CodegenContext"

#: The one method allowed to assign the instance's attributes.
CONSTRUCTOR: Final[str] = "__init__"

#: Package subtree the gate scans.
SOURCE_SUBTREE: Final[str] = "src"

#: Directories under a source tree that hold no framework source.
SKIP_DIRS: Final[frozenset[str]] = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", "node_modules"})

#: Calls that assign an attribute of their first argument.
_SETATTR_CALLEES: Final[frozenset[str]] = frozenset({"setattr", "__setattr__"})

#: The instance's attribute dictionary, written through by subscript assignment.
_INSTANCE_DICT: Final[str] = "__dict__"

#: Kind label of an attribute assigned after construction.
KIND_ASSIGN: Final[str] = "generator-attribute-assigned"
#: Kind label of a constructor parameter typed as the run context.
KIND_CONTEXT_PARAM: Final[str] = "generator-init-takes-context"


class GateInputError(Exception):
    """A source file the gate must read cannot be parsed."""


@dataclass(frozen=True, slots=True)
class Finding:
    """One piece of run state a generator holds."""

    path: Path
    line: int
    kind: str
    detail: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.kind}: {self.detail}"


@dataclass(slots=True)
class Module:
    """One parsed source module and the names its top level binds to qualified names."""

    name: str
    path: Path
    tree: ast.Module
    aliases: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ClassInfo:
    """One class, top-level or local to a function: where it lives and its definition."""

    qualname: str
    module: Module
    node: ast.ClassDef


def _module_name(root: Path, path: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _package_of(module: str, path: Path) -> str:
    """The package a relative import in *module* is resolved against."""
    if path.name == "__init__.py":
        return module
    return module.rpartition(".")[0]


def _import_from_base(module: Module, node: ast.ImportFrom) -> str:
    if node.level == 0:
        return node.module or ""
    package = _package_of(module.name, module.path).split(".")
    base = package[: len(package) - (node.level - 1)]
    if node.module:
        base.append(node.module)
    return ".".join(base)


def _import_aliases(node: ast.Import) -> Iterator[tuple[str, str]]:
    for alias in node.names:
        if alias.asname:
            yield alias.asname, alias.name
        else:
            head = alias.name.split(".")[0]
            yield head, head


def _bind_aliases(module: Module) -> None:
    """Record what each top-level import and class binds, by qualified name."""
    for node in module.tree.body:
        if isinstance(node, ast.Import):
            module.aliases.update(_import_aliases(node))
        elif isinstance(node, ast.ImportFrom):
            base = _import_from_base(module, node)
            for alias in node.names:
                module.aliases[alias.asname or alias.name] = f"{base}.{alias.name}"
        elif isinstance(node, ast.ClassDef):
            module.aliases[node.name] = f"{module.name}.{node.name}"


def _dotted(expression: ast.expr) -> str:
    """``a.b.C`` for a name or attribute chain; empty for any other expression."""
    if isinstance(expression, ast.Name):
        return expression.id
    if isinstance(expression, ast.Attribute):
        head = _dotted(expression.value)
        return f"{head}.{expression.attr}" if head else ""
    return ""


class ClassGraph:
    """Every class of the scanned modules, with bases resolved through imports.

    A class defined inside a function is a class too: its bases resolve through
    the module's top-level names, and it is keyed by its line so two local
    classes of one name stay apart.
    """

    def __init__(self, modules: Sequence[Module]) -> None:
        self._modules = {module.name: module for module in modules}
        self._classes: dict[str, ClassInfo] = {}
        for module in modules:
            top_level = {id(node) for node in module.tree.body}
            for node in ast.walk(module.tree):
                if isinstance(node, ast.ClassDef):
                    local = "" if id(node) in top_level else f"<locals>.{node.lineno}."
                    qualname = f"{module.name}.{local}{node.name}"
                    self._classes[qualname] = ClassInfo(qualname, module, node)

    def resolve(self, module: Module, dotted: str) -> str:
        """The qualified name *dotted*, as written in *module*, refers to."""
        head, _, rest = dotted.partition(".")
        target = module.aliases.get(head)
        if target is None:
            return dotted
        return self._follow(f"{target}.{rest}" if rest else target, frozenset())

    def _follow(self, qualname: str, seen: frozenset[str]) -> str:
        """Follow re-exports until *qualname* names a class or leaves the scanned modules."""
        if qualname in self._classes or qualname in seen:
            return qualname
        owner, _, name = qualname.rpartition(".")
        module = self._modules.get(owner)
        if module is None or name not in module.aliases:
            return qualname
        return self._follow(module.aliases[name], seen | {qualname})

    def _bases(self, info: ClassInfo) -> set[str]:
        return {self.resolve(info.module, _dotted(base)) for base in info.node.bases}

    def subclasses_of(self, root: str) -> dict[str, ClassInfo]:
        """Every class whose base chain reaches *root*, *root* included when scanned."""
        reached = {root}
        changed = True
        while changed:
            added = {
                qualname
                for qualname, info in self._classes.items()
                if qualname not in reached and self._bases(info) & reached
            }
            reached |= added
            changed = bool(added)
        return {qualname: self._classes[qualname] for qualname in reached if qualname in self._classes}

    def _scanned_ancestors(self, qualname: str) -> set[str]:
        """Every scanned class *qualname* inherits from, transitively."""
        found: set[str] = set()
        pending = [qualname]
        while pending:
            for base in self._bases(self._classes[pending.pop()]):
                if base in self._classes and base not in found:
                    found.add(base)
                    pending.append(base)
        return found

    def generator_classes(self, root: str) -> dict[str, ClassInfo]:
        """The subclasses of *root* and every scanned class they mix in.

        A mixin's methods run on the generator instance it is mixed into, so an
        attribute a mixin method assigns is generator state like any other.
        """
        subclasses = self.subclasses_of(root)
        mixed_in = {ancestor for qualname in subclasses for ancestor in self._scanned_ancestors(qualname)}
        return subclasses | {qualname: self._classes[qualname] for qualname in mixed_in}


def _assigned_targets(target: ast.expr) -> Iterator[ast.expr]:
    """Each single target an assignment target binds, tuples and starred unpacked."""
    if isinstance(target, ast.Tuple | ast.List):
        for element in target.elts:
            yield from _assigned_targets(element)
    elif isinstance(target, ast.Starred):
        yield from _assigned_targets(target.value)
    else:
        yield target


def _with_targets(node: ast.With | ast.AsyncWith) -> Iterator[ast.expr]:
    for item in node.items:
        if item.optional_vars is not None:
            yield from _assigned_targets(item.optional_vars)


def _statement_targets(node: ast.AST) -> Iterator[ast.expr]:
    """The targets *node* assigns, when it is an assignment of any form."""
    if isinstance(node, ast.Assign):
        for target in node.targets:
            yield from _assigned_targets(target)
    elif isinstance(node, ast.AugAssign | ast.AnnAssign):
        yield node.target
    elif isinstance(node, ast.For | ast.AsyncFor):
        yield from _assigned_targets(node.target)
    elif isinstance(node, ast.With | ast.AsyncWith):
        yield from _with_targets(node)


def _instance_dict_write(target: ast.Subscript, owners: frozenset[str]) -> str:
    """``x.__dict__[...]`` when *target* writes through the instance dict of a name in *owners*."""
    holder = target.value
    if not (isinstance(holder, ast.Attribute) and holder.attr == _INSTANCE_DICT):
        return ""
    if isinstance(holder.value, ast.Name) and holder.value.id in owners:
        return f"{holder.value.id}.{_INSTANCE_DICT}[...]"
    return ""


def _written_attribute(target: ast.expr, owners: frozenset[str]) -> str:
    """``x.attr`` when *target* writes an attribute of a name in *owners*; else empty."""
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
        return f"{target.value.id}.{target.attr}" if target.value.id in owners else ""
    if isinstance(target, ast.Subscript):
        return _instance_dict_write(target, owners)
    return ""


def _setattr_owner(call: ast.Call, owners: frozenset[str]) -> str:
    """``setattr(owner, ...)`` when *call* writes an attribute of a name in *owners*; else empty."""
    callee = call.func.id if isinstance(call.func, ast.Name) else _dotted(call.func).rpartition(".")[2]
    if callee not in _SETATTR_CALLEES or not call.args:
        return ""
    first = call.args[0]
    if isinstance(first, ast.Name) and first.id in owners:
        return f"{callee}({first.id}, ...)"
    return ""


def _node_writes(node: ast.AST, owners: frozenset[str]) -> Iterator[str]:
    """Each attribute of a name in *owners* that *node* itself writes."""
    for target in _statement_targets(node):
        written = _written_attribute(target, owners)
        if written:
            yield written
    if isinstance(node, ast.Call):
        written = _setattr_owner(node, owners)
        if written:
            yield written


def _attribute_writes(body: Sequence[ast.stmt], owners: frozenset[str]) -> Iterator[tuple[int, str]]:
    """``(line, what)`` for each write to an attribute of a name in *owners* under *body*."""
    for statement in body:
        for node in ast.walk(statement):
            for written in _node_writes(node, owners):
                yield node.lineno, written


def _instance_name(method: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """The name ``self`` (or ``cls``) is bound to in *method*; empty for a static method."""
    if any(_dotted(decorator) == "staticmethod" for decorator in method.decorator_list):
        return ""
    positional = [*method.args.posonlyargs, *method.args.args]
    return positional[0].arg if positional else ""


def _methods(node: ast.ClassDef) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for statement in node.body:
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
            yield statement


def _parameters(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.arg]:
    arguments = function.args
    extra = [arg for arg in (arguments.vararg, arguments.kwarg) if arg is not None]
    return [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs, *extra]


def _string_annotation_names(text: str) -> Iterator[str]:
    try:
        parsed = ast.parse(text, mode="eval")
    except SyntaxError:
        return
    yield from _annotation_names(parsed.body)


def _annotation_names(annotation: ast.expr) -> Iterator[str]:
    """Every dotted name an annotation mentions, string annotations parsed."""
    for node in ast.walk(annotation):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield from _string_annotation_names(node.value)
        elif isinstance(node, ast.Name | ast.Attribute):
            dotted = _dotted(node)
            if dotted:
                yield dotted


def _iterated_targets(function: ast.FunctionDef | ast.AsyncFunctionDef, sources: set[str]) -> set[str]:
    """The names a ``for`` loop binds while iterating a name in *sources*."""
    bound: set[str] = set()
    for node in ast.walk(function):
        if isinstance(node, ast.For | ast.AsyncFor) and isinstance(node.iter, ast.Name) and node.iter.id in sources:
            bound.update(target.id for target in _assigned_targets(node.target) if isinstance(target, ast.Name))
    return bound


class _Scanner:
    """Runs the three checks over one module, given the generator classes of the scan."""

    def __init__(self, graph: ClassGraph, generators: dict[str, ClassInfo]) -> None:
        self._graph = graph
        self._generators = generators
        self._generator_names = frozenset(generators)

    def _names_a(self, module: Module, annotation: ast.expr | None, qualnames: frozenset[str]) -> bool:
        if annotation is None:
            return False
        return any(self._graph.resolve(module, name) in qualnames for name in _annotation_names(annotation))

    def _constructor_context_params(self, info: ClassInfo) -> Iterator[Finding]:
        for method in _methods(info.node):
            if method.name != CONSTRUCTOR:
                continue
            for parameter in _parameters(method):
                if self._names_a(info.module, parameter.annotation, frozenset({CODEGEN_CONTEXT})):
                    yield Finding(
                        info.module.path,
                        parameter.lineno,
                        KIND_CONTEXT_PARAM,
                        f"{info.node.name}.__init__({parameter.arg}: CodegenContext): pass the context to generate",
                    )

    def _post_construction_writes(self, info: ClassInfo) -> Iterator[Finding]:
        for method in _methods(info.node):
            owner = _instance_name(method)
            if method.name == CONSTRUCTOR or not owner:
                continue
            for line, written in _attribute_writes(method.body, frozenset({owner})):
                yield Finding(
                    info.module.path,
                    line,
                    KIND_ASSIGN,
                    f"{info.node.name}.{method.name} assigns {written} after construction",
                )

    def _typed_generator_names(
        self, module: Module, function: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> frozenset[str]:
        """Names in *function* typed as a generator, and ``for`` targets iterating one."""
        typed = {
            parameter.arg
            for parameter in _parameters(function)
            if self._names_a(module, parameter.annotation, self._generator_names)
        }
        typed.update(
            node.target.id
            for node in ast.walk(function)
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and self._names_a(module, node.annotation, self._generator_names)
        )
        typed |= _iterated_targets(function, typed)
        return frozenset(typed)

    def _typed_instance_writes(self, module: Module) -> Iterator[Finding]:
        for function in ast.walk(module.tree):
            if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            typed = self._typed_generator_names(module, function)
            for line, written in _attribute_writes(function.body, typed):
                yield Finding(module.path, line, KIND_ASSIGN, f"{function.name} assigns generator attribute {written}")

    def scan(self, module: Module) -> list[Finding]:
        findings: list[Finding] = []
        for info in self._generators.values():
            if info.module is module:
                findings.extend(self._constructor_context_params(info))
                findings.extend(self._post_construction_writes(info))
        findings.extend(self._typed_instance_writes(module))
        unique = {(finding.line, finding.kind, finding.detail): finding for finding in findings}
        return sorted(unique.values(), key=lambda finding: finding.line)


def _python_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
        if not SKIP_DIRS.intersection(path.relative_to(root).parts):
            yield path


def _parse(root: Path, path: Path) -> Module:
    """Parse *path* under *root*.

    Raises:
        GateInputError: The file is not valid Python or not UTF-8.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as error:
        raise GateInputError(
            f"Cannot parse {path}: {error}. Expected: a UTF-8 Python source file. "
            f"Fix: correct the file, since the gate never skips a file it cannot read."
        ) from error
    module = Module(_module_name(root, path), path, tree)
    _bind_aliases(module)
    return module


def default_roots(workspace: Path) -> list[Path]:
    """The ``src/`` tree of every ``datrix-*`` package on disk."""
    return [
        package / SOURCE_SUBTREE
        for package in workspace_package_dirs(workspace, any_of=frozenset({PackageMarker.SRC}))
    ]


def scan(roots: Sequence[Path]) -> tuple[list[Finding], int, int]:
    """Every finding under *roots*, how many files were read, and how many generator classes were found."""
    modules = [_parse(root, path) for root in roots for path in _python_files(root)]
    graph = ClassGraph(modules)
    generators = graph.generator_classes(GENERATOR_ROOT)
    scanner = _Scanner(graph, generators)
    findings = [finding for module in modules for finding in scanner.scan(module)]
    return findings, len(modules), len(generators)


_PLANTED_KERNEL: Final[str] = textwrap.dedent(
    """\
    from datrix_common.config.codegen_context import CodegenContext


    class Generator:
        def __init__(self) -> None:
            self.description = "base"

        def generate(self, app, context: CodegenContext, output_dir) -> None:
            return None


    class PlatformGenerator(Generator):
        def __init__(self, platform_config: object) -> None:
            self.platform_config = platform_config
    """
)

_PLANTED_KERNEL_INIT: Final[str] = "from .generation.generator import Generator, PlatformGenerator\n"

_PLANTED_TARGET: Final[str] = textwrap.dedent(
    """\
    from datrix_common.config import codegen_context
    from datrix_codegen_kernel import Generator, PlatformGenerator


    class DockerGenerator(PlatformGenerator):
        def __init__(self, context: codegen_context.CodegenContext | None = None) -> None:
            self.cache = {}

        def generate(self, app, context, output_dir) -> None:
            self.context = context
            self.count += 1
            self.spec: str = "x"
            self.a, (self.b, *self.c) = 1, (2, 3)
            for self.item in app:
                print(self.item)
            setattr(self, "late", 1)
            object.__setattr__(self, "later", 2)
            self.__dict__["direct"] = 3
            self.cache["key"] = 4
            local = context
            local.profile = "p"

            def inner() -> None:
                self.nested = 5

        @classmethod
        def build(cls) -> None:
            cls.shared = 6

        @staticmethod
        def helper(other) -> None:
            other.value = 7


    class Unrelated:
        def run(self, context: "codegen_context.CodegenContext") -> None:
            self.context = context


    def attach(generators: "list[Generator]", context) -> None:
        for generator in generators:
            generator.context = context


    def describe(generator: DockerGenerator | None) -> None:
        generator.label = "x"


    def make_variant() -> object:
        class _Variant(DockerGenerator):
            def generate(self, app, context, output_dir) -> None:
                self.variant = context

        return _Variant


    class RememberMixin:
        def remember(self, value) -> None:
            self.remembered = value


    class CachingGenerator(Generator, RememberMixin):
        def generate(self, app, context, output_dir) -> None:
            self.remember(context)
    """
)

#: The planted target lines that must be reported, by kind.
_PLANTED_EXPECTED: Final[frozenset[tuple[int, str]]] = frozenset(
    {
        (6, KIND_CONTEXT_PARAM),
        (10, KIND_ASSIGN),
        (11, KIND_ASSIGN),
        (12, KIND_ASSIGN),
        (13, KIND_ASSIGN),
        (14, KIND_ASSIGN),
        (16, KIND_ASSIGN),
        (17, KIND_ASSIGN),
        (18, KIND_ASSIGN),
        (24, KIND_ASSIGN),
        (28, KIND_ASSIGN),
        (42, KIND_ASSIGN),
        (46, KIND_ASSIGN),
        (52, KIND_ASSIGN),
        (59, KIND_ASSIGN),
    }
)

#: Findings the planted target yields: line 13 writes three attributes.
_PLANTED_COUNT: Final[int] = len(_PLANTED_EXPECTED) + 2

#: Source files the planted tree holds under ``src/``: the kernel's three and the target.
_PLANTED_FILES: Final[int] = 4

#: Generator classes the planted tree declares: the kernel's two, the target's one, its local one,
#: and a second subclass with the mixin it carries.
_PLANTED_GENERATORS: Final[int] = 6


def _plant(scratch: Path) -> Path:
    """Write the planted kernel and target packages (and a tests copy); return the target module."""
    kernel = scratch / "datrix-codegen-kernel" / SOURCE_SUBTREE / "datrix_codegen_kernel"
    target_package = scratch / "datrix-planted"
    target = target_package / SOURCE_SUBTREE / "planted" / "module.py"
    files = {
        kernel / "__init__.py": _PLANTED_KERNEL_INIT,
        kernel / "generation" / "__init__.py": "",
        kernel / "generation" / "generator.py": _PLANTED_KERNEL,
        target: _PLANTED_TARGET,
        target_package / "tests" / "test_module.py": _PLANTED_TARGET,
    }
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return target


def self_test() -> bool:
    """The gate reports every planted shape at its line, and nothing else."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TMP_DIR, prefix="stateless-generator-") as scratch:
        target = _plant(Path(scratch))
        findings, files, generators = scan(default_roots(Path(scratch)))
    found = {(finding.line, finding.kind) for finding in findings}
    misplaced = [finding.render() for finding in findings if finding.path != target]
    if files != _PLANTED_FILES or generators != _PLANTED_GENERATORS or misplaced:
        logger.error("self_test_failed files=%d generators=%d misplaced=%s", files, generators, misplaced)
        return False
    if found != _PLANTED_EXPECTED or len(findings) != _PLANTED_COUNT:
        logger.error(
            "self_test_failed missed=%s unexpected=%s count=%d",
            sorted(_PLANTED_EXPECTED - found),
            sorted(found - _PLANTED_EXPECTED),
            len(findings),
        )
        return False
    logger.info("self_test_passed findings=%d", len(findings))
    return True


def run_gate(roots: Sequence[Path]) -> int:
    """Scan *roots*; print each finding and a count."""
    try:
        findings, files, generators = scan(roots)
    except GateInputError as error:
        print(f"FAIL {error}")
        return _EXIT_GATE_BROKEN
    if generators == 0:
        print(f"FAIL no Generator subclass found under {len(roots)} src tree(s); expected the kernel's {GENERATOR_ROOT}")
        return _EXIT_GATE_BROKEN
    for finding in findings:
        print(f"FAIL {finding.render()}")
    print(
        f"{files} file(s) under {len(roots)} src tree(s), {generators} generator class(es), "
        f"{len(findings)} piece(s) of generator run state"
    )
    return _EXIT_FINDINGS if findings else _EXIT_OK


def _check_planted_run_state_is_reported_exactly() -> None:
    assert self_test(), "the scan did not report exactly the planted run state (see the self_test_failed record)"


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/repo-hygiene/stateless-generator-gate.ps1``: one per wrapper parameter, spelled
    exactly."""
    return roots_gate_parser(
        WRAPPER,
        "Fail if a generator holds run state: an attribute assigned after construction, or a constructor that "
        "takes the run context.",
        debug=True,
    )


def _run(args: argparse.Namespace) -> int:
    report_by_printing(args.debug)
    if args.self_test:
        return wrappers.run_self_test(
            [_check_planted_run_state_is_reported_exactly, check_requested_roots_split_on_commas],
            wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=wrappers.REPO_HYGIENE_GATES_DIR,
        )
    if not self_test():
        print("Stateless-generator gate self-test failed: the gate cannot tell generator run state from clean code.")
        return _EXIT_GATE_BROKEN
    requested = requested_roots(args.roots)
    return run_gate([Path(root) for root in requested] if requested else default_roots(WORKSPACE_DIR))


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
