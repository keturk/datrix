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


def _datrix_float_or_none(
    value: decimal.Decimal | float | int | str | None,
) -> float | None:
    """A nullable DSL number bound to a ``Float?`` slot: ``None`` flows through unchanged.

    Accepts a ``Decimal``, ``int``, ``float`` or a numeric string -- the form a
    Decimal-origin number takes after crossing a service boundary as JSON, since
    ``_json_helpers._json_default`` encodes ``decimal.Decimal`` as a string.
    """
    if value is None:
        return None
    return float(value)


def _datrix_decimal_or_none(
    value: decimal.Decimal | float | int | str | None,
) -> decimal.Decimal | None:
    """A nullable DSL number bound to a ``Decimal?`` slot: ``None`` flows through unchanged.

    Converts through ``str`` so a float's shortest round-trip repr is what the
    Decimal carries, never the binary expansion ``decimal.Decimal(0.1)`` would;
    a numeric string (JSON-encoded Decimal) parses as written.
    """
    if value is None:
        return None
    return decimal.Decimal(str(value))


def _datrix_int_or_none(value: float | int | str | None) -> int | None:
    """A nullable JSON number bound to an ``Integer?`` slot: ``None`` flows through unchanged."""
    if value is None:
        return None
    return int(value)


def _datrix_exc_message(exc: BaseException) -> str:
    """Message for a DSL ``<exception>.message`` read, including the cause chain.

    ``str(exc)`` alone is empty for the whole family of exceptions that carry
    their detail in ``__cause__`` rather than in their own args.  Every ``httpx``
    transport error is built that way -- ``httpx`` raises ``mapped_exc(str(inner))
    from inner`` over an ``httpcore`` error which in turn wraps an ``anyio``
    exception with empty args -- so a peer that closes the connection during the
    TLS handshake and a name-resolution failure both render as ``ConnectError('')``
    and cannot be told apart by whoever reads the log.

    When the exception carries a message of its own it is returned unchanged, so
    every message that has content today is byte-identical.  Only the provably
    contentless case walks the chain, preferring ``__cause__`` (explicit
    ``raise ... from ...``) over ``__context__`` (implicit chaining, which is how
    ``httpcore``'s ``map_exceptions`` and several stdlib paths chain), and renders
    each hop's class name plus whatever detail that hop does carry.

    The walk is guarded by an identity set: a handler that re-raises an exception
    it caught can produce a cyclic chain, and an unguarded walk would not
    terminate.
    """
    text = str(exc)
    if text:
        return text
    chain = [type(exc).__name__]
    seen = {id(exc)}
    current: BaseException = exc
    while True:
        nxt = current.__cause__ or current.__context__
        if nxt is None or id(nxt) in seen:
            return " <- ".join(chain)
        seen.add(id(nxt))
        current = nxt
        detail = str(current)
        name = type(current).__name__
        chain.append(f"{name}({detail})" if detail else name)
