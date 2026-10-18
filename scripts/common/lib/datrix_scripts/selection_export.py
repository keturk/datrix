"""pytest plugin exporting a session's final selection: each item's node ID and ``serial`` mark.

Loaded with ``-p datrix_scripts.selection_export`` and given
``--datrix-selection-out=<path>``. After collection -- once every
``pytest_collection_modifyitems`` hook (feature tags, ``-k``, ``-m``) has filtered
-- it writes the items the session kept to that path, so a later session can run
exactly those node IDs without collecting the test tree again. It never changes
which items are collected or selected, and without the option it does nothing.

The file is ``{"schema": 1, "items": [{"nodeid": "<id>", "serial": <bool>}]}``,
written through a temporary file in the same directory and one replace, so a
reader never sees a partial export. :func:`read_selection` is its one reader.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    import pytest

SELECTION_OUT_OPTION: Final[str] = "--datrix-selection-out"
SELECTION_SCHEMA: Final[int] = 1
#: The marker of tests that must run one at a time, outside any worker pool.
SERIAL_MARKER: Final[str] = "serial"

_OPTION_DEST: Final[str] = "datrix_selection_out"
_SCHEMA_KEY: Final[str] = "schema"
_ITEMS_KEY: Final[str] = "items"
_NODEID_KEY: Final[str] = "nodeid"
_SERIAL_KEY: Final[str] = "serial"


@dataclass(frozen=True)
class SelectedItem:
    """One item a session kept: its node ID and whether it carries the ``serial`` mark."""

    nodeid: str
    serial: bool


class SelectionExportError(RuntimeError):
    """A selection export is missing or does not hold the expected schema."""


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        SELECTION_OUT_OPTION,
        dest=_OPTION_DEST,
        default=None,
        metavar="PATH",
        help="write the node IDs and serial marks of the selected items to PATH as JSON",
    )


def pytest_collection_finish(session: pytest.Session) -> None:
    """Write the session's final items when an export path was given."""
    out = session.config.getoption(_OPTION_DEST)
    if out is None:
        return
    items = [
        SelectedItem(nodeid=item.nodeid, serial=item.get_closest_marker(SERIAL_MARKER) is not None)
        for item in session.items
    ]
    write_selection(Path(out), items)


def write_selection(path: Path, items: Sequence[SelectedItem]) -> None:
    """Write *items* to *path* in the export schema, through a temporary file and one replace."""
    payload = {
        _SCHEMA_KEY: SELECTION_SCHEMA,
        _ITEMS_KEY: [{_NODEID_KEY: item.nodeid, _SERIAL_KEY: item.serial} for item in items],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, staging = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".part", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=1)
            stream.write("\n")
        os.replace(staging, path)
    except BaseException:
        Path(staging).unlink(missing_ok=True)
        raise


def read_selection(path: Path) -> tuple[SelectedItem, ...]:
    """The items of the export at *path*.

    Raises:
        SelectionExportError: the file does not exist, is not JSON, or does not
            hold the schema-1 shape; the message names the file.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise SelectionExportError(
            f"The selection export {path} was not written. Expected the collection session "
            f"loading -p datrix_scripts.selection_export with {SELECTION_OUT_OPTION}={path} "
            f"to write it when collection finished. Check that the session loaded the plugin "
            f"(the scripts package must be on PYTHONPATH)."
        ) from error
    try:
        payload: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise SelectionExportError(
            f"The selection export {path} is not JSON ({error}). Expected the schema "
            f'{{"{_SCHEMA_KEY}": {SELECTION_SCHEMA}, "{_ITEMS_KEY}": [...]}} written by '
            f"datrix_scripts.selection_export. Re-run the collection to rewrite it."
        ) from error
    return _items_of(path, payload)


def _items_of(path: Path, payload: object) -> tuple[SelectedItem, ...]:
    if not isinstance(payload, dict) or payload.get(_SCHEMA_KEY) != SELECTION_SCHEMA:
        raise SelectionExportError(
            f"The selection export {path} does not carry {_SCHEMA_KEY} {SELECTION_SCHEMA}. "
            f"Expected an object written by datrix_scripts.selection_export; re-run the "
            f"collection with the current scripts tree."
        )
    entries = payload.get(_ITEMS_KEY)
    if not isinstance(entries, list):
        raise SelectionExportError(
            f"The selection export {path} has no {_ITEMS_KEY!r} list. Expected "
            f'[{{"{_NODEID_KEY}": "<id>", "{_SERIAL_KEY}": <bool>}}, ...].'
        )
    return tuple(_item_of(path, index, entry) for index, entry in enumerate(entries))


def _item_of(path: Path, index: int, entry: object) -> SelectedItem:
    if isinstance(entry, dict):
        nodeid = entry.get(_NODEID_KEY)
        serial = entry.get(_SERIAL_KEY)
        if isinstance(nodeid, str) and nodeid and isinstance(serial, bool):
            return SelectedItem(nodeid=nodeid, serial=serial)
    raise SelectionExportError(
        f"Entry {index} of the selection export {path} is {entry!r}. Expected "
        f'{{"{_NODEID_KEY}": "<non-empty node id>", "{_SERIAL_KEY}": <true|false>}}.'
    )
