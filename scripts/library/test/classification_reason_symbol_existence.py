#!/usr/bin/env python3
"""Classification-reason symbol-existence gate for the two parallel-implementation
drift classification files (language axis + platform axis).

`collapsibility_classification.py` asserts that every drifted name carries a
schema-VALID `collapsibility` field -- it never reads what the prose actually SAYS.
This module is the accuracy layer: it extracts every code-symbol-shaped and
`file.py:NN`-shaped reference out of each entry's `reason` and
`collapsibility.reason`, and fails loud when a referenced symbol does not resolve
anywhere relevant to the live `src/` trees of the packages on that axis. A
classification entry whose prose cites dead code is a worklist that lies, and the
schema-validity gate cannot see it -- the schema stays valid regardless of what the
prose claims.

**This is a naming-shape heuristic, not semantic analysis** -- the same documented
limitation `dependency_declaration_ratchet.py` carries for its own vocabulary:
candidate extraction is a syntactic pattern over backtick-quoted spans, so an
exotic reference phrased outside that shape is under-reported, never flagged. This
is an accepted, documented trade-off. What is NOT accepted is a hardcoded
per-entry allowlist of "known dead but fine" symbols -- that would drift silently
out of sync with the classification file it polices the moment either side changes.

**Resolution searches three surfaces, all scoped to the axis's own target
package `src/` trees (never the whole monorepo, never "everywhere else"):**
1. Real Python identifiers declared or used anywhere in those trees (function
   names, class names, attribute names, arguments, imports, keyword-argument
   names) -- an AST walk, never a substring search over raw file text.
2. String-literal content parsed from those same `.py` files (`ast.Constant`
   string values), matched by WHOLE TOKEN (word-boundary regex, never a bare
   substring). Many of these classifications cite a construct in the
   GENERATED target language or a third-party API a language's generator
   emits (a C# `using` statement, EF Core's `FirstOrDefaultAsync`,
   SQLAlchemy's `_sa_instance_state`) -- Datrix's own Python source never
   declares those as one of ITS OWN functions/classes/attributes; they exist
   only inside the f-string/template fragments that BUILD the emitted code.
   Restricting resolution to Python-identifier declarations alone would
   over-report every one of these as dead. This surface deliberately EXCLUDES
   raw comments: a Python comment carries no AST node at all, so text drawn
   only from parsed string constants never includes one.
3. Raw text of every `.j2` Jinja template under those same trees (also
   word-boundary matched) -- the other primary surface generated-code
   fragments live on.
   Word-boundary matching (never `in`) is what keeps this sound: a substring
   check would false-resolve a dead name that merely appears as part of a
   longer identifier (e.g. `_CACHE_CLIENT_PACKAGE` inside an unrelated
   `_MY_CACHE_CLIENT_PACKAGE_V2`) -- see `resolve_candidate`.

**A DOTTED candidate (`ClassName.attribute`) is resolved more strictly when its
base segment names a real class found in the tree**: the attribute must be one
that class ITSELF defines (a class-body field) or assigns (an
`<something>.attribute = ...` anywhere in the class's own body) -- never merely
"some attribute somewhere in the codebase". This is what catches the real defect
this task exists to catch: a reason once cited `RemoteConfigBackendSpec.
maven_coordinates`, and `RemoteConfigBackendSpec` genuinely exists, but its
docstring explicitly states Maven coordinates are NOT part of its spec -- the
class existing must not launder a nonexistent attribute on it. When the base
segment does NOT name a recognized class (e.g. `this.field`, a generated
TypeScript/C# receiver reference, not a Datrix class at all), each segment falls
back to the same broad per-segment resolution a bare identifier gets, because the
citation is not describing Datrix's own class shape in the first place.

**Two traps this heuristic deliberately does NOT try to solve:**
1. **Negation.** A reason can say a symbol "no longer exists" or "is not part of
   this spec" while still citing it in backticks as evidence. This module does
   NOT parse negation: a backtick-quoted citation is checked and, if dead,
   reported exactly the same whether the surrounding sentence asserts the
   symbol's presence or its absence. Parsing negation semantics is far beyond a
   naming-shape heuristic, and erring toward flagging (rather than silently
   trusting the sentence's polarity) is the safe failure direction for a check
   that exists to catch prose describing dead code.
2. **A backtick span that does not start with an identifier character** (e.g.
   `` `.maven_coordinates` ``, opening with a dot) never matches
   `_BACKTICK_CANDIDATE_RE` at all -- it is not a candidate, not silently
   skipped after being found, simply never produced by extraction. This is a
   consequence of the specified extraction rule, made explicit here rather than
   left as an accident someone has to rediscover.

Usage:
    python classification_reason_symbol_existence.py                 # languages
    python classification_reason_symbol_existence.py --axis platforms
    python classification_reason_symbol_existence.py --self-test      # non-vacuity only
"""

