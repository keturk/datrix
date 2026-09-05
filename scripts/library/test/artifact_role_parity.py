"""Cross-language artifact-role parity gate (D7): the G-A closure.

Detects a language silently emitting nothing for a construct another
language realizes, WITHOUT GENERATING ANYTHING -- it reads the blessed
baseline manifests that reference-example-parity-gate.ps1 already writes
under datrix/scripts/config/parity-baselines/<example_id>/<language>.sha256.

For every example with >= 2 blessed language baselines:
  1. Load each blessed language's manifest (a path list, ignoring hashes).
  2. Classify each path by domain ROLE using that language's OWN derived
     DomainDeclaration.structural_pattern set (derive_domain_declarations
     over the plugin's own registered specs -- the same fnmatch globs the
     domain self-consistency gate uses). A path matching no pattern goes to
     an "unclassified" bucket, reported but never compared (template-level
     naming differs by design across languages; the ROLE set is the
     contract, not the literal path shape).
  3. The set of roles with >= 1 matching path must be IDENTICAL across the
     example's blessed languages, EXCLUDING two kinds of non-drift:
       a. any domain the "missing" language declares globally `unsupported`
          in its own DomainDeclaration -- a declared absence explained once,
          at the language level, never a per-example fact, so the
          domain-parity gates already report it and this gate skips it
          rather than demanding an exemption entry for every example it
          would otherwise recur on; and
       b. any domain the "missing" language declares `supported` whose
          structural_pattern nonetheless matches ZERO files across that
          language's ENTIRE blessed footprint (every example, not just the
          one being compared) -- an EMPIRICAL corpus-wide fact derived from
          the same manifests this gate already reads (never DSL source):
          the domain's triggering construct simply never occurs anywhere in
          the corpus for this language, so a single-example "missing"
          verdict against it carries no information either. That skip is
          silent no longer: every corpus-vacuous (language, domain) must
          carry a typed, counted record in corpus-vacuity-records.json
          saying WHY nothing exercises it, and the gate fails both on an
          unrecorded pair and on a record whose pair is no longer vacuous
          (see check_corpus_vacuity_records). A generator no reference
          example reaches has no end-to-end signal at all -- silence about
          which of those generators CANNOT be reached and which merely ARE
          NOT is the state this file's records end.
     A difference over a domain the language declares `supported` AND
     realizes somewhere else in its own blessed footprint (this specific
     example's blessed manifest just has no matching file, while another
     blessed language's does) must carry an entry in
     artifact-role-exemptions.json (coordinates + reason, pinned count) --
     `load_exemptions` itself refuses an entry naming a domain its language
     declares `unsupported`, since the gate never consults the exemption
     file for those in the first place.

Relationship to the byte gate: replaces nothing. reference-example-parity-gate.ps1
still pins CONTENT per (example, language) pair; this gate pins PRESENCE
across languages. Its coverage grows automatically as later phases bless
more of the (example, language) matrix -- no code change needed here when
that happens.

Built-in non-vacuity self-test, every invocation: proves compare_role_sets
detects a forced mismatch and does not false-positive a matching pair, and
proves classify_paths correctly buckets a synthetic manifest against
synthetic declarations (including the unclassified bucket). Refuses to pass
vacuously: zero examples with >= 2 blessed languages is exit 2, never a
silent 0-example pass.

Usage:
    python artifact_role_parity.py
    python artifact_role_parity.py --debug
    python artifact_role_parity.py --self-test
    python artifact_role_parity.py --census
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import logging
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, cast

from datrix_codegen_common.parity.derived_declarations import DerivationError
from datrix_codegen_common.parity.domain_declaration import (
    DomainDeclaration,
    DomainDeclarations,
)

# Add scripts/library to sys.path to import shared.registered_targets --
# mirrors reference_example_parity.py's own shim (this file lives at
# library/test/, shared/ lives at the sibling library/shared/).
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.registered_targets import registered_language_names  # noqa: E402

logger = logging.getLogger(__name__)

# This file: datrix/scripts/library/test/artifact_role_parity.py
# parents[3] -> datrix/ ; parents[4] -> the monorepo root. Mirrors
# reference_example_parity.py's own identical-depth path math.
_HERE = Path(__file__).resolve()
DATRIX_DIR: Path = _HERE.parents[3]

BASELINES_ROOT: Path = DATRIX_DIR / "scripts" / "config" / "parity-baselines"
EXEMPTIONS_PATH: Path = DATRIX_DIR / "scripts" / "config" / "artifact-role-exemptions.json"
CORPUS_VACUITY_RECORDS_PATH: Path = (
    DATRIX_DIR / "scripts" / "config" / "corpus-vacuity-records.json"
)

_MIN_LANGUAGES_FOR_COMPARISON: Final[int] = 2
_MANIFEST_SEP = "  "  # matches reference_example_parity.py's _SEP

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

_SELF_TEST_LANGUAGE_A: Final[str] = "self_test_lang_a"
_SELF_TEST_LANGUAGE_B: Final[str] = "self_test_lang_b"
_SELF_TEST_DOMAIN_SHARED: Final[str] = "self_test_order"
_SELF_TEST_DOMAIN_FORCED_GAP: Final[str] = "self_test_shipment"

#: A corpus-vacuity record's `status`: NO reference example can produce a file
#: matching this pattern, whatever it declares and whatever it targets, because
#: something outside the example's control gates the emission (the blessing
#: pipeline's own configuration, a realization the language deliberately routes
#: to a different file family). Adding an example is never the remedy; the
#: record's `reason` names what the remedy actually is.
VACUITY_UNREACHABLE: Final[str] = "unreachable-by-design"

#: A corpus-vacuity record's `status`: reachable ONLY by an example whose
#: deployment profile resolves to a cloud provider. Every reference example
#: resolves `provider = "local"`, so this is not a DSL block an example is
#: missing -- it is the corpus having no cloud-targeting example at all, which
#: swaps that example's ENTIRE infrastructure output and is a materially larger
#: decision than adding a block.
VACUITY_CLOUD_ONLY: Final[str] = "cloud-platform-only"

#: A corpus-vacuity record's `status`: reachable under the corpus's own
#: local/docker shape -- nothing structural stands between a reference example
#: and this output -- and no example declares the triggering construct.
#: Ordinary corpus-coverage debt: the remedy is one DSL addition to an existing
#: example, and the record is deleted when one lands.
VACUITY_UNEXERCISED: Final[str] = "unexercised"

_VACUITY_STATUSES: Final[frozenset[str]] = frozenset(
    {VACUITY_UNREACHABLE, VACUITY_CLOUD_ONLY, VACUITY_UNEXERCISED}
)


@dataclass(frozen=True)
class ExemptionEntry:
    """One reviewed hole in artifact-role-exemptions.json."""

    example: str
    domain: str
    language: str
    reason: str


@dataclass(frozen=True)
class CorpusVacuityRecord:
    """One reviewed (language, domain) corpus-vacuity record.

    Attributes:
        language: A registered `datrix.languages` entry-point name.
        domain: A domain id that language declares `supported`.
        status: One of `VACUITY_UNREACHABLE`, `VACUITY_CLOUD_ONLY`,
            `VACUITY_UNEXERCISED` -- never interchangeable, since each carries
            a different remedy (see each constant's own docstring).
        reason: The concrete structural fact, with the coordinates that prove
            it. Used verbatim in this gate's error messages.
    """

    language: str
    domain: str
    status: str
    reason: str


# ---------------------------------------------------------------------------
# Baseline discovery + manifest reading
# ---------------------------------------------------------------------------


def blessed_language_baselines(example_id: str) -> dict[str, Path]:
    """Return {language: baseline_path} for every REGISTERED language that has
    a blessed .sha256 manifest for *example_id*.

    Args:
        example_id: An example id as used by parity-baselines/ directory names
            (kebab-joined path segments, e.g. "01-foundation").

    Returns:
        Mapping of registered language name -> its baseline file, for
        languages that actually have one blessed. Never raises for a missing
        manifest -- an unblessed language for this example is simply absent.
    """
    example_dir = BASELINES_ROOT / example_id
    if not example_dir.is_dir():
        return {}
    found: dict[str, Path] = {}
    for language in sorted(registered_language_names()):
        candidate = example_dir / f"{language}.sha256"
        if candidate.is_file():
            found[language] = candidate
    return found


def discover_multi_language_examples() -> dict[str, dict[str, Path]]:
    """Every example id under BASELINES_ROOT with >= 2 blessed language baselines.

    Returns:
        {example_id: {language: baseline_path}}, only for examples meeting
        the >= 2 threshold. Sorted by example id for deterministic output.
    """
    result: dict[str, dict[str, Path]] = {}
    if not BASELINES_ROOT.is_dir():
        return result
    for example_dir in sorted(p for p in BASELINES_ROOT.iterdir() if p.is_dir()):
        languages = blessed_language_baselines(example_dir.name)
        if len(languages) >= _MIN_LANGUAGES_FOR_COMPARISON:
            result[example_dir.name] = languages
    return result


def manifest_paths(baseline_path: Path) -> list[str]:
    """The relative-path column of one blessed .sha256 manifest (hashes ignored).

    Args:
        baseline_path: A `<example_id>/<language>.sha256` file.

    Returns:
        Every path recorded in the manifest, in file order.

    Raises:
        ValueError: On a malformed line (not "path<2sp>sha256hex").
    """
    paths: list[str] = []
    for raw in baseline_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(_MANIFEST_SEP, 1)
        if len(parts) != 2:
            raise ValueError(
                f"Malformed manifest line in {baseline_path} (expected "
                f"'path{_MANIFEST_SEP}sha256hex'): {line!r}"
            )
        paths.append(parts[0])
    return paths


# ---------------------------------------------------------------------------
# Role classification
# ---------------------------------------------------------------------------


def language_domain_declarations(language: str) -> DomainDeclarations:
    """Fresh, derived DomainDeclarations for *language*.

    Computed independently of whatever mechanism the plugin's OWN
    `.domain_declarations` attribute currently uses in production -- calling
    `derive_domain_declarations` directly guarantees one consistent
    structural-pattern basis across all four languages for this gate, rather
    than trusting each package's own wiring to already route through it.

    Args:
        language: A registered `datrix.languages` entry-point name.

    Returns:
        `domain_id -> DomainDeclaration`, derived fresh from the plugin's
        registered sub-generator specs.
    """
    from datrix_codegen_common.parity.derived_declarations import (
        derive_domain_declarations,
    )
    from datrix_codegen_common.testkit.gates.domain_self_consistency import (
        DomainDeclaringPlugin,
    )
    from datrix_common.generation.discovery import get_language_plugin

    plugin = cast(DomainDeclaringPlugin, get_language_plugin(language))
    specs = plugin.generator.get_sub_generators()
    return derive_domain_declarations(
        specs,
        unsupported_reason=lambda domain_id: (
            f"{language} registers no sub-generator for domain {domain_id!r} "
            f"(artifact-role-parity gate probe -- not a committed exemption reason)."
        ),
    )


#: Package-init marker basenames: language package-structure boilerplate
#: (e.g. Python's `__init__.py`, created wherever a package directory exists
#: for ANY reason) rather than domain-specific generated content. A trailing
#: `*.py`-shaped structural_pattern trivially matches this marker for every
#: domain whose files happen to share that directory, manufacturing a false
#: "domain present" signal with no bearing on what the DSL actually declared.
#: Excluded from classification entirely (routed to "unclassified") rather
#: than credited to any domain.
_PACKAGE_MARKER_BASENAMES: Final[frozenset[str]] = frozenset({"__init__.py"})


def _pattern_specificity(pattern: str) -> int:
    """Number of '/'-separated segments in a structural_pattern glob.

    `fnmatch.fnmatch`'s `*` spans `/` (by design -- the leading `*/` absorbs
    a variable-depth service-directory prefix). A side effect: when one
    domain's pattern is a strict directory-shallower generalization of a
    sibling domain's pattern (e.g. struct's `*/src/*/schemas/*.py` vs
    schema's `*/src/*/schemas/*/*.py`), the shallower pattern also matches
    files that structurally belong to the deeper, more specific sibling.
    Segment count is the tie-break: the pattern requiring more path segments
    is the more specific match for a path both patterns accept.
    """
    return pattern.count("/")


def classify_paths(
    paths: list[str], declarations: Mapping[str, DomainDeclaration]
) -> tuple[frozenset[str], list[str]]:
    """Classify each manifest path by domain role via fnmatch against every
    SUPPORTED declaration's structural_pattern -- the same glob shape
    `domain_self_consistency._pattern_mismatch_violations` uses.

    When a path matches more than one domain's pattern, only the most
    SPECIFIC match (see `_pattern_specificity`) is credited -- this is a
    property of this gate's own aggregation, not a different fnmatch rule:
    each candidate is still tested with the exact same `fnmatch.fnmatch`
    call domain_self_consistency uses. A package-init marker basename (see
    `_PACKAGE_MARKER_BASENAMES`) is routed to `unclassified` before any
    pattern is even tried -- it is package-structure boilerplate, never
    domain-specific content.

    Args:
        paths: Relative paths from one blessed manifest.
        declarations: `domain_id -> DomainDeclaration`.

    Returns:
        `(role_set, unclassified_paths)`. `role_set` is every domain id with
        >= 1 matching path (after the most-specific tie-break).
        `unclassified_paths` is reported by the caller but never compared --
        template-level naming legitimately differs by language; the role set
        is the contract, not the literal path shape.
    """
    supported: list[tuple[str, str]] = [
        (domain_id, decl.structural_pattern)
        for domain_id, decl in declarations.items()
        if decl.status == "supported" and decl.structural_pattern is not None
    ]
    roles: set[str] = set()
    unclassified: list[str] = []
    for path in paths:
        if PurePosixPath(path).name in _PACKAGE_MARKER_BASENAMES:
            unclassified.append(path)
            continue
        matches = [
            (domain_id, pattern)
            for domain_id, pattern in supported
            if fnmatch.fnmatch(path, pattern)
        ]
        if not matches:
            unclassified.append(path)
            continue
        most_specific = max(_pattern_specificity(pattern) for _, pattern in matches)
        for domain_id, pattern in matches:
            if _pattern_specificity(pattern) == most_specific:
                roles.add(domain_id)
    return frozenset(roles), unclassified


def compare_role_sets(
    per_language: Mapping[str, frozenset[str]],
) -> dict[str, frozenset[str]]:
    """Compare every language's role set against the union of all, for one example.

    Mirrors `supported_domain_parity.compare_supported_domain_sets` exactly
    (same union-minus-own shape) -- reuse that reasoning rather than
    reinventing a comparison rule.

    Args:
        per_language: {language: role_set} for one example's blessed languages.

    Returns:
        {language: missing_role_ids} -- empty per language iff every
        language's role set is identical (D7's POSITIVE acceptance property
        for that example).

    Raises:
        ValueError: If *per_language* has fewer than
            `_MIN_LANGUAGES_FOR_COMPARISON` entries.
    """
    if len(per_language) < _MIN_LANGUAGES_FOR_COMPARISON:
        raise ValueError(
            f"compare_role_sets requires at least {_MIN_LANGUAGES_FOR_COMPARISON} "
            f"languages to compare, got {len(per_language)} ({sorted(per_language)})."
        )
    union_ids: frozenset[str] = frozenset[str]().union(*per_language.values())
    return {name: union_ids - ids for name, ids in per_language.items()}


# ---------------------------------------------------------------------------
# Exemptions
# ---------------------------------------------------------------------------


def load_exemptions() -> tuple[list[ExemptionEntry], int]:
    """Load and validate artifact-role-exemptions.json.

    Returns:
        `(entries, expected_count)`.

    Raises:
        ValueError: If the file is missing, malformed, has an empty field on
            any entry, its entry count does not match the pinned
            `expected_count`, or if any entry names a ``(domain, language)``
            pair that language now declares ``unsupported`` -- that is a
            declared absence the domain-parity gates already report; a
            per-example exemption for the same fact is a stale duplicate
            that must be deleted, not kept.
    """
    if not EXEMPTIONS_PATH.exists():
        raise ValueError(
            f"Missing exemption file {EXEMPTIONS_PATH}. Restore it from git; "
            f"the gate never creates it."
        )
    data = json.loads(EXEMPTIONS_PATH.read_text(encoding="utf-8"))
    expected = data.get("expected_count")
    raw_entries = data.get("exemptions")
    if not isinstance(raw_entries, list) or not isinstance(expected, int):
        raise ValueError(
            f"Malformed {EXEMPTIONS_PATH}: expected an object with "
            f"'expected_count' (int) and 'exemptions' (array of "
            f"{{example, domain, language, reason}})."
        )
    entries: list[ExemptionEntry] = []
    for i, raw in enumerate(raw_entries):
        if not isinstance(raw, dict):
            raise ValueError(f"exemptions[{i}] is not an object: {raw!r}")
        example = raw.get("example")
        domain = raw.get("domain")
        language = raw.get("language")
        reason = raw.get("reason")
        if (
            not isinstance(example, str) or not example.strip()
            or not isinstance(domain, str) or not domain.strip()
            or not isinstance(language, str) or not language.strip()
            or not isinstance(reason, str) or not reason.strip()
        ):
            raise ValueError(
                f"exemptions[{i}] must have non-empty string 'example', 'domain', "
                f"'language', and 'reason' fields; got {raw!r}."
            )
        entries.append(ExemptionEntry(example, domain, language, reason))
    _reject_exemptions_for_unsupported_domains(entries)
    if len(entries) != expected:
        raise ValueError(
            f"{EXEMPTIONS_PATH} has {len(entries)} entries but 'expected_count' is "
            f"pinned at {expected}. Update the count in the same change that adds "
            f"or removes an entry."
        )
    return entries, expected


def _assert_no_stale_exemptions_for_self_test(
    entries: list[ExemptionEntry],
    declarations: dict[str, dict[str, DomainDeclaration]],
) -> None:
    """Same rule as `_reject_exemptions_for_unsupported_domains`, but taking
    already-resolved declarations instead of deriving them -- lets the
    self-test exercise the rejection rule against synthetic data without a
    real language plugin.

    Args:
        entries: Exemption entries to check.
        declarations: `language -> (domain_id -> DomainDeclaration)`.

    Raises:
        ValueError: If any entry names a domain its language declares
            `unsupported` -- naming the entry's coordinates and the
            declared reason, so the fix (delete the exemption; the
            domain-parity gate already covers it) is unambiguous.
    """
    for entry in entries:
        declaration = declarations.get(entry.language, {}).get(entry.domain)
        if declaration is not None and declaration.status == "unsupported":
            raise ValueError(
                f"artifact-role-exemptions.json entry (example="
                f"{entry.example!r}, domain={entry.domain!r}, language="
                f"{entry.language!r}) duplicates a declared absence: "
                f"{entry.language!r} declares {entry.domain!r} unsupported "
                f"({declaration.reason!r}). Delete this exemption -- the "
                f"domain-parity gate already reports this as a declared "
                f"absence, not a per-example gap."
            )


def _reject_exemptions_for_unsupported_domains(entries: list[ExemptionEntry]) -> None:
    """Fail loud on an exemption entry duplicating a declared-unsupported domain.

    Derives each entry's language's declarations fresh via
    `language_domain_declarations` (grouped by language so the derivation
    runs once per language, not once per entry) and delegates the actual
    rejection rule to `_assert_no_stale_exemptions_for_self_test`, so the
    rule itself has exactly one implementation.

    Args:
        entries: Exemption entries to check.

    Raises:
        ValueError: If any entry names a domain its language declares
            `unsupported`.
    """
    entries_by_language: dict[str, list[ExemptionEntry]] = {}
    for entry in entries:
        entries_by_language.setdefault(entry.language, []).append(entry)
    declarations = {
        language: language_domain_declarations(language)
        for language in entries_by_language
    }
    _assert_no_stale_exemptions_for_self_test(entries, declarations)


def _is_exempt(
    exemptions: list[ExemptionEntry], example: str, domain: str, language: str
) -> bool:
    """Whether (example, domain, language) has a reviewed exemption entry."""
    return any(
        e.example == example and e.domain == domain and e.language == language
        for e in exemptions
    )


def _is_declared_unsupported(declarations: Mapping[str, DomainDeclaration], domain_id: str) -> bool:
    """Whether *domain_id* is a declared absence for the language *declarations* came from.

    A `True` result means the language's OWN `DomainDeclaration` already
    explains why this domain never appears in its role set -- on every
    example, not just the one currently being compared -- so the caller
    should skip it rather than treat it as a role-parity violation needing
    a per-example exemption.
    """
    declaration = declarations.get(domain_id)
    return declaration is not None and declaration.status == "unsupported"


#: Every path from every blessed baseline for a language, across the WHOLE
#: corpus under BASELINES_ROOT (not just examples with >= 2 blessed
#: languages) -- memoized per language since `_is_corpus_vacuous_for_language`
#: is consulted once per (example, language, missing domain) triple and
#: re-reading every one of a language's baselines on each call would be
#: quadratic in the corpus size.
_ALL_BLESSED_PATHS_CACHE: dict[str, list[str]] = {}


def _all_blessed_paths_for_language(language: str) -> list[str]:
    """Every path in every blessed `.sha256` baseline for *language*, across
    every example directory under `BASELINES_ROOT` -- not scoped to examples
    with >= 2 blessed languages, since a domain's corpus-wide realization
    must be judged against the language's FULL blessed footprint, not just
    the subset this gate compares.
    """
    if language not in _ALL_BLESSED_PATHS_CACHE:
        paths: list[str] = []
        if BASELINES_ROOT.is_dir():
            for example_dir in sorted(p for p in BASELINES_ROOT.iterdir() if p.is_dir()):
                baseline = example_dir / f"{language}.sha256"
                if baseline.is_file():
                    paths.extend(manifest_paths(baseline))
        _ALL_BLESSED_PATHS_CACHE[language] = paths
    return _ALL_BLESSED_PATHS_CACHE[language]


def _domain_ever_matches_for_self_test(pattern: str, all_paths: Iterable[str]) -> bool:
    """Whether *pattern* matches at least one path in *all_paths* -- the pure
    predicate `_is_corpus_vacuous_for_language` delegates to, taking an
    already-resolved path list so the self-test can exercise it directly
    against synthetic data without touching real blessed baselines.
    """
    return any(fnmatch.fnmatch(path, pattern) for path in all_paths)


def _is_corpus_vacuous_for_language(
    language: str, domain_id: str, declarations: Mapping[str, DomainDeclaration]
) -> bool:
    """Whether *domain_id* is a declared-`supported` domain for *language*
    whose structural_pattern matches ZERO files anywhere in *language*'s
    ENTIRE blessed footprint -- not just the one example currently being
    compared.

    A `True` result means the domain's triggering DSL construct simply never
    occurs anywhere in the reference-example corpus for this language (e.g.
    a `requires feature extern_services`-gated generator when no example
    anywhere declares an `extern service`): a corpus-wide fact, not a
    per-example one, so a single-example 'missing' verdict against it carries
    no information and is not drift. Distinct from `_is_declared_unsupported`
    (a language-level stance the plugin itself asserts) -- this is instead
    an EMPIRICAL fact about the language's own blessed output, derived from
    the same manifests this gate already reads, never from DSL source.

    Args:
        language: The language whose blessed footprint to scan.
        domain_id: The domain to check.
        declarations: `language`'s own `domain_id -> DomainDeclaration`.
    """
    declaration = declarations.get(domain_id)
    if declaration is None or declaration.status != "supported" or not declaration.structural_pattern:
        return False
    return not _domain_ever_matches_for_self_test(
        declaration.structural_pattern, _all_blessed_paths_for_language(language)
    )


# ---------------------------------------------------------------------------
# Corpus-vacuity census + reviewed records
# ---------------------------------------------------------------------------


def corpus_vacuous_pairs() -> list[tuple[str, str]]:
    """Census every `(language, domain)` this gate would skip as corpus-vacuous.

    `_is_corpus_vacuous_for_language` is consulted per (example, language,
    missing domain) triple, so the pairs it actually silences depend on which
    examples happen to be blessed in >= 2 languages. This census does not: it
    asks the question over EVERY registered language and EVERY domain that
    language declares `supported`, so the reviewed-record set below is
    complete regardless of how the blessed matrix grows.

    Returns:
        Sorted `(language, domain_id)` pairs whose declared structural_pattern
        matches zero paths anywhere in that language's blessed footprint.
    """
    pairs: list[tuple[str, str]] = []
    for language in sorted(registered_language_names()):
        declarations = language_domain_declarations(language)
        pairs.extend(
            (language, domain_id)
            for domain_id in sorted(declarations)
            if _is_corpus_vacuous_for_language(language, domain_id, declarations)
        )
    return pairs


def _parse_vacuity_record(index: int, raw: object) -> CorpusVacuityRecord:
    """Validate and build one record from its raw JSON object.

    Args:
        index: Position in the `records` array, for error messages.
        raw: The decoded JSON value at that position.

    Returns:
        The validated record.

    Raises:
        ValueError: If the entry is not an object, has an empty or non-string
            field, or names a `status` outside `_VACUITY_STATUSES`.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"records[{index}] is not an object: {raw!r}")
    fields: dict[str, str] = {}
    for key in ("language", "domain", "status", "reason"):
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"records[{index}] must have a non-empty string {key!r} field; "
                f"got {raw!r}."
            )
        fields[key] = value
    if fields["status"] not in _VACUITY_STATUSES:
        raise ValueError(
            f"records[{index}] has status {fields['status']!r}, which is not one "
            f"of {sorted(_VACUITY_STATUSES)}. The three carry different "
            f"remedies and are never interchangeable: "
            f"'{VACUITY_UNREACHABLE}' = no example can produce it at all; "
            f"'{VACUITY_CLOUD_ONLY}' = only a cloud-targeting example could, "
            f"and the corpus has none; '{VACUITY_UNEXERCISED}' = an ordinary "
            f"example could and none declares the construct. Recording a "
            f"weaker claim as a stronger one hides a corpus-coverage gap."
        )
    return CorpusVacuityRecord(
        language=fields["language"],
        domain=fields["domain"],
        status=fields["status"],
        reason=fields["reason"],
    )


