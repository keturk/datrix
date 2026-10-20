"""AST helpers and self-test fixtures shared by two or more import-boundary scanners."""

from __future__ import annotations

import ast
import json
import re
import sys
import tomllib
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from datrix_common.plugin.capability_resolution import (
    declaration_for_language,
)

from datrix_scripts.count_ratchet import RatchetMode, compare
from datrix_scripts.gate_harness import NamedCheck, report_condition
from datrix_scripts.paths import WORKSPACE_DIR

#: The command line the scanners' CLI non-vacuity self-tests run as a subprocess: the scan alone
#: (this package's ``__main__``), under the interpreter running them, whose ``PYTHONPATH`` it inherits.
CLI_COMMAND: tuple[str, ...] = (sys.executable, "-m", "datrix_scripts.scan.import_boundaries")

# Language-core packages: a package holding one language's transpiler core,
# language profile and web-client mechanics, split out of that language's
# backend generator so a frontend target emitting the same file language can
# depend on it without depending on the backend. It registers no entry point
# (it is a library, not a plugin), so the taxonomy cannot discover its role;
# each one is named here with the language package it serves.
#
# The language it serves and every frontend target emitting that language may
# import it; every other language (and that language's own core) is a sibling
# it may not reach, and the platform, SQL, component and extension packages --
# forbidden the language layer -- are forbidden it too.
LANGUAGE_CORE_PACKAGES: dict[str, str] = {
    "datrix_codegen_typescript_core": "datrix_codegen_typescript",
}


@dataclass(frozen=True)
class PackageInfo:
    """Package metadata for scanning."""

    name: str  # e.g., datrix_common
    root: Path  # e.g., d:/datrix/datrix-common
    src_dir: Path  # e.g., d:/datrix/datrix-common/src/datrix_common


#: The array of tables every count baseline holds: ``[[baseline]] <key> = "..." count = <int>``.
_BASELINE_TABLE = "baseline"
_BASELINE_COUNT_FIELD = "count"
_BASELINE_REASON_FIELD = "reason"
#: The entry key of a per-file count baseline.
FILE_BASELINE_KEY = "file"
_NO_REASONS: Mapping[str, str] = MappingProxyType({})


@dataclass(frozen=True)
class CountBaseline:
    """A frozen count record: one count per key, plus the written reason of every entry
    that carries one.

    A reason is part of the frozen record, not a comment beside it: ``--update-baseline``
    reads it back and re-emits it, so a regenerated baseline never silently turns a
    reviewed entry into an unexplained count.
    """

    counts: dict[str, int]
    reasons: dict[str, str]


def load_count_baseline(baseline_path: Path, *, key_field: str = FILE_BASELINE_KEY) -> CountBaseline:
    """Read a count baseline's ``[[baseline]]`` entries.

    ``key_field`` names the entry's key (``file`` for a per-file ratchet, ``package`` for a
    per-package one). A ``reason`` is kept only when it is a non-blank string.

    Raises:
        FileNotFoundError: The baseline does not exist; a ratchet never runs against an
            absent record (run the scan with ``--update-baseline`` to freeze one).
        ValueError: An entry has no non-empty string ``key_field`` or no integer ``count``.
    """
    with baseline_path.open("rb") as handle:
        data = tomllib.load(handle)
    counts: dict[str, int] = {}
    reasons: dict[str, str] = {}
    for index, entry in enumerate(data.get(_BASELINE_TABLE, [])):
        fields = entry if isinstance(entry, dict) else {}
        key = fields.get(key_field)
        count = fields.get(_BASELINE_COUNT_FIELD)
        if not isinstance(key, str) or not key or type(count) is not int:
            raise ValueError(
                f"{baseline_path}: [[{_BASELINE_TABLE}]] entry {index} must carry a non-empty "
                f"string '{key_field}' and an integer '{_BASELINE_COUNT_FIELD}', got {entry!r}. "
                f"Fix the entry, or regenerate the file with --update-baseline."
            )
        counts[key] = count
        reason = fields.get(_BASELINE_REASON_FIELD)
        if isinstance(reason, str) and reason.strip():
            reasons[key] = reason
    return CountBaseline(counts=counts, reasons=reasons)


