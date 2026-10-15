"""The framework package directories and git repositories in a Datrix workspace.

``workspace_package_dirs`` is the one enumeration of ``datrix-*`` directories: every script that
needs "the packages" calls it with the marker that defines a package for its purpose (a
``src/`` tree, a ``tests/`` tree, a manifest, a git checkout) and keys the result its own way.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

SHOWCASE_REPO_NAME = "datrix"
FRAMEWORK_REPO_PREFIX = "datrix-"
GIT_DIR_NAME = ".git"


class PackageMarker(StrEnum):
    """A file or directory whose presence makes a workspace directory a package for a purpose."""

    SRC = "src"
    TESTS = "tests"
    PYPROJECT = "pyproject.toml"
    PACKAGE_JSON = "package.json"
    GIT = ".git"


def workspace_package_dirs(
    workspace: Path,
    *,
    any_of: frozenset[PackageMarker] = frozenset(),
    include_showcase: bool = False,
) -> list[Path]:
    """Every ``datrix-*`` directory (and ``datrix`` when ``include_showcase``), sorted by name.

    Discovered, not hardcoded: a newly cloned ``datrix-codegen-<lang>`` joins the day it
    appears, and Datrix is a multi-language, multi-platform generator whose package set is
    open-ended. With ``any_of`` given, a directory is returned only when it holds at least one
    of those markers; with it empty, every matching directory is returned.
    """
    found: list[Path] = []
    for child in sorted(workspace.iterdir(), key=lambda path: path.name):
        if not child.is_dir():
            continue
        named = child.name.startswith(FRAMEWORK_REPO_PREFIX) or (
            include_showcase and child.name == SHOWCASE_REPO_NAME
        )
        if not named:
            continue
        if any_of and not any((child / marker.value).exists() for marker in any_of):
            continue
        found.append(child)
    return found


def framework_repos(workspace_root: Path) -> list[Path]:
    """Discover the framework git repos in the workspace (the showcase repo included).

    Any other repository at the workspace root -- a customer project checkout -- is not a
    framework repo.
    """
    return workspace_package_dirs(
        workspace_root, any_of=frozenset({PackageMarker.GIT}), include_showcase=True
    )


def select_framework_repos(workspace_root: Path, wanted: list[str] | None) -> list[Path]:
    """Return the framework repos named in *wanted*, or every one when *wanted* is None.

    Raises:
        ValueError: If a requested name is not a framework repo in the workspace, naming
            the unknown names and every known one.
    """
    repos = framework_repos(workspace_root)
    if wanted is None:
        return repos
    requested = set(wanted)
    selected = [repo for repo in repos if repo.name in requested]
    missing = sorted(requested - {repo.name for repo in selected})
    if missing:
        raise ValueError(
            f"No framework repo named {', '.join(missing)} under {workspace_root}. "
            f"Known: {', '.join(repo.name for repo in repos)}. Pass one of the known names."
        )
    return selected
