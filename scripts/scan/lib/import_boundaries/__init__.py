"""The import-boundary scanners behind ``scan/lib/check_import_boundaries.py``.

One module per scanner, each holding its ratchet and its own self-test checks; the taxonomy and
rule model live in ``taxonomy``, helpers shared by two or more scanners in ``_ast_common`` and
``_module_resolution``. This initializer imports nothing.
"""
