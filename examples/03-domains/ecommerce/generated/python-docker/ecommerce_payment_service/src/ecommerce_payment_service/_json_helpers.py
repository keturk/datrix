"""Helper functions for JSON builtin method mappings.

These functions are emitted into the generated code when JSON.get, JSON.set,
JSON.has, JSON.delete, JSON.merge, JSON.flatten, JSON.unflatten, JSON.isValid,
or JSON.typeOf are used.
"""

from __future__ import annotations

import copy
import datetime
import decimal
import enum
import json
import logging
import uuid

logger = logging.getLogger(__name__)


def _json_default(value: object) -> object:
    """Encode JSON-incompatible values for ``json.dumps``.

    DSL values carry native Python objects (``datetime``, ``date``, ``time``,
    ``UUID``, ``Decimal``, ``Enum``, and Pydantic models) that the standard JSON
    encoder cannot handle. ``JSON.serialize``/``JSON.stringify`` route through
    this default so that serializing a struct containing, for example,
    ``DateTime.now()`` yields an ISO-8601 string instead of raising
    ``Object of type datetime is not JSON serializable``.

    Args:
        value: A value the standard JSON encoder rejected.

    Returns:
        A JSON-serializable representation of ``value``.

    Raises:
        TypeError: If ``value`` is not a type this encoder knows how to convert.
    """
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, datetime.datetime | datetime.date | datetime.time):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, enum.Enum):
        return value.value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json", by_alias=True)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _json_data(value: object) -> object:
    """Return *value* as JSON data, converting every non-JSON value in its subtree.

    A DSL ``JSON`` slot -- an event or queue payload field declared ``JSON``, a
    ``JSON``-declared local -- holds JSON data, but the expression that fills it
    routinely produces native Python objects: a ``UUID`` primary key read off an
    entity, a ``Decimal`` measure, an ``Enum``, a ``datetime``, a decoded response
    model. Those are rejected by ``pydantic.JsonValue``, so the value is converted
    once, here, where it crosses into JSON.

    Containers are rebuilt so a non-JSON value nested at any depth is converted
    too; scalars are passed through :func:`_json_default`, the single conversion
    policy shared with ``JSON.serialize``.

    Args:
        value: Any DSL value entering a JSON slot.

    Returns:
        An equivalent value built only from JSON-native types.

    Raises:
        TypeError: If some value in the subtree has no JSON form. The message
            names the offending type -- convert it in the DSL before dispatching.
    """
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_data(item) for item in value]
    return _json_data(_json_default(value))


def _json_value(value: object) -> object:
    """Return *value* as plain JSON data, converting a struct to its wire form.

    A typed inter-service call result is a Pydantic response model, and the DSL may
    consume that same value as ``JSON`` (``JSON.get`` / ``JSON.has`` / ``JSON.typeOf``).
    Dumping it ``by_alias=True`` yields exactly the payload it was decoded from, so a
    JSON path written against the provider's wire keys resolves against a decoded struct
    as it does against a raw body. Anything that is not a model is returned unchanged
    (``model_dump`` already converts a model's whole subtree), and the JSON helpers apply
    this at every traversal step, so a struct nested inside a dict/list is converted when
    the path reaches it — never eagerly over the whole payload.

    Args:
        value: A JSON value or a response struct.

    Returns:
        The struct's wire-form dict, or *value* unchanged.
    """
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json", by_alias=True)
    return value


def _require_json_object(value: object, role: str) -> dict[str, object]:
    """Return *value* as a JSON object, or fail loud naming which operand was wrong.

    Args:
        value: A candidate JSON object (already struct-converted by :func:`_json_value`).
        role: The operand's name in the calling helper, surfaced in the error.

    Returns:
        The value as a ``dict``.

    Raises:
        TypeError: If *value* is not a JSON object.
    """
    if not isinstance(value, dict):
        raise TypeError(
            f"JSON operand '{role}' must be a JSON object, got "
            f"{type(value).__name__}. Pass a JSON object or a response struct."
        )
    return value


