"""Resolve dotted ``datrix_*`` references against the installed framework.

A dotted reference (``datrix_common.utils.text.to_snake_case``) written in text
-- a committed snapshot, a generator template, a comment or docstring in
framework source -- names a module and, optionally, a member chain under it.
Text is never imported, so nothing notices when the module moves or the member
is renamed. This module is the one resolver every gate uses to notice.

Resolution: the longest leading run of segments ``importlib.util.find_spec``
finds is imported, and each remaining segment must be a member of the object
before it. A member is an attribute, or -- on a class -- a declared field that
is not a class attribute: a Pydantic model field, a dataclass field, an
annotated attribute anywhere in the MRO, or an instance attribute a method of a
class in the MRO assigns on ``self``. A chain is followed through attributes
only; a segment after a declared field is not checked, because a field's value
does not exist on the class.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
import re
import textwrap
from collections.abc import Sequence
from typing import Final

#: A dotted framework reference: a ``datrix_*`` package followed by one or more
#: dotted identifier segments. A ``datrix_*`` segment preceded by a dot is part
#: of a longer chain (``datrix_common.datrix_model.ui``), never a reference of
#: its own.
FRAMEWORK_REFERENCE: Final = re.compile(
    r"(?<![\w.])datrix_[a-z0-9_]+(?:\.[A-Za-z_][A-Za-z0-9_]*)+"
)

_PYDANTIC_FIELDS_ATTRIBUTE: Final = "model_fields"
_DATACLASS_FIELDS_ATTRIBUTE: Final = "__dataclass_fields__"
_SELF: Final = "self"


def _assigns_self_attribute(klass: type, name: str) -> bool:
    """Whether a method in *klass*'s own source assigns ``self.<name>``."""
    try:
        source = inspect.getsource(klass)
    except (OSError, TypeError):
        return False
    tree = ast.parse(textwrap.dedent(source))
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        for target in targets:
            if (
                isinstance(target, ast.Attribute)
                and target.attr == name
                and isinstance(target.value, ast.Name)
                and target.value.id == _SELF
            ):
                return True
    return False


def _declared_field(owner: type, name: str) -> bool:
    """Whether *name* is a member *owner* declares without a class attribute.

    A Pydantic or dataclass field, an annotation anywhere in the MRO, or an
    instance attribute a method of a class in the MRO assigns on ``self``.
    """
    for fields_attribute in (_PYDANTIC_FIELDS_ATTRIBUTE, _DATACLASS_FIELDS_ATTRIBUTE):
        fields = getattr(owner, fields_attribute, None)
        if isinstance(fields, dict) and name in fields:
            return True
    if any(name in inspect.get_annotations(klass) for klass in owner.__mro__):
        return True
    return any(
        _assigns_self_attribute(klass, name)
        for klass in owner.__mro__
        if klass.__module__ != object.__module__
    )


class ReferenceResolver:
    """Resolves dotted ``datrix_*`` references through ``importlib``, caching verdicts."""

    def __init__(self) -> None:
        self._verdicts: dict[str, str | None] = {}

    def unresolved_reason(self, reference: str) -> str | None:
        """Return why *reference* does not resolve, or ``None`` when it does."""
        if reference not in self._verdicts:
            self._verdicts[reference] = self._resolve(reference)
        return self._verdicts[reference]

    @staticmethod
    def _longest_importable_prefix(parts: Sequence[str]) -> int:
        """Length of the longest leading run of *parts* ``find_spec`` finds; 0 when none.

        ``find_spec`` on a dotted name imports its parents, so a parent that
        raises while importing propagates: that is a broken module, reported by
        the caller, never a shorter prefix.
        """
        for length in range(len(parts), 0, -1):
            try:
                spec = importlib.util.find_spec(".".join(parts[:length]))
            except (ModuleNotFoundError, ValueError):
                continue
            if spec is not None:
                return length
        return 0

    def _resolve(self, reference: str) -> str | None:
        parts = reference.split(".")
        try:
            length = self._longest_importable_prefix(parts)
            if length == 0:
                return f"top-level package '{parts[0]}' is not importable"
            module_name = ".".join(parts[:length])
            target: object = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 -- any import-time failure is this reference's verdict
            return f"importing it raises {type(exc).__name__}: {exc}"
        for position in range(length, len(parts)):
            name = parts[position]
            if hasattr(target, name):
                target = getattr(target, name)
                continue
            if isinstance(target, type) and _declared_field(target, name):
                return None
            return f"'{'.'.join(parts[:position])}' has no attribute or submodule '{name}'"
        return None
