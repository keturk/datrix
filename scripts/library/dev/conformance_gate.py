#!/usr/bin/env python3
"""Declarative design-acceptance assertion runner over a file tree.

Replaces the recurring hand-rolled acceptance-check scripts in
``D:\\datrix\\.scripts`` (``a2_conformance_check.py``, ``gate_16_19_verify.py``,
the ``i5_*``/``prove_*`` families, ``task-31-03-acceptance-check.py``): a JSON
spec declares assertions over a target tree (generated output or package
src), the gate evaluates them and writes a per-assertion PASS/FAIL ledger.

Spec schema::

    {
      "target": "<dir>",                 // absolute, or relative to the spec file
      "negative_control": "<dir>|null",  // vacuity control for must_not_contain
      "assertions": [
        {"id": "...", "type": "...", "pattern": "...", "path": "...",
         "glob": "...", "expected_count": 0, "description": "..."}
      ]
    }

Assertion types:

* ``must_contain``     -- regex found in >= 1 text file matching ``glob``.
* ``must_not_contain`` -- regex found in NO text file matching ``glob``. When
  ``negative_control`` is set, the pattern MUST appear in the control tree or
  the assertion FAILS as VACUOUS (the ``a2_conformance_check.py`` rule: a grep
  for tokens no generator ever emits proves nothing).
* ``file_exists`` / ``file_absent`` -- ``path`` (exact, relative to target) or
  ``glob`` (>= 1 match / 0 matches).
* ``count_equals``     -- total regex occurrences across ``glob`` ==
  ``expected_count``.

Patterns are Python regexes. Only text files are scanned -- binaries are
skipped by a null-byte sniff of the first ``BINARY_SNIFF_BYTES`` bytes.

A built-in self-test (temp target + control trees proving EVERY assertion
type both detects a violation and passes a satisfied case, including the
vacuous-must_not_contain failure) runs as step 1 of every normal invocation,
like ``check-generated-file-ratchet.ps1`` -- a self-test failure aborts with
exit 2 before any real result is trusted.

Usage:
  python scripts/library/dev/conformance_gate.py --spec my-spec.json
  python scripts/library/dev/conformance_gate.py --self-test
  .\\scripts\\dev\\conformance-gate.ps1 my-spec.json
  .\\scripts\\dev\\conformance-gate.ps1 -SelfTest

Exit codes: 0 = all assertions pass, 1 = any assertion fails,
2 = usage error / bad spec (unknown assertion type is exit 2, never silently
skipped) / self-test failure.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import re
import sys
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Configure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add library directory to sys.path to import from shared
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.venv import get_datrix_root  # noqa: E402

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

TYPE_MUST_CONTAIN = "must_contain"
TYPE_MUST_NOT_CONTAIN = "must_not_contain"
TYPE_FILE_EXISTS = "file_exists"
TYPE_FILE_ABSENT = "file_absent"
TYPE_COUNT_EQUALS = "count_equals"
KNOWN_TYPES: frozenset[str] = frozenset(
    {
        TYPE_MUST_CONTAIN,
        TYPE_MUST_NOT_CONTAIN,
        TYPE_FILE_EXISTS,
        TYPE_FILE_ABSENT,
        TYPE_COUNT_EQUALS,
    }
)
#: Assertion types whose ``pattern`` field is mandatory.
PATTERN_TYPES: frozenset[str] = frozenset(
    {TYPE_MUST_CONTAIN, TYPE_MUST_NOT_CONTAIN, TYPE_COUNT_EQUALS}
)
#: Assertion types that take ``path`` or ``glob`` (at least one).
PATH_TYPES: frozenset[str] = frozenset({TYPE_FILE_EXISTS, TYPE_FILE_ABSENT})

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"

#: Default glob for pattern-scanning assertion types.
DEFAULT_GLOB = "**/*"
#: How many bytes to sniff for a null byte before treating a file as binary.
BINARY_SNIFF_BYTES = 8192
#: Ledger path cap: every entry records at most this many paths + the total.
PATH_CAP = 100

#: Ledger location (test-output artifact per the script conventions).
OUTPUT_SUBDIRS: tuple[str, ...] = (".test-output", "conformance")
LEDGER_SUFFIX = "-ledger.json"


class UsageError(Exception):
    """Bad usage or malformed spec; the script exits with code 2."""


@dataclass(frozen=True)
class Assertion:
    """One validated assertion from the spec."""

    id: str
    type: str
    description: str
    pattern: re.Pattern[str] | None
    pattern_text: str | None
    path: str | None
    glob: str


@dataclass(frozen=True)
class AssertionResult:
    """The evaluated outcome of one assertion."""

    id: str
    type: str
    description: str
    status: str
    detail: str
    paths: list[str]
    paths_total: int

    def to_json(self) -> dict[str, object]:
        """Serialize for the ledger payload."""
        return {
            "id": self.id,
            "type": self.type,
            "description": self.description,
            "status": self.status,
            "detail": self.detail,
            "paths": self.paths[:PATH_CAP],
            "paths_total": self.paths_total,
        }


@dataclass(frozen=True)
class Spec:
    """A validated conformance spec."""

    spec_path: Path
    target: Path
    negative_control: Path | None
    assertions: list[Assertion]


# ---------------------------------------------------------------------------
# Spec loading
# ---------------------------------------------------------------------------


def _require_str(raw: dict[str, object], key: str, context: str) -> str:
    """Fetch a required non-empty string field, failing loud.

    Args:
        raw: The JSON object.
        key: Required key.
        context: Human-readable location for the error message.

    Returns:
        The string value.

    Raises:
        UsageError: If the key is missing, not a string, or empty.
    """
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise UsageError(
            f"{context}: field {key!r} must be a non-empty string, got {value!r}. "
            f"Fix the spec file."
        )
    return value


def _compile_pattern(pattern_text: str, context: str) -> re.Pattern[str]:
    """Compile an assertion's regex, failing loud on a bad pattern.

    Args:
        pattern_text: The regex source from the spec.
        context: Human-readable location for the error message.

    Returns:
        The compiled pattern.

    Raises:
        UsageError: If the regex does not compile.
    """
    try:
        return re.compile(pattern_text)
    except re.error as exc:
        raise UsageError(
            f"{context}: pattern {pattern_text!r} is not a valid Python regex "
            f"({exc}). Fix the spec file."
        ) from exc


def build_assertion(raw: object, index: int) -> Assertion:
    """Validate and build one assertion from its raw JSON object.

    Args:
        raw: The raw JSON value at ``assertions[index]``.
        index: Position in the spec's assertion list (for error messages).

    Returns:
        The validated assertion.

    Raises:
        UsageError: On any malformed field, unknown type, or missing
            type-specific requirement. Unknown assertion types are ALWAYS a
            hard error (exit 2), never silently skipped.
    """
    context = f"assertions[{index}]"
    if not isinstance(raw, dict):
        raise UsageError(f"{context}: must be a JSON object, got {type(raw).__name__}.")
    assertion_id = _require_str(raw, "id", context)
    assertion_type = _require_str(raw, "type", context)
    description = _require_str(raw, "description", context)
    if assertion_type not in KNOWN_TYPES:
        raise UsageError(
            f"{context} (id={assertion_id!r}): unknown assertion type "
            f"{assertion_type!r}. Valid types: {sorted(KNOWN_TYPES)}. Unknown types "
            f"are a hard error -- they are never silently skipped."
        )

    pattern_raw = raw.get("pattern")
    path_raw = raw.get("path")
    glob_raw = raw.get("glob")
    pattern_text = pattern_raw if isinstance(pattern_raw, str) else None
    path_value = path_raw if isinstance(path_raw, str) else None
    glob_value = glob_raw if isinstance(glob_raw, str) else None

    if assertion_type in PATTERN_TYPES and pattern_text is None:
        raise UsageError(
            f"{context} (id={assertion_id!r}): type {assertion_type!r} requires a "
            f"'pattern' (regex) field."
        )
    if assertion_type in PATH_TYPES and path_value is None and glob_value is None:
        raise UsageError(
            f"{context} (id={assertion_id!r}): type {assertion_type!r} requires a "
            f"'path' (exact, relative to target) or a 'glob' field."
        )

    compiled = (
        _compile_pattern(pattern_text, f"{context} (id={assertion_id!r})")
        if pattern_text is not None
        else None
    )
    return Assertion(
        id=assertion_id,
        type=assertion_type,
        description=description,
        pattern=compiled,
        pattern_text=pattern_text,
        path=path_value,
        glob=glob_value if glob_value is not None else DEFAULT_GLOB,
    )


def _expected_count(raw: object, assertion_id: str) -> int:
    """Fetch and validate the ``expected_count`` field of a count assertion.

    Args:
        raw: The raw assertion JSON object.
        assertion_id: The assertion's id (for error messages).

    Returns:
        The expected count.

    Raises:
        UsageError: If the field is missing or not a non-negative integer.
    """
    if not isinstance(raw, dict):
        raise UsageError(f"Assertion {assertion_id!r}: not a JSON object.")
    value = raw.get("expected_count")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise UsageError(
            f"Assertion {assertion_id!r}: type '{TYPE_COUNT_EQUALS}' requires "
            f"'expected_count' as a non-negative integer, got {value!r}."
        )
    return value


def _resolve_dir(value: str, spec_path: Path, field: str) -> Path:
    """Resolve a spec directory field (absolute, or relative to the spec file).

    Args:
        value: The raw path string.
        spec_path: The spec file's own path.
        field: Field name for error messages.

    Returns:
        The resolved directory.

    Raises:
        UsageError: If the directory does not exist.
    """
    candidate = Path(value)
    resolved = candidate if candidate.is_absolute() else (spec_path.parent / candidate)
    resolved = resolved.resolve()
    if not resolved.is_dir():
        raise UsageError(
            f"Spec field {field!r}: directory {resolved} does not exist. Paths may "
            f"be absolute or relative to the spec file ({spec_path})."
        )
    return resolved


def load_spec(spec_path: Path) -> tuple[Spec, dict[str, int]]:
    """Load and fully validate a spec file.

    Args:
        spec_path: Path to the spec JSON.

    Returns:
        ``(spec, expected_counts)`` where ``expected_counts`` maps
        count_equals assertion ids to their expected values.

    Raises:
        UsageError: On a missing file, malformed JSON, or any invalid field.
    """
    if not spec_path.is_file():
        raise UsageError(f"Spec file not found: {spec_path}. Pass -Spec <spec.json>.")
    try:
        data = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UsageError(f"Spec file {spec_path} is not valid JSON: {exc}.") from exc
    if not isinstance(data, dict):
        raise UsageError(f"Spec file {spec_path} must contain a JSON object at top level.")

    target = _resolve_dir(_require_str(data, "target", "spec"), spec_path, "target")
    control_raw = data.get("negative_control")
    control: Path | None = None
    if control_raw is not None:
        if not isinstance(control_raw, str):
            raise UsageError(
                f"Spec field 'negative_control' must be a directory string or null, "
                f"got {control_raw!r}."
            )
        control = _resolve_dir(control_raw, spec_path, "negative_control")

    assertions_raw = data.get("assertions")
    if not isinstance(assertions_raw, list) or not assertions_raw:
        raise UsageError(
            f"Spec file {spec_path} must define a non-empty 'assertions' list."
        )

    assertions: list[Assertion] = []
    expected_counts: dict[str, int] = {}
    seen_ids: set[str] = set()
    for index, raw in enumerate(assertions_raw):
        assertion = build_assertion(raw, index)
        if assertion.id in seen_ids:
            raise UsageError(
                f"Duplicate assertion id {assertion.id!r} in {spec_path}. Every "
                f"assertion needs a unique id so the ledger is unambiguous."
            )
        seen_ids.add(assertion.id)
        if assertion.type == TYPE_COUNT_EQUALS:
            expected_counts[assertion.id] = _expected_count(raw, assertion.id)
        assertions.append(assertion)

    return Spec(spec_path, target, control, assertions), expected_counts


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def _iter_text_files(root: Path, glob: str) -> Iterator[tuple[str, str]]:
    """Yield ``(relative_posix_path, text)`` for text files matching *glob*.

    Binary files (null byte within the first :data:`BINARY_SNIFF_BYTES`
    bytes) are skipped. Content is decoded as UTF-8 with replacement so a
    stray invalid byte cannot crash a scan.

    Args:
        root: Tree root.
        glob: Glob pattern relative to *root*.
    """
    for path in sorted(root.glob(glob)):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if b"\x00" in raw[:BINARY_SNIFF_BYTES]:
            logger.debug("skip_binary path=%s", path)
            continue
        yield path.relative_to(root).as_posix(), raw.decode("utf-8", errors="replace")


def _matching_files(root: Path, assertion: Assertion) -> tuple[list[str], int]:
    """Files under *root* (matching the glob) whose text matches the pattern.

    Args:
        root: Tree root to scan.
        assertion: The assertion carrying the compiled pattern and glob.

    Returns:
        ``(matching_relative_paths, scanned_file_count)``.

    Raises:
        UsageError: If the assertion carries no compiled pattern (spec-load
            validation guarantees it does; this guards internal misuse).
    """
    if assertion.pattern is None:
        raise UsageError(
            f"Assertion {assertion.id!r}: internal error -- pattern-type assertion "
            f"without a compiled pattern."
        )
    matching: list[str] = []
    scanned = 0
    for rel, text in _iter_text_files(root, assertion.glob):
        scanned += 1
        if assertion.pattern.search(text):
            matching.append(rel)
    return matching, scanned


def _result(
    assertion: Assertion, status: str, detail: str, paths: list[str]
) -> AssertionResult:
    """Build an :class:`AssertionResult` for *assertion*.

    Args:
        assertion: The evaluated assertion.
        status: ``PASS`` or ``FAIL``.
        detail: Human-readable explanation.
        paths: Every violating/matching path (capped on serialization).
    """
    return AssertionResult(
        id=assertion.id,
        type=assertion.type,
        description=assertion.description,
        status=status,
        detail=detail,
        paths=paths,
        paths_total=len(paths),
    )


def _eval_must_contain(
    assertion: Assertion, target: Path, control: Path | None, expected: int | None
) -> AssertionResult:
    """Evaluate ``must_contain``: the pattern appears in >= 1 matching file."""
    matching, scanned = _matching_files(target, assertion)
    if matching:
        return _result(
            assertion, STATUS_PASS, f"pattern found in {len(matching)} file(s)", matching
        )
    return _result(
        assertion,
        STATUS_FAIL,
        f"pattern {assertion.pattern_text!r} not found in any of {scanned} text "
        f"file(s) matching glob {assertion.glob!r} under {target}",
        [],
    )


def _eval_must_not_contain(
    assertion: Assertion, target: Path, control: Path | None, expected: int | None
) -> AssertionResult:
    """Evaluate ``must_not_contain`` with the non-vacuity control rule."""
    violating, scanned = _matching_files(target, assertion)
    if violating:
        return _result(
            assertion,
            STATUS_FAIL,
            f"forbidden pattern {assertion.pattern_text!r} found in "
            f"{len(violating)} file(s)",
            violating,
        )
    if control is not None:
        control_hits, _ = _matching_files(control, assertion)
        if not control_hits:
            return _result(
                assertion,
                STATUS_FAIL,
                f"VACUOUS: pattern {assertion.pattern_text!r} is absent from the "
                f"negative-control tree {control} too, so this check would 'pass' "
                f"against anything and proves nothing. Point negative_control at a "
                f"tree that genuinely contains the pattern, or fix the pattern.",
                [],
            )
        return _result(
            assertion,
            STATUS_PASS,
            f"pattern absent from all {scanned} scanned file(s); non-vacuity proven "
            f"by {len(control_hits)} hit(s) in the negative-control tree",
            control_hits,
        )
    return _result(
        assertion,
        STATUS_PASS,
        f"pattern absent from all {scanned} scanned file(s) (no negative_control "
        f"configured -- vacuity not independently proven)",
        [],
    )


def _eval_file_exists(
    assertion: Assertion, target: Path, control: Path | None, expected: int | None
) -> AssertionResult:
    """Evaluate ``file_exists``: exact path exists, or the glob matches."""
    if assertion.path is not None:
        exists = (target / assertion.path).exists()
        if exists:
            return _result(assertion, STATUS_PASS, "path exists", [assertion.path])
        return _result(
            assertion, STATUS_FAIL, f"expected path {assertion.path!r} under {target}", []
        )
    matches = sorted(p.relative_to(target).as_posix() for p in target.glob(assertion.glob))
    if matches:
        return _result(
            assertion, STATUS_PASS, f"glob matched {len(matches)} path(s)", matches
        )
    return _result(
        assertion,
        STATUS_FAIL,
        f"glob {assertion.glob!r} matched nothing under {target}",
        [],
    )


def _eval_file_absent(
    assertion: Assertion, target: Path, control: Path | None, expected: int | None
) -> AssertionResult:
    """Evaluate ``file_absent``: exact path missing, or the glob matches nothing."""
    if assertion.path is not None:
        if (target / assertion.path).exists():
            return _result(
                assertion,
                STATUS_FAIL,
                f"path {assertion.path!r} exists under {target} but must be absent",
                [assertion.path],
            )
        return _result(assertion, STATUS_PASS, "path absent", [])
    matches = sorted(p.relative_to(target).as_posix() for p in target.glob(assertion.glob))
    if matches:
        return _result(
            assertion,
            STATUS_FAIL,
            f"glob {assertion.glob!r} matched {len(matches)} path(s) that must be absent",
            matches,
        )
    return _result(assertion, STATUS_PASS, "glob matched nothing", [])


def _eval_count_equals(
    assertion: Assertion, target: Path, control: Path | None, expected: int | None
) -> AssertionResult:
    """Evaluate ``count_equals``: total pattern occurrences == expected_count."""
    if assertion.pattern is None or expected is None:
        raise UsageError(
            f"Assertion {assertion.id!r}: internal error -- count_equals without a "
            f"compiled pattern or expected count."
        )
    per_file: list[str] = []
    total = 0
    for rel, text in _iter_text_files(target, assertion.glob):
        occurrences = len(assertion.pattern.findall(text))
        if occurrences:
            per_file.append(f"{rel}: {occurrences}")
            total += occurrences
    status = STATUS_PASS if total == expected else STATUS_FAIL
    return _result(
        assertion,
        status,
        f"{total} occurrence(s) of pattern {assertion.pattern_text!r} across glob "
        f"{assertion.glob!r} (expected {expected})",
        per_file,
    )


_HANDLERS: dict[
    str, Callable[[Assertion, Path, Path | None, int | None], AssertionResult]
] = {
    TYPE_MUST_CONTAIN: _eval_must_contain,
    TYPE_MUST_NOT_CONTAIN: _eval_must_not_contain,
    TYPE_FILE_EXISTS: _eval_file_exists,
    TYPE_FILE_ABSENT: _eval_file_absent,
    TYPE_COUNT_EQUALS: _eval_count_equals,
}


def evaluate_assertion(
    assertion: Assertion,
    target: Path,
    control: Path | None,
    expected_count: int | None,
) -> AssertionResult:
    """Evaluate one assertion against the target (and control) tree.

    Args:
        assertion: The validated assertion.
        target: Target tree root.
        control: Negative-control tree root (``must_not_contain`` vacuity).
        expected_count: Expected total for ``count_equals`` assertions.

    Returns:
        The evaluated result.
    """
    handler = _HANDLERS[assertion.type]
    return handler(assertion, target, control, expected_count)


# ---------------------------------------------------------------------------
# Self-test (non-vacuity of the gate itself)
# ---------------------------------------------------------------------------

_ST_FORBIDDEN = "FORBIDDEN_TOKEN"
_ST_CONTROL_ONLY = "CONTROL_ONLY_TOKEN"
_ST_NOWHERE = "NOWHERE_TOKEN"
_ST_BINARY_ONLY = "BINARY_ONLY_TOKEN"


@dataclass(frozen=True)
class SelfTestCase:
    """One self-test case: an assertion, its trees, and the expected status."""

    name: str
    raw: dict[str, object]
    use_control: bool
    expected_status: str


def _build_self_test_trees(root: Path) -> tuple[Path, Path]:
    """Materialize the self-test target and negative-control trees.

    Args:
        root: Temp directory to build under.

    Returns:
        ``(target, control)`` roots.
    """
    target = root / "target"
    control = root / "control"
    (target / "src").mkdir(parents=True)
    control.mkdir(parents=True)
    (target / "src" / "app.py").write_text("alpha alpha\n", encoding="utf-8")
    (target / "present.txt").write_text("present\n", encoding="utf-8")
    (target / "viol.py").write_text(f"{_ST_FORBIDDEN} = 1\n", encoding="utf-8")
    (target / "blob.dat").write_bytes(b"\x00" + _ST_BINARY_ONLY.encode("ascii") + b"\x00")
    (control / "control.py").write_text(
        f"{_ST_FORBIDDEN} = 0\n{_ST_CONTROL_ONLY} = 0\n{_ST_BINARY_ONLY} = 0\n",
        encoding="utf-8",
    )
    return target, control


def _self_test_cases() -> list[SelfTestCase]:
    """Every assertion type's detect-a-violation and pass-a-satisfied case."""

    def _case(
        name: str, expected: str, use_control: bool, **fields: object
    ) -> SelfTestCase:
        raw: dict[str, object] = {"id": name, "description": name}
        raw.update(fields)
        return SelfTestCase(name, raw, use_control, expected)

    return [
        _case("must_contain-hit", STATUS_PASS, False,
              type=TYPE_MUST_CONTAIN, pattern="alpha", glob="**/*.py"),
        _case("must_contain-miss", STATUS_FAIL, False,
              type=TYPE_MUST_CONTAIN, pattern="zeta_never_present"),
        _case("must_not_contain-violation", STATUS_FAIL, True,
              type=TYPE_MUST_NOT_CONTAIN, pattern=_ST_FORBIDDEN),
        _case("must_not_contain-clean-nonvacuous", STATUS_PASS, True,
              type=TYPE_MUST_NOT_CONTAIN, pattern=_ST_CONTROL_ONLY),
        _case("must_not_contain-vacuous-control-miss", STATUS_FAIL, True,
              type=TYPE_MUST_NOT_CONTAIN, pattern=_ST_NOWHERE),
        _case("must_not_contain-clean-no-control", STATUS_PASS, False,
              type=TYPE_MUST_NOT_CONTAIN, pattern=_ST_NOWHERE),
        _case("must_not_contain-binary-skipped", STATUS_PASS, True,
              type=TYPE_MUST_NOT_CONTAIN, pattern=_ST_BINARY_ONLY),
        _case("file_exists-present", STATUS_PASS, False,
              type=TYPE_FILE_EXISTS, path="present.txt"),
        _case("file_exists-missing", STATUS_FAIL, False,
              type=TYPE_FILE_EXISTS, path="missing.txt"),
        _case("file_exists-glob", STATUS_PASS, False,
              type=TYPE_FILE_EXISTS, glob="**/*.dat"),
        _case("file_absent-ok", STATUS_PASS, False,
              type=TYPE_FILE_ABSENT, path="missing.txt"),
        _case("file_absent-violated", STATUS_FAIL, False,
              type=TYPE_FILE_ABSENT, path="present.txt"),
        _case("count_equals-exact", STATUS_PASS, False,
              type=TYPE_COUNT_EQUALS, pattern="alpha", glob="**/*.py", expected_count=2),
        _case("count_equals-mismatch", STATUS_FAIL, False,
              type=TYPE_COUNT_EQUALS, pattern="alpha", glob="**/*.py", expected_count=3),
    ]


