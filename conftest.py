"""Root conftest for datrix integration tests.

Registers datrix-language protocol implementations so that parse_fixture
helpers work in every test under tests/.
"""

from __future__ import annotations

from datrix_language.registration import register_all

register_all()
