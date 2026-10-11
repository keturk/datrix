"""The [dev] extra specs of a datrix-* package, in the form the shared venv installs.

Every workspace package is installed into the shared venv in editable mode. A
package's [dev] extra may still name a sibling workspace package by direct URL
(``datrix-extensions @ file:../datrix-extensions``) so that a standalone
install of that package can find a sibling that is on no index. Handing such a
spec to ``pip install`` in the shared venv replaces the editable install of the
sibling with a built copy, frozen at the moment of the install: every later
edit to the sibling's source is then invisible to every package that imports
it, until someone notices the stale copy in site-packages.

So a direct-URL spec naming a workspace package directory becomes the bare
package name, which pip resolves against the editable install already present.
Every other spec is returned unchanged.

Usage:
    python -m datrix_scripts.dev_specs <package-root>   # JSON list of specs
    python -m datrix_scripts.dev_specs --self-test
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

try:
    import tomllib
except ImportError:
    tomllib = None  # type: ignore[assignment]

from datrix_scripts.pyproject_deps import DATRIX_PREFIX

_DIRECT_URL_SEPARATOR = " @ "
_FILE_URL_PREFIX = "file:"


def read_dev_specs(project_root: Path) -> list[str]:
    """Read ``[project.optional-dependencies].dev`` of *project_root*'s pyproject.toml.

    Returns an empty list when the package has no pyproject.toml or declares no
    dev extra. Raises RuntimeError when tomllib is unavailable.
    """
    if tomllib is None:
        raise RuntimeError("tomllib is required (Python 3.11+).")
    pyproject_path = project_root / "pyproject.toml"
    if not pyproject_path.is_file():
        return []
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    specs = data.get("project", {}).get("optional-dependencies", {}).get("dev", [])
    if not isinstance(specs, list):
        return []
    return [spec for spec in specs if isinstance(spec, str)]


def _workspace_package_name(spec: str, project_root: Path) -> str | None:
    """The package a direct-URL *spec* names when its URL is a workspace package directory.

    ``None`` for every other spec: a version spec, a URL that is not a local
    file path, or a path that is not a datrix-* directory holding a
    pyproject.toml beside *project_root*.
    """
    if _DIRECT_URL_SEPARATOR not in spec:
        return None
    name, url = (part.strip() for part in spec.split(_DIRECT_URL_SEPARATOR, 1))
    if not url.startswith(_FILE_URL_PREFIX):
        return None
    target = (project_root / url[len(_FILE_URL_PREFIX):]).resolve()
    workspace_root = project_root.resolve().parent
    is_workspace_package = (
        target.parent == workspace_root
        and target.name.startswith(DATRIX_PREFIX)
        and (target / "pyproject.toml").is_file()
    )
    return name if is_workspace_package else None


def installable_dev_specs(project_root: Path) -> list[str]:
    """The [dev] specs of *project_root*, with workspace packages named by bare name."""
    installable: list[str] = []
    for spec in read_dev_specs(project_root):
        workspace_package = _workspace_package_name(spec, project_root)
        installable.append(spec if workspace_package is None else workspace_package)
    return installable


# ---------------------------------------------------------------------------
# Self-Test (--self-test)
# ---------------------------------------------------------------------------


def _write_package(workspace: Path, name: str, dev_specs: list[str]) -> Path:
    root = workspace / name
    root.mkdir()
    dev = ", ".join(json.dumps(spec) for spec in dev_specs)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\n\n[project.optional-dependencies]\ndev = [{dev}]\n',
        encoding="utf-8",
    )
    return root


def run_self_test() -> bool:
    """Check the rewrite on a throwaway two-package workspace; print each failure."""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        _write_package(workspace, "datrix-extensions", [])
        (workspace / "not-a-package").mkdir()
        consumer = _write_package(
            workspace,
            "datrix-codegen-component",
            [
                "datrix-extensions @ file:../datrix-extensions",
                "datrix-language",
                "pytest>=7.0",
                "other @ file:../not-a-package",
                "remote @ https://example.invalid/remote.whl",
            ],
        )
        cases = [
            (
                "workspace direct URL becomes the bare name; everything else is unchanged",
                installable_dev_specs(consumer),
                [
                    "datrix-extensions",
                    "datrix-language",
                    "pytest>=7.0",
                    "other @ file:../not-a-package",
                    "remote @ https://example.invalid/remote.whl",
                ],
            ),
            (
                "a package without a dev extra has no specs",
                installable_dev_specs(workspace / "datrix-extensions"),
                [],
            ),
        ]
    failures = [(label, got, want) for label, got, want in cases if got != want]
    for label, got, want in failures:
        print(f"FAIL {label}: got {got}, expected {want}", file=sys.stderr)
    if not failures:
        print(f"dev_specs self-test: {len(cases)} case(s) passed")
    return not failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("package_root", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return 0 if run_self_test() else 1
    if args.package_root is None:
        print(
            "Error: a package root is required unless --self-test "
            "(usage: python -m datrix_scripts.dev_specs <package-root>).",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(installable_dev_specs(args.package_root)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
