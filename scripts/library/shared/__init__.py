"""Shared utilities for Datrix scripts.

Import each utility from its own module (``from shared.venv import
get_datrix_root``). This package initializer deliberately imports nothing:
``shared.venv`` is a leaf that almost every script and library module needs,
and an initializer that pulled in the test-runner stack on every such import
would put each module that stack depends on into an import cycle with every
module that only wanted the leaf.
"""
