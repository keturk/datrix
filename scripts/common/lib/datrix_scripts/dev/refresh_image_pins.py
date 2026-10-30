"""Rewrite every package's container image pin table from its registry.

The module behind ``dev/refresh-image-pins.ps1`` (and its ``.sh`` twin). Every package that chooses
container images for a generated project ships ``image_pins.json`` beside its top module
(``datrix_common.config.image_pins``): each ``<name>:<tag>`` reference it names, mapped to the digest
of that tag's multi-platform index. This script is the only writer of those tables. For each table
found under ``<workspace>/datrix-*/src/*/image_pins.json`` it resolves every reference with
``docker buildx imagetools inspect`` and rewrites the table sorted by reference, so a tag moved
upstream shows as a table diff in review. ``-Package`` limits the run to one package's table, and
``-Add`` puts new references into that table first. It is the only network step of image pinning: no
framework test runs it.

A reference the registry does not resolve, or answers with something that is not a digest, fails the
run and no table is written (all tables or none). A registry's rate-limit answer is retried with a
growing wait before it counts as a failure.

Exit codes: 0 = every table rewritten (or ``--self-test`` passed), 1 = a reference did not resolve or a
failed self-test, 2 = a usage error (``-Add`` without ``-Package``, an unknown package, no tables).

Usage:
    python -m datrix_scripts.dev.refresh_image_pins
    python -m datrix_scripts.dev.refresh_image_pins --package datrix-codegen-docker --add redis:7
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_common.config.image_pins import IMAGE_PIN_TABLE_FILE, TAGGED_IMAGE, ImagePinTable
from datrix_common.errors.configuration import ConfigurationError

from datrix_scripts.dev.arguments import comma_values
from datrix_scripts.framework_repos import workspace_package_dirs
from datrix_scripts.gate_harness import EXIT_VIOLATION, UsageError, expect_usage_error
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import DEV_SCRIPTS_DIR, module_main, run_self_test

logger = logging.getLogger(__name__)

MODULE: Final = "datrix_scripts.dev.refresh_image_pins"
WRAPPER: Final = "refresh-image-pins"
EXIT_OK: Final[int] = 0

#: The registry query: the digest of the reference's top-level manifest (its multi-platform index).
_INSPECT_FORMAT: Final[str] = "{{json .Manifest.Digest}}"
_INSPECT_TIMEOUT_SECONDS: Final[int] = 120
#: A registry's rate-limit answer, retried with a growing wait.
_RATE_LIMIT_MARKERS: Final[tuple[str, ...]] = ("429", "toomanyrequests", "Rate exceeded")
_RATE_LIMIT_ATTEMPTS: Final[int] = 5
_RATE_LIMIT_WAIT_SECONDS: Final[int] = 30

#: Resolves one reference to its digest; raises ``ResolveError`` when the registry does not.
Resolver = Callable[[str], str]


class ResolveError(Exception):
    """A reference the registry did not resolve to a digest."""


@dataclass(frozen=True)
class PinTableFile:
    """One package's pin table on disk.

    Attributes:
        package: The package directory name (``datrix-codegen-docker``).
        path: The table file.
    """

    package: str
    path: Path

    def references(self) -> list[str]:
        """The table's references, validated by the loader every package reads it with."""
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return sorted(ImagePinTable.from_mapping(str(self.path), raw).digests)


def build_parser() -> argparse.ArgumentParser:
    """The options of ``dev/refresh-image-pins.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--package", default="",
                        help="Refresh only this package directory's table (datrix-codegen-docker); -Add extends it.")
    parser.add_argument("--add", action="append", default=[],
                        help="A '<name>:<tag>' reference to add to -Package's table. Repeatable or comma-separated.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: planted tables are rewritten, and each refusal fires.")
    parser.set_defaults(debug=False)
    return parser


def find_tables(workspace: Path) -> list[PinTableFile]:
    """Every ``datrix-*/src/*/image_pins.json`` under *workspace*, by package name."""
    return [
        PinTableFile(package=package_dir.name, path=path)
        for package_dir in workspace_package_dirs(workspace)
        for path in sorted((package_dir / "src").glob(f"*/{IMAGE_PIN_TABLE_FILE}"))
    ]


def _is_rate_limited(output: str) -> bool:
    return any(marker in output for marker in _RATE_LIMIT_MARKERS)


