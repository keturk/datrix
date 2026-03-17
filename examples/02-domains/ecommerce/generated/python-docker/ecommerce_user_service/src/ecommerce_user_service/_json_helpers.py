"""Helper functions for JSON builtin method mappings.

These functions are emitted into the generated code when JSON.get, JSON.set,
JSON.has, JSON.delete, JSON.merge, JSON.flatten, JSON.unflatten, JSON.isValid,
or JSON.typeOf are used.
"""

from __future__ import annotations

import copy
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _json_get(obj: dict[str, object], path: str) -> object:
    """Get a nested value by dot-notation path.

    Args:
        obj: Source dictionary.
        path: Dot-delimited key path (e.g., "a.b.c").

    Returns:
        The value at the given path.

    Raises:
        KeyError: If any key along the path does not exist.
    """
    current: Any = obj
    for key in path.split("."):
        if isinstance(current, dict):
            current = current[key]
        elif isinstance(current, list):
            current = current[int(key)]
        else:
            raise KeyError(f"Cannot traverse into {type(current).__name__} at key '{key}'")
    return current


def _json_set(obj: dict[str, object], path: str, value: Any) -> dict[str, object]:
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
    current: Any = result
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value
    return result


def _json_has(obj: dict[str, object], path: str) -> bool:
    """Check if a dot-notation path exists in the object.

    Args:
        obj: Source dictionary.
        path: Dot-delimited key path (e.g., "a.b.c").

    Returns:
        True if the path exists, False otherwise.
    """
    current: Any = obj
    for key in path.split("."):
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
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
    current: Any = result
    for key in keys[:-1]:
        current = current[key]
    del current[keys[-1]]
    return result


def _json_merge(base: dict[str, object], overlay: dict[str, object]) -> dict[str, object]:
    """Deep merge two dictionaries. Overlay values overwrite base.

    Args:
        base: Base dictionary.
        overlay: Dictionary to merge on top of base.

    Returns:
        A new deep-merged dictionary.
    """
    result = copy.deepcopy(base)
    for key, value in overlay.items():
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

    def _recurse(current: Any, prefix: str) -> None:
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
        current: Any = result
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


def _json_type_of(value: Any) -> str:
    """Get the JSON type name of a value.

    Args:
        value: Value to check.

    Returns:
        JSON type string: "object", "array", "string", "number", "boolean", or "null".
    """
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
