"""Count-map ratchets: the two semantics the gates use, and the baseline table they read.

A count ratchet compares a live ``{key: count}`` map with a committed baseline map:

``TIGHTEN_ONLY``
    An increase fails; a decrease passes (bank it with the gate's ``--update-baseline``); a key
    the baseline does not name is pinned at zero.
``EXACT_PIN``
    Any difference fails: an increase is a regression and an unbanked decrease is an improvement
    the baseline must record in the same change. When the caller names the key set (the
    registered targets), a baseline key outside it is stale.

``compare`` returns the failing deltas; each gate formats its own message from them. A baseline
file that does not exist, or a table holding anything but non-negative integers, is a
``ValueError`` -- a missing baseline never reads as empty, which would pass every count.
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class RatchetMode(StrEnum):
    TIGHTEN_ONLY = "tighten-only"
    EXACT_PIN = "exact-pin"


@dataclass(frozen=True)
class RatchetDelta:
    """One failing key: its baseline count, its live count, and whether the key is stale."""

    key: str
    frozen: int
    current: int
    stale: bool = False

    @property
    def increased(self) -> bool:
        return not self.stale and self.current > self.frozen

    @property
    def decreased(self) -> bool:
        return not self.stale and self.current < self.frozen


def compare(
    current: Mapping[str, int],
    baseline: Mapping[str, int],
    mode: RatchetMode,
    *,
    keys: frozenset[str] | None = None,
) -> list[RatchetDelta]:
    """The failing deltas of ``current`` against ``baseline`` under ``mode``, sorted by key.

    ``keys`` restricts the comparison to a known key set (every key in it is compared, a missing
    live or baseline count reading as zero); under ``EXACT_PIN`` a baseline key outside ``keys``
    is reported stale. Without ``keys`` the compared set is the live keys (``TIGHTEN_ONLY``) or
    the union of live and baseline keys (``EXACT_PIN``).
    """
    if keys is not None:
        compared = set(keys)
    elif mode is RatchetMode.TIGHTEN_ONLY:
        compared = set(current)
    else:
        compared = set(current) | set(baseline)

    deltas: list[RatchetDelta] = []
    for key in sorted(compared):
        live = current.get(key, 0)
        frozen = baseline.get(key, 0)
        failing = live > frozen if mode is RatchetMode.TIGHTEN_ONLY else live != frozen
        if failing:
            deltas.append(RatchetDelta(key=key, frozen=frozen, current=live))
    if keys is not None and mode is RatchetMode.EXACT_PIN:
        for key in sorted(set(baseline) - keys):
            deltas.append(RatchetDelta(key=key, frozen=baseline[key], current=0, stale=True))
    return deltas


def read_counts(table: object, *, source: Path, table_name: str) -> dict[str, int]:
    """Validate a parsed baseline table as ``{str: non-negative int}``.

    Raises:
        ValueError: ``table`` is not a mapping, or a value is a bool, not an int, or negative --
            naming the file, the table, the key and the value.
    """
    if not isinstance(table, dict):
        raise ValueError(
            f"{source}: [{table_name}] is {type(table).__name__}, expected a table of "
            "key = count entries. Fix: restore the table, seeded from a live run of the gate."
        )
    counts: dict[str, int] = {}
    for key, value in table.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(
                f"{source}: [{table_name}] {key!r} = {value!r}; expected a non-negative integer "
                "(a bool is not one). Fix: write the live count for the key."
            )
        counts[str(key)] = value
    return counts


def _missing(path: Path) -> ValueError:
    return ValueError(
        f"count baseline {path} does not exist. A missing baseline is not an empty one. "
        "Fix: restore the file, or create it from the live tree with the gate's --update-baseline."
    )


def load_counts_json(path: Path, *, table_key: str) -> dict[str, int]:
    """Read ``{table_key: {key: count}}`` from a JSON baseline; missing file is a ValueError."""
    if not path.is_file():
        raise _missing(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: not valid JSON ({exc}). Fix: correct the syntax.") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object holding {table_key!r}. Fix: restore it.")
    return read_counts(data.get(table_key), source=path, table_name=table_key)


def load_counts_toml(path: Path, *, table_key: str) -> dict[str, int]:
    """Read ``[table_key]`` from a TOML baseline; missing file is a ValueError."""
    if not path.is_file():
        raise _missing(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{path}: not valid TOML ({exc}). Fix: correct the syntax.") from exc
    return read_counts(data.get(table_key), source=path, table_name=table_key)


def write_counts_json(
    path: Path, counts: Mapping[str, int], *, comment: str, table_key: str
) -> None:
    """Write ``{"_comment": comment, table_key: counts}`` sorted by key."""
    payload = {"_comment": comment, table_key: {key: counts[key] for key in sorted(counts)}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _toml_key(key: str) -> str:
    bare = key.replace("-", "").replace("_", "").isalnum() and key.isascii()
    return key if bare else json.dumps(key)


def write_counts_toml(
    path: Path, counts: Mapping[str, int], *, header: str, table_key: str
) -> None:
    """Write ``header`` (each line as a ``#`` comment) then ``[table_key]`` sorted by key."""
    lines = [f"# {line}".rstrip() for line in header.splitlines()]
    lines.append("")
    lines.append(f"[{table_key}]")
    lines.extend(f"{_toml_key(key)} = {counts[key]}" for key in sorted(counts))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
