"""The behaviour of the repo-hygiene gate wrappers in ``scripts/gates/repo-hygiene/``.

Each gate module here is the ``argparse`` entry point a wrapper rendered from
``common/templates/entrypoint.ps1`` runs, in gate mode (``datrix_scripts.gate_log.run_as_gate``):
``ignored-source-gate.ps1`` runs ``datrix_scripts.gates.repo_hygiene.ignored_source_gate``, and so on.
A repo-hygiene gate holds a property of the committed trees themselves (what they publish, what they
cite, what their documentation names), not of a generation.

This initializer imports nothing, as ``datrix_scripts`` itself does.
"""
