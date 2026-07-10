"""Unit tests for the I5 docs-conformance gate scanner (design 026).

Real temporary files and real filesystem checks under ``tmp_path`` only -- no
mocks, no ``SimpleNamespace`` -- per project test guidelines. Covers design
026, Invariant I5.

The resolution functions under test (``resolve_path_candidate``,
``resolve_module_candidate``) hardcode the fixed 13 package-directory names /
12 import names as module-level constants (by design -- see the scanner's
own module docstring), so every fixture below is built under one of those
REAL names (``datrix-common``, ``datrix-codegen-common``) inside ``tmp_path``
acting as a fake monorepo root, rather than an arbitrary made-up package name.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

_SCANNER_PATH = (
    Path(__file__).resolve().parents[4] / "scripts" / "test" / "check-docs-conformance.py"
)

_MODULE_ALIAS = "check_docs_conformance"

if _MODULE_ALIAS not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_MODULE_ALIAS, _SCANNER_PATH)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Could not load scanner module from {_SCANNER_PATH}")
    _mod: types.ModuleType = importlib.util.module_from_spec(_spec)
    sys.modules[_MODULE_ALIAS] = _mod
    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_scanner = sys.modules[_MODULE_ALIAS]

extract_path_candidates = _scanner.extract_path_candidates
extract_module_candidates = _scanner.extract_module_candidates
resolve_path_candidate = _scanner.resolve_path_candidate
resolve_module_candidate = _scanner.resolve_module_candidate
load_exceptions = _scanner.load_exceptions
check_against_exceptions = _scanner.check_against_exceptions
UnresolvedReference = _scanner.UnresolvedReference


@pytest.mark.unit
class TestExtractPathCandidates:
    """Extraction step 1 + 2: which backtick spans are path-reference candidates."""

    def test_windows_absolute_span_is_a_candidate(self) -> None:
        doc_text = "See `D:\\datrix\\datrix-common\\src\\datrix_common\\foo.py` for details."
        candidates = extract_path_candidates(doc_text)
        assert len(candidates) == 1
        assert candidates[0][1] == "D:\\datrix\\datrix-common\\src\\datrix_common\\foo.py"

    def test_package_prefixed_span_is_a_candidate(self) -> None:
        doc_text = "See `datrix-common/src/datrix_common/foo.py` for details."
        candidates = extract_path_candidates(doc_text)
        assert len(candidates) == 1
        assert candidates[0][1] == "datrix-common/src/datrix_common/foo.py"

    def test_bare_span_with_no_package_prefix_is_excluded(self) -> None:
        doc_text = "See `foo.py` for details."
        candidates = extract_path_candidates(doc_text)
        assert candidates == []

    def test_ellipsis_elided_span_is_rejected(self) -> None:
        doc_text = "See `datrix-codegen-common/.../subdir/file.py` for details."
        candidates = extract_path_candidates(doc_text)
        assert candidates == []

    def test_placeholder_span_is_rejected(self) -> None:
        doc_text = (
            "Baselines live at "
            "`datrix-codegen-common/tests/parity/baselines/<example_id>/<language>.sha256`."
        )
        candidates = extract_path_candidates(doc_text)
        assert candidates == []

    def test_glob_span_is_rejected(self) -> None:
        doc_text = "See `datrix-common/src/datrix_common/*.py` for details."
        candidates = extract_path_candidates(doc_text)
        assert candidates == []

    def test_line_ref_suffix_is_captured_verbatim_by_extraction(self) -> None:
        """Extraction captures the raw span including any :LINE suffix --
        stripping happens later, in resolve_path_candidate."""
        doc_text = "See `datrix-common/src/datrix_common/foo.py:42` for details."
        candidates = extract_path_candidates(doc_text)
        assert len(candidates) == 1
        assert candidates[0][1] == "datrix-common/src/datrix_common/foo.py:42"

    def test_line_number_is_tracked_per_span(self) -> None:
        doc_text = "line one\nline two\n`datrix-common/src/datrix_common/foo.py`\n"
        candidates = extract_path_candidates(doc_text)
        assert len(candidates) == 1
        assert candidates[0][0] == 3


@pytest.mark.unit
class TestExtractModuleCandidates:
    """Extraction step 1 (module shape): fully import-qualified dotted chains only."""

    def test_fully_qualified_module_span_is_a_candidate(self) -> None:
        doc_text = "See `datrix_common.generation.type_resolver` for details."
        candidates = extract_module_candidates(doc_text)
        assert len(candidates) == 1
        assert candidates[0][1] == "datrix_common.generation.type_resolver"

    def test_generic_dotted_identifier_without_known_import_name_is_excluded(self) -> None:
        doc_text = "Set `service.name` to the desired value."
        candidates = extract_module_candidates(doc_text)
        assert candidates == []

    def test_trailing_class_name_segment_is_excluded_from_extraction(self) -> None:
        """A trailing PascalCase class name breaks the module regex outright
        -- such spans are never candidates (deliberately, see module docstring)."""
        doc_text = "See `datrix_codegen_common.orchestration.hooks.seed_hooks.SeedGeneratorHooks`."
        candidates = extract_module_candidates(doc_text)
        assert candidates == []


@pytest.mark.unit
class TestResolvePathCandidateTier1:
    def test_tier1_literal_match_resolves(self, tmp_path: Path) -> None:
        target = tmp_path / "datrix-common" / "src" / "datrix_common" / "foo.py"
        target.parent.mkdir(parents=True)
        target.write_text("x = 1\n", encoding="utf-8")

        assert resolve_path_candidate("datrix-common/src/datrix_common/foo.py", tmp_path) is True

    def test_tier1_directory_hint_requires_a_real_directory(self, tmp_path: Path) -> None:
        (tmp_path / "datrix-common" / "src" / "datrix_common").mkdir(parents=True)
        # A file (not a directory) at the trailing-slash candidate's path must not resolve.
        file_masquerading_as_dir = tmp_path / "datrix-common" / "src" / "datrix_common" / "notadir"
        file_masquerading_as_dir.write_text("x\n", encoding="utf-8")

        assert resolve_path_candidate("datrix-common/src/datrix_common/notadir/", tmp_path) is False

    def test_genuinely_missing_path_stays_unresolved(self, tmp_path: Path) -> None:
        (tmp_path / "datrix-common" / "src" / "datrix_common").mkdir(parents=True)

        assert resolve_path_candidate("datrix-common/src/datrix_common/nope.py", tmp_path) is False

    def test_line_ref_suffix_is_stripped_before_resolution(self, tmp_path: Path) -> None:
        target = tmp_path / "datrix-common" / "src" / "datrix_common" / "foo.py"
        target.parent.mkdir(parents=True)
        target.write_text("x = 1\n", encoding="utf-8")

        assert resolve_path_candidate("datrix-common/src/datrix_common/foo.py:42", tmp_path) is True
        assert (
            resolve_path_candidate("datrix-common/src/datrix_common/foo.py:262-291", tmp_path)
            is True
        )
        assert (
            resolve_path_candidate("datrix-common/src/datrix_common/foo.py:262,282", tmp_path)
            is True
        )


@pytest.mark.unit
class TestResolvePathCandidateTier2:
    def test_tier2_src_shorthand_match_resolves(self, tmp_path: Path) -> None:
        target = (
            tmp_path
            / "datrix-codegen-common"
            / "src"
            / "datrix_codegen_common"
            / "orchestration"
            / "hooks"
            / "seed_hooks.py"
        )
        target.parent.mkdir(parents=True)
        target.write_text("x = 1\n", encoding="utf-8")

        # Package name immediately followed by "orchestration" (neither src/
        # nor tests/), so Tier 2 shorthand search is attempted and finds the
        # unique match under src/.
        assert (
            resolve_path_candidate(
                "datrix-codegen-common/orchestration/hooks/seed_hooks.py", tmp_path
            )
            is True
        )

    def test_tier2_tests_shorthand_match_resolves_with_two_segment_omission(
        self, tmp_path: Path
    ) -> None:
        """A candidate omitting BOTH the 'tests' root name and one further
        intermediate segment ('unit') still resolves, as long as the
        remaining suffix uniquely identifies one file under tests/."""
        target = (
            tmp_path / "datrix-common" / "tests" / "unit" / "generation" / "test_foo.py"
        )
        target.parent.mkdir(parents=True)
        target.write_text("def test_x(): ...\n", encoding="utf-8")

        # Package name immediately followed by "generation" (neither src/ nor
        # tests/), so Tier 2 searches both roots and finds the unique match
        # under tests/unit/generation/test_foo.py.
        assert resolve_path_candidate("datrix-common/generation/test_foo.py", tmp_path) is True

    def test_tier2_is_skipped_when_next_segment_is_already_tests(self, tmp_path: Path) -> None:
        """A candidate that already writes 'tests/' explicitly is never
        expanded by Tier 2 -- if the exact literal path doesn't exist, it
        stays unresolved (this is what real doc drift looked like: a doc
        citing 'datrix-common/tests/generation/x.py' when the real file is
        one level deeper at 'datrix-common/tests/unit/generation/x.py')."""
        target = (
            tmp_path / "datrix-common" / "tests" / "unit" / "generation" / "test_foo.py"
        )
        target.parent.mkdir(parents=True)
        target.write_text("def test_x(): ...\n", encoding="utf-8")

        assert (
            resolve_path_candidate("datrix-common/tests/generation/test_foo.py", tmp_path)
            is False
        )

    def test_ambiguous_tier2_match_stays_unresolved(self, tmp_path: Path) -> None:
        """Two real files under the fixture src/ tree whose relative paths
        both end with the same suffix -- an ambiguous match must never be
        silently guessed."""
        first = tmp_path / "datrix-common" / "src" / "datrix_common" / "foo" / "bar.py"
        second = tmp_path / "datrix-common" / "src" / "datrix_common" / "baz" / "bar.py"
        first.parent.mkdir(parents=True)
        second.parent.mkdir(parents=True)
        first.write_text("x = 1\n", encoding="utf-8")
        second.write_text("y = 2\n", encoding="utf-8")

        assert resolve_path_candidate("datrix-common/bar.py", tmp_path) is False


@pytest.mark.unit
class TestResolveModuleCandidate:
    def test_exact_module_match_resolves(self, tmp_path: Path) -> None:
        target = (
            tmp_path
            / "datrix-common"
            / "src"
            / "datrix_common"
            / "generation"
            / "type_resolver.py"
        )
        target.parent.mkdir(parents=True)
        target.write_text("class TypeResolver: ...\n", encoding="utf-8")

        assert (
            resolve_module_candidate("datrix_common.generation.type_resolver", tmp_path) is True
        )

    def test_trailing_symbol_name_is_tolerated(self, tmp_path: Path) -> None:
        target = (
            tmp_path
            / "datrix-common"
            / "src"
            / "datrix_common"
            / "generation"
            / "type_resolver.py"
        )
        target.parent.mkdir(parents=True)
        target.write_text("def _dispatch(): ...\n", encoding="utf-8")

        # The 2-segment prefix "generation/type_resolver.py" matches; the
        # trailing "_dispatch" symbol name is tolerated without needing its
        # own AST verification.
        assert (
            resolve_module_candidate(
                "datrix_common.generation.type_resolver._dispatch", tmp_path
            )
            is True
        )

    def test_package_init_module_resolves(self, tmp_path: Path) -> None:
        target = (
            tmp_path / "datrix-common" / "src" / "datrix_common" / "stdlib" / "__init__.py"
        )
        target.parent.mkdir(parents=True)
        target.write_text("", encoding="utf-8")

        assert resolve_module_candidate("datrix_common.stdlib", tmp_path) is True

    def test_genuinely_missing_module_stays_unresolved(self, tmp_path: Path) -> None:
        (tmp_path / "datrix-common" / "src" / "datrix_common").mkdir(parents=True)

        assert (
            resolve_module_candidate("datrix_common.nonexistent.module", tmp_path) is False
        )

    def test_unknown_import_name_stays_unresolved(self, tmp_path: Path) -> None:
        assert resolve_module_candidate("not_a_real_import.foo", tmp_path) is False


@pytest.mark.unit
class TestExceptionsBaselineFiltering:
    def test_span_present_in_baseline_is_removed_from_failures(self) -> None:
        unresolved = [
            UnresolvedReference(doc="pkg/docs/architecture.md", line=5, span="a/b.py", kind="path"),
            UnresolvedReference(doc="pkg/docs/architecture.md", line=9, span="c/d.py", kind="path"),
        ]
        exceptions = {"a/b.py": "legitimately removed, see migration notes"}

        failures = check_against_exceptions(unresolved, exceptions)

        assert failures == [
            UnresolvedReference(doc="pkg/docs/architecture.md", line=9, span="c/d.py", kind="path")
        ]

    def test_span_absent_from_baseline_remains_a_failure(self) -> None:
        unresolved = [
            UnresolvedReference(doc="pkg/docs/architecture.md", line=5, span="a/b.py", kind="path"),
        ]
        failures = check_against_exceptions(unresolved, {})
        assert failures == unresolved

    def test_load_exceptions_reads_span_to_reason_mapping(self, tmp_path: Path) -> None:
        baseline_path = tmp_path / "docs-conformance-exceptions.json"
        baseline_path.write_text(
            json.dumps(
                {
                    "exceptions": [
                        {"span": "a/b.py", "doc": "pkg/docs/architecture.md", "reason": "removed"},
                    ]
                }
            ),
            encoding="utf-8",
        )

        exceptions = load_exceptions(baseline_path)

        assert exceptions == {"a/b.py": "removed"}

    def test_load_exceptions_raises_when_file_missing(self, tmp_path: Path) -> None:
        missing_path = tmp_path / "does-not-exist.json"
        with pytest.raises(FileNotFoundError):
            load_exceptions(missing_path)