def _inspect_once(reference: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", reference, "--format", _INSPECT_FORMAT],
        capture_output=True, text=True, encoding="utf-8", timeout=_INSPECT_TIMEOUT_SECONDS, check=False,
    )


def registry_digest(reference: str) -> str:
    """The digest of *reference*'s multi-platform index, as its registry answers it.

    Raises:
        ResolveError: The registry did not resolve it (after the rate-limit retries).
    """
    for attempt in range(1, _RATE_LIMIT_ATTEMPTS + 1):
        result = _inspect_once(reference)
        output = f"{result.stdout}{result.stderr}".strip()
        if result.returncode == 0:
            return str(json.loads(result.stdout))
        if not _is_rate_limited(output) or attempt == _RATE_LIMIT_ATTEMPTS:
            raise ResolveError(f"{reference}: {output}")
        wait = _RATE_LIMIT_WAIT_SECONDS * attempt
        logger.warning("registry_rate_limited reference=%s attempt=%d wait_seconds=%d", reference, attempt, wait)
        time.sleep(wait)
    raise ResolveError(f"{reference}: not resolved after {_RATE_LIMIT_ATTEMPTS} attempts")


def _resolve_all(references: Sequence[str], resolve: Resolver) -> tuple[dict[str, str], list[str]]:
    """Each distinct reference's digest, and the failures (one line each)."""
    digests: dict[str, str] = {}
    failures: list[str] = []
    for reference in sorted(set(references)):
        try:
            digests[reference] = resolve(reference)
        except ResolveError as error:
            failures.append(str(error))
    return digests, failures


def _table_text(table: PinTableFile, digests: Mapping[str, str]) -> str:
    """The table's new text, validated by the package loader before anything is written."""
    entries = {reference: digests[reference] for reference in sorted(digests)}
    ImagePinTable.from_mapping(str(table.path), entries)
    return json.dumps(entries, indent=2) + "\n"


def _require_additions(tables: Sequence[PinTableFile], package: str, additions: Sequence[str]) -> None:
    if additions and not package:
        raise UsageError("-Add needs -Package: name the package directory whose table the reference joins.")
    if package and package not in {table.package for table in tables}:
        known = ", ".join(sorted(table.package for table in tables)) or "none"
        raise UsageError(f"-Package {package!r} ships no {IMAGE_PIN_TABLE_FILE} (packages with one: {known}).")
    malformed = [reference for reference in additions if TAGGED_IMAGE.fullmatch(reference) is None]
    if malformed:
        raise UsageError(f"-Add takes '<name>:<tag>' references, no digest; refused: {', '.join(malformed)}.")


def refresh(tables: Sequence[PinTableFile], *, package: str, additions: Sequence[str], resolve: Resolver) -> int:
    """Resolve the references of every table (only *package*'s when given, with *additions*) and rewrite
    them all; the exit code."""
    if not tables:
        raise UsageError(f"No {IMAGE_PIN_TABLE_FILE} was found under datrix-*/src/*/ in the workspace.")
    _require_additions(tables, package, additions)
    chosen = [table for table in tables if not package or table.package == package]
    wanted = {table: [*table.references(), *(additions if table.package == package else ())] for table in chosen}
    digests, failures = _resolve_all([reference for refs in wanted.values() for reference in refs], resolve)
    if failures:
        print("NOT REWRITTEN: these references did not resolve, so no table was written:")
        for failure in failures:
            print(f"  {failure}")
        return EXIT_VIOLATION
    try:
        texts = {table: _table_text(table, {ref: digests[ref] for ref in refs}) for table, refs in wanted.items()}
    except ConfigurationError as error:
        print(f"NOT REWRITTEN: the registry answered something that is not a digest: {error}")
        return EXIT_VIOLATION
    for table, text in texts.items():
        changed = table.path.read_text(encoding="utf-8") != text
        table.path.write_text(text, encoding="utf-8")
        print(f"{'UPDATED' if changed else 'unchanged'} {table.path} ({len(wanted[table])} references)")
    return EXIT_OK


_PLANTED_DIGEST: Final[str] = "sha256:" + "a" * 64
_PLANTED_OTHER: Final[str] = "sha256:" + "b" * 64


