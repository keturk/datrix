"""The import-boundary scanners behind ``datrix_scripts.scan.check_import_boundaries``.

One module per scanner, each holding its ratchet and its own self-test checks; the taxonomy and
rule model live in ``taxonomy``, helpers shared by two or more scanners in ``_ast_common`` and
``_module_resolution``. ``__main__`` runs the scan alone, for the scanners' CLI self-tests. This
initializer imports nothing.
"""
