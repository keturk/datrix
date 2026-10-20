"""How the ``scripts/dev/`` modules read the values their wrappers pass."""

from __future__ import annotations

from collections.abc import Sequence


def comma_values(values: Sequence[str]) -> list[str]:
    """Every value of *values* split on commas, stripped, empty items dropped, in given order.

    ``powershell -File`` passes ``-Module "a,b"`` as one string, so a list parameter is given either
    as one comma-separated value or as one value per item, and both read alike.
    """
    return [item.strip() for value in values for item in value.split(",") if item.strip()]