def _planted_resolver(answers: Mapping[str, str]) -> Resolver:
    def resolve(reference: str) -> str:
        if reference not in answers:
            raise ResolveError(f"{reference}: not found")
        return answers[reference]

    return resolve


def _planted_table(root: Path, package: str, entries: Mapping[str, str]) -> PinTableFile:
    path = root / package / "src" / package.replace("-", "_") / IMAGE_PIN_TABLE_FILE
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(dict(entries)), encoding="utf-8")
    return PinTableFile(package=package, path=path)


def _check_tables_are_rewritten_with_additions() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        table = _planted_table(Path(temporary), "datrix-planted", {"redis:7": _PLANTED_OTHER})
        resolve = _planted_resolver({"redis:7": _PLANTED_DIGEST, "alpine:3.22": _PLANTED_DIGEST})
        code = refresh([table], package="datrix-planted", additions=["alpine:3.22"], resolve=resolve)
        written = json.loads(table.path.read_text(encoding="utf-8"))
    assert code == EXIT_OK, f"a resolvable table must be rewritten with exit {EXIT_OK}; got {code}"
    assert written == {"alpine:3.22": _PLANTED_DIGEST, "redis:7": _PLANTED_DIGEST}, written


def _check_package_limits_the_run() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        chosen = _planted_table(root, "datrix-chosen", {"redis:7": _PLANTED_OTHER})
        other = _planted_table(root, "datrix-other", {"gone/image:1": _PLANTED_OTHER})
        resolve = _planted_resolver({"redis:7": _PLANTED_DIGEST})
        code = refresh([chosen, other], package="datrix-chosen", additions=[], resolve=resolve)
        written = json.loads(chosen.path.read_text(encoding="utf-8"))
    assert code == EXIT_OK, f"-Package must leave every other table out of the run; got exit {code}"
    assert written == {"redis:7": _PLANTED_DIGEST}, written


def _check_an_unresolved_reference_writes_nothing() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        good = _planted_table(root, "datrix-good", {"redis:7": _PLANTED_OTHER})
        bad = _planted_table(root, "datrix-bad", {"gone/image:1": _PLANTED_OTHER})
        code = refresh([good, bad], package="", additions=[], resolve=_planted_resolver({"redis:7": _PLANTED_DIGEST}))
        untouched = json.loads(good.path.read_text(encoding="utf-8"))
    assert code == EXIT_VIOLATION, f"an unresolved reference must exit {EXIT_VIOLATION}; got {code}"
    assert untouched == {"redis:7": _PLANTED_OTHER}, f"no table may be written when one fails; got {untouched}"


def _check_a_non_digest_answer_writes_nothing() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        table = _planted_table(Path(temporary), "datrix-planted", {"redis:7": _PLANTED_OTHER})
        code = refresh([table], package="", additions=[], resolve=_planted_resolver({"redis:7": "sha256:short"}))
        untouched = json.loads(table.path.read_text(encoding="utf-8"))
    assert code == EXIT_VIOLATION, f"a non-digest answer must exit {EXIT_VIOLATION}; got {code}"
    assert untouched == {"redis:7": _PLANTED_OTHER}, untouched


def _check_usage_refusals() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        table = _planted_table(Path(temporary), "datrix-planted", {"redis:7": _PLANTED_OTHER})
        resolve = _planted_resolver({})
        expect_usage_error(lambda: refresh([table], package="", additions=["a:1"], resolve=resolve), "-Add needs -Package")
        expect_usage_error(
            lambda: refresh([table], package="datrix-none", additions=[], resolve=resolve), "ships no image_pins.json"
        )
        expect_usage_error(
            lambda: refresh([table], package="datrix-planted", additions=[f"a:1@{_PLANTED_DIGEST}"], resolve=resolve),
            "no digest",
        )
    expect_usage_error(lambda: refresh([], package="", additions=[], resolve=resolve), "No image_pins.json")


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [
            _check_tables_are_rewritten_with_additions,
            _check_package_limits_the_run,
            _check_an_unresolved_reference_writes_nothing,
            _check_a_non_digest_answer_writes_nothing,
            _check_usage_refusals,
        ]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=DEV_SCRIPTS_DIR)
    return refresh(
        find_tables(WORKSPACE_DIR), package=args.package, additions=comma_values(args.add), resolve=registry_digest
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