from __future__ import annotations

import argparse
import ast
import functools
import json
import logging
import re
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from test.parallel_implementation_drift import (  # noqa: E402
    AXIS_LANGUAGES,
    AXIS_PLATFORMS,
    WORKSPACE_ROOT,
    discover_target_package_src_dirs,
)
from shared.registered_targets import (  # noqa: E402
    registered_language_names,
    registered_platform_names,
)

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve()
DATRIX_DIR: Path = _HERE.parents[3]

LANGUAGE_CLASSIFICATION_PATH: Path = DATRIX_DIR / "scripts" / "config" / "parallel-implementation-drift-classification.json"
PLATFORM_CLASSIFICATION_PATH: Path = DATRIX_DIR / "scripts" / "config" / "platform-implementation-drift-classification.json"

_AXIS_CLASSIFICATION_PATHS: Final[dict[str, Path]] = {
    AXIS_LANGUAGES: LANGUAGE_CLASSIFICATION_PATH,
    AXIS_PLATFORMS: PLATFORM_CLASSIFICATION_PATH,
}
_AXIS_NAME_RESOLVERS: Final[dict[str, Callable[[], frozenset[str]]]] = {
    AXIS_LANGUAGES: registered_language_names,
    AXIS_PLATFORMS: registered_platform_names,
}

#: Backtick-quoted prose/schema vocabulary that is never a code-symbol candidate,
#: even though it matches the identifier shape. Kept as one named, reviewable
#: constant -- NOT an inline literal scattered through the extraction logic --
#: because it is a closed, small list of words the classification schema itself
#: uses (status/mechanism values, structural field names), not an allowlist of
#: "known dead symbols" (that would be the anti-pattern this gate exists to catch).
_SCHEMA_PROSE_VOCABULARY: Final[frozenset[str]] = frozenset(
    {
        "intentional",
        "tracked",
        "none",
        "status",
        "reason",
        "mechanism",
        "collapsibility",
        "classifications",
    }
)

#: Matches a backtick-quoted candidate: a dotted Python identifier path
#: (`Foo.bar_baz`, `_private_name`) or a `some_module.py:123` citation.
_BACKTICK_CANDIDATE_RE: Final[re.Pattern[str]] = re.compile(r"`([A-Za-z_][A-Za-z0-9_.]*(?::\d+)?)`")
_FILE_LINE_RE: Final[re.Pattern[str]] = re.compile(r"^([\w./-]+\.py):(\d+)$")

EXIT_OK: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_USAGE: Final[int] = 2

#: Self-test-only synthetic identifiers, chosen to be unmistakably not one of
#: the real registered symbols -- proving the scan is driven entirely by its
#: injected/discovered package trees, never a hardcoded literal.
_SELF_TEST_DEAD_SYMBOL: Final[str] = "self_test_dead_symbol_never_exists"
_SELF_TEST_PRESENT_FUNCTION: Final[str] = "self_test_present_helper"
_SELF_TEST_CLASS_NAME: Final[str] = "SelfTestSpecClass"
_SELF_TEST_PRESENT_ATTR: Final[str] = "present_field"
_SELF_TEST_ABSENT_ATTR: Final[str] = "absent_field_never_declared"


@dataclass(frozen=True)
class DeadSymbolReference:
    """One reference extracted from a classification entry's prose that did not
    resolve to anything in the live source tree."""

    entry_name: str
    field: str  # "reason" or "collapsibility.reason"
    candidate: str


