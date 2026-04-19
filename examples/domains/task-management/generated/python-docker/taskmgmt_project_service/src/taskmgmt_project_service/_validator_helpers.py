"""Helper functions for Validator builtin method mappings.

Used by Validator.isJson, Validator.isDate, Validator.isDateString (and optionally
Validator.isCreditCard) when the mapping cannot be a single expression (e.g. try/except).
"""

from __future__ import annotations

import json
import re
from datetime import datetime


def _is_valid_json(value: str) -> bool:
    """Check if a string is valid JSON.

    Args:
        value: String to validate.

    Returns:
        True if the string is valid JSON, False otherwise.
    """
    try:
        json.loads(value)
        return True
    except (json.JSONDecodeError, TypeError):
        return False


def _is_valid_date_string(value: str) -> bool:
    """Check if a string can be parsed as a date/datetime.

    Tries ISO format first, then common formats. Uses stdlib only.

    Args:
        value: String to validate.

    Returns:
        True if the string can be parsed as a date, False otherwise.
    """
    if not value or not isinstance(value, str):
        return False
    value = value.strip()
    if not value:
        return False
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%Y",
    ]
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except (ValueError, TypeError):
        ...  # try formats below
    for fmt in formats:
        try:
            datetime.strptime(value, fmt)
            return True
        except (ValueError, TypeError):
            continue
    return False


def _is_valid_credit_card(value: str) -> bool:
    """Check if a string is a valid credit card number (Luhn algorithm).

    Accepts digits only (spaces/dashes stripped). Does not validate card brand.

    Args:
        value: String to validate (digits, optional spaces or hyphens).

    Returns:
        True if the string passes Luhn check and has valid length, False otherwise.
    """
    if not value or not isinstance(value, str):
        return False
    digits = re.sub(r"[\s\-]", "", value)
    if not digits.isdigit() or len(digits) < 12 or len(digits) > 19:
        return False
    total = 0
    for i, c in enumerate(reversed(digits)):
        n = int(c)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0