def load_corpus_vacuity_records() -> tuple[list[CorpusVacuityRecord], int]:
    """Load and validate corpus-vacuity-records.json.

    Returns:
        `(records, expected_count)`.

    Raises:
        ValueError: If the file is missing or malformed, an entry is invalid
            (see `_parse_vacuity_record`), two entries name the same
            `(language, domain)`, or the entry count does not match the pinned
            `expected_count`.
    """
    if not CORPUS_VACUITY_RECORDS_PATH.exists():
        raise ValueError(
            f"Missing corpus-vacuity record file {CORPUS_VACUITY_RECORDS_PATH}. "
            f"Restore it from git; the gate never creates it."
        )
    data = json.loads(CORPUS_VACUITY_RECORDS_PATH.read_text(encoding="utf-8"))
    expected = data.get("expected_count")
    raw_records = data.get("records")
    if not isinstance(raw_records, list) or not isinstance(expected, int):
        raise ValueError(
            f"Malformed {CORPUS_VACUITY_RECORDS_PATH}: expected an object with "
            f"'expected_count' (int) and 'records' (array of "
            f"{{language, domain, status, reason}})."
        )
    records = [_parse_vacuity_record(i, raw) for i, raw in enumerate(raw_records)]
    seen: set[tuple[str, str]] = set()
    for record in records:
        key = (record.language, record.domain)
        if key in seen:
            raise ValueError(
                f"{CORPUS_VACUITY_RECORDS_PATH} names ({record.language!r}, "
                f"{record.domain!r}) more than once. One (language, domain) "
                f"carries exactly one record."
            )
        seen.add(key)
    if len(records) != expected:
        raise ValueError(
            f"{CORPUS_VACUITY_RECORDS_PATH} has {len(records)} records but "
            f"'expected_count' is pinned at {expected}. Update the count in the "
            f"same change that adds or removes a record."
        )
    return records, expected