def _four_part_message(what: str, expected: str, valid_options: str, fix: str) -> str:
    """Compose the repo-mandated four-part error/violation message.

    Args:
        what: What went wrong.
        expected: What was expected instead.
        valid_options: The valid values/shape.
        fix: A concrete fix suggestion.

    Returns:
        A single formatted message string.
    """
    return f"{what} Expected: {expected} Valid options: {valid_options} Fix: {fix}"


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def extract_candidates(text: str) -> frozenset[str]:
    """Extract backtick-quoted, identifier- or `file.py:NN`-shaped candidates from
    *text*, excluding `_SCHEMA_PROSE_VOCABULARY` entries.

    A backtick span that does not start with an identifier character (e.g.
    `` `.maven_coordinates` ``) never matches `_BACKTICK_CANDIDATE_RE` at all --
    it is simply never produced here, not filtered out afterward.

    Args:
        text: A `reason` or `collapsibility.reason` string.

    Returns:
        The candidate spans worth resolving.
    """
    return frozenset(
        candidate for candidate in _BACKTICK_CANDIDATE_RE.findall(text) if candidate not in _SCHEMA_PROSE_VOCABULARY
    )


# ---------------------------------------------------------------------------
# Resolution -- one cached symbol index per invocation, never re-walked per candidate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SymbolIndex:
    """Everything `resolve_candidate` needs about one axis's target `src/`
    trees, built ONCE per invocation (`functools.lru_cache`) -- 625+ entries
    would otherwise re-walk the tree hundreds of times over."""

    identifier_names: frozenset[str]
    class_attribute_names: dict[str, frozenset[str]]
    text_content: str


def _collect_identifier_names(tree: ast.Module) -> set[str]:
    """Every function/class/attribute/argument/import/keyword-argument name
    declared or used anywhere in *tree*."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.alias):
            names.add(node.name.rsplit(".", 1)[-1])
            if node.asname:
                names.add(node.asname)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
    return names


def _class_body_field_names(class_node: ast.ClassDef) -> frozenset[str]:
    """Direct class-body-level `Name` assignment/annotation targets --
    dataclass-style field declarations, e.g. `engine: ConfigStoreEngine`."""
    names: set[str] = set()
    for stmt in class_node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            names.add(stmt.target.id)
        elif isinstance(stmt, ast.Assign):
            names.update(target.id for target in stmt.targets if isinstance(target, ast.Name))
    return frozenset(names)


def _class_assigned_attribute_names(class_node: ast.ClassDef) -> frozenset[str]:
    """Every `<something>.<attribute> = ...` assignment target anywhere within
    the class's own subtree (its methods included), e.g. `self.attribute = ...`.

    Combined with `_class_body_field_names`, this is "an attribute the class
    itself defines or assigns" -- never merely "some attribute somewhere in
    the codebase" (see module docstring's RemoteConfigBackendSpec example).
    """
    return frozenset(
        node.attr for node in ast.walk(class_node) if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store)
    )


@functools.lru_cache(maxsize=8)
def _build_symbol_index(src_dirs: frozenset[Path]) -> _SymbolIndex:
    """Walk every `.py` and `.j2` file under *src_dirs* exactly once and build
    the combined identifier/attribute/text index `resolve_candidate` queries.

    Args:
        src_dirs: The axis's package source roots (hashable, so this is safe
            to cache -- `resolve_candidate` calls this once per invocation
            via the module-level cache rather than the caller re-walking the
            tree per candidate).

    Returns:
        The built `_SymbolIndex`.

    Raises:
        SyntaxError: If a `.py` file under *src_dirs* cannot be parsed.
    """
    identifier_names: set[str] = set()
    class_attribute_names: dict[str, frozenset[str]] = {}
    text_chunks: list[str] = []

    for src_dir in sorted(src_dirs):
        if not src_dir.is_dir():
            continue
        for py_file in sorted(src_dir.rglob("*.py")):
            source = py_file.read_text(encoding="utf-8-sig")
            try:
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError as exc:
                raise SyntaxError(
                    f"Failed to parse {py_file} while indexing symbols for the "
                    f"classification-reason symbol-existence gate: {exc}"
                ) from exc
            identifier_names.update(_collect_identifier_names(tree))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_attribute_names[node.name] = _class_body_field_names(node) | _class_assigned_attribute_names(
                        node
                    )
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    text_chunks.append(node.value)
        for template_file in sorted(src_dir.rglob("*.j2")):
            text_chunks.append(template_file.read_text(encoding="utf-8-sig"))

    return _SymbolIndex(
        identifier_names=frozenset(identifier_names),
        class_attribute_names=class_attribute_names,
        text_content="\n".join(text_chunks),
    )


def _resolve_bare_identifier(word: str, index: _SymbolIndex) -> bool:
    """*word* resolves if it is a real declared/used Python identifier
    anywhere in the axis's src trees, OR appears as a whole token
    (word-boundary matched, never a bare substring) inside a string-literal
    constant or a Jinja template -- see module docstring for why both
    surfaces are searched."""
    if word in index.identifier_names:
        return True
    return re.search(rf"\b{re.escape(word)}\b", index.text_content) is not None


def _line_within_file(path: Path, line_number: int) -> bool:
    """True iff *line_number* (1-indexed) is within *path*'s line count."""
    if line_number < 1:
        return False
    with path.open(encoding="utf-8-sig") as handle:
        line_count = sum(1 for _ in handle)
    return line_number <= line_count