def write_count_baseline(
    baseline_path: Path,
    counts: dict[str, int],
    *,
    header: str,
    key_field: str = FILE_BASELINE_KEY,
    reasons: Mapping[str, str] = _NO_REASONS,
) -> None:
    """Write ``counts`` as ``[[baseline]]`` entries under ``header``, sorted by key.

    A ``reason`` is emitted for every key in ``reasons`` that still has a count, so a
    hand-written reason survives every regeneration; a key without one is written without
    one (a reason is never invented here).
    """
    lines = [header]
    for key in sorted(counts):
        lines.append(f"\n[[{_BASELINE_TABLE}]]\n")
        lines.append(f'{key_field} = "{key}"\n')
        lines.append(f"{_BASELINE_COUNT_FIELD} = {counts[key]}\n")
        if key in reasons:
            # json.dumps yields a TOML basic string: the escapes it emits
            # (\" \\ \n \r \t \b \f \uXXXX) are all TOML basic-string escapes.
            lines.append(f"{_BASELINE_REASON_FIELD} = {json.dumps(reasons[key])}\n")
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text("".join(lines), encoding="utf-8")


def tighten_only_messages(current: dict[str, int], baseline: dict[str, int], label: str) -> list[str]:
    """One message per key whose ``label`` count rose above its baseline (an absent key is 0).

    A decrease never fails: these ratchets only tighten.
    """
    return [
        f"{delta.key}: {label} count increased from baseline {delta.frozen} to {delta.current}"
        for delta in compare(current, baseline, RatchetMode.TIGHTEN_ONLY)
    ]


# Registered-target identifier-segment call names this ratchet treats as a
# TYPE reference (the second argument names a class/type, not a value).
_TYPE_REFERENCE_CALL_NAMES: frozenset[str] = frozenset({"isinstance", "issubclass"})

_CAMEL_TO_SNAKE_RE1 = re.compile(r"(.)([A-Z][a-z]+)")
_CAMEL_TO_SNAKE_RE2 = re.compile(r"([a-z0-9])([A-Z])")


def _identifier_segments(identifier: str) -> tuple[str, ...]:
    """Tokenize *identifier* into lowercase segments, splitting on ``_`` and
    at camelCase word boundaries (``fooBar`` -> ``foo``, ``bar``;
    ``PythonStructFieldRow`` -> ``python``, ``struct``, ``field``, ``row``).
    """
    with_boundaries = _CAMEL_TO_SNAKE_RE1.sub(r"\1_\2", identifier)
    with_boundaries = _CAMEL_TO_SNAKE_RE2.sub(r"\1_\2", with_boundaries)
    return tuple(seg.lower() for seg in with_boundaries.split("_") if seg)


def _identifier_carries_target_name(
    identifier: str, target_names: frozenset[str]
) -> str | None:
    """Return the registered target name *identifier* carries as a segment
    (or a contiguous run of adjacent camelCase segments -- e.g.
    ``TypeScript`` tokenizes as ``type`` + ``script``, which must still
    match the single registered target name ``typescript``), or ``None`` if
    it carries none.

    Segment-EXACT matching (never bare substring) is deliberate: ``java``
    must never match inside a hypothetical ``javascript`` identifier (a
    single, unsplit segment, since it has no internal capital or
    underscore) -- only a genuine identifier segment, or an exact
    concatenation of adjacent segments, counts.

    Args:
        identifier: The identifier to test.
        target_names: Registered language names and their declared alias
            tokens, lowercased (``shared_target_name_vocabulary()``).

    Returns:
        The matched target name or alias token, or ``None``.
    """
    segments = _identifier_segments(identifier)
    for start in range(len(segments)):
        for end in range(start + 1, len(segments) + 1):
            candidate = "".join(segments[start:end])
            if candidate in target_names:
                return candidate
    return None


_TYPE_ALIAS_ANNOTATION_NAME = "TypeAlias"


def _annotation_declares_type_alias(annotation: ast.AST) -> bool:
    """True when *annotation* is ``TypeAlias`` or a dotted ``<module>.TypeAlias``
    (``typing.TypeAlias``, ``typing_extensions.TypeAlias``).

    The value of an annotated assignment is a type expression only under this
    annotation, where a string element really is a forward reference
    (``X: TypeAlias = "Foo | Bar"``). Under any other annotation the value is
    data (``EXTS: tuple[str, ...] = ("js", "css")``) and a string in it is not
    an identifier.
    """
    if isinstance(annotation, ast.Name):
        return annotation.id == _TYPE_ALIAS_ANNOTATION_NAME
    if isinstance(annotation, ast.Attribute):
        return annotation.attr == _TYPE_ALIAS_ANNOTATION_NAME
    return False


