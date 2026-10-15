#!/usr/bin/env python3
r"""Observability native-only example-conformance guard.

Scans every datrix/examples/**/config/system.dcfg for an observability
provider pairing the platform-boundary rule forbids: a PORTABLE provider (one
no cloud platform declares as native) configured together with a CLOUD
deployment target (provider aws or azure) in the SAME resolved profile.
Verified (2026-07-18) that every current example observability block sits on
a LOCAL target; this script is the RETAINED standing guard against future
drift.

Every profile of every system.dcfg is checked (not just the default "test"
profile) -- a violation could hide in a non-default profile whose deployment
or observability block overrides the base.

Uses the real config pipeline (datrix_common.config.unified_loader.
load_system_config over datrix_language's disk config document source) to resolve
each profile, exactly as datrix_cli's generation pipeline does -- never a
hand-rolled regex/text scan of the DSL, which cannot correctly follow
profile inheritance.

A built-in self-test (real tempfile.TemporaryDirectory() fixtures: one
hand-crafted violation, one clean LOCAL example, one clean cloud-native
example) runs as step 1 of every normal invocation, like
check_docs_conformance.py -- a self-test failure aborts with exit 2 before
any real result is trusted.

Exit codes:
    0: No violations found (or --warn mode, or a successful --self-test).
    1: At least one violation found (or --self-test reports a failing check).
    2: Usage error, missing examples root, or the automatic self-test step
       failing on a normal invocation.
"""

from __future__ import annotations

import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from datrix_common.errors.generation import GenerationError
from datrix_common.protocols.parser import ConfigDocumentSourceProtocol

from datrix_scripts.gate_harness import (
    EXIT_PASS,
    EXIT_USAGE,
    EXIT_VIOLATION,
    NamedCheck,
    gate_argument_parser,
    harness_self_test,
    named_checks,
    report_step,
    run_checks,
)
from datrix_scripts.paths import SHOWCASE_DIR

# Matches the exact f-string in datrix_common.plugin.capability_resolution.
# validate_native_observability_providers (module line ~937-943):
#   f"Platform {platform_name!r} ({declaration.platform_label}) does "
#   f"not natively realize {category} provider {provider_value!r}. "
# This substring ("does not natively realize <category> provider '<value>'")
# is unique to that one validator (grepped the whole datrix-common src tree --
# no other GenerationError site uses it, e.g. the platform-surface checks word
# their refusals as "... is not realizable on platform ..." instead), so a match
# proves the GenerationError came from the native-only observability guard and
# not from an unrelated config defect (bad config-store compatibility, an
# unrealizable network/serviceDiscovery/registry surface, etc).
_NATIVE_ONLY_VIOLATION_PATTERN = re.compile(
    r"^Platform '(?P<platform>[^']+)' \([^)]*\) does not natively realize "
    r"(?P<category>\w+) provider '(?P<provider>[^']+)'\."
)

# Portable provider values per category (values with no native cloud-platform
# realization, mirrored from the provider enums in models.py:26-62).
# "datadog" stays listed even if MetricsProvider.DATADOG is later removed
# from the enum independently -- harmless either way, since a value no
# config can produce simply never matches.
PORTABLE_METRICS_PROVIDERS: frozenset[str] = frozenset({"prometheus", "datadog"})
PORTABLE_TRACING_PROVIDERS: frozenset[str] = frozenset({"jaeger", "zipkin"})
PORTABLE_LOGGING_PROVIDERS: frozenset[str] = frozenset({"loki"})
PORTABLE_VISUALIZATION_PROVIDERS: frozenset[str] = frozenset({"grafana"})
PORTABLE_ALERTING_PROVIDERS: frozenset[str] = frozenset({"alertmanager"})

# Cloud deployment provider values (the cloud deployment targets datrix supports).
CLOUD_DEPLOYMENT_PROVIDERS: frozenset[str] = frozenset({"aws", "azure"})


@dataclass(frozen=True)
class Violation:
    """One (example, profile, category, provider) pairing that violates the native-only observability rule."""

    example: str  # repo-relative path to the system.dcfg
    profile: str  # resolved profile name
    category: str  # "metrics" | "tracing" | "logging" | "visualization" | "alerting"
    provider: str  # the portable provider value found
    deployment_provider: str  # "aws" | "azure"


def discover_system_configs(examples_root: Path) -> list[Path]:
    """Every examples/**/config/system.dcfg, sorted -- never hard-coded."""
    return sorted(examples_root.rglob("config/system.dcfg"))


