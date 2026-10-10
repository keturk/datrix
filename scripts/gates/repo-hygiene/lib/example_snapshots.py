"""Committed example-snapshot gate.

An example may carry ``generated/<language>-<platform>/`` snapshots of its own
output. Nothing compares a snapshot with the generator, so without a standing
check they rot: a tree for a language nobody can generate any more drifts with
every framework change, and a framework module that was moved keeps being
imported by the committed copy.

Two checks, both derived from what is registered and what resolves -- never
from a hand-written inventory:

  - Snapshot identity. Every directory directly under any
    ``datrix/examples/**/generated/`` is named ``<language>-<platform>`` with
    ``<language>`` a registered ``datrix.languages`` name and ``<platform>`` a
    registered ``datrix.platforms`` name. Platform names contain hyphens
    (``azure-vm``), so the name is parsed by matching a registered language
    prefix and then testing the remainder against the platform set. For each
    example and each platform it carries, the snapshot languages must equal the
    registered language set. Fewer than two registered languages is a usage
    error (exit 2): with one language the equality is vacuous.
  - Framework references resolve. Every dotted ``datrix_*`` reference in (a)
    every text file of every snapshot and (b) every ``.j2`` template under
    every ``datrix-*/src`` is resolved by the shared
    ``datrix_scripts.framework_references`` resolver: the longest prefix
    ``importlib.util.find_spec`` finds is imported and the remaining segments
    resolve as members. The check reads text, so it is language- and
    platform-agnostic: it catches a Python import, a comment and a Java doc
    comment alike.

The gate does not regenerate and diff -- that is a whole-system generation per
language per run. ``refresh-example-snapshot.ps1`` makes regeneration one
command.

Built-in non-vacuity self-test, every invocation: a fixture ``generated/``
tree with an unregistered language, a fixture missing one registered language,
a planted reference to a removed module, a planted reference to a missing
attribute, and the passing counterparts of each must all be classified
correctly before the live comparison is trusted. The live run must also find at
least one snapshot and at least one template reference.

Usage:
    python example_snapshots.py
    python example_snapshots.py --debug
    python example_snapshots.py --self-test
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.framework_references import FRAMEWORK_REFERENCE, ReferenceResolver
from datrix_scripts.paths import SHOWCASE_DIR, WORKSPACE_DIR
from datrix_scripts.registered_targets import (
    registered_language_names,
    registered_platform_names,
)

logger = logging.getLogger(__name__)

DATRIX_DIR: Path = SHOWCASE_DIR
WORKSPACE_ROOT: Path = WORKSPACE_DIR
EXAMPLES_ROOT: Path = DATRIX_DIR / "examples"
SCRATCH_ROOT: Path = WORKSPACE_ROOT / ".tmp"

EXIT_OK: Final = 0
EXIT_FAIL: Final = 1
EXIT_USAGE: Final = 2

#: Directory name that holds an example's committed snapshots.
SNAPSHOT_CONTAINER_NAME: Final = "generated"
#: Fewer registered languages than this makes the language-set equality vacuous.
MIN_REGISTERED_LANGUAGES: Final = 2
TEMPLATE_SUFFIX: Final = ".j2"
REFRESH_COMMAND: Final = (
    "powershell -File d:/datrix/datrix/scripts/generation/refresh-example-snapshot.ps1 "
    "-Source <example>/system.dtrx -Language <language>"
)

#: A name the file itself binds with ``import ... as <name>`` (Dart import
#: prefixes, Python and TypeScript aliases). A reference rooted at such a name
#: is a use of the file's own binding, not a framework module.
LOCAL_ALIAS_BINDING: Final = re.compile(r"\bas\s+(datrix_[a-z0-9_]+)\b")

# Fixture content for the self-test (names are neutral; resolution is live).
_SELF_TEST_UNREGISTERED_LANGUAGE: Final = "cobol"
_REMOVED_MODULE_REFERENCE: Final = "datrix_common.migration.live_snapshot_export"
_MOVED_MODULE_REFERENCE: Final = "datrix_migration.live_snapshot_export"
_EXISTING_ATTRIBUTE_REFERENCE: Final = "datrix_common.utils.text.to_snake_case"
_MISSING_ATTRIBUTE_REFERENCE: Final = "datrix_common.utils.text.no_such_function_here"
_ALIAS_NAME: Final = "datrix_alias_fixture"


# ---------------------------------------------------------------------------
# Snapshot identity
# ---------------------------------------------------------------------------


def parse_snapshot_name(
    name: str, languages: Iterable[str], platforms: Iterable[str]
) -> tuple[str, str] | None:
    """Split ``<language>-<platform>`` against the registered sets.

    A registered language prefix is matched first (longest first, so a
    hyphenated language name is never shadowed by a shorter one), then the
    remainder is tested against the platform set, because platform names carry
    hyphens themselves.

    Returns:
        ``(language, platform)``, or ``None`` when no registered pair spells *name*.
    """
    platform_set = frozenset(platforms)
    for language in sorted(languages, key=len, reverse=True):
        prefix = f"{language}-"
        if name.startswith(prefix) and name[len(prefix) :] in platform_set:
            return language, name[len(prefix) :]
    return None


def compute_identity_violations(
    snapshots: Mapping[Path, Sequence[str]],
    languages: frozenset[str],
    platforms: frozenset[str],
) -> list[str]:
    """Compare every ``generated/`` directory with the registered targets.

    Args:
        snapshots: ``generated/`` directory -> names of the directories directly under it.
        languages: Registered ``datrix.languages`` names.
        platforms: Registered ``datrix.platforms`` names.

    Returns:
        One message per violation; empty when every snapshot is registered and
        every example carries one snapshot per registered language per platform.
    """
    violations: list[str] = []
    installed = (
        f"registered languages {sorted(languages)}, registered platforms {sorted(platforms)}"
    )
    for container, names in sorted(snapshots.items()):
        languages_by_platform: dict[str, set[str]] = {}
        for name in sorted(names):
            parsed = parse_snapshot_name(name, languages, platforms)
            if parsed is None:
                violations.append(
                    f"{container / name}: '{name}' is not '<language>-<platform>' over "
                    f"{installed}. Fix: delete the directory (a snapshot nobody can "
                    f"regenerate is stale output), or refresh a registered pair with: "
                    f"{REFRESH_COMMAND}"
                )
                continue
            language, platform = parsed
            languages_by_platform.setdefault(platform, set()).add(language)
        for platform, present in sorted(languages_by_platform.items()):
            missing = sorted(languages - present)
            if missing:
                violations.append(
                    f"{container}: platform '{platform}' carries snapshots for "
                    f"{sorted(present)} but not for registered language(s) {missing} "
                    f"({installed}). Fix: {REFRESH_COMMAND}"
                )
    return violations


def find_snapshot_containers(examples_root: Path) -> dict[Path, list[str]]:
    """Every ``generated/`` directory under *examples_root* with the directories directly under it."""
    containers: dict[Path, list[str]] = {}
    for dirpath, dirnames, _filenames in os.walk(examples_root):
        if SNAPSHOT_CONTAINER_NAME not in dirnames:
            continue
        dirnames.remove(SNAPSHOT_CONTAINER_NAME)
        container = Path(dirpath) / SNAPSHOT_CONTAINER_NAME
        containers[container] = sorted(
            entry.name for entry in container.iterdir() if entry.is_dir()
        )
    return containers


# ---------------------------------------------------------------------------
# Framework references
# ---------------------------------------------------------------------------


def scan_text(
    text: str, source: str, resolver: ReferenceResolver
) -> tuple[int, list[str]]:
    """Resolve every framework reference in *text*.

    Returns:
        ``(references_seen, violations)``; each violation names ``source:line`` and the reference.
    """
    seen = 0
    violations: list[str] = []
    local_bindings = frozenset(LOCAL_ALIAS_BINDING.findall(text))
    for line_number, line in enumerate(text.splitlines(), start=1):
        for match in FRAMEWORK_REFERENCE.finditer(line):
            if match.group(0).split(".", 1)[0] in local_bindings:
                continue
            seen += 1
            reason = resolver.unresolved_reason(match.group(0))
            if reason is not None:
                violations.append(
                    f"{source}:{line_number}: unresolved framework reference "
                    f"'{match.group(0)}' ({reason}). Fix: point it at the module that "
                    f"defines the name now, or regenerate the snapshot."
                )
    return seen, violations


def read_text_file(path: Path) -> str | None:
    """Return the file's text, or ``None`` for a binary (NUL-bearing or non-UTF-8) file."""
    data = path.read_bytes()
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def scan_files(paths: Iterable[Path], resolver: ReferenceResolver) -> tuple[int, list[str]]:
    """Resolve the framework references of every text file in *paths*."""
    seen = 0
    violations: list[str] = []
    for path in paths:
        text = read_text_file(path)
        if text is None:
            continue
        file_seen, file_violations = scan_text(text, str(path), resolver)
        seen += file_seen
        violations.extend(file_violations)
    return seen, violations