def _identifiers_in_type_expression(node: ast.AST) -> list[tuple[str, int]]:
    """Every ``(identifier, line_number)`` pair reachable from *node* by
    walking ONLY the syntactic shapes a type expression / isinstance
    argument can take: a bare name, a dotted attribute (``mod.Name``), a
    ``X | Y`` union, a generic subscript (``Callable[..., X | Y]``,
    ``Union[X, Y]``), a tuple of names (the ``isinstance(x, (A, B))`` form),
    or a string forward-reference.

    Does NOT descend into a function/lambda body, a comprehension, or any
    other executable-statement context -- this is only ever called on an
    annotation / isinstance-argument / base-class / type-alias-value
    expression, which is what keeps an ordinary local variable (e.g.
    ``local_cache = {}`` inside a function body) out of scope entirely: it
    is never a type expression (see the module docstring for why this
    matters -- a bare local variable can coincidentally be named after a
    registered language, e.g. ``python = fetch_stat()``).
    """
    results: list[tuple[str, int]] = []
    stack: list[ast.AST] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, ast.Name):
            results.append((current.id, current.lineno))
        elif isinstance(current, ast.Attribute):
            results.append((current.attr, current.lineno))
        elif isinstance(current, ast.BinOp) and isinstance(current.op, ast.BitOr):
            stack.extend([current.left, current.right])
        elif isinstance(current, ast.Subscript):
            stack.append(current.value)
            stack.append(current.slice)
        elif isinstance(current, (ast.Tuple, ast.List)):
            stack.extend(current.elts)
        elif isinstance(current, ast.Constant) and isinstance(current.value, str):
            results.append((current.value, current.lineno))
    return results


def _scoped_plain_assign_targets(tree: ast.Module) -> list[tuple[str, int]]:
    """Every ``(identifier, line_number)`` target of a plain (unannotated)
    ``ast.Assign`` statement declared at MODULE top level or immediate
    CLASS-BODY level -- never inside a function/method body.

    This is the scoped counterpart to the ``ast.AnnAssign`` handling in
    ``scan_file_for_shared_target_names``: an annotated declaration
    (``StructSliceBuilder: TypeAlias = ...``) is always a genuine module- or
    class-level declaration syntactically, but a PLAIN assignment
    (``PYTHON_DEFAULT_PORT = 8000``) is syntactically identical
    to an ordinary function-local variable assignment -- the only thing
    that distinguishes a real module constant from
    ``def f(): python_helper = 1`` is WHERE the statement sits in the tree.
    Restricting to ``tree.body`` and each ``ClassDef.body`` (a SCOPED
    traversal, never a blanket ``ast.walk``) is what keeps a function-body
    assignment out of scope, exactly like the declaration/type-reference-only
    dispatch in ``scan_file_for_shared_target_names`` keeps a bare local
    variable out of scope.

    Args:
        tree: The parsed module AST.

    Returns:
        ``(identifier, line_number)`` pairs for every ``ast.Name`` target of
        a qualifying plain ``Assign`` statement.
    """
    targets: list[tuple[str, int]] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            targets.extend(
                (target.id, stmt.lineno)
                for target in stmt.targets
                if isinstance(target, ast.Name)
            )
        elif isinstance(stmt, ast.ClassDef):
            for class_stmt in stmt.body:
                if isinstance(class_stmt, ast.Assign):
                    targets.extend(
                        (target.id, class_stmt.lineno)
                        for target in class_stmt.targets
                        if isinstance(target, ast.Name)
                    )
    return targets


#: The declaration/type-reference position an identifier was found in.
DeclarationKind = Literal["class_def", "function_def", "field_or_alias", "type_reference"]
DeclarationIdentifier = tuple[str, int, DeclarationKind]


def declaration_identifiers(tree: ast.Module) -> list[DeclarationIdentifier]:
    """Every ``(identifier, line_number, kind)`` in a declaration or
    type-reference position: a class or function/method DEFINITION name, a
    base class, a parameter or return annotation, an annotated field or type
    alias name with its annotation (and a ``TypeAlias``'s value), an
    ``isinstance``/``issubclass`` type argument -- in AST-walk order -- then
    each module-/class-level plain assignment target
    (``_scoped_plain_assign_targets``). Never a bare local variable,
    parameter name, loop variable or attribute read: the identifier-shape
    ratchets match only these positions."""
    identifiers = [
        identifier for node in ast.walk(tree) for identifier in _node_declarations(node)
    ]
    identifiers.extend(
        (identifier, line_number, "field_or_alias")
        for identifier, line_number in _scoped_plain_assign_targets(tree)
    )
    return identifiers


def _type_references(expression: ast.AST) -> Iterator[DeclarationIdentifier]:
    """Every identifier of a type expression, as a ``type_reference``."""
    for identifier, lineno in _identifiers_in_type_expression(expression):
        yield identifier, lineno, "type_reference"


def _class_declarations(node: ast.ClassDef) -> Iterator[DeclarationIdentifier]:
    """A class definition's name, then each base class's type references."""
    yield node.name, node.lineno, "class_def"
    for base in node.bases:
        yield from _type_references(base)


