"""Find classes that inherit abstract methods they never implement.

The module behind ``scan/find-unimplemented-abstracts.ps1`` (and its ``.sh`` twin); the editable
installs are checked first. Imports every module of the selected Datrix packages (default: every
``datrix-*`` package with a ``src/`` tree) and inspects every class defined there. A class whose
``__abstractmethods__`` is non-empty cannot be instantiated; that is intended for an abstract base
and a defect for a class meant to be concrete -- for example a generator that misses one of its
base's abstract methods after a merge, which otherwise surfaces only when something instantiates it.

A class counts as an **intended abstract base** when it subclasses ``abc.ABC`` directly, uses
``ABCMeta`` while declaring at least one abstract method itself, is a ``typing.Protocol``, or is
itself subclassed (an intermediate base whose subclasses supply the methods). Every other class
with outstanding abstract methods -- a leaf meant to be concrete -- is **incomplete** and is
reported with the methods it is missing and the base each one comes from.

Exit codes: 0 = no incomplete class, 1 = incomplete class(es) found or the package install check
failed, 2 = a module failed to import or a bad argument (every import failure is listed; none is
skipped silently).

Usage:
    python -m datrix_scripts.scan.find_unimplemented_abstracts [--package IMPORT_NAME ...] [--show-bases] [--dbg]
    python -m datrix_scripts.scan.find_unimplemented_abstracts --self-test
"""

from __future__ import annotations

import abc
import argparse
import contextlib
import importlib
import importlib.util
import inspect
import io
import logging
import os
import pkgutil
import sys
import tempfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Final

from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, write_files
from datrix_scripts.registered_targets import WORKSPACE_ROOT, discover_all_package_locations
from datrix_scripts.dev.arguments import comma_values
from datrix_scripts.test.wrappers import SCAN_SCRIPTS_DIR, module_main, run_self_test

logger = logging.getLogger(__name__)

MODULE: Final = "datrix_scripts.scan.find_unimplemented_abstracts"
WRAPPER: Final = "find-unimplemented-abstracts"
EXIT_OK: Final[int] = 0
EXIT_INCOMPLETE: Final[int] = 1
EXIT_ERROR: Final[int] = 2
_PROTOCOL_FLAG: Final[str] = "_is_protocol"
_ABSTRACT_FLAG: Final[str] = "__isabstractmethod__"

#: The self-test's planted packages: one with an abstract base, an intermediate base and an incomplete
#: leaf; one whose submodule fails to import.
_PLANTED_INCOMPLETE: Final = "datrix_selftest_abstracts_incomplete"
_PLANTED_BROKEN: Final = "datrix_selftest_abstracts_broken"
_PLANTED_SOURCES: Final = {
    f"{_PLANTED_INCOMPLETE}/__init__.py": "",
    f"{_PLANTED_INCOMPLETE}/shapes.py": (
        "import abc\n\n\n"
        "class Shape(abc.ABC):\n"
        "    @abc.abstractmethod\n"
        "    def area(self) -> float: ...\n\n"
        "    @abc.abstractmethod\n"
        "    def name(self) -> str: ...\n\n\n"
        "class Polygon(Shape):\n"
        "    def name(self) -> str:\n"
        "        return 'polygon'\n\n\n"
        "class Square(Polygon):\n"
        "    pass\n\n\n"
        "class Circle(Shape):\n"
        "    def area(self) -> float:\n"
        "        return 3.14\n\n"
        "    def name(self) -> str:\n"
        "        return 'circle'\n"
    ),
    f"{_PLANTED_BROKEN}/__init__.py": "",
    f"{_PLANTED_BROKEN}/broken.py": "raise ImportError('planted import failure')\n",
}


@dataclass(frozen=True)
class AbstractClass:
    """One class that still carries abstract methods."""

    qualified_name: str
    missing: tuple[tuple[str, str], ...]  # (method name, base class that declares it abstract)
    intended: bool


@dataclass(frozen=True)
class ImportFailure:
    """A module that could not be imported."""

    module: str
    error: str


def _declares_abstract(cls: type) -> bool:
    return any(getattr(value, _ABSTRACT_FLAG, False) for value in vars(cls).values())


