"""The behaviour of the test runner wrappers in ``scripts/test/``.

Each module here is the ``argparse`` entry point a wrapper rendered from
``common/templates/entrypoint.ps1`` runs: ``test.ps1`` runs ``datrix_scripts.test.test``,
``test-single.ps1`` runs ``datrix_scripts.test.test_single``, and so on, with the wrapper's
parameters as the module's ``--kebab-name`` options. ``datrix_scripts.test.wrappers`` holds what
they share (the scripts folder, the self-test loop and its wrapper-seam check).

This initializer imports nothing, as ``datrix_scripts`` itself does.
"""
