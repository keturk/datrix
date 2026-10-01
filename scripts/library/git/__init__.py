"""Git utilities for Datrix scripts: pre-review and commit-and-push.

A regular package, like every other library subpackage, so ``library/`` at the front of
``sys.path`` makes ``git.pre_review`` resolve here. As a namespace package it lost to any
installed regular package named ``git`` (GitPython is one), wherever that sat on the path.
"""