def _function_declarations(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterator[DeclarationIdentifier]:
    """A function definition's name, then its parameter and return annotations."""
    yield node.name, node.lineno, "function_def"
    arguments = node.args
    for arg in (*arguments.args, *arguments.kwonlyargs, arguments.vararg, arguments.kwarg):
        if arg is not None and arg.annotation is not None:
            yield from _type_references(arg.annotation)
    if node.returns is not None:
        yield from _type_references(node.returns)


def _annotated_declarations(
    node: ast.AnnAssign, target: ast.Name
) -> Iterator[DeclarationIdentifier]:
    """An annotated field or alias's name, a type alias's value, then its annotation."""
    yield target.id, node.lineno, "field_or_alias"
    if node.value is not None and _annotation_declares_type_alias(node.annotation):
        yield from _type_references(node.value)
    yield from _type_references(node.annotation)


def _type_check_references(node: ast.Call) -> Iterator[DeclarationIdentifier]:
    """The type arguments of an ``isinstance()``/``issubclass()`` call."""
    func = node.func
    if isinstance(func, ast.Name) and func.id in _TYPE_REFERENCE_CALL_NAMES:
        for call_arg in node.args[1:]:
            yield from _type_references(call_arg)


def _node_declarations(node: ast.AST) -> Iterator[DeclarationIdentifier]:
    """The declaration and type-reference identifiers one AST node carries."""
    if isinstance(node, ast.ClassDef):
        yield from _class_declarations(node)
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        yield from _function_declarations(node)
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        yield from _annotated_declarations(node, node.target)
    elif isinstance(node, ast.Call):
        yield from _type_check_references(node)


def _language_name_tokens(language_name: str) -> frozenset[str]:
    """One language's identifier vocabulary: its registered name plus every
    declared alias (``declaration_for_language(...).name_tokens``), lowercase."""
    return frozenset(
        token.lower()
        for token in (*declaration_for_language(language_name).name_tokens, language_name)
    )




# ---------------------------------------------------------------------------
# Self-Test (--self-test)
#
# Proves the rule model, the AST scanners, and the ratchet comparators are
# non-vacuous: every check below is exercised against both a known-good and a
# known-bad case, and the CLI mutation proof plants a real regression in an
# isolated fixture and proves detection + clearing on revert. Runs
# automatically as step 1 of every normal invocation (see main()); can also
# be run standalone via --self-test. Real files are written under
# D:\datrix\.tmp\ per this project's temp-file policy -- never
# unittest.mock/SimpleNamespace.
# ---------------------------------------------------------------------------

_SELF_TEST_SCRATCH_ROOT = WORKSPACE_DIR / ".tmp" / "check_import_boundaries_selftest"

#: The prefix a scanner's self-test function carries; its check is reported without it.
_SELF_TEST_PREFIX = "_self_test_"


def _check(label: str, condition: bool) -> bool:
    """Report one self-test assertion through the gate harness, label first, and return it."""
    return report_condition(condition, label)


def self_test_check(self_test: Callable[[], bool], name: str = "") -> NamedCheck:
    """One scanner self-test as a harness check.

    A scanner self-test reports each of its assertions as it goes and returns whether all held;
    the check fails when it returned False, so ``gate_harness.run_checks`` counts it. ``name``
    is required for a self-test bound to its arguments (a ``functools.partial`` has no name).
    """
    check_name = name or self_test.__name__.removeprefix(_SELF_TEST_PREFIX)

    def run() -> None:
        if not self_test():
            raise AssertionError(f"{check_name}: an assertion above reported [FAIL]")

    return NamedCheck(check_name, run)


def _self_test_write_manifest(
    tmp_root: Path,
    dist_name: str,
    import_package: str,
    *,
    entry_point_groups: dict[str, dict[str, str]],
) -> Path:
    """Write a minimal ``pyproject.toml`` for a fixture package.

    Creates ``<tmp_root>/<dist_name>/pyproject.toml`` declaring *dist_name*
    and the given ``[project.entry-points."<group>"]`` tables (each value is
    an object reference rooted at *import_package*). The scanner's taxonomy
    discovery reads exactly this shape.
    """
    package_dir = tmp_root / dist_name
    package_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "[project]",
        f'name = "{dist_name}"',
        'version = "0.0.0"',
        "",
    ]
    for group, entries in entry_point_groups.items():
        lines.append(f'[project.entry-points."{group}"]')
        for entry_name, attribute in entries.items():
            lines.append(f'{entry_name} = "{import_package}.plugin:{attribute}"')
        lines.append("")
    manifest = package_dir / "pyproject.toml"
    manifest.write_text("\n".join(lines), encoding="utf-8")
    return manifest
