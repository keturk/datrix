"""The [dev] extra specs of a datrix-* package, and the scripts tree's dependency group, in the
form the shared venv installs.

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

The datrix repository is not an installable package, yet its scripts tree imports and runs
third-party tools (libcst, bowler, semgrep, ...) that no datrix-* package needs. Those are
declared once, as the PEP 735 dependency group ``scripts`` of ``datrix/pyproject.toml``, and
the shared venv installs that group beside the packages' [dev] extras.

``datrix_scripts.venv`` calls ``installable_dev_specs`` and ``read_dependency_group``. Run from
``common/venv-dev-specs.ps1``, which passes only ``--self-test``:
    python -m datrix_scripts.dev_specs --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import tomllib
from pathlib import Path

from datrix_scripts.entrypoint import wrapper_command, wrapper_problems
from datrix_scripts.paths import SCRIPTS_DIR
from datrix_scripts.pyproject_deps import DATRIX_PREFIX

_DIRECT_URL_SEPARATOR = " @ "
_FILE_URL_PREFIX = "file:"

#: The dependency group of ``datrix/pyproject.toml`` holding the scripts tree's third-party tools.
SCRIPTS_DEPENDENCY_GROUP = "scripts"
_DEPENDENCY_GROUPS_TABLE = "dependency-groups"
_INCLUDE_GROUP_KEY = "include-group"
_GROUP_NAME_SEPARATORS = re.compile(r"[-_.]+")


def read_dev_specs(project_root: Path) -> list[str]:
    """Read ``[project.optional-dependencies].dev`` of *project_root*'s pyproject.toml.

    Returns an empty list when the package has no pyproject.toml or declares no
    dev extra.
    """
    pyproject_path = project_root / "pyproject.toml"
    if not pyproject_path.is_file():
        return []
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    specs = data.get("project", {}).get("optional-dependencies", {}).get("dev", [])
    if not isinstance(specs, list):
        return []
    return [spec for spec in specs if isinstance(spec, str)]


def _normalized_group_name(name: str) -> str:
    """A dependency group name as PEP 735 compares it (PEP 503 normalization)."""
    return _GROUP_NAME_SEPARATORS.sub("-", name).lower()


def read_dependency_group(project_root: Path, group: str) -> list[str]:
    """The requirement specs of the PEP 735 dependency group *group* in *project_root*'s pyproject.toml.

    ``{include-group = "<name>"}`` entries are expanded in place. Raises ValueError naming the file
    when the file or a named group is missing, when an entry is neither a requirement string nor an
    include-group table, or when groups include each other in a cycle.
    """
    pyproject_path = project_root / "pyproject.toml"
    if not pyproject_path.is_file():
        raise ValueError(
            f"{pyproject_path} does not exist, so dependency group '{group}' cannot be read. "
            f"Expected a pyproject.toml declaring a [{_DEPENDENCY_GROUPS_TABLE}] table at {project_root}."
        )
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    groups = data.get(_DEPENDENCY_GROUPS_TABLE, {})
    if not isinstance(groups, dict):
        raise ValueError(
            f"{pyproject_path}: [{_DEPENDENCY_GROUPS_TABLE}] must be a table of named lists, "
            f"got {type(groups).__name__}."
        )
    by_name = {_normalized_group_name(name): entries for name, entries in groups.items()}
    return _expand_group(by_name, group, pyproject_path, ())


def _expand_group(
    groups: dict[str, object], group: str, pyproject_path: Path, including: tuple[str, ...]
) -> list[str]:
    """The specs of *group*, its include-group entries expanded; *including* is the chain that reached it."""
    key = _normalized_group_name(group)
    if key in including:
        raise ValueError(
            f"{pyproject_path}: dependency groups include each other in a cycle "
            f"({' -> '.join((*including, key))}). Remove one of the include-group entries."
        )
    if key not in groups:
        raise ValueError(
            f"{pyproject_path} declares no dependency group '{group}' "
            f"(declared: {sorted(groups) or 'none'}). Add it under [{_DEPENDENCY_GROUPS_TABLE}]."
        )
    entries = groups[key]
    if not isinstance(entries, list):
        raise ValueError(f"{pyproject_path}: dependency group '{group}' must be a list, got {type(entries).__name__}.")
    specs: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            specs.append(entry)
        elif (
            isinstance(entry, dict)
            and set(entry) == {_INCLUDE_GROUP_KEY}
            and isinstance(entry[_INCLUDE_GROUP_KEY], str)
        ):
            specs.extend(_expand_group(groups, entry[_INCLUDE_GROUP_KEY], pyproject_path, (*including, key)))
        else:
            raise ValueError(
                f"{pyproject_path}: dependency group '{group}' holds {entry!r}. Each entry is a requirement "
                f'string or {{{_INCLUDE_GROUP_KEY} = "<group>"}} (PEP 735).'
            )
    return specs


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


def _group_refusal(project_root: Path, group: str, fragment: str) -> str:
    """``"refused"`` when reading *group* raises a ValueError naming *fragment*; otherwise what happened."""
    try:
        return f"accepted: {read_dependency_group(project_root, group)}"
    except ValueError as exc:
        return "refused" if fragment in str(exc) else f"refused without naming {fragment!r}: {exc}"


def _dependency_group_cases(workspace: Path) -> list[tuple[str, object, object]]:
    """Dependency-group reads on a planted non-package project: expansion, normalization, refusals."""
    project = workspace / "showcase"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        "[project]\n"
        'name = "showcase"\n'
        "dependencies = []\n\n"
        "[dependency-groups]\n"
        'scripts = ["libcst>=1.8", { include-group = "Lint_Tools" }]\n'
        "lint-tools = [\"semgrep>=1.0; sys_platform != 'win32'\"]\n"
        'loop-a = [{ include-group = "loop-b" }]\n'
        'loop-b = [{ include-group = "loop-a" }]\n'
        "bad-entry = [3]\n",
        encoding="utf-8",
    )
    return [
        (
            "a group's include-group entry expands in place, the name matched after normalization",
            read_dependency_group(project, SCRIPTS_DEPENDENCY_GROUP),
            ["libcst>=1.8", "semgrep>=1.0; sys_platform != 'win32'"],
        ),
        (
            "an undeclared group is refused",
            _group_refusal(project, "absent", "declares no dependency group 'absent'"),
            "refused",
        ),
        (
            "groups including each other are refused",
            _group_refusal(project, "loop-a", "cycle (loop-a -> loop-b -> loop-a)"),
            "refused",
        ),
        (
            "an entry that is no requirement string is refused",
            _group_refusal(project, "bad-entry", "dependency group 'bad-entry' holds 3"),
            "refused",
        ),
        (
            "a project with no pyproject.toml is refused",
            _group_refusal(workspace / "not-a-package", SCRIPTS_DEPENDENCY_GROUP, "does not exist"),
            "refused",
        ),
    ]


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
        cases.extend(_dependency_group_cases(workspace))
    cases.append((
        "venv-dev-specs.ps1 is the template rendered and passes only this module's options",
        wrapper_problems(SCRIPTS_DIR / "common" / "venv-dev-specs.ps1", __spec__.name, build_parser()),
        [],
    ))
    failures = [(label, got, want) for label, got, want in cases if got != want]
    for label, got, want in failures:
        print(f"FAIL {label}: got {got}, expected {want}", file=sys.stderr)
    if not failures:
        print(f"dev_specs self-test: {len(cases)} case(s) passed")
    return not failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-test", action="store_true", help="run only the dev-spec rewrite self-test")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.self_test:
        parser.print_usage(sys.stderr)
        print(f"Error: pass --self-test ({wrapper_command('common/venv-dev-specs', 'SelfTest')}).", file=sys.stderr)
        return 1
    return 0 if run_self_test() else 1


if __name__ == "__main__":
    sys.exit(main())