def snapshot_files(containers: Iterable[Path]) -> list[Path]:
    """Every file of every snapshot directory under the given ``generated/`` containers."""
    files: list[Path] = []
    for container in containers:
        for entry in sorted(container.iterdir()):
            if entry.is_dir():
                files.extend(sorted(p for p in entry.rglob("*") if p.is_file()))
    return files


def template_files(workspace_root: Path) -> list[Path]:
    """Every ``.j2`` template under every ``datrix-*/src`` tree."""
    return sorted(workspace_root.glob(f"datrix-*/src/**/*{TEMPLATE_SUFFIX}"))


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def _self_test_identity(
    languages: frozenset[str], platforms: frozenset[str], failures: list[str]
) -> None:
    ordered = sorted(languages)
    platform = sorted(platforms)[0]
    container = Path("fixture") / SNAPSHOT_CONTAINER_NAME
    clean = {container: [f"{language}-{platform}" for language in ordered]}
    _expect(
        compute_identity_violations(clean, languages, platforms) == [],
        "a snapshot set covering every registered language was reported as a violation",
        failures,
    )
    planted = {
        container: [*clean[container], f"{_SELF_TEST_UNREGISTERED_LANGUAGE}-{platform}"]
    }
    planted_violations = compute_identity_violations(planted, languages, platforms)
    _expect(
        len(planted_violations) == 1
        and f"{_SELF_TEST_UNREGISTERED_LANGUAGE}-{platform}" in planted_violations[0],
        f"a planted '{_SELF_TEST_UNREGISTERED_LANGUAGE}-{platform}' was not reported: "
        f"{planted_violations}",
        failures,
    )
    dropped = ordered[0]
    missing = {container: clean[container][1:]}
    missing_violations = compute_identity_violations(missing, languages, platforms)
    _expect(
        len(missing_violations) == 1 and dropped in missing_violations[0],
        f"a snapshot set missing '{dropped}' was not reported naming it: {missing_violations}",
        failures,
    )
    hyphenated = [name for name in sorted(platforms) if "-" in name]
    for name in hyphenated:
        _expect(
            parse_snapshot_name(f"{ordered[0]}-{name}", languages, platforms)
            == (ordered[0], name),
            f"hyphenated platform '{name}' was not parsed",
            failures,
        )