def _resolve_file_line_candidate(match: re.Match[str], src_dirs: frozenset[Path]) -> bool:
    """A `file.py:NN` candidate resolves only if a file matching the named
    path (either the exact relative path under some *src_dirs* entry, or --
    for a bare filename with no directory component -- any file of that name
    anywhere under *src_dirs*) exists AND *NN* is within that file's line
    count."""
    relative_path = Path(match.group(1))
    line_number = int(match.group(2))

    candidate_files: list[Path] = []
    for src_dir in src_dirs:
        direct = src_dir / relative_path
        if direct.is_file():
            candidate_files.append(direct)
        candidate_files.extend(found for found in src_dir.rglob(relative_path.name) if found.is_file())

    return any(_line_within_file(found, line_number) for found in candidate_files)


def resolve_candidate(candidate: str, src_dirs: frozenset[Path]) -> bool:
    """Resolve one candidate against *src_dirs* -- the axis's own package `src/`
    trees (from `discover_target_package_src_dirs`).

    A `file.py:NN` candidate is dispatched to `_resolve_file_line_candidate`.
    A DOTTED candidate whose base segment names a real class in the tree is
    resolved strictly: the final segment must be an attribute that specific
    class defines or assigns (see `_class_body_field_names` /
    `_class_assigned_attribute_names`) -- a class existing does not launder a
    nonexistent attribute on it. A dotted candidate whose base is NOT a
    recognized class (e.g. a generated-language receiver like `this.field`)
    falls back to resolving each segment independently, the same way a bare
    identifier does.

    Args:
        candidate: One extracted candidate string.
        src_dirs: The axis's package source roots to search.

    Returns:
        True if the candidate resolves somewhere under *src_dirs*.

    Raises:
        SyntaxError: If a `.py` file under *src_dirs* cannot be parsed.
    """
    file_line_match = _FILE_LINE_RE.match(candidate)
    if file_line_match:
        return _resolve_file_line_candidate(file_line_match, src_dirs)

    index = _build_symbol_index(src_dirs)
    segments = candidate.split(".")
    if len(segments) == 1:
        return _resolve_bare_identifier(segments[0], index)

    base, final = segments[0], segments[-1]
    if base in index.class_attribute_names:
        return final in index.class_attribute_names[base]
    return _resolve_bare_identifier(base, index) and _resolve_bare_identifier(final, index)


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