def profile_names(config_path: Path, documents: ConfigDocumentSourceProtocol) -> list[str]:
    """Every resolvable profile name declared in a system.dcfg, read through *documents*."""
    decl = documents.config_document(config_path)
    return [profile.name for profile in decl.profiles]


def check_profile(
    config_path: Path,
    project_root: Path,
    profile: str,
    example_relpath: str,
    documents: ConfigDocumentSourceProtocol,
) -> list[Violation]:
    """Resolve one profile and return every native-only-observability violation it contains.

    ``load_system_config`` itself wires a native-only observability
    ``@model_validator`` onto ``SystemConfigProfileConfig`` (see
    ``validate_native_observability_providers`` in
    ``datrix_common.plugin.capability_resolution``), which raises
    ``GenerationError`` for exactly a cloud+portable pairing -- before this
    function's own resolved-config inspection below would otherwise catch it.
    That raise IS a violation the live validator detected, so it is caught
    and converted into a ``Violation`` here rather than left to abort the
    scan. A ``GenerationError`` whose message does NOT match the native-only
    observability pattern is a genuinely unrelated failure (a pre-existing
    example-config defect on a different validator, e.g. config-store
    compatibility or an unrealizable network/serviceDiscovery/registry
    surface) and is re-raised unchanged, exactly like ``scan_examples``'s
    docstring says an unrelated load failure must -- never silently
    swallowed as a native-only violation.
    """
    from datrix_common.config.unified_loader import load_system_config

    try:
        unified = load_system_config(
            config_path=config_path,
            project_root=project_root,
            profile=profile,
            documents=documents,
        )
    except GenerationError as e:
        match = _NATIVE_ONLY_VIOLATION_PATTERN.match(str(e))
        if match is None:
            raise
        return [
            Violation(
                example_relpath,
                profile,
                match.group("category"),
                match.group("provider"),
                match.group("platform"),
            )
        ]
    deployment_provider = str(unified.system.deployment.provider)
    if deployment_provider not in CLOUD_DEPLOYMENT_PROVIDERS:
        return []
    observability = unified.observability
    if observability is None:
        return []

    violations: list[Violation] = []

    def _record(category: str, provider_value: str) -> None:
        violations.append(
            Violation(example_relpath, profile, category, provider_value, deployment_provider)
        )

    if observability.metrics is not None:
        value = str(observability.metrics.provider)
        if value in PORTABLE_METRICS_PROVIDERS:
            _record("metrics", value)
    if observability.tracing is not None:
        value = str(observability.tracing.provider)
        if value in PORTABLE_TRACING_PROVIDERS:
            _record("tracing", value)
    if observability.logging is not None and observability.logging.provider is not None:
        value = str(observability.logging.provider)
        if value in PORTABLE_LOGGING_PROVIDERS:
            _record("logging", value)
    if observability.visualization is not None:
        value = str(observability.visualization.provider)
        if value in PORTABLE_VISUALIZATION_PROVIDERS:
            _record("visualization", value)
    if observability.alerting is not None:
        value = str(observability.alerting.provider)
        if value in PORTABLE_ALERTING_PROVIDERS:
            _record("alerting", value)

    return violations


def scan_examples(examples_root: Path) -> list[Violation]:
    """Scan every example's every profile; return every violation found.

    A load_system_config failure unrelated to this guard (a pre-existing
    example config defect) is never caught-and-skipped -- it propagates,
    exactly like generate.ps1 does for the same example. Every ``.dcfg`` is
    read through one config document source, so each is parsed once per scan.
    """
    from datrix_language.parser.dcfg_documents import disk_config_documents

    documents = disk_config_documents()
    violations: list[Violation] = []
    for config_path in discover_system_configs(examples_root):
        config_path = config_path.resolve()
        project_root = config_path.parent.parent
        example_relpath = str(config_path.relative_to(examples_root.resolve().parent))
        for profile in profile_names(config_path, documents):
            violations.extend(
                check_profile(config_path, project_root, profile, example_relpath, documents)
            )
    return sorted(violations, key=lambda v: (v.example, v.profile, v.category))


# --------------------------------------------------------------------------
# --self-test: real tempfile.TemporaryDirectory() fixtures, no mocks.
# --------------------------------------------------------------------------

