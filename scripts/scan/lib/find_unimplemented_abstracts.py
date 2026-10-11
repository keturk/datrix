#!/usr/bin/env python3
"""Find classes that inherit abstract methods they never implement.

Imports every module of the selected Datrix packages (default: every ``datrix-*`` package with
a ``src/`` tree) and inspects every class defined there. A class whose ``__abstractmethods__``
is non-empty cannot be instantiated; that is intended for an abstract base and a defect for a
class meant to be concrete -- for example a generator that misses one of its base's abstract
methods after a merge, which otherwise surfaces only when something instantiates it.

A class counts as an **intended abstract base** when it subclasses ``abc.ABC`` directly, uses
``ABCMeta`` while declaring at least one abstract method itself, is a ``typing.Protocol``, or is
itself subclassed (an intermediate base whose subclasses supply the methods). Every other class
with outstanding abstract methods -- a leaf meant to be concrete -- is **incomplete** and is
reported with the methods it is missing and the base each one comes from.

Exit codes: 0 = no incomplete class, 1 = incomplete class(es) found, 2 = a module failed to
import or a bad argument (every import failure is listed; none is skipped silently).

Usage:
    python find_unimplemented_abstracts.py [--package IMPORT_NAME ...] [--show-bases] [--debug]
"""

from __future__ import annotations

import abc
import argparse
import importlib
import inspect
import logging
import pkgutil
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from types import ModuleType
from typing import Final

from datrix_scripts.registered_targets import WORKSPACE_ROOT, discover_all_package_locations

logger = logging.getLogger(__name__)

EXIT_OK: Final[int] = 0
EXIT_INCOMPLETE: Final[int] = 1
EXIT_ERROR: Final[int] = 2
_PROTOCOL_FLAG: Final[str] = "_is_protocol"
_ABSTRACT_FLAG: Final[str] = "__isabstractmethod__"


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


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--package",
        action="append",
        default=[],
        help="Import name to scan (e.g. datrix_codegen_python). Repeatable. Default: every datrix-* package.",
    )
    parser.add_argument("--show-bases", action="store_true", help="Also list the intended abstract bases.")
    parser.add_argument("--debug", action="store_true", help="Debug logging.")
    return parser.parse_args(argv)


def _print_class(item: AbstractClass, label: str) -> None:
    print(f"{label} {item.qualified_name}")
    for method, base in item.missing:
        print(f"    {method}  (abstract in {base})")


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format="%(levelname)s: %(message)s")
    available = sorted(discover_all_package_locations(WORKSPACE_ROOT))
    packages = args.package or available
    unknown = sorted(set(packages) - set(available))
    if unknown:
        logger.error(
            "Unknown package import name(s) %s. Expected one of: %s. Fix: pass the import name "
            "(underscores), not the repository name.",
            unknown,
            ", ".join(available),
        )
        return EXIT_ERROR

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
    if args.show_bases:
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


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
