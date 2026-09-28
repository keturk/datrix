"""Read datrix-* package dependency declarations from pyproject.toml.

Shared by scripts/library/metrics/dependency.py (dependency report) and
scripts/library/common/install_order.py (venv install ordering).
"""

from __future__ import annotations

import re
from pathlib import Path

try:
    import tomllib
except ImportError:
    tomllib = None  # type: ignore[assignment]

DATRIX_PREFIX = "datrix-"

_REQUIREMENT_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def parse_package_name(spec: str) -> str:
    """Extract the package name from a dependency spec (e.g. 'datrix-common>=1.0.0')."""
    return re.split(r"\s*[\[\]<>!=~]", spec.strip(), maxsplit=1)[0].strip()


def read_project_dependencies(pyproject_path: Path) -> list[str]:
    """Read [project].dependencies from pyproject.toml.

    Returns an empty list when the file is absent. Raises RuntimeError when
    tomllib is unavailable, and propagates (OSError, ValueError) from a file
    that exists but cannot be opened or parsed -- callers that want a
    cosmetic, best-effort read (the dependency report) catch and swallow
    those themselves; callers that must not silently drop a package (the
    install-order tool) let them surface.
    """
    if tomllib is None:
        raise RuntimeError("tomllib is required (Python 3.11+).")
    if not pyproject_path.is_file():
        return []
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    deps = data.get("project", {}).get("dependencies", [])
    if not isinstance(deps, list):
        return []
    return [s for s in deps if isinstance(s, str)]


def discover_packages(workspace_root: Path) -> dict[str, Path]:
    """Map of package name -> project root for each datrix-* dir with a pyproject.toml."""
    result: dict[str, Path] = {}
    if not workspace_root.is_dir():
        return result
    for child in workspace_root.iterdir():
        if not child.is_dir() or not child.name.startswith(DATRIX_PREFIX):
            continue
        if (child / "pyproject.toml").is_file():
            result[child.name] = child
    return dict(sorted(result.items()))


def build_dependency_graph(
    packages: dict[str, Path],
) -> tuple[list[str], list[tuple[str, str]]]:
    """datrix-to-datrix dependency graph: (package names, (package, dependency) edges).

    Used by the dependency report, which tolerates an unreadable/malformed
    pyproject.toml by silently treating it as declaring no dependencies (via
    read_project_dependencies's own OSError/ValueError propagation caught
    here) -- a cosmetic report degrading gracefully is acceptable; the
    install-order tool does NOT reuse this function for that reason (see
    install_order.py's own dependency-reading loop, which re-raises).
    """
    package_names = list(packages.keys())
    edges: list[tuple[str, str]] = []
    for name, project_root in packages.items():
        try:
            specs = read_project_dependencies(project_root / "pyproject.toml")
        except (OSError, ValueError):
            specs = []
        for spec in specs:
            dep_name = parse_package_name(spec)
            if dep_name.startswith(DATRIX_PREFIX) and dep_name in packages and dep_name != name:
                edges.append((name, dep_name))
    edges.sort(key=lambda e: (e[0], e[1]))
    return package_names, edges