def is_intended_abstract(cls: type) -> bool:
    """True for a class written to be abstract (see the module docstring)."""
    if getattr(cls, _PROTOCOL_FLAG, False):
        return True
    if abc.ABC in cls.__bases__:
        return True
    if cls.__subclasses__():
        return True
    return isinstance(cls, abc.ABCMeta) and _declares_abstract(cls)


def _declaring_base(cls: type, method: str) -> str:
    for base in cls.__mro__:
        value = vars(base).get(method)
        if value is not None and getattr(value, _ABSTRACT_FLAG, False):
            return f"{base.__module__}.{base.__qualname__}"
    return f"{cls.__module__}.{cls.__qualname__}"


def walk_modules(package: str) -> tuple[list[ModuleType], list[ImportFailure]]:
    """Import *package* and every submodule; collect each failure instead of stopping."""
    try:
        root = importlib.import_module(package)
    except Exception as exc:  # noqa: BLE001 -- any import failure is reported, never skipped
        return [], [ImportFailure(package, f"{type(exc).__name__}: {exc}")]
    modules: list[ModuleType] = [root]
    failures: list[ImportFailure] = []
    for info in pkgutil.walk_packages(root.__path__, f"{package}.", onerror=lambda name: failures.append(
        ImportFailure(name, "package __init__ failed during the walk")
    )):
        try:
            modules.append(importlib.import_module(info.name))
        except Exception as exc:  # noqa: BLE001 -- any import failure is reported, never skipped
            failures.append(ImportFailure(info.name, f"{type(exc).__name__}: {exc}"))
    return modules, failures


def abstract_classes(package: str, modules: Sequence[ModuleType]) -> list[AbstractClass]:
    """Every class defined in *package*'s modules that still carries abstract methods."""
    seen: set[type] = set()
    found: list[AbstractClass] = []
    for module in modules:
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls in seen or not cls.__module__.startswith(package):
                continue
            seen.add(cls)
            missing = sorted(getattr(cls, "__abstractmethods__", ()))
            if not missing:
                continue
            found.append(
                AbstractClass(
                    qualified_name=f"{cls.__module__}.{cls.__qualname__}",
                    missing=tuple((name, _declaring_base(cls, name)) for name in missing),
                    intended=is_intended_abstract(cls),
                )
            )
    return sorted(found, key=lambda item: item.qualified_name)


def _print_class(item: AbstractClass, label: str) -> None:
    print(f"{label} {item.qualified_name}")
    for method, base in item.missing:
        print(f"    {method}  (abstract in {base})")


def inspect_packages(packages: Sequence[str], show_bases: bool) -> int:
    """Import *packages*, print every incomplete class (and with *show_bases* every intended base) and
    every import failure; the exit code."""
    incomplete: list[AbstractClass] = []
    bases: list[AbstractClass] = []
    failures: list[ImportFailure] = []
    for package in packages:
        modules, package_failures = walk_modules(package)
        failures.extend(package_failures)
        found = abstract_classes(package, modules)
        logger.debug("%s: %d module(s), %d abstract class(es)", package, len(modules), len(found))
        incomplete.extend(item for item in found if not item.intended)
        bases.extend(item for item in found if item.intended)

    for item in incomplete:
        _print_class(item, "INCOMPLETE")
    if show_bases:
        for item in bases:
            _print_class(item, "ABSTRACT BASE")
    for failure in failures:
        print(f"IMPORT FAILED {failure.module}: {failure.error}")
    print(
        f"Scanned {len(packages)} package(s): {len(incomplete)} incomplete class(es), "
        f"{len(bases)} intended abstract base(s), {len(failures)} import failure(s)."
    )
    if failures:
        return EXIT_ERROR
    return EXIT_INCOMPLETE if incomplete else EXIT_OK


def find(requested: Sequence[str], available: Sequence[str], show_bases: bool) -> int:
    """Inspect the *requested* packages (every *available* one when none is named); an unknown name is
    refused with exit 2."""
    packages = list(requested) or list(available)
    unknown = sorted(set(packages) - set(available))
    if unknown:
        logger.error(
            "Unknown package import name(s) %s. Expected one of: %s. Fix: pass the import name "
            "(underscores), not the repository name.",
            unknown,
            ", ".join(available),
        )
        return EXIT_ERROR
    return inspect_packages(packages, show_bases)