def _self_test_references(failures: list[str]) -> None:
    resolver = ReferenceResolver()
    fixture_text = "\n".join(
        [
            f"from {_REMOVED_MODULE_REFERENCE} import export",
            f"from {_MOVED_MODULE_REFERENCE} import export",
            f"# {_EXISTING_ATTRIBUTE_REFERENCE}",
            f"# {_MISSING_ATTRIBUTE_REFERENCE}",
        ]
    )
    with tempfile.TemporaryDirectory(dir=_scratch_root()) as scratch:
        fixture = Path(scratch) / "planted.txt"
        fixture.write_text(fixture_text, encoding="utf-8")
        seen, violations = scan_files([fixture], resolver)
    _expect(seen == 4, f"planted fixture should contain 4 references, saw {seen}", failures)
    flagged = {
        reference
        for reference in (
            _REMOVED_MODULE_REFERENCE,
            _MOVED_MODULE_REFERENCE,
            _EXISTING_ATTRIBUTE_REFERENCE,
            _MISSING_ATTRIBUTE_REFERENCE,
        )
        if any(f"'{reference}'" in violation for violation in violations)
    }
    expected = {_REMOVED_MODULE_REFERENCE, _MISSING_ATTRIBUTE_REFERENCE}
    _expect(
        flagged == expected,
        f"reference matcher flagged {sorted(flagged)}, expected exactly {sorted(expected)}",
        failures,
    )
    bound = f"import 'x.dart' as {_ALIAS_NAME};\nuse({_ALIAS_NAME}.Thing);"
    bound_seen, bound_violations = scan_text(bound, "bound.dart", resolver)
    _expect(
        bound_seen == 0 and not bound_violations,
        f"a reference rooted at a file-local import alias was checked: {bound_violations}",
        failures,
    )
    _, unbound_violations = scan_text(f"use({_ALIAS_NAME}.Thing);", "unbound.dart", resolver)
    _expect(
        len(unbound_violations) == 1,
        f"the alias exemption leaked into a file that does not bind '{_ALIAS_NAME}'",
        failures,
    )


