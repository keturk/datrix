"""Test-tooling library for Datrix scripts.

This package MUST declare itself with this file. Python's standard library ships
its own regular package named ``test``; a directory without ``__init__.py`` is
only a *namespace portion*, and the import system prefers a regular package found
anywhere on ``sys.path`` over namespace portions found earlier. Without this file
``from test.status_tests import ...`` resolves against the stdlib ``test`` package
and raises ``ModuleNotFoundError: No module named 'test.status_tests'``, even
though the library directory is first on ``sys.path``.

Sibling library packages (``shared``, ``dev``, ``metrics``, ``review``) already
declare themselves the same way; they happen not to collide with a stdlib name,
so the omission was only ever observable here.

Deliberately exports nothing: modules in this package are imported by their full
path (``from test.status_tests import ...``), and re-exporting them here would
execute every module on any single import.
"""
