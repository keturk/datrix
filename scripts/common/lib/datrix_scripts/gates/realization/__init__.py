"""The behaviour of the realization gate wrappers in ``scripts/gates/realization/``.

Each gate module here is the ``argparse`` entry point a wrapper rendered from
``common/templates/entrypoint.ps1`` runs, in gate mode (``datrix_scripts.gate_log.run_as_gate``):
``generation-determinism-gate.ps1`` runs ``datrix_scripts.gates.realization.generation_determinism_gate``,
and so on. ``generating_gates`` holds what the gates that generate share: their common options and
self-test, the walk over a generated tree, and the single-project generation each run makes.

This initializer imports nothing, as ``datrix_scripts`` itself does.
"""