def _json_serialize(value: object, indent: int | None = None) -> str:
    """Serialize a value to a JSON string, ISO-encoding temporal/UUID/enum scalars.

    Mirrors ``json.dumps`` but supplies :func:`_json_default` so that DSL values
    carrying native ``datetime``/``date``/``time``/``UUID``/``Decimal``/``Enum``
    objects (or Pydantic models) serialize without raising. Used by
    ``JSON.serialize``, ``JSON.stringify``, and ``JSON.stringifyPretty``.

    Args:
        value: Value to serialize (dict, list, or scalar).
        indent: Indentation width for pretty-printing, or ``None`` for compact.

    Returns:
        The JSON string representation of ``value``.
    """
    return json.dumps(value, default=_json_default, indent=indent)


def _json_get(obj: object, path: str) -> object:
    """Get a nested value by dot-notation path.

    Args:
        obj: Source JSON value or response struct.
        path: Dot-delimited key path (e.g., "a.b.c").

    Returns:
        The value at the given path.

    Raises:
        KeyError: If any key along the path does not exist.
    """
    current: object = obj
    for key in path.split("."):
        current = _json_value(current)
        if isinstance(current, dict):
            current = current[key]
        elif isinstance(current, list):
            current = current[int(key)]
        else:
            raise KeyError(
                f"Cannot traverse into {type(current).__name__} at key '{key}'"
            )
    return current


def _json_index(obj: object, index: object) -> object:
    """Read a single element from a JSON value by key or positional index.

    A DSL ``JSON`` value is a dict, a list, or a scalar at runtime, so subscript
    access (``value[index]``) must work for both objects and arrays and must
    yield JSON null (``None``) on a miss rather than raising. ``dict.get`` cannot
    be used directly because it does not exist on ``list``; this helper bridges
    both shapes.

    Args:
        obj: Source JSON value (dict, list, scalar, or response struct).
        index: Object key (str) or array position (int).

    Returns:
        The element at the given key/position, or ``None`` if absent,
        out of range, or ``obj`` is not indexable.
    """
    obj = _json_value(obj)
    if isinstance(obj, dict):
        return obj.get(index)
    if isinstance(obj, (list, tuple)):
        if isinstance(index, bool) or not isinstance(index, int):
            return None
        if -len(obj) <= index < len(obj):
            return obj[index]
        return None
    return None


def _json_set(obj: dict[str, object], path: str, value: object) -> dict[str, object]:
    """Set a nested value by dot-notation path (returns a new dict).

    Args:
        obj: Source dictionary.
        path: Dot-delimited key path (e.g., "a.b.c").
        value: Value to set at the given path.

    Returns:
        A new dictionary with the value set.
    """
    result = copy.deepcopy(obj)
    keys = path.split(".")
    current: object = result
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value
    return result


def _json_has(obj: object, path: str) -> bool:
    """Check if a dot-notation path exists in the object.

    Args:
        obj: Source JSON value or response struct.
        path: Dot-delimited key path (e.g., "a.b.c").

    Returns:
        True if the path exists, False otherwise.
    """
    current: object = obj
    for key in path.split("."):
        current = _json_value(current)
        if isinstance(current, dict) and key in current:
            current = current[key]
            continue
        # Array positions are traversable exactly as in _json_get: a guard
        # (``JSON.has``) that cannot see a path ``JSON.get`` resolves would skip a
        # legitimate read.
        if isinstance(current, list):
            try:
                index = int(key)
            except ValueError:
                return False
            if not -len(current) <= index < len(current):
                return False
            current = current[index]
            continue
        return False
    return True


def _json_delete(obj: dict[str, object], path: str) -> dict[str, object]:
    """Delete a nested value by dot-notation path (returns a new dict).

    Args:
        obj: Source dictionary.
        path: Dot-delimited key path (e.g., "a.b.c").

    Returns:
        A new dictionary with the value removed.

    Raises:
        KeyError: If the path does not exist.
    """
    result = copy.deepcopy(obj)
    keys = path.split(".")
    current: object = result
    for key in keys[:-1]:
        current = current[key]
    del current[keys[-1]]
    return result


