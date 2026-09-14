"""Domain errors for contract validation (auto-generated)."""

from __future__ import annotations

from typing import Mapping


class ContractViolationError(Exception):
    """Raised when an event payload violates a declared ``ensure`` clause."""

    __slots__ = ("event", "clause", "actual")

    def __init__(
        self,
        *,
        event: str,
        clause: str,
        actual: Mapping[str, object],
    ) -> None:
        self.event = event
        self.clause = clause
        self.actual = actual
        super().__init__(
            f"Contract violation: event={event!r} clause={clause!r} actual={dict(actual)!r}"
        )
