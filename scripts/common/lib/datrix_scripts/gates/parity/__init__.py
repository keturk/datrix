"""The behaviour of the parity gate wrappers in ``scripts/gates/parity/``.

Each gate module here is the ``argparse`` entry point a wrapper rendered from
``common/templates/entrypoint.ps1`` runs, in gate mode (``datrix_scripts.gate_log.run_as_gate``):
``builtin-claims-parity-gate.ps1`` runs ``datrix_scripts.gates.parity.builtin_claims_parity_gate``, and
so on. ``parity-cases.ps1`` (``parity_cases``) authors the parity rows ``parity-cases-gate.ps1``
(``parity_cases_gate``) reads, and ``parity_observers`` holds the probe readings both share.

This initializer imports nothing, as ``datrix_scripts`` itself does.
"""