def compare_vacuity_records(
    pairs: Iterable[tuple[str, str]], records: Iterable[CorpusVacuityRecord]
) -> list[str]:
    """Two-directional comparison of the census against the reviewed records.

    Pure over its arguments so the self-test can exercise it on synthetic
    coordinates without touching real baselines or plugins.

    Args:
        pairs: `(language, domain)` pairs the census found corpus-vacuous.
        records: The reviewed records.

    Returns:
        One problem description per unrecorded pair (a domain this gate would
        silently skip with nothing on the record saying why) and one per stale
        record (a pair that is no longer vacuous, so the record must be
        deleted and the pinned count decremented). Empty means the two agree.
    """
    censused = set(pairs)
    recorded = {(record.language, record.domain) for record in records}
    problems: list[str] = []
    problems.extend(
        f"UNRECORDED CORPUS VACUITY language={language} domain={domain}: this "
        f"language declares the domain 'supported', its structural_pattern "
        f"matches zero paths anywhere in its blessed footprint, and "
        f"{CORPUS_VACUITY_RECORDS_PATH.name} says nothing about it. Add a "
        f"record naming the structural reason and its status (one of "
        f"{sorted(_VACUITY_STATUSES)}), or add a reference example that "
        f"exercises it."
        for language, domain in sorted(censused - recorded)
    )
    problems.extend(
        f"STALE CORPUS-VACUITY RECORD language={language} domain={domain}: the "
        f"blessed corpus now matches this domain's structural_pattern, so the "
        f"record no longer describes anything. Delete it and decrement "
        f"'expected_count' in the same change."
        for language, domain in sorted(recorded - censused)
    )
    return problems