def _rejection_checks() -> list[str]:
    """Prove malformed specs are rejected loudly (exit-2 path), not skipped.

    Returns:
        Problem descriptions; empty when every rejection fires.
    """
    problems: list[str] = []
    rejects: list[tuple[str, dict[str, object]]] = [
        ("unknown-type-rejected",
         {"id": "x", "type": "grep_maybe", "description": "d"}),
        ("bad-regex-rejected",
         {"id": "x", "type": TYPE_MUST_CONTAIN, "description": "d", "pattern": "("}),
        ("missing-pattern-rejected",
         {"id": "x", "type": TYPE_MUST_CONTAIN, "description": "d"}),
        ("missing-path-and-glob-rejected",
         {"id": "x", "type": TYPE_FILE_EXISTS, "description": "d"}),
    ]
    for name, raw in rejects:
        try:
            build_assertion(raw, 0)
        except UsageError:
            continue
        problems.append(f"{name}: expected UsageError, but the assertion was accepted")
    return problems


def run_self_test(verbose: bool) -> list[str]:
    """Prove every assertion type both detects a violation and passes.

    Builds a temp target + negative-control tree, runs every
    :func:`_self_test_cases` case through the REAL evaluator, and checks the
    spec-rejection paths. A gate that cannot fail is worse than no gate.

    Args:
        verbose: Print one ``[OK]``/``[FAIL]`` line per check.

    Returns:
        Problem descriptions; empty means the gate is sound.
    """
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        target, control = _build_self_test_trees(Path(tmp))
        for case in _self_test_cases():
            assertion = build_assertion(case.raw, 0)
            expected = (
                _expected_count(case.raw, assertion.id)
                if assertion.type == TYPE_COUNT_EQUALS
                else None
            )
            result = evaluate_assertion(
                assertion, target, control if case.use_control else None, expected
            )
            ok = result.status == case.expected_status
            if verbose:
                print(f"  [{'OK' if ok else 'FAIL'}] {case.name}")
            if not ok:
                problems.append(
                    f"{case.name}: expected {case.expected_status}, got "
                    f"{result.status} ({result.detail})"
                )
    rejection_problems = _rejection_checks()
    if verbose:
        for name in ("unknown-type-rejected", "bad-regex-rejected",
                     "missing-pattern-rejected", "missing-path-and-glob-rejected"):
            failed = any(p.startswith(name) for p in rejection_problems)
            print(f"  [{'FAIL' if failed else 'OK'}] {name}")
    problems.extend(rejection_problems)
    return problems


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def run_spec(spec_path: Path, output_override: str | None) -> int:
    """Evaluate a spec and write its ledger.

    Args:
        spec_path: The spec JSON path.
        output_override: Optional ledger path override.

    Returns:
        Process exit code (0 all pass, 1 any fail).

    Raises:
        UsageError: On a malformed spec.
    """
    spec, expected_counts = load_spec(spec_path)
    results = [
        evaluate_assertion(
            assertion, spec.target, spec.negative_control,
            expected_counts.get(assertion.id),
        )
        for assertion in spec.assertions
    ]

    passed = sum(1 for r in results if r.status == STATUS_PASS)
    overall = STATUS_PASS if passed == len(results) else STATUS_FAIL

    ledger_path = (
        Path(output_override).resolve()
        if output_override
        else get_datrix_root().joinpath(*OUTPUT_SUBDIRS)
        / f"{spec_path.stem}{LEDGER_SUFFIX}"
    )
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "spec_path": str(spec_path.resolve()),
        "target": str(spec.target),
        "negative_control": str(spec.negative_control) if spec.negative_control else None,
        "self_test": STATUS_PASS,
        "results": [r.to_json() for r in results],
        "passed": passed,
        "failed": len(results) - passed,
        "overall": overall,
    }
    ledger_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    for result in results:
        print(f"[{result.status}] {result.id}: {result.description}")
    print(f"CONFORMANCE: {overall} ({passed}/{len(results)})")
    print(f"Details: {ledger_path}")
    return EXIT_PASS if overall == STATUS_PASS else EXIT_FAIL


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments.

    Args:
        argv: Argument list (without the program name).

    Returns:
        Parsed namespace.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Declarative design-acceptance assertion runner: evaluates a JSON spec "
            "of must_contain/must_not_contain/file_exists/file_absent/count_equals "
            "assertions over a tree and writes a per-assertion PASS/FAIL ledger. "
            "A built-in self-test runs first on every invocation."
        ),
    )
    parser.add_argument(
        "--spec", default=None, help="Path to the conformance spec JSON."
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the built-in self-test (every assertion type must detect a "
        "violation and pass a satisfied case) and exit.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Override the ledger path (default: "
        "<workspace>/.test-output/conformance/<spec-stem>-ledger.json).",
    )
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Returns:
        Process exit code: 0 = all assertions pass (or standalone self-test
        passes), 1 = any assertion fails, 2 = usage/bad-spec/self-test error.
    """
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    if args.self_test:
        print("conformance-gate self-test:")
        problems = run_self_test(verbose=True)
        if problems:
            print(f"SELF-TEST FAILED ({len(problems)} problem(s)):")
            for problem in problems:
                print(f"  {problem}")
            return EXIT_USAGE
        print("SELF-TEST PASSED (every assertion type detects and passes)")
        return EXIT_PASS

    if not args.spec:
        print(
            "ERROR: pass -Spec <spec.json> (or -SelfTest to run only the built-in "
            "self-test).",
            file=sys.stderr,
        )
        return EXIT_USAGE

    # Step 1 of every normal invocation: the gate proves its own teeth first.
    problems = run_self_test(verbose=False)
    if problems:
        print(f"SELF-TEST FAILED ({len(problems)} problem(s)) -- aborting before the spec:")
        for problem in problems:
            print(f"  {problem}")
        return EXIT_USAGE

    try:
        return run_spec(Path(args.spec), args.output)
    except UsageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