def _json_merge(base: object, overlay: object) -> dict[str, object]:
    """Deep merge two JSON objects. Overlay values overwrite base.

    Args:
        base: Base JSON object or response struct.
        overlay: JSON object or response struct to merge on top of base.

    Returns:
        A new deep-merged dictionary.

    Raises:
        TypeError: If either side is not a JSON object once structs are converted.
    """
    base_obj = _require_json_object(_json_value(base), "base")
    overlay_obj = _require_json_object(_json_value(overlay), "overlay")
    result = copy.deepcopy(base_obj)
    for key, value in overlay_obj.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _json_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _json_flatten(obj: dict[str, object], delimiter: str = ".") -> dict[str, object]:
    """Flatten a nested dictionary to single-level with delimited keys.

    Args:
        obj: Nested dictionary to flatten.
        delimiter: Key delimiter (default: ".").

    Returns:
        A flat dictionary with delimited keys.
    """
    result: dict[str, object] = {}

    def _recurse(current: object, prefix: str) -> None:
        if isinstance(current, dict):
            for key, value in current.items():
                new_key = f"{prefix}{delimiter}{key}" if prefix else key
                _recurse(value, new_key)
        else:
            result[prefix] = current

    _recurse(obj, "")
    return result


def _json_unflatten(obj: dict[str, object], delimiter: str = ".") -> dict[str, object]:
    """Unflatten a dictionary with delimited keys to nested structure.

    Args:
        obj: Flat dictionary with delimited keys.
        delimiter: Key delimiter (default: ".").

    Returns:
        A nested dictionary.
    """
    result: dict[str, object] = {}
    for key, value in obj.items():
        keys = key.split(delimiter)
        current: object = result
        for part in keys[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[keys[-1]] = value
    return result


def _json_is_valid(text: str) -> bool:
    """Check if a string is valid JSON.

    Args:
        text: String to validate.

    Returns:
        True if the string is valid JSON, False otherwise.
    """
    try:
        json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return False
    return True


def _json_parse_tabular(raw_data: object, format_hint: str) -> list[dict[str, object]]:
    """Parse raw tabular data into a list of JSON-like dicts.

    Dispatches on ``format_hint``:
    - ``csv``: RFC 4180 CSV via ``csv.DictReader`` (header on row 0).
    - ``csv|skip=5`` / ``csv|header=5``: CSV whose column-name row is row 5
      (0-indexed); all preceding rows are discarded and data starts after it.
      Use for multi-header CSV exports (sensor data exports, etc.) that prepend
      several metadata/units lines before the header. ``csv|delimiter=\\t`` selects a
      tab (or other single-character) delimiter for TSV-style data.
    - ``pipe|field=1|count:int=2``: delimited text where fields are 1-indexed.
    - ``fixed-width|field=1-4|count:int=5-8``: fixed-width text where
      columns are 1-indexed and inclusive.
    - Other formats (``shapefile``, ``dat``, ``feed-*``, ``csv-*``):
      Delegates to a pluggable parser registered under that format name.
      Override ``_TABULAR_PARSERS`` to register domain-specific parsers.

    Args:
        raw_data: Raw bytes or string to parse.
        format_hint: Format identifier (e.g., ``"csv"``, ``"shapefile"``, ``"dat"``).

    Returns:
        A list of dicts, one per record.
    """
    fmt = str(format_hint).strip().lower()

    if fmt == "csv" or fmt.startswith("csv|"):
        return _parse_csv(raw_data, str(format_hint))

    if fmt == "pipe" or fmt.startswith("pipe|"):
        return _parse_delimited(raw_data, str(format_hint), "|")

    if fmt == "fixed-width" or fmt.startswith("fixed-width|"):
        return _parse_fixed_width(raw_data, str(format_hint))

    # Pluggable parser registry for domain-specific formats.
    parser = _TABULAR_PARSERS.get(fmt)
    if parser is not None:
        return parser(raw_data)

    raise ValueError(
        f"Unsupported tabular format '{format_hint}'. "
        f"Available: {sorted(['csv'] + list(_TABULAR_PARSERS.keys()))}. "
        "Register a custom parser in _TABULAR_PARSERS for domain-specific formats."
    )


def _parse_csv(raw_data: object, format_hint: str) -> list[dict[str, object]]:
    """Parse CSV text, optionally skipping ragged leading header lines.

    Supports ``csv`` (header on row 0) and ``csv|skip=N`` / ``csv|header=N``
    (the column-name row is at 0-indexed line ``N``; every line before it is
    discarded and data records start after it). ``csv|delimiter=X`` selects a
    single-character delimiter other than comma (e.g. ``\\t`` for TSV).
    """
    import csv
    import io

    text = (
        raw_data.decode("utf-8")
        if isinstance(raw_data, (bytes, bytearray))
        else str(raw_data)
    )
    header_row, delimiter = _parse_csv_spec(format_hint)
    if header_row > 0:
        lines = text.splitlines(keepends=True)
        if header_row >= len(lines):
            raise ValueError(
                f"CSV header row {header_row} is beyond the file's {len(lines)} lines."
            )
        text = "".join(lines[header_row:])
    # restval="" so rows shorter than the header yield "" (not None) for missing
    # trailing columns; the `if k is not None` clause drops csv.DictReader's restkey
    # overflow bucket (extra fields from a ragged/unquoted-comma row are collected
    # under key None) instead of crashing on None.strip(); and `v if v is not None`
    # guards any remaining None values. One ragged row no longer aborts the whole parse.
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter, restval="")
    return [
        {
            k.strip(): (v if v is not None else "")
            for k, v in row.items()
            if k is not None
        }
        for row in reader
    ]