def _scratch_root() -> Path:
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    return SCRATCH_ROOT


def run_self_test(languages: frozenset[str], platforms: frozenset[str]) -> list[str]:
    """Prove both checks detect what they claim to; returns the failures (empty = sound)."""
    failures: list[str] = []
    _self_test_identity(languages, platforms, failures)
    _self_test_references(failures)
    return failures


# ---------------------------------------------------------------------------
# Live run
# ---------------------------------------------------------------------------


def run_live(languages: frozenset[str], platforms: frozenset[str]) -> int:
    """Run both checks against the real tree; returns the exit code."""
    containers = find_snapshot_containers(EXAMPLES_ROOT)
    snapshot_count = sum(len(names) for names in containers.values())
    if snapshot_count == 0:
        print(
            f"ERROR: no snapshot directory found under {EXAMPLES_ROOT} -- a gate that "
            f"inspects nothing proves nothing."
        )
        return EXIT_USAGE

    resolver = ReferenceResolver()
    violations = compute_identity_violations(containers, languages, platforms)
    snapshot_seen, snapshot_violations = scan_files(snapshot_files(containers), resolver)
    template_seen, template_violations = scan_files(
        template_files(WORKSPACE_ROOT), resolver
    )
    if template_seen == 0:
        print(
            f"ERROR: no framework reference found in any template under "
            f"{WORKSPACE_ROOT}\\datrix-*\\src -- the reference matcher is vacuous."
        )
        return EXIT_USAGE
    violations.extend(snapshot_violations)
    violations.extend(template_violations)

    print(
        f"Example snapshots: {snapshot_count} snapshot(s) in {len(containers)} example(s); "
        f"{snapshot_seen} snapshot reference(s), {template_seen} template reference(s) "
        f"resolved against {sorted(languages)} x {sorted(platforms)}"
    )
    for violation in violations:
        print(f"VIOLATION: {violation}")
    if violations:
        print(f"Example-snapshot gate FAILED: {len(violations)} violation(s)")
        return EXIT_FAIL
    return EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging")
    parser.add_argument(
        "--self-test", action="store_true", help="Run only the non-vacuity self-test"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    languages = registered_language_names()
    platforms = registered_platform_names()
    if len(languages) < MIN_REGISTERED_LANGUAGES:
        print(
            f"ERROR: {len(languages)} registered language(s) {sorted(languages)}; the gate "
            f"needs at least {MIN_REGISTERED_LANGUAGES} for the per-language snapshot "
            f"equality to mean anything. Fix: install the missing datrix-codegen-<language> "
            f"package(s) into D:\\datrix\\.venv."
        )
        return EXIT_USAGE

    failures = run_self_test(languages, platforms)
    if failures:
        for failure in failures:
            print(f"SELF-TEST FAILURE: {failure}")
        return EXIT_USAGE
    print("Self-test passed")
    if args.self_test:
        return EXIT_OK
    return run_live(languages, platforms)


if __name__ == "__main__":
    sys.exit(main())
