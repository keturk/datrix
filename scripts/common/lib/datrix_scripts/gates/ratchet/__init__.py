"""The behaviour of the ratchet gate wrappers in ``scripts/gates/ratchet/``.

Each gate module here is the ``argparse`` entry point a wrapper rendered from
``common/templates/entrypoint.ps1`` runs, in gate mode (``datrix_scripts.gate_log.run_as_gate``):
``slow-test-ratchet-gate.ps1`` runs ``datrix_scripts.gates.ratchet.slow_test_ratchet_gate``, and so on.
A ratchet compares a census of the tree with a recorded baseline that may only shrink.

This initializer imports nothing, as ``datrix_scripts`` itself does.
"""
