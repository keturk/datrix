"""Regression tests for the ConfigDSL formatter (``config_linter.format_dcfg``).

Guards the round-trip fidelity bugs that previously let the formatter silently
corrupt ``.dcfg`` files: dropping ``replace ... from tpl() { body }`` bodies and
``inheriting base`` clauses, and emitting the name-less ``service`` wildcard as
the invalid token ``service *``. Also covers the fail-safe that declines to
rewrite a file when formatting would drop comments.
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

# config_linter.py lives one directory up from this tests/ folder.
_LINTER_PATH = Path(__file__).resolve().parents[1] / "config_linter.py"
_MODULE_ALIAS = "config_linter_under_test"

if _MODULE_ALIAS not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_MODULE_ALIAS, _LINTER_PATH)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Could not load config_linter from {_LINTER_PATH}")
    _mod: types.ModuleType = importlib.util.module_from_spec(_spec)
    sys.modules[_MODULE_ALIAS] = _mod
    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_linter = sys.modules[_MODULE_ALIAS]

_SOURCE_NO_COMMENTS = """config service test.Foo {
  base {
    pubsub fooEvents from kafkaContainer();
    rdbms fooDb from postgresContainer(id: "x", database: "d", schema: "s");
    resilience {
      dependencyPolicy {
        defaults {
          service from standardServicePolicy();
        }
      }
    }
  }

  profile production as "prod" extends base {
    replace pubsub fooEvents from eventHubsKafka() {
      namespaceGroup = "core-events";
    }
    replace rdbms fooDb from postgresFlexibleServer() inheriting base {
      serverGroup = "core";
    }
  }
}
"""


@pytest.mark.unit
class TestFormatterRoundTripFidelity:
    """The formatter must change only whitespace, never meaning."""

    def test_semantic_constructs_survive_formatting(self) -> None:
        formatted, _issues, error = _linter.format_dcfg(
            _SOURCE_NO_COMMENTS, Path("test.dcfg")
        )
        assert error is None
        # Name-less service wildcard must not become the invalid token "service *".
        assert "service from standardServicePolicy();" in formatted
        assert "service * from" not in formatted
        # replace-with-body and inheriting base must be preserved, not dropped.
        assert 'namespaceGroup = "core-events";' in formatted
        assert "inheriting base" in formatted
        assert 'serverGroup = "core";' in formatted

    def test_formatted_output_is_idempotent(self) -> None:
        once, _i1, _e1 = _linter.format_dcfg(_SOURCE_NO_COMMENTS, Path("t.dcfg"))
        twice, _i2, _e2 = _linter.format_dcfg(once, Path("t.dcfg"))
        assert once == twice


@pytest.mark.unit
class TestFormatterFailSafe:
    """The formatter refuses to write rather than drop content."""

    def test_comment_bearing_file_is_left_unchanged(self) -> None:
        source = "// keep this note\n" + _SOURCE_NO_COMMENTS
        formatted, issues, error = _linter.format_dcfg(source, Path("t.dcfg"))
        assert error is None
        # Unchanged source returned; a blocking issue explains why.
        assert formatted == source
        assert any("comment" in issue.message.lower() for issue in issues)