def _parse_csv_spec(format_hint: str) -> tuple[int, str]:
    """Parse a ``csv`` format hint into ``(header_row, delimiter)``.

    ``header_row`` is the 0-indexed line that holds the column names (0 for a
    plain ``csv``). ``delimiter`` is the field separator (``,`` by default).
    ``skip`` and ``header`` are aliases for the header-row index; supplying both
    with conflicting values is rejected.
    """
    parts = [part.strip() for part in format_hint.split("|") if part.strip()]
    if not parts or parts[0].lower() != "csv":
        raise ValueError("csv format hints must start with 'csv'.")
    header_row = 0
    header_set = False
    delimiter = ","
    for token in parts[1:]:
        key, sep, value = token.partition("=")
        if not sep:
            raise ValueError(f"Invalid csv token '{token}'. Expected key=value.")
        key = key.strip().lower()
        if key in {"skip", "header"}:
            row = int(value)
            if row < 0:
                raise ValueError(f"csv '{key}' must be >= 0, got '{value}'.")
            if header_set and row != header_row:
                raise ValueError(
                    f"Conflicting csv header rows: {header_row} and {row}."
                )
            header_row = row
            header_set = True
        elif key == "delimiter":
            delimiter = value.encode().decode("unicode_escape") or ","
            if len(delimiter) != 1:
                raise ValueError(
                    f"csv delimiter must be a single character, got '{value}'."
                )
        else:
            raise ValueError(
                f"Unknown csv directive '{key}'. Supported: skip, header, delimiter."
            )
    return header_row, delimiter


def _parse_shapefile_zip(raw_data: object) -> list[dict[str, object]]:
    """Parse a shapefile ZIP archive into a list of feature dicts.

    Each dict contains attribute fields from the .dbf table plus a ``geometry``
    key with GeoJSON geometry (or ``None`` for records with NULL geometry).

    Requires ``pyshp`` (``pip install pyshp``).
    """
    import io
    import zipfile

    import shapefile as pyshp  # type: ignore[import-untyped]

    data = raw_data if isinstance(raw_data, (bytes, bytearray)) else bytes(raw_data)
    archive = zipfile.ZipFile(io.BytesIO(data))
    shp_names = [n for n in archive.namelist() if n.lower().endswith(".shp")]
    if not shp_names:
        raise ValueError("No .shp file found in ZIP archive")
    shp_name = max(shp_names, key=lambda n: archive.getinfo(n).file_size)
    base = shp_name.rsplit(".", 1)[0]

    shp_bytes = archive.read(shp_name)
    dbf_name = base + ".dbf"
    dbf_bytes = archive.read(dbf_name) if dbf_name in archive.namelist() else None
    shx_name = base + ".shx"
    shx_bytes = archive.read(shx_name) if shx_name in archive.namelist() else None

    shp_io = io.BytesIO(shp_bytes)
    dbf_io = io.BytesIO(dbf_bytes) if dbf_bytes else None
    shx_io = io.BytesIO(shx_bytes) if shx_bytes else None

    reader = pyshp.Reader(shp=shp_io, dbf=dbf_io, shx=shx_io)
    features: list[dict[str, object]] = []
    for shape_rec in reader.iterShapeRecords():
        feature: dict[str, object] = shape_rec.record.as_dict()
        if shape_rec.shape.shapeType == pyshp.NULL:
            feature["geometry"] = None
        else:
            feature["geometry"] = shape_rec.shape.__geo_interface__
        features.append(feature)
    return features


