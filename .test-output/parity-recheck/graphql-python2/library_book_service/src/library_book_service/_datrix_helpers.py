"""Small runtime helpers for generated Datrix service code."""

from __future__ import annotations

import decimal
import enum


def _datrix_str(value: object) -> str:
    """String conversion matching Datrix DSL concatenation semantics."""
    if value is None:
        return ""
    if isinstance(value, enum.Enum):
        return str(value.value)
    if isinstance(value, decimal.Decimal):
        text = format(value.normalize(), "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text
    return str(value)