def _load_classifications(path: Path, axis: str) -> dict[str, dict[str, object]]:
    """Load *path*'s `classifications` map.

    Args:
        path: A classification JSON file (language or platform axis).
        axis: The axis being loaded, named in error messages.

    Returns:
        The parsed `classifications` object.

    Raises:
        ValueError: If *path* does not exist, or its top-level shape is wrong.
    """
    if not path.exists():
        raise ValueError(
            _four_part_message(
                what=f"axis={axis}: classification file {path} does not exist.",
                expected="a classification file present for every axis this gate supports.",
                valid_options=f"create {path} via that axis's classification process.",
                fix=f"run the axis's classification task and commit the resulting file at {path} before running this gate.",
            )
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    classifications = data.get("classifications")
    if not isinstance(classifications, dict):
        raise ValueError(
            _four_part_message(
                what=f"Malformed classification file {path}: top-level 'classifications' key is {type(classifications).__name__}, not an object.",
                expected="an object mapping each drifted name to its {status, reason, collapsibility} entry.",
                valid_options="{'_comment': [...], 'classifications': {name: {...}, ...}}",
                fix="regenerate the file via that axis's classification process rather than hand-editing its top-level structure.",
            )
        )
    return classifications


def scan_axis(axis: str) -> list[DeadSymbolReference]:
    """Load *axis*'s classification file, extract every candidate from every
    entry's `reason` and `collapsibility.reason`, and resolve each against that
    axis's own package `src/` trees.

    Args:
        axis: `AXIS_LANGUAGES` or `AXIS_PLATFORMS`.

    Returns:
        One `DeadSymbolReference` per candidate that failed to resolve.

    Raises:
        ValueError: If the classification file is missing or malformed, or a
            registered target cannot be resolved to an on-disk package.
        SyntaxError: If a `.py` file under the axis's src trees cannot be parsed.
    """
    classification_path = _AXIS_CLASSIFICATION_PATHS[axis]
    classifications = _load_classifications(classification_path, axis)

    target_names = _AXIS_NAME_RESOLVERS[axis]()
    target_src_dirs = discover_target_package_src_dirs(axis, target_names, WORKSPACE_ROOT)
    src_dirs = frozenset(target_src_dirs.values())

    dead_refs: list[DeadSymbolReference] = []
    for name, entry in sorted(classifications.items()):
        reason = entry.get("reason") or ""
        for candidate in sorted(extract_candidates(reason)):
            if not resolve_candidate(candidate, src_dirs):
                dead_refs.append(DeadSymbolReference(entry_name=name, field="reason", candidate=candidate))

        collapsibility = entry.get("collapsibility")
        collapsibility_reason = collapsibility.get("reason") if isinstance(collapsibility, dict) else ""
        collapsibility_reason = collapsibility_reason or ""
        for candidate in sorted(extract_candidates(collapsibility_reason)):
            if not resolve_candidate(candidate, src_dirs):
                dead_refs.append(
                    DeadSymbolReference(entry_name=name, field="collapsibility.reason", candidate=candidate)
                )

    return dead_refs


def _dead_symbol_message(axis: str, ref: DeadSymbolReference) -> str:
    """The repo-mandated four-part message for one `DeadSymbolReference`."""
    return _four_part_message(
        what=f"axis={axis}: entry {ref.entry_name!r}'s `{ref.field}` cites `{ref.candidate}`, which does not "
        f"resolve to anything in axis={axis}'s live src trees.",
        expected="every code symbol or file.py:NN citation in `reason`/`collapsibility.reason` to resolve to "
        "something that currently exists.",
        valid_options=f"a symbol, or a file:line, that exists in axis={axis}'s src trees.",
        fix=f"correct entry {ref.entry_name!r}'s `{ref.field}` field on axis={axis} to cite a live symbol, or "
        "remove the dead citation from the prose.",
    )


# ---------------------------------------------------------------------------
# Non-vacuity self-test: plant / observe / revert
# ---------------------------------------------------------------------------


def _assert(condition: bool, label: str) -> bool:
    if condition:
        print(f"[OK] {label}")
    else:
        print(f"[FAIL] {label}")
    return condition


def _self_test_extraction() -> bool:
    """`extract_candidates`: schema vocabulary excluded, dot-prefixed spans
    are never candidates (trap #2), and a citation inside a NEGATION sentence
    is still extracted (trap #1 -- this module never parses negation)."""
    ok = True

    sample_text = (
        "the `reason` field is schema prose and must be excluded; this cites "
        f"`{_SELF_TEST_DEAD_SYMBOL}` and a dot-prefixed span "
        "`.dot_prefixed_never_matches` that the identifier-shaped regex cannot match at all."
    )
    candidates = extract_candidates(sample_text)
    ok &= _assert(_SELF_TEST_DEAD_SYMBOL in candidates, "a real backtick-quoted identifier is extracted")
    ok &= _assert("reason" not in candidates, "schema-prose vocabulary word 'reason' is excluded from candidates")
    ok &= _assert(
        "dot_prefixed_never_matches" not in candidates and ".dot_prefixed_never_matches" not in candidates,
        "a dot-prefixed backtick span never matches the identifier-shaped regex (trap #2) -- it is never a candidate",
    )

    negation_text = f"the generator no longer defines `{_SELF_TEST_DEAD_SYMBOL}` at all -- it was fully removed."
    ok &= _assert(
        _SELF_TEST_DEAD_SYMBOL in extract_candidates(negation_text),
        "a citation inside a negation sentence is still extracted as a candidate (trap #1 -- no negation parsing)",
    )
    return ok


def _write_self_test_package(package_dir: Path) -> None:
    """Plant one synthetic package: a present function, and a class that
    declares one attribute but NOT another -- mirroring the real
    RemoteConfigBackendSpec/maven_coordinates shape this task exists to catch."""
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "module.py").write_text(
        f"def {_SELF_TEST_PRESENT_FUNCTION}() -> None:\n"
        "    return None\n"
        "\n"
        "\n"
        f"class {_SELF_TEST_CLASS_NAME}:\n"
        '    """A synthetic spec class, mirroring RemoteConfigBackendSpec: it\n'
        f"    declares {_SELF_TEST_PRESENT_ATTR} only -- {_SELF_TEST_ABSENT_ATTR} is\n"
        '    never part of it.\n'
        '    """\n'
        "\n"
        f"    {_SELF_TEST_PRESENT_ATTR}: str\n",
        encoding="utf-8",
    )


