"""Shared code for Datrix scripts: everything imported from more than one scripts folder.

Python run by a wrapper lives in the ``lib/`` folder beside that wrapper; a module that a
second folder (or a Claude Code hook, or a package test) also imports lives here instead.
Wrappers put ``scripts/common/lib`` on ``PYTHONPATH`` (``Set-DatrixPythonPath`` in
``common/venv.ps1``), so every script imports this package the same way. Repository
locations come from ``datrix_scripts.paths``, never from counting ``.parent`` steps.

Import each utility from its own module (``from datrix_scripts.venv import
get_datrix_root``). This package initializer deliberately imports nothing:
``datrix_scripts.venv`` is a leaf that almost every script needs, and an initializer
that pulled in the test-runner stack on every such import would put each module that
stack depends on into an import cycle with every module that only wanted the leaf.
"""