def check_corpus_vacuity_records() -> bool:
    """Hold every corpus-vacuous `(language, domain)` to a reviewed record.

    A corpus-vacuous domain is skipped SILENTLY by
    `check_artifact_role_parity` -- correctly, since a single-example
    "missing" verdict over a construct no example declares carries no
    information. Silence is the problem: a generator no example reaches has
    no end-to-end signal at all, and nothing distinguishes "no example CAN
    reach this" from "no example HAPPENS to". This turns each skip into a
    typed, counted, reviewed record.

    Returns:
        True when the census and the records agree in both directions.
    """
    records, expected = load_corpus_vacuity_records()
    pairs = corpus_vacuous_pairs()
    logger.info(
        "corpus_vacuity_census pairs=%d records=%d", len(pairs), expected,
    )
    problems = compare_vacuity_records(pairs, records)
    if problems:
        for problem in problems:
            logger.error("%s", problem)
        return False
    by_status = {
        status: sum(1 for record in records if record.status == status)
        for status in sorted(_VACUITY_STATUSES)
    }
    logger.info("corpus_vacuity_records_ok recorded=%d by_status=%s", expected, by_status)
    return True


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def run_self_test() -> list[str]:
    """Prove the comparator and classifier are non-vacuous before any real
    comparison is trusted.

    Returns:
        Problem descriptions; empty means the gate is sound.
    """
    problems: list[str] = []

    matching = {
        _SELF_TEST_LANGUAGE_A: frozenset({_SELF_TEST_DOMAIN_SHARED}),
        _SELF_TEST_LANGUAGE_B: frozenset({_SELF_TEST_DOMAIN_SHARED}),
    }
    matching_result = compare_role_sets(matching)
    if any(matching_result.values()):
        problems.append(
            f"self-test: compare_role_sets reported a divergence for a synthetic "
            f"MATCHING pair: {matching_result}"
        )

    mismatched = {
        _SELF_TEST_LANGUAGE_A: frozenset({_SELF_TEST_DOMAIN_SHARED, _SELF_TEST_DOMAIN_FORCED_GAP}),
        _SELF_TEST_LANGUAGE_B: frozenset({_SELF_TEST_DOMAIN_SHARED}),
    }
    mismatched_result = compare_role_sets(mismatched)
    if _SELF_TEST_DOMAIN_FORCED_GAP not in mismatched_result.get(_SELF_TEST_LANGUAGE_B, frozenset()):
        problems.append(
            f"self-test: compare_role_sets did not detect the forced mismatch: "
            f"{mismatched_result}"
        )
    if mismatched_result.get(_SELF_TEST_LANGUAGE_A):
        problems.append(
            f"self-test: compare_role_sets reported {_SELF_TEST_LANGUAGE_A!r} as "
            f"missing domains it actually declares: {mismatched_result}"
        )

    # _is_declared_unsupported: a language's own unsupported declaration for
    # the forced-missing domain is a declared absence (True, skip it); a
    # supported declaration for the same domain is a genuine gap needing an
    # exemption (False, still report it); an undeclared domain id is neither.
    unsupported_gap_declarations: DomainDeclarations = {
        _SELF_TEST_DOMAIN_FORCED_GAP: DomainDeclaration(
            domain_id=_SELF_TEST_DOMAIN_FORCED_GAP,
            status="unsupported",
            reason="self-test: declared absence, not a role-parity violation",
        ),
    }
    if not _is_declared_unsupported(unsupported_gap_declarations, _SELF_TEST_DOMAIN_FORCED_GAP):
        problems.append(
            "self-test: _is_declared_unsupported did not recognize a domain "
            "its language declares unsupported"
        )
    supported_gap_declarations: DomainDeclarations = {
        _SELF_TEST_DOMAIN_FORCED_GAP: DomainDeclaration(
            domain_id=_SELF_TEST_DOMAIN_FORCED_GAP,
            status="supported",
            structural_pattern="*/self_test_forced_gap/*.txt",
        ),
    }
    if _is_declared_unsupported(supported_gap_declarations, _SELF_TEST_DOMAIN_FORCED_GAP):
        problems.append(
            "self-test: _is_declared_unsupported flagged a domain its "
            "language declares supported as a declared absence"
        )
    if _is_declared_unsupported({}, _SELF_TEST_DOMAIN_FORCED_GAP):
        problems.append(
            "self-test: _is_declared_unsupported flagged a domain with NO "
            "declaration at all as a declared absence"
        )

    declarations: DomainDeclarations = {
        _SELF_TEST_DOMAIN_SHARED: DomainDeclaration(
            domain_id=_SELF_TEST_DOMAIN_SHARED,
            status="supported",
            structural_pattern="*/orders/*.txt",
        ),
    }
    roles, unclassified = classify_paths(
        ["svc/orders/order.txt", "svc/unrelated/readme.md"], declarations
    )
    if roles != frozenset({_SELF_TEST_DOMAIN_SHARED}):
        problems.append(f"self-test: classify_paths role mismatch: {roles}")
    if unclassified != ["svc/unrelated/readme.md"]:
        problems.append(f"self-test: classify_paths unclassified mismatch: {unclassified}")

    # Package-init marker exclusion: __init__.py sitting in a domain's own
    # matching directory is package-structure boilerplate, never credited,
    # even though its bare name would otherwise satisfy a trailing `*` glob.
    marker_declarations: DomainDeclarations = {
        _SELF_TEST_DOMAIN_SHARED: DomainDeclaration(
            domain_id=_SELF_TEST_DOMAIN_SHARED,
            status="supported",
            structural_pattern="*/orders/*.py",
        ),
    }
    marker_roles, marker_unclassified = classify_paths(
        ["svc/orders/__init__.py"], marker_declarations
    )
    if marker_roles != frozenset():
        problems.append(
            f"self-test: classify_paths credited a package-init marker to a "
            f"domain: {marker_roles}"
        )
    if marker_unclassified != ["svc/orders/__init__.py"]:
        problems.append(
            f"self-test: classify_paths did not route the package-init marker to "
            f"unclassified: {marker_unclassified}"
        )

    # Most-specific-wins tie-break: a shallow pattern that also matches a
    # sibling's deeper, more specific path must NOT be credited for that path.
    _SELF_TEST_DOMAIN_SHALLOW = "self_test_order_shallow"
    _SELF_TEST_DOMAIN_DEEP = "self_test_order_deep"
    overlap_declarations: DomainDeclarations = {
        _SELF_TEST_DOMAIN_SHALLOW: DomainDeclaration(
            domain_id=_SELF_TEST_DOMAIN_SHALLOW,
            status="supported",
            structural_pattern="*/orders/*.txt",
        ),
        _SELF_TEST_DOMAIN_DEEP: DomainDeclaration(
            domain_id=_SELF_TEST_DOMAIN_DEEP,
            status="supported",
            structural_pattern="*/orders/*/*.txt",
        ),
    }
    overlap_roles, _ = classify_paths(
        ["svc/orders/archive/order.txt", "svc/orders/order.txt"], overlap_declarations
    )
    if overlap_roles != frozenset({_SELF_TEST_DOMAIN_SHALLOW, _SELF_TEST_DOMAIN_DEEP}):
        problems.append(
            f"self-test: classify_paths most-specific tie-break failed: expected both "
            f"domains credited (one per path, at its own most-specific match), got "
            f"{overlap_roles}"
        )

    try:
        compare_role_sets({_SELF_TEST_LANGUAGE_A: frozenset()})
        problems.append("self-test: compare_role_sets accepted a single-language mapping")
    except ValueError:
        pass

    # _reject_exemptions_for_unsupported_domains non-vacuity proof.
    # Uses the module's OWN ExemptionEntry/DomainDeclaration types with fully
    # synthetic coordinates -- never a real language or example id.
    synthetic_unsupported_entry = ExemptionEntry(
        example="self_test_example",
        domain=_SELF_TEST_DOMAIN_SHARED,
        language=_SELF_TEST_LANGUAGE_A,
        reason="self-test: should be rejected as a stale duplicate",
    )
    try:
        _assert_no_stale_exemptions_for_self_test(
            [synthetic_unsupported_entry],
            declarations={
                _SELF_TEST_LANGUAGE_A: {
                    _SELF_TEST_DOMAIN_SHARED: DomainDeclaration(
                        domain_id=_SELF_TEST_DOMAIN_SHARED,
                        status="unsupported",
                        reason="self-test: declared absence",
                    ),
                },
            },
        )
        problems.append(
            "self-test: _reject_exemptions_for_unsupported_domains did not "
            "reject an exemption duplicating a declared-unsupported domain"
        )
    except ValueError:
        pass  # expected -- the guard correctly rejected the stale exemption

    # _is_corpus_vacuous_for_language: proves the three-way split -- a
    # declared-supported domain matching zero paths anywhere in the
    # language's blessed footprint is corpus-vacuous (True); the SAME
    # pattern matching >= 1 path elsewhere is NOT corpus-vacuous (False,
    # even though it is also absent from the one path list checked here);
    # and a declared-unsupported domain is never corpus-vacuous (False --
    # `_is_declared_unsupported` already owns that case, so this predicate
    # only ever fires for domains a language claims to realize). The cache
    # is pre-populated directly (never touching real blessed baselines) so
    # `_all_blessed_paths_for_language` is exercised for real while the
    # underlying file scan stays fully synthetic.
    _SELF_TEST_VACUOUS_LANGUAGE: Final[str] = "self_test_lang_vacuous_check"
    _ALL_BLESSED_PATHS_CACHE[_SELF_TEST_VACUOUS_LANGUAGE] = [
        "svc/unrelated/readme.md",
        "svc/orders/order.txt",
    ]
    vacuous_domain_declarations: DomainDeclarations = {
        _SELF_TEST_DOMAIN_SHARED: DomainDeclaration(
            domain_id=_SELF_TEST_DOMAIN_SHARED,
            status="supported",
            structural_pattern="*/never_matches_anything/*.txt",
        ),
        _SELF_TEST_DOMAIN_FORCED_GAP: DomainDeclaration(
            domain_id=_SELF_TEST_DOMAIN_FORCED_GAP,
            status="supported",
            structural_pattern="*/orders/*.txt",
        ),
    }
    if not _is_corpus_vacuous_for_language(
        _SELF_TEST_VACUOUS_LANGUAGE, _SELF_TEST_DOMAIN_SHARED, vacuous_domain_declarations
    ):
        problems.append(
            "self-test: _is_corpus_vacuous_for_language did not flag a domain "
            "whose pattern matches zero paths anywhere in the language's "
            "blessed footprint"
        )
    if _is_corpus_vacuous_for_language(
        _SELF_TEST_VACUOUS_LANGUAGE, _SELF_TEST_DOMAIN_FORCED_GAP, vacuous_domain_declarations
    ):
        problems.append(
            "self-test: _is_corpus_vacuous_for_language flagged a domain "
            "whose pattern DOES match a path elsewhere in the language's "
            "blessed footprint"
        )
    if _is_corpus_vacuous_for_language(
        _SELF_TEST_VACUOUS_LANGUAGE, _SELF_TEST_DOMAIN_SHARED,
        {_SELF_TEST_DOMAIN_SHARED: DomainDeclaration(
            domain_id=_SELF_TEST_DOMAIN_SHARED, status="unsupported",
            reason="self-test: declared absence, not corpus-vacuous territory",
        )},
    ):
        problems.append(
            "self-test: _is_corpus_vacuous_for_language flagged a "
            "declared-unsupported domain -- that case belongs to "
            "_is_declared_unsupported, not this predicate"
        )
    del _ALL_BLESSED_PATHS_CACHE[_SELF_TEST_VACUOUS_LANGUAGE]

    problems.extend(_self_test_vacuity_records())

    return problems