#: The self-test fixtures deliberately carry no ``language`` key: the generation
#: target is a CLI input (``datrix generate --language <lang>``), not system
#: configuration, and ``SystemConfigProfileConfig`` rejects it outright. A fixture
#: carrying it aborts this gate before a single real check runs.
_VIOLATION_DCFG = """config system fixture.System {
  base {
    deployment {
      runtime = "ecs-fargate";
      provider = "aws";
    }
    observability {
      metrics {
        provider = "prometheus";
      }
    }
  }

  profile test as "test" extends base {
  }
}
"""

_CLEAN_LOCAL_DCFG = """config system fixture.System {
  base {
    deployment {
      runtime = "docker-compose";
      provider = "local";
    }
    observability {
      metrics {
        provider = "prometheus";
      }
    }
  }

  profile test as "test" extends base {
  }
}
"""

_CLEAN_CLOUD_NATIVE_DCFG = """config system fixture.System {
  base {
    deployment {
      runtime = "ecs-fargate";
      provider = "aws";
    }
    observability {
      metrics {
        provider = "cloudwatch";
      }
    }
  }

  profile test as "test" extends base {
  }
}
"""


def _write_fixture_example(examples_root: Path, name: str, dcfg_text: str) -> None:
    config_dir = examples_root / name / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "system.dcfg").write_text(dcfg_text, encoding="utf-8")


def _check_cloud_plus_portable_metrics_is_flagged() -> None:
    with tempfile.TemporaryDirectory(prefix="obs-native-only-selftest-") as tmp:
        examples_root = Path(tmp) / "examples"
        _write_fixture_example(examples_root, "bad-example", _VIOLATION_DCFG)
        violations = scan_examples(examples_root)
        assert len(violations) == 1, f"expected 1 violation, got {violations}"
        assert violations[0].category == "metrics"
        assert violations[0].provider == "prometheus"
        assert violations[0].deployment_provider == "aws"


def _check_local_with_portable_metrics_is_clean() -> None:
    with tempfile.TemporaryDirectory(prefix="obs-native-only-selftest-") as tmp:
        examples_root = Path(tmp) / "examples"
        _write_fixture_example(examples_root, "good-local-example", _CLEAN_LOCAL_DCFG)
        assert scan_examples(examples_root) == []


def _check_cloud_with_native_metrics_is_clean() -> None:
    with tempfile.TemporaryDirectory(prefix="obs-native-only-selftest-") as tmp:
        examples_root = Path(tmp) / "examples"
        _write_fixture_example(examples_root, "good-cloud-example", _CLEAN_CLOUD_NATIVE_DCFG)
        assert scan_examples(examples_root) == []


_SELF_TEST_CHECKS: list[NamedCheck] = named_checks(
    [
        _check_cloud_plus_portable_metrics_is_flagged,
        _check_local_with_portable_metrics_is_clean,
        _check_cloud_with_native_metrics_is_clean,
    ]
)


def main() -> int:
    parser = gate_argument_parser("Observability native-only example-conformance guard")
    parser.add_argument("-w", "--warn", action="store_true", help="Report violations but exit 0")
    parser.add_argument(
        "--examples-root",
        type=Path,
        default=None,
        help="Override examples root (default: auto-detect datrix/examples)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Print each system.dcfg scanned"
    )
    args = parser.parse_args()

    if args.harness_self_test:
        return EXIT_PASS if harness_self_test() else EXIT_VIOLATION
    report_step("Self-test: observability native-only guard scanner edge cases")
    self_test_passed = run_checks(_SELF_TEST_CHECKS)
    if args.self_test:
        return EXIT_PASS if self_test_passed else EXIT_VIOLATION
    if not self_test_passed:
        print("\nError: self-test failed -- refusing to trust the scanner.", file=sys.stderr)
        return EXIT_USAGE

    examples_root = args.examples_root.resolve() if args.examples_root else SHOWCASE_DIR / "examples"

    if not examples_root.is_dir():
        print(f"Error: examples root not found: {examples_root}", file=sys.stderr)
        return 2

    if args.verbose:
        for config_path in discover_system_configs(examples_root):
            print(f"  - {config_path}", file=sys.stderr)

    violations = scan_examples(examples_root)

    if violations:
        mode = "Warning" if args.warn else "Error"
        print(f"{mode}: {len(violations)} native-only observability violation(s):\n")
        for v in violations:
            print(
                f"{v.example} (profile={v.profile}): {v.category}={v.provider} "
                f"paired with cloud deployment provider={v.deployment_provider}"
            )
        if args.warn:
            return 0
        return 1

    if args.verbose:
        print("No native-only observability violations found.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
