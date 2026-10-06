"""The framework git repositories in a Datrix workspace."""

from __future__ import annotations

from pathlib import Path

SHOWCASE_REPO_NAME = "datrix"
FRAMEWORK_REPO_PREFIX = "datrix-"
GIT_DIR_NAME = ".git"


def framework_repos(workspace_root: Path) -> list[Path]:
    """Discover the framework git repos in the workspace.

    Discovered, not hardcoded: a newly cloned ``datrix-codegen-<lang>`` must be
    policed the day it appears, and Datrix is a multi-language, multi-platform
    generator whose repo set is open-ended. The showcase repo anchors the list.
    Any other repository at the workspace root -- a customer project checkout --
    is not a framework repo.
    """
    repos: list[Path] = []
    showcase = workspace_root / SHOWCASE_REPO_NAME
    if (showcase / GIT_DIR_NAME).exists():
        repos.append(showcase)
    for child in sorted(workspace_root.iterdir()):
        if child.name.startswith(FRAMEWORK_REPO_PREFIX) and (child / GIT_DIR_NAME).exists():
            repos.append(child)
    return repos
