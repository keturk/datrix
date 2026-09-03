#!/usr/bin/env python3
"""Third-party dependency parity gate: every ``datrix-*`` manifest's third-party
runtime dependencies equal the third-party distributions its ``src/`` tree
imports.

The sibling ``manifest-import-parity-gate`` holds this invariant for the
DATRIX distributions; this gate holds it for everything else. The shared
editable venv makes every installed distribution importable from every
package, so a manifest can lie in either direction with every suite green:

- **undeclared**: ``src/`` imports a distribution the manifest never names.
  It works here only because something else installed it -- once, four
  packages imported a password-hashing library that no framework manifest
  declared and that was present only because generated customer projects
  installed into the same venv required it.
- **dead**: the manifest names a distribution ``src/`` never imports. Once,
  five packages declared a template engine only a sixth (which did not
  declare it) imported, one CLI declared a linter only a language package
  (which did not declare it) invoked, and a generator declared the web
  framework and ORM of the projects it GENERATES.

Rules, per package:

1. ``declared`` = the third-party names in ``[project] dependencies``.
   Extras (``[project.optional-dependencies]``) other than ``dev`` are
   optional runtime surfaces (a ``testing`` helper subpackage, an ``lsp``
   server): an import they satisfy is a declared optional dependency, not a
   violation. The ``dev`` extra never satisfies a ``src/`` import.
2. ``imported`` = every absolute import root in ``src/**/*.py`` (``ast``,
   nested imports included) that is neither standard library nor a Datrix
   package, mapped to its distribution(s) through the installed metadata
   (``importlib.metadata.packages_distributions``). A root several
   distributions provide (``ruamel`` -> ``ruamel.yaml`` and its C helper) is
   satisfied by ANY declared candidate. A root no installed distribution
   provides is itself a violation: the import cannot work anywhere.
3. ``imported - declared`` (undeclared) and ``declared - imported`` (dead)
   must both be empty, except for a reviewed **executable** exemption: a
   distribution the package invokes as a subprocess rather than imports
   (a formatter run over generated code), recorded with a reason in
   ``datrix/scripts/config/third-party-dependency-exemptions.json``. An
   exemption that no longer matches a declared-but-unimported distribution
   is stale and fails the gate.

Non-vacuity, before the real scan: a planted dirty package yields exactly
its five violations (undeclared import, unmapped import, dev-extra-only
import, dead declaration, stale exemption) while its non-dev-extra import
and its exempted executable are accepted; a planted clean package yields
none; a workspace with fewer than two packages is refused; and the live scan
must see at least one real package both declare and import the same
distribution -- the scanner is proven against the tree it guards.

Exit codes:
    0: No violation (or a successful --self-test run).
    1: At least one violation or stale exemption.
    2: Usage error, too few packages, or the self-test failed.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tempfile
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import packages_distributions
from pathlib import Path

DEV_EXTRA_NAMES: frozenset[str] = frozenset({"dev"})
EXEMPTIONS_RELATIVE_PATH = (
    Path("datrix") / "scripts" / "config" / "third-party-dependency-exemptions.json"
)
MIN_PACKAGES = 2
DATRIX_DISTRIBUTION_PREFIX = "datrix"
DATRIX_IMPORT_PREFIX = "datrix_"
#: Pseudo-modules that exist only inside a type checker (``_typeshed`` ships
#: with the checker's stub bundle, never as an installable distribution).
#: They are imported under ``TYPE_CHECKING`` only and have no manifest home.
TYPING_STUB_ROOTS: frozenset[str] = frozenset({"_typeshed"})
_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


class GateError(Exception):
    """A gate-level failure (usage, discovery, or self-test)."""


def normalize(distribution: str) -> str:
    """PEP 503 normalization: case-insensitive, ``_``/``.`` runs read as ``-``."""
    return re.sub(r"[-_.]+", "-", distribution).lower()


@dataclass(frozen=True)
class Manifest:
    distribution: str
    src_dir: Path
    runtime: frozenset[str]
    optional_runtime: frozenset[str]


@dataclass(frozen=True)
class Violation:
    package: str
    kind: str
    subject: str
    detail: str


@dataclass(frozen=True)
class Exemption:
    package: str
    distribution: str
    reason: str


def _ok(message: str) -> None:
    print(f"{GREEN}[OK]{RESET} {message}")


def _fail(message: str) -> None:
    print(f"{RED}[FAIL]{RESET} {message}")


# ---------------------------------------------------------------------------
# Manifests
# ---------------------------------------------------------------------------


def requirement_name(requirement: str) -> str:
    """The distribution name of one PEP 508 requirement string, normalized."""
    match = _REQUIREMENT_NAME.match(requirement)
    if match is None:
        raise GateError(f"Cannot parse requirement {requirement!r}.")
    return normalize(match.group(1))


def _third_party(requirements: list[object], where: str) -> frozenset[str]:
    names: set[str] = set()
    for requirement in requirements:
        if not isinstance(requirement, str):
            raise GateError(f"{where}: requirement entries must be strings, got {requirement!r}.")
        dist = requirement_name(requirement)
        if not dist.startswith(DATRIX_DISTRIBUTION_PREFIX):
            names.add(dist)
    return frozenset(names)


def read_manifest(pyproject: Path) -> Manifest | None:
    """The manifest for one package directory, or ``None`` when it has no ``src/``."""
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data.get("project")
    if not isinstance(project, dict):
        raise GateError(f"{pyproject}: no [project] table.")
    src_dir = pyproject.parent / "src"
    if not src_dir.is_dir():
        return None
    runtime = _third_party(project.get("dependencies", []), f"{pyproject} dependencies")
    optional: set[str] = set()
    extras = project.get("optional-dependencies", {})
    if not isinstance(extras, dict):
        raise GateError(f"{pyproject}: optional-dependencies must be a table.")
    for extra_name, requirements in extras.items():
        if extra_name in DEV_EXTRA_NAMES:
            continue
        optional |= _third_party(requirements, f"{pyproject} extra {extra_name}")
    return Manifest(
        distribution=normalize(pyproject.parent.name),
        src_dir=src_dir,
        runtime=runtime,
        optional_runtime=frozenset(optional),
    )


def discover_manifests(base_dir: Path) -> list[Manifest]:
    manifests: list[Manifest] = []
    for pyproject in sorted(base_dir.glob("datrix-*/pyproject.toml")):
        manifest = read_manifest(pyproject)
        if manifest is not None:
            manifests.append(manifest)
    return manifests


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------


def import_roots(src_dir: Path) -> set[str]:
    """Every absolute import root under *src_dir*, nested imports included."""
    roots: set[str] = set()
    for path in sorted(src_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    roots.add(alias.name.split(".", 1)[0])
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                roots.add(node.module.split(".", 1)[0])
    return roots


def third_party_roots(roots: set[str], stdlib: frozenset[str]) -> set[str]:
    return {
        root
        for root in roots
        if root not in stdlib
        and root != "__future__"
        and root not in TYPING_STUB_ROOTS
        and not root.startswith(DATRIX_IMPORT_PREFIX)
    }


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def compare(
    manifest: Manifest,
    root_to_dists: Mapping[str, list[str]],
    stdlib: frozenset[str],
    exemptions: list[Exemption],
) -> tuple[list[Violation], list[Exemption]]:
    """Return (violations, exemptions this package used)."""
    violations: list[Violation] = []
    declared = manifest.runtime | manifest.optional_runtime
    imported_dists: set[str] = set()
    for root in sorted(third_party_roots(import_roots(manifest.src_dir), stdlib)):
        candidates = [normalize(d) for d in root_to_dists.get(root, [])]
        candidates = [c for c in candidates if not c.startswith(DATRIX_DISTRIBUTION_PREFIX)]
        if not candidates:
            violations.append(
                Violation(
                    manifest.distribution,
                    "unmapped-import",
                    root,
                    f"src/ imports {root!r} but no installed distribution provides it; "
                    "the import cannot work on a clean install.",
                )
            )
            continue
        satisfied = [c for c in candidates if c in declared]
        if satisfied:
            imported_dists.update(satisfied)
            continue
        imported_dists.add(candidates[0])
        violations.append(
            Violation(
                manifest.distribution,
                "undeclared-import",
                root,
                f"src/ imports {root!r} (provided by {', '.join(candidates)}) but the "
                "manifest declares none of them in [project] dependencies or a non-dev extra.",
            )
        )
    used_exemptions: list[Exemption] = []
    for dist in sorted(manifest.runtime - imported_dists):
        exemption = next(
            (e for e in exemptions if e.package == manifest.distribution and e.distribution == dist),
            None,
        )
        if exemption is not None:
            used_exemptions.append(exemption)
            continue
        violations.append(
            Violation(
                manifest.distribution,
                "dead-declaration",
                dist,
                f"[project] dependencies declares {dist!r} but src/ never imports it.",
            )
        )
    return violations, used_exemptions


def load_exemptions(path: Path) -> list[Exemption]:
    if not path.is_file():
        raise GateError(f"Exemptions file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("exemptions")
    expected_count = data.get("expected_count")
    if not isinstance(entries, list) or not isinstance(expected_count, int):
        raise GateError(f"{path}: expected 'exemptions' (list) and 'expected_count' (int).")
    if expected_count != len(entries):
        raise GateError(
            f"{path}: expected_count={expected_count} but {len(entries)} entries are listed; "
            "remediation removes the entry AND decrements the count in the same change."
        )
    exemptions: list[Exemption] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise GateError(f"{path}: every exemption must be an object, got {entry!r}.")
        for key in ("package", "distribution", "reason"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise GateError(f"{path}: exemption {entry!r} is missing a non-empty {key!r}.")
        exemptions.append(
            Exemption(
                package=normalize(entry["package"]),
                distribution=normalize(entry["distribution"]),
                reason=entry["reason"],
            )
        )
    return exemptions


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


_SELFTEST_MAPPING: dict[str, list[str]] = {
    "engine": ["engine-lib"],
    "hasher": ["hasher-lib"],
    "devtool": ["devtool-lib"],
    "helper": ["helper-lib"],
    "twin": ["twin-core", "twin-clib"],
}
_SELFTEST_STDLIB: frozenset[str] = frozenset({"os", "json"})


def _plant_dirty(root: Path) -> None:
    _write(
        root / "datrix-selftest-dirty" / "pyproject.toml",
        "[project]\n"
        'name = "datrix-selftest-dirty"\n'
        'version = "0.0.0"\n'
        'dependencies = ["engine-lib>=1", "Dead_Lib>=1", "Exec-Tool>=1", "twin-core>=1"]\n'
        "[project.optional-dependencies]\n"
        'dev = ["devtool-lib>=1"]\n'
        'helpers = ["helper-lib>=1"]\n',
    )
    _write(
        root / "datrix-selftest-dirty" / "src" / "selftest_dirty" / "mod.py",
        "import os\n"
        "import engine\n"
        "import hasher\n"
        "import devtool\n"
        "import helper\n"
        "import twin.core\n"
        "import ghost\n"
        "\n"
        "\n"
        "def f() -> None:\n"
        "    import json\n",
    )


def _plant_clean(root: Path) -> None:
    _write(
        root / "datrix-selftest-clean" / "pyproject.toml",
        "[project]\n"
        'name = "datrix-selftest-clean"\n'
        'version = "0.0.0"\n'
        'dependencies = ["engine-lib>=1", "datrix-selftest-dirty"]\n',
    )
    _write(
        root / "datrix-selftest-clean" / "src" / "selftest_clean" / "mod.py",
        "import os\nfrom engine import thing\nimport datrix_selftest_dirty\n",
    )


def run_self_test(base_dir: Path, root_to_dists: Mapping[str, list[str]], stdlib: frozenset[str]) -> bool:
    ok = True
    exemptions = [
        Exemption("datrix-selftest-dirty", "exec-tool", "invoked as a subprocess"),
        Exemption("datrix-selftest-dirty", "engine-lib", "stale: engine-lib IS imported"),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _plant_dirty(root)
        _plant_clean(root)
        manifests = {m.distribution: m for m in discover_manifests(root)}
        if set(manifests) == {"datrix-selftest-dirty", "datrix-selftest-clean"}:
            _ok("discovery finds every planted package with a src/ tree")
        else:
            _fail(f"discovery returned {sorted(manifests)}")
            ok = False
        dirty_violations, used = compare(
            manifests["datrix-selftest-dirty"], _SELFTEST_MAPPING, _SELFTEST_STDLIB, exemptions
        )
        got = sorted((v.kind, v.subject) for v in dirty_violations)
        expected = [
            ("dead-declaration", "dead-lib"),
            ("undeclared-import", "devtool"),
            ("undeclared-import", "hasher"),
            ("unmapped-import", "ghost"),
        ]
        if got == expected:
            _ok(
                "dirty package: undeclared import, dev-extra-only import, unmapped import and "
                "dead declaration are reported; the non-dev-extra import, the ambiguous root "
                "satisfied by one declared candidate, and the exempted executable are not"
            )
        else:
            _fail(f"dirty package yielded {got}, expected {expected}")
            ok = False
        if [e.distribution for e in used] == ["exec-tool"]:
            _ok("only the matching executable exemption is consumed; the stale one is left over")
        else:
            _fail(f"used exemptions were {[e.distribution for e in used]}")
            ok = False
        clean_violations, _ = compare(
            manifests["datrix-selftest-clean"], _SELFTEST_MAPPING, _SELFTEST_STDLIB, []
        )
        if not clean_violations:
            _ok("clean package yields zero violations (Datrix distributions are out of scope)")
        else:
            _fail(f"clean package yielded {clean_violations}")
            ok = False
        try:
            _require_enough([manifests["datrix-selftest-clean"]])
        except GateError:
            _ok("fewer than two packages is refused, never a silent pass")
        else:
            _fail("a single package was accepted")
            ok = False

    live = [m for m in discover_manifests(base_dir) if m.runtime]
    proven = False
    for manifest in live:
        roots = third_party_roots(import_roots(manifest.src_dir), stdlib)
        imported = {normalize(d) for r in roots for d in root_to_dists.get(r, [])}
        if manifest.runtime & imported:
            proven = True
            break
    if proven:
        _ok("live scan sees a real package both declare and import one third-party distribution")
    else:
        _fail("live scan found no package whose declared dependency is also imported")
        ok = False
    return ok


def _require_enough(manifests: list[Manifest]) -> None:
    if len(manifests) < MIN_PACKAGES:
        raise GateError(
            f"Discovered {len(manifests)} package(s) with a src/ tree; at least "
            f"{MIN_PACKAGES} are required for a non-vacuous scan."
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _detect_base_dir() -> Path:
    return Path(__file__).resolve().parents[3]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-dir", type=Path, default=None)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    base_dir = (args.base_dir or _detect_base_dir()).resolve()
    stdlib = frozenset(sys.stdlib_module_names)
    root_to_dists: Mapping[str, list[str]] = packages_distributions()

    try:
        manifests = discover_manifests(base_dir)
        _require_enough(manifests)
        if not run_self_test(base_dir, root_to_dists, stdlib):
            print(f"{RED}SELF-TEST FAILED{RESET}")
            return 2
        print(f"{GREEN}SELF-TEST PASSED{RESET}")
        if args.self_test:
            return 0
        exemptions = load_exemptions(base_dir / EXEMPTIONS_RELATIVE_PATH)
    except GateError as error:
        print(f"{RED}ERROR{RESET}: {error}", file=sys.stderr)
        return 2

    violations: list[Violation] = []
    used_exemptions: list[Exemption] = []
    for manifest in manifests:
        package_violations, used = compare(manifest, root_to_dists, stdlib, exemptions)
        if args.verbose:
            print(f"INFO: package={manifest.distribution} declared={sorted(manifest.runtime)}")
        print(f"INFO: package={manifest.distribution} violations={len(package_violations)}")
        violations.extend(package_violations)
        used_exemptions.extend(used)
    stale = [e for e in exemptions if e not in used_exemptions]

    for violation in violations:
        _fail(f"{violation.package}: {violation.kind} {violation.subject!r} -- {violation.detail}")
    for exemption in stale:
        _fail(
            f"stale exemption: {exemption.package} no longer declares-without-importing "
            f"{exemption.distribution!r}"
        )
    print(
        f"THIRD-PARTY DEPENDENCY PARITY REPORT: {len(manifests)} package(s) scanned, "
        f"{len(violations)} violation(s), {len(used_exemptions)} exemption(s) used, "
        f"{len(stale)} stale exemption(s)."
    )
    if violations or stale:
        return 1
    print(f"{GREEN}Third-party dependency parity gate passed{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