def _self_test_vacuity_records() -> list[str]:
    """Prove the corpus-vacuity record comparison is non-vacuous.

    Fully synthetic coordinates -- never a real language, domain, or record
    file. Three properties: an agreeing census/record pair reports nothing; a
    censused pair with NO record is reported (the silence this comparison
    exists to end); and a record whose pair is no longer censused is reported
    stale. Plus: `_parse_vacuity_record` accepts both declared statuses and
    refuses a third, so "unexercised" can never be spelled as something the
    loader waves through.

    Returns:
        Problem descriptions; empty means the comparison is sound.
    """
    problems: list[str] = []
    record = CorpusVacuityRecord(
        language=_SELF_TEST_LANGUAGE_A,
        domain=_SELF_TEST_DOMAIN_SHARED,
        status=VACUITY_UNREACHABLE,
        reason="self-test: synthetic record, never a real coordinate",
    )
    agreeing = compare_vacuity_records([(_SELF_TEST_LANGUAGE_A, _SELF_TEST_DOMAIN_SHARED)], [record])
    if agreeing:
        problems.append(
            f"self-test: compare_vacuity_records reported problems for an "
            f"agreeing census/record pair: {agreeing}"
        )
    unrecorded = compare_vacuity_records(
        [
            (_SELF_TEST_LANGUAGE_A, _SELF_TEST_DOMAIN_SHARED),
            (_SELF_TEST_LANGUAGE_A, _SELF_TEST_DOMAIN_FORCED_GAP),
        ],
        [record],
    )
    if not any(_SELF_TEST_DOMAIN_FORCED_GAP in problem for problem in unrecorded):
        problems.append(
            f"self-test: compare_vacuity_records did not report a censused "
            f"pair with no reviewed record: {unrecorded}"
        )
    stale = compare_vacuity_records([], [record])
    if not any(_SELF_TEST_DOMAIN_SHARED in problem for problem in stale):
        problems.append(
            f"self-test: compare_vacuity_records did not report a record whose "
            f"pair is no longer corpus-vacuous: {stale}"
        )

    for status in sorted(_VACUITY_STATUSES):
        parsed = _parse_vacuity_record(
            0,
            {
                "language": _SELF_TEST_LANGUAGE_A,
                "domain": _SELF_TEST_DOMAIN_SHARED,
                "status": status,
                "reason": "self-test: declared status must parse",
            },
        )
        if parsed.status != status:
            problems.append(
                f"self-test: _parse_vacuity_record mangled a declared status: "
                f"{parsed.status!r} != {status!r}"
            )
    try:
        _parse_vacuity_record(
            0,
            {
                "language": _SELF_TEST_LANGUAGE_A,
                "domain": _SELF_TEST_DOMAIN_SHARED,
                "status": "self_test_undeclared_status",
                "reason": "self-test: should be rejected",
            },
        )
        problems.append(
            "self-test: _parse_vacuity_record accepted a status outside the "
            "declared set"
        )
    except ValueError:
        pass  # expected -- the loader correctly refused an undeclared status
    return problems


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def check_artifact_role_parity() -> int:
    """Run the gate over every example with >= 2 blessed language baselines.

    A domain missing from one language's role set is compared against
    exemptions only when that language declares the domain `supported` AND
    realizes it somewhere else in its own blessed footprint. Two kinds of
    "missing" are never drift and never need an exemption:
      - the language declares the domain `unsupported` -- a declared absence
        explained once at the language level (see `language_domain_declarations`
        / `_is_declared_unsupported`), not a per-example fact; or
      - the language declares the domain `supported`, but its structural_pattern
        matches zero files anywhere across that language's ENTIRE blessed
        footprint (see `_is_corpus_vacuous_for_language`) -- an empirical,
        corpus-wide fact (the triggering construct never occurs in the corpus
        for this language) rather than something particular to this example.

    The second kind is skipped but never silent: `check_corpus_vacuity_records`
    holds every corpus-vacuous `(language, domain)` to a reviewed record
    stating WHY nothing exercises it, and refuses both an unrecorded pair and
    a record whose pair is no longer vacuous.

    Returns:
        Exit code (0 = every example's role sets agree modulo exemptions,
        declared-unsupported domains, and recorded corpus-vacuous domains,
        1 = an un-exempted divergence over a genuinely per-example-realized
        domain was found, or a corpus-vacuous domain has no reviewed record
        (or a record has no corpus-vacuous domain), 2 = zero examples have
        >= 2 blessed language baselines -- a vacuous comparison).
    """
    multi_language_examples = discover_multi_language_examples()
    if not multi_language_examples:
        logger.error(
            "ARTIFACT-ROLE GATE CANNOT RUN: no example has >= 2 blessed language "
            "baselines under %s -- a cross-language comparison over < 2 languages "
            "is vacuous.",
            BASELINES_ROOT,
        )
        return EXIT_USAGE

    exemptions, expected_count = load_exemptions()
    logger.info(
        "artifact_role_parity_start examples=%d exemptions=%d",
        len(multi_language_examples), expected_count,
    )

    ok = check_corpus_vacuity_records()
    for example_id, language_baselines in multi_language_examples.items():
        per_language_roles: dict[str, frozenset[str]] = {}
        per_language_declarations: dict[str, DomainDeclarations] = {}
        for language, baseline_path in sorted(language_baselines.items()):
            declarations = language_domain_declarations(language)
            per_language_declarations[language] = declarations
            paths = manifest_paths(baseline_path)
            roles, unclassified = classify_paths(paths, declarations)
            per_language_roles[language] = roles
            if unclassified:
                logger.info(
                    "artifact_role_unclassified example=%s language=%s count=%d "
                    "(reported, not compared): %s",
                    example_id, language, len(unclassified), unclassified[:5],
                )
        missing_by_language = compare_role_sets(per_language_roles)
        example_clean = True
        for language, missing in sorted(missing_by_language.items()):
            declarations = per_language_declarations[language]
            for domain_id in sorted(missing):
                if _is_declared_unsupported(declarations, domain_id):
                    # A declared absence, not a role-parity violation: this
                    # language's own stance already explains why the domain
                    # never appears in its role set, on EVERY example, not
                    # just this one -- the domain-parity gates own reporting
                    # this fact. No per-example exemption is needed or
                    # accepted for it (see _reject_exemptions_for_unsupported_domains).
                    continue
                if _is_corpus_vacuous_for_language(language, domain_id, declarations):
                    # An empirical corpus-wide fact, not a per-example one:
                    # this language declares the domain supported, but its
                    # ENTIRE blessed footprint (every example, not just this
                    # one) matches zero files to it -- the domain's
                    # triggering DSL construct simply never occurs anywhere
                    # in the reference-example corpus for this language. A
                    # per-example exemption would freeze today's corpus
                    # shape and go silently uncovered the day someone adds
                    # an example that DOES exercise the construct; this skip
                    # self-corrects instead.
                    continue
                if _is_exempt(exemptions, example_id, domain_id, language):
                    continue
                ok = False
                example_clean = False
                logger.error(
                    "ARTIFACT-ROLE DRIFT example=%s language=%s missing_domain=%s "
                    "(present in >= 1 other blessed language for this example; "
                    "%s's blessed manifest matches no file to this domain's "
                    "structural_pattern)",
                    example_id, language, domain_id, language,
                )
        if example_clean:
            logger.info(
                "artifact_role_example_clean example=%s languages=%s",
                example_id, sorted(language_baselines),
            )

    if ok:
        logger.info(
            "ARTIFACT-ROLE GATE PASSED: %d example(s) with >= 2 blessed languages, "
            "role sets identical modulo %d reviewed exemption(s).",
            len(multi_language_examples), expected_count,
        )
        return EXIT_OK
    return EXIT_FAIL


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Cross-language artifact-role parity gate (D7): for every example "
            "with >= 2 blessed language baselines, the set of domain roles with "
            ">= 1 matching file must be identical across languages. Reads blessed "
            "manifests only -- generates nothing."
        ),
    )
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip the real comparison",
    )
    parser.add_argument(
        "--census",
        action="store_true",
        help=(
            "Print every (language, domain) the blessed corpus exercises "
            "nowhere, with its reviewed record status, and exit -- the "
            "measurement corpus-vacuity-records.json is authored against"
        ),
    )
    return parser.parse_args(argv)