def _self_test_resolution() -> bool:
    """`resolve_candidate`: plant a dead-symbol reason, prove it does not
    resolve; a genuinely present symbol resolves; a dotted citation onto an
    attribute a real (synthetic) class does NOT define still fails even
    though the class itself exists; the same class's genuinely declared
    attribute resolves; and `file.py:NN` resolution behaves for both an
    in-range and an out-of-range line."""
    ok = True
    tmp_dir = Path(tempfile.mkdtemp(prefix="classification-symbol-existence-selftest-"))
    try:
        package_dir = tmp_dir / "self_test_pkg"
        _write_self_test_package(package_dir)
        src_dirs = frozenset({package_dir})
        module_line_count = sum(1 for _ in (package_dir / "module.py").open(encoding="utf-8"))

        # PLANT: a dead-symbol citation must not resolve.
        ok &= _assert(
            resolve_candidate(_SELF_TEST_DEAD_SYMBOL, src_dirs) is False,
            f"planted dead symbol {_SELF_TEST_DEAD_SYMBOL!r} does not resolve against the synthetic tree",
        )

        # REVERT: a symbol genuinely present in the synthetic tree resolves.
        ok &= _assert(
            resolve_candidate(_SELF_TEST_PRESENT_FUNCTION, src_dirs) is True,
            f"a symbol genuinely present ({_SELF_TEST_PRESENT_FUNCTION!r}) in the synthetic tree resolves",
        )

        # Dotted-attribute ownership: the class exists, the cited attribute
        # does not -- must still fail (the RemoteConfigBackendSpec shape).
        dead_dotted = f"{_SELF_TEST_CLASS_NAME}.{_SELF_TEST_ABSENT_ATTR}"
        ok &= _assert(
            resolve_candidate(dead_dotted, src_dirs) is False,
            f"a class that exists ({_SELF_TEST_CLASS_NAME!r}) with a cited attribute it does NOT define "
            f"({_SELF_TEST_ABSENT_ATTR!r}) still fails to resolve",
        )
        live_dotted = f"{_SELF_TEST_CLASS_NAME}.{_SELF_TEST_PRESENT_ATTR}"
        ok &= _assert(
            resolve_candidate(live_dotted, src_dirs) is True,
            f"the same class's genuinely declared attribute ({_SELF_TEST_PRESENT_ATTR!r}) resolves",
        )

        # `file.py:NN` resolution: in-range resolves, out-of-range does not.
        ok &= _assert(
            resolve_candidate(f"module.py:{module_line_count}", src_dirs) is True,
            "a file.py:NN citation within the file's real line count resolves",
        )
        ok &= _assert(
            resolve_candidate(f"module.py:{module_line_count + 500}", src_dirs) is False,
            "a file.py:NN citation past the file's real line count does not resolve",
        )
        ok &= _assert(
            resolve_candidate(f"does_not_exist.py:{1}", src_dirs) is False,
            "a file.py:NN citation naming a file that does not exist does not resolve",
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # KNOWN-PRESENT real symbol, resolved against THIS module's own directory
    # -- proves the scan finds a real, currently-live symbol via the exact
    # same resolver the real gate uses, not only a synthetic fixture. A scan
    # that can only ever return zero, or can only ever flag a synthetic
    # plant, is not evidence.
    this_module_dir = frozenset({_HERE.parent})
    ok &= _assert(
        resolve_candidate("scan_axis", this_module_dir) is True,
        "a known-present real symbol (scan_axis, this module's own function) resolves against this module's own file",
    )
    # Built by runtime concatenation of several small literal pieces, never as
    # ONE literal string constant, so the word itself is never embedded
    # verbatim anywhere in this module's own source (unlike `_SELF_TEST_DEAD_
    # SYMBOL`, which this self-test's own messages legitimately quote as a
    # string literal many times over, and would therefore trivially "resolve"
    # against this module's own directory for a reason that has nothing to do
    # with the resolver being correct).
    never_literal_word = "".join(("genuinely_", "absent_", "from_", "this_", "gate_", "module_", "z9q7"))
    ok &= _assert(
        resolve_candidate(never_literal_word, this_module_dir) is False,
        "a symbol absent from this module's own directory does not resolve against it",
    )
    return ok


def run_non_vacuity_self_test() -> bool:
    """Plant a classification entry whose reason names a symbol that cannot
    exist, prove the scan reports it; revert, prove the count clears; and prove a
    known-present symbol (e.g. this module's own `scan_axis`) is NOT reported. A
    scan that can only return zero is not evidence.

    Returns:
        True iff every assertion passed.
    """
    return _self_test_extraction() & _self_test_resolution()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    """CLI entry point.

    Returns:
        0 (clean run or successful `--self-test`), 1 (at least one dead-symbol
        reference found), 2 (self-test failed or a discovery/parse error).
    """
    parser = argparse.ArgumentParser(
        description="Classification-reason symbol-existence gate for the parallel-implementation drift classification files.",
    )
    parser.add_argument("--axis", choices=(AXIS_LANGUAGES, AXIS_PLATFORMS), default=AXIS_LANGUAGES)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format="%(levelname)s: %(message)s")

    if not run_non_vacuity_self_test():
        logger.error("NON-VACUITY SELF-TEST FAILED -- aborting before any real check is trusted.")
        return EXIT_USAGE
    logger.info("non-vacuity self-test: PASS")

    if args.self_test:
        return EXIT_OK

    try:
        dead_refs = scan_axis(args.axis)
    except (ValueError, ImportError, SyntaxError) as exc:
        logger.error("SYMBOL-EXISTENCE GATE CANNOT RUN: %s", exc)
        return EXIT_USAGE

    for ref in dead_refs:
        logger.error(_dead_symbol_message(args.axis, ref))

    if dead_refs:
        logger.error("%d dead-symbol reference(s) found on axis=%s.", len(dead_refs), args.axis)
        return EXIT_FAIL

    logger.info("Symbol-existence gate clean (axis=%s).", args.axis)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