def build_parser() -> argparse.ArgumentParser:
    """The options of ``scan/find-unimplemented-abstracts.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument(
        "--package",
        action="append",
        default=[],
        help="Import name to scan (e.g. datrix_codegen_python). Repeatable and/or comma-separated. "
             "Default: every datrix-* package.",
    )
    parser.add_argument("--show-bases", action="store_true", help="Also list the intended abstract bases.")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true",
                        help="Debug logging (per-package module and class counts).")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: a planted incomplete leaf exits 1 while its bases are "
                             "intended, a planted import failure exits 2, an unknown package is refused, and the "
                             "wrapper seam holds.")
    return parser


def _load_package(root: Path, name: str) -> None:
    """Load package *name* from ``root/name`` into ``sys.modules``; its submodules then resolve through
    the package's own ``__path__``, so the import path is left as the venv set it."""
    package_dir = root / name
    spec = importlib.util.spec_from_file_location(
        name, package_dir / "__init__.py", submodule_search_locations=[str(package_dir)]
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"the planted package {name} has no loader at {package_dir}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


@contextlib.contextmanager
def _planted_packages() -> Iterator[None]:
    """The planted packages importable for the duration, then removed from ``sys.modules``."""
    with tempfile.TemporaryDirectory() as tmp:
        write_files(Path(tmp), _PLANTED_SOURCES)
        try:
            for name in (_PLANTED_INCOMPLETE, _PLANTED_BROKEN):
                _load_package(Path(tmp), name)
            yield
        finally:
            for name in [name for name in sys.modules if name.startswith((_PLANTED_INCOMPLETE, _PLANTED_BROKEN))]:
                del sys.modules[name]


def _found(requested: Sequence[str], available: Sequence[str]) -> tuple[int, str]:
    """``find`` with the bases shown: the exit code and what it printed."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = find(requested, available, show_bases=True)
    return code, out.getvalue()


def _check_an_incomplete_leaf_is_reported() -> None:
    with _planted_packages():
        code, out = _found([_PLANTED_INCOMPLETE], [_PLANTED_INCOMPLETE])
    assert code == EXIT_INCOMPLETE, f"an incomplete leaf must exit {EXIT_INCOMPLETE}; got {code}: {out!r}"
    assert f"INCOMPLETE {_PLANTED_INCOMPLETE}.shapes.Square" in out, f"the leaf Square is incomplete: {out!r}"
    assert f"area  (abstract in {_PLANTED_INCOMPLETE}.shapes.Shape)" in out, f"the missing method names its base: {out!r}"
    for base in ("Shape", "Polygon"):
        assert f"ABSTRACT BASE {_PLANTED_INCOMPLETE}.shapes.{base}" in out, f"{base} is an intended base: {out!r}"
    assert "Circle" not in out, f"the complete Circle is not reported: {out!r}"


def _check_an_import_failure_exits_2() -> None:
    with _planted_packages():
        code, out = _found([_PLANTED_BROKEN], [_PLANTED_BROKEN])
    assert code == EXIT_ERROR, f"an import failure must exit {EXIT_ERROR}; got {code}: {out!r}"
    assert f"IMPORT FAILED {_PLANTED_BROKEN}.broken: ImportError: planted import failure" in out, out


def _check_an_unknown_package_is_refused() -> None:
    code, out = _found(comma_values(["datrix-common"]), ["datrix_common"])
    assert code == EXIT_ERROR and not out, f"a repository name must be refused before any import; got {code}: {out!r}"


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [
            _check_an_incomplete_leaf_is_reported,
            _check_an_import_failure_exits_2,
            _check_an_unknown_package_is_refused,
        ]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=SCAN_SCRIPTS_DIR)
    from datrix_scripts.test.test import ensure_packages
    from datrix_scripts.venv import require_packages

    if not ensure_packages(os.environ, require_packages):
        return EXIT_INCOMPLETE
    available = sorted(discover_all_package_locations(WORKSPACE_ROOT))
    return find(comma_values(args.package), available, args.show_bases)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