def print_corpus_vacuity_census() -> int:
    """Report the corpus-vacuity census next to the reviewed records.

    Returns:
        Exit code: 0 always -- this is a measurement, not a gate. The gate's
        own verdict on the same data is `check_corpus_vacuity_records`.
    """
    records, _ = load_corpus_vacuity_records() if CORPUS_VACUITY_RECORDS_PATH.exists() else ([], 0)
    by_pair = {(record.language, record.domain): record for record in records}
    pairs = corpus_vacuous_pairs()
    patterns_by_language: dict[str, DomainDeclarations] = {}
    for language, domain in pairs:
        record = by_pair.get((language, domain))
        if language not in patterns_by_language:
            patterns_by_language[language] = language_domain_declarations(language)
        declaration = patterns_by_language[language][domain]
        logger.info(
            "corpus_vacuous language=%s domain=%s pattern=%s status=%s",
            language, domain, declaration.structural_pattern,
            record.status if record else "UNRECORDED",
        )
    for language, domain in sorted(set(by_pair) - set(pairs)):
        logger.info("record_without_census language=%s domain=%s", language, domain)
    logger.info("corpus_vacuity_census_total pairs=%d records=%d", len(pairs), len(records))
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Returns:
        Process exit code: 0 = gate passed (or a successful `--self-test`),
        1 = an un-exempted role drift was found, 2 = self-test failure, zero
        comparable examples, a malformed exemption file, or an underivable
        domain declaration.
    """
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    problems = run_self_test()
    if problems:
        logger.error("NON-VACUITY SELF-TEST FAILED -- aborting before any real comparison:")
        for problem in problems:
            logger.error("  %s", problem)
        return EXIT_USAGE
    logger.info("non-vacuity self-test: PASS")

    if args.self_test:
        return EXIT_OK

    try:
        if args.census:
            return print_corpus_vacuity_census()
        return check_artifact_role_parity()
    except (ValueError, DerivationError) as exc:
        logger.error("ERROR: %s", exc)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