# Pluggable parser registry: maps format names to callables
# (raw_data) -> list[dict[str, object]].
_TABULAR_PARSERS: dict[str, object] = {
    "shapefile": _parse_shapefile_zip,
}


def _parse_delimited(
    raw_data: object, format_hint: str, delimiter: str
) -> list[dict[str, object]]:
    text = (
        raw_data.decode("utf-8", errors="replace")
        if isinstance(raw_data, (bytes, bytearray))
        else str(raw_data)
    )
    spec = _parse_delimited_spec(format_hint)
    rows: list[dict[str, object]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        columns = line.rstrip("\r\n").split(delimiter)
        record_filter = spec.get("record")
        if record_filter is not None:
            expected, index = record_filter
            if _get_delimited_column(columns, index).strip() != expected:
                continue
        row: dict[str, object] = {}
        for name, kind, index, extra in spec["fields"]:
            raw_value = (
                extra
                if kind == "const"
                else _get_delimited_column(columns, index).strip()
            )
            if kind in {"seconds-hemi", "seconds_hemisphere"}:
                if extra is None:
                    raise ValueError(
                        f"Delimited field '{name}' with kind '{kind}' requires a hemisphere column."
                    )
                value = _parse_all_seconds_coordinate(
                    raw_value + _get_delimited_column(columns, int(extra)).strip()
                )
            else:
                value = _coerce_tabular_value(raw_value, kind, extra)
            if value is not None:
                row[name] = value
        if row:
            rows.append(row)
    return rows


def _parse_delimited_spec(format_hint: str) -> dict[str, object]:
    parts = [part.strip() for part in format_hint.split("|") if part.strip()]
    if not parts or parts[0].lower() != "pipe":
        raise ValueError("pipe format hints must start with 'pipe'.")
    spec: dict[str, object] = {"fields": []}
    fields: list[tuple[str, str, int, str | None]] = []
    for token in parts[1:]:
        key, sep, value = token.partition("=")
        if not sep:
            raise ValueError(f"Invalid pipe token '{token}'. Expected name=index.")
        key_parts = key.split(":")
        name = key_parts[0]
        kind = key_parts[1] if len(key_parts) > 1 else "str"
        if name == "record":
            expected, index = _parse_delimited_record_filter(value)
            spec["record"] = (expected, index)
            continue
        if kind == "const":
            fields.append((name, kind, 0, value))
            continue
        index = int(value)
        if index < 1:
            raise ValueError(f"Invalid pipe field index '{value}'.")
        extra = key_parts[2] if len(key_parts) > 2 else None
        fields.append((name, kind, index, extra))
    spec["fields"] = fields
    return spec


def _parse_delimited_record_filter(value: str) -> tuple[str, int]:
    expected, sep, index_text = value.partition("@")
    if not sep:
        raise ValueError("record filters must use record=VALUE@index.")
    index = int(index_text)
    if index < 1:
        raise ValueError(f"Invalid record field index '{index_text}'.")
    return expected, index


def _get_delimited_column(columns: list[str], index: int) -> str:
    if index > len(columns):
        return ""
    return columns[index - 1]


def _parse_fixed_width(raw_data: object, format_hint: str) -> list[dict[str, object]]:
    text = (
        raw_data.decode("utf-8", errors="replace")
        if isinstance(raw_data, (bytes, bytearray))
        else str(raw_data)
    )
    spec = _parse_fixed_width_spec(format_hint)
    rows: list[dict[str, object]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        record_filter = spec.get("record")
        if record_filter is not None:
            expected, start, end = record_filter
            if _slice_fixed_width(line, start, end).strip() != expected:
                continue
        row: dict[str, object] = {}
        for name, kind, start, end, extra in spec["fields"]:
            raw_value = (
                extra
                if kind == "const"
                else _slice_fixed_width(line, start, end).strip()
            )
            value = _coerce_tabular_value(raw_value, kind, extra)
            if value is not None:
                row[name] = value
        if row:
            rows.append(row)
    return rows


def _parse_fixed_width_spec(format_hint: str) -> dict[str, object]:
    parts = [part.strip() for part in format_hint.split("|") if part.strip()]
    if not parts or parts[0].lower() != "fixed-width":
        raise ValueError("fixed-width format hints must start with 'fixed-width'.")
    spec: dict[str, object] = {"fields": []}
    fields: list[tuple[str, str, int, int, str | None]] = []
    for token in parts[1:]:
        key, sep, value = token.partition("=")
        if not sep:
            raise ValueError(
                f"Invalid fixed-width token '{token}'. Expected name=start-end."
            )
        key_parts = key.split(":")
        name = key_parts[0]
        kind = key_parts[1] if len(key_parts) > 1 else "str"
        if name == "record":
            expected, start, end = _parse_fixed_width_record_filter(value)
            spec["record"] = (expected, start, end)
            continue
        if kind == "const":
            fields.append((name, kind, 0, 0, value))
            continue
        start, end = _parse_fixed_width_range(value)
        extra = key_parts[2] if len(key_parts) > 2 else None
        fields.append((name, kind, start, end, extra))
    spec["fields"] = fields
    return spec


def _parse_fixed_width_record_filter(value: str) -> tuple[str, int, int]:
    expected, sep, span = value.partition("@")
    if not sep:
        raise ValueError("record filters must use record=VALUE@start-end.")
    start, end = _parse_fixed_width_range(span)
    return expected, start, end


def _parse_fixed_width_range(value: str) -> tuple[int, int]:
    start_text, sep, end_text = value.partition("-")
    if not sep:
        raise ValueError(f"Invalid fixed-width range '{value}'. Expected start-end.")
    start = int(start_text)
    end = int(end_text)
    if start < 1 or end < start:
        raise ValueError(f"Invalid fixed-width range '{value}'.")
    return start, end


def _slice_fixed_width(line: str, start: int, end: int) -> str:
    return line[start - 1 : end]


def _coerce_tabular_value(raw_value: str, kind: str, extra: str | None) -> object:
    value = raw_value.strip()
    if kind in {"str", "string"}:
        return value
    if kind in {"int", "integer"}:
        return int(float(value)) if value else None
    if kind in {"float", "decimal", "number"}:
        return float(value) if value else None
    if kind == "seconds":
        return _parse_all_seconds_coordinate(value)
    if kind == "dms":
        return _parse_dms_coordinate(value)
    if kind == "bool":
        return value.upper() == (extra or "Y").upper()
    if kind == "const":
        return raw_value
    return value


def _parse_all_seconds_coordinate(value: str) -> float | None:
    if not value or not value.strip():
        return None
    hemi = value[-1].upper()
    seconds_text = value[:-1].strip() if hemi in {"N", "S", "E", "W"} else value.strip()
    if not seconds_text:
        return None
    magnitude = float(seconds_text) / 3600.0
    return -magnitude if hemi in {"S", "W"} else magnitude


def _parse_dms_coordinate(value: str) -> float | None:
    if not value:
        return None
    compact = " ".join(value.strip().split())
    parts = compact.split(" ")
    if len(parts) != 3:
        raise ValueError(
            f"Invalid DMS coordinate '{value}'. Expected degrees minutes seconds+hemisphere."
        )
    hemi = parts[2][-1].upper()
    seconds_text = parts[2][:-1] if hemi in {"N", "S", "E", "W"} else parts[2]
    degrees = float(parts[0])
    minutes = float(parts[1])
    seconds = float(seconds_text)
    magnitude = degrees + (minutes / 60.0) + (seconds / 3600.0)
    return -magnitude if hemi in {"S", "W"} else magnitude


def _json_type_of(value: object) -> str:
    """Get the JSON type name of a value.

    Args:
        value: Value to check (a response struct reports as "object").

    Returns:
        JSON type string: "object", "array", "string", "number", "boolean", or "null".
    """
    value = _json_value(value)
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"
