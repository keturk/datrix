"""Example secret-seed gate: every example's deploy test can start its stack.

A handle a service declares in its ``secrets { }`` table is delivered to the
container as a mounted file, and the generated deployment script refuses to
start the stack while that file is absent -- by design, with nothing written
in its place, because an operator-provisioned value is a credential the
deployment does not hold. On a local secret profile the generator writes the
file only from the handle's ``localDefault``.

The example corpus is deploy-tested on the ``test`` profile by an unattended
harness with no operator in front of it. So for every example, on that
profile, every REQUIRED operator-provisioned handle must carry a ``localDefault``
-- or the example is one no full-corpus run can ever bring up, and the deploy
log is the first place anyone finds out. Three examples shipped that way the
day secret delivery moved to compose file secrets.

Violation class (fail-loud, one line per handle with the fix):
  - unseeded: a ``required = true`` handle with ``provisioningAuthority``
    ``operator`` and no ``localDefault`` in the resolved ``test`` profile of a
    service ``.dcfg``.

A handle that the profile does not need (a live-model API key on a profile
that binds ``replay``) is not seeded with a fake value; it is removed from
that profile with ``replace secrets { ... }``, and this gate then sees no
handle at all.

Built-in non-vacuity self-test, every invocation: the pure comparator is fed
synthetic handles covering every combination that must and must not be
reported, before any real config is trusted.

This module is what ``gates/repo-hygiene/example-secret-seed-gate.ps1`` (and its ``.sh`` twin) runs,
in gate mode (``datrix_scripts.gate_log.run_as_gate``): the last line is the
``[GATE] example-secret-seed PASSED|FAILED exit=<n> log=<path>`` verdict.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from datrix_common.config.dcfg.errors import DcfgResolutionError, DcfgSyntaxError
from datrix_common.config.secrets.models import LogicalSecretDef
from datrix_common.config.unified_loader import load_service_config
from datrix_common.errors.configuration import ConfigValidationError
from datrix_common.protocols.config_documents import ConfigDocumentSourceProtocol
from datrix_language.parser.dcfg_documents import disk_config_documents

from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.gates.repo_hygiene.gate_options import packages_current, self_test_gate_parser
from datrix_scripts.paths import SHOWCASE_DIR
from datrix_scripts.test import wrappers

logger = logging.getLogger(__name__)

GATE: Final = "example-secret-seed"
MODULE: Final = "datrix_scripts.gates.repo_hygiene.example_secret_seed_gate"
WRAPPER: Final = "example-secret-seed-gate"

DATRIX_DIR: Path = SHOWCASE_DIR
EXAMPLES_ROOT: Path = DATRIX_DIR / "examples"

#: The profile the unattended deploy-test harness generates and deploys.
DEPLOY_TEST_PROFILE: str = "test"

#: The provisioning authority whose values the generator never writes.
_OPERATOR_AUTHORITY: str = "operator"

#: The one ``.dcfg`` kind whose ``secrets { }`` table declares mounted handles.
_SERVICE_KIND: str = "service"

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

_UNSEEDED_MESSAGE = (
    "UNSEEDED OPERATOR SECRET example=%s config=%s handle=%s -- required, "
    "operator-provisioned, and without a localDefault in the '%s' profile, so the "
    "deploy test can never start this stack: the generator writes no file for it "
    "and the deployment script refuses to start while the file is absent. Fix: "
    "add a throwaway 'localDefault' to the handle (written on local profiles "
    "only), or, if nothing in this profile consumes the handle, drop it from the "
    "profile with 'replace secrets { ... }'."
)


# ---------------------------------------------------------------------------
# Pure comparator
# ---------------------------------------------------------------------------


def unseeded_required_operator_handles(
    secrets: Mapping[str, LogicalSecretDef],
) -> list[str]:
    """Every handle the deploy test cannot supply, in declaration order.

    Args:
        secrets: One resolved profile's logical-secret table.

    Returns:
        The handle names that are required, operator-provisioned, and carry no
        ``localDefault``.
    """
    return [
        handle
        for handle, definition in secrets.items()
        if definition.required
        and definition.provisioning_authority == _OPERATOR_AUTHORITY
        and definition.local_default is None
    ]


# ---------------------------------------------------------------------------
# Disk discovery
# ---------------------------------------------------------------------------


def discover_examples() -> list[Path]:
    """Every example directory: the parent of each ``system.dtrx``."""
    return sorted(path.parent for path in EXAMPLES_ROOT.rglob("system.dtrx"))


def service_config_paths(
    example_dir: Path, documents: ConfigDocumentSourceProtocol
) -> list[Path]:
    """The example's service-kind ``.dcfg`` files, by reading each one's kind
    through *documents*."""
    config_dir = example_dir / "config"
    if not config_dir.is_dir():
        return []
    services: list[Path] = []
    for path in sorted(config_dir.glob("*.dcfg")):
        absolute = path.resolve()
        if documents.config_document(absolute).kind == _SERVICE_KIND:
            services.append(absolute)
    return services


def example_violations(
    example_dir: Path, documents: ConfigDocumentSourceProtocol
) -> list[str]:
    """Fail-loud messages for every unseeded handle in one example's services."""
    example_id = example_dir.relative_to(EXAMPLES_ROOT).as_posix()
    messages: list[str] = []
    for config_path in service_config_paths(example_dir, documents):
        loaded = load_service_config(
            config_path, example_dir, DEPLOY_TEST_PROFILE, documents=documents
        )
        secrets = loaded.profile.secrets
        if secrets is None:
            continue
        for handle in unseeded_required_operator_handles(secrets.secrets):
            messages.append(
                _UNSEEDED_MESSAGE
                % (example_id, config_path.name, handle, DEPLOY_TEST_PROFILE)
            )
    return messages


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def run_self_test() -> list[str]:
    """Prove the comparator reports exactly the unseeded required operator handles."""
    secrets = {
        "seeded": LogicalSecretDef(name="seeded", localDefault="dev-only"),
        "unseeded": LogicalSecretDef(name="unseeded"),
        "optional": LogicalSecretDef(name="optional", required=False),
        "owned": LogicalSecretDef(
            name="owned",
            purpose="token-signing-key",
            provisioningAuthority="datrix",
        ),
        "also_unseeded": LogicalSecretDef(name="also_unseeded", purpose="vendor key"),
    }
    reported = unseeded_required_operator_handles(secrets)
    problems: list[str] = []
    if reported != ["unseeded", "also_unseeded"]:
        problems.append(
            "comparator reported %r; expected exactly ['unseeded', 'also_unseeded'] "
            "(seeded, optional and datrix-owned handles must not be reported)" % (reported,)
        )
    if unseeded_required_operator_handles({}) != []:
        problems.append("comparator reported a violation on an empty table")
    return problems


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def check_example_secret_seeds() -> int:
    """Run the gate against the real examples tree."""
    examples = discover_examples()
    if not examples:
        logger.error(
            "EXAMPLE-SECRET-SEED GATE CANNOT RUN: zero system.dtrx found under %s -- "
            "an empty corpus would make this check vacuously pass.",
            EXAMPLES_ROOT,
        )
        return EXIT_USAGE
    # One source for the whole run: every .dcfg is read and parsed once.
    documents = disk_config_documents()
    violations: list[str] = []
    services_checked = 0
    for example_dir in examples:
        services_checked += len(service_config_paths(example_dir, documents))
        violations.extend(example_violations(example_dir, documents))
    if services_checked == 0:
        logger.error(
            "EXAMPLE-SECRET-SEED GATE CANNOT RUN: %d example(s) but zero service "
            ".dcfg files parsed -- the check would verify nothing.",
            len(examples),
        )
        return EXIT_USAGE
    for message in violations:
        logger.error("  %s", message)
    if violations:
        logger.error(
            "EXAMPLE-SECRET-SEED GATE FAILED: %d unseeded handle(s) across %d example(s).",
            len(violations),
            len(examples),
        )
        return EXIT_FAIL
    logger.info(
        "EXAMPLE-SECRET-SEED GATE PASSED: %d example(s), %d service config(s), every "
        "required operator handle on the '%s' profile carries a localDefault.",
        len(examples),
        services_checked,
        DEPLOY_TEST_PROFILE,
    )
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/repo-hygiene/example-secret-seed-gate.ps1``: one per wrapper parameter,
    spelled exactly."""
    return self_test_gate_parser(
        WRAPPER,
        "Example secret-seed gate: on the deploy-test profile, every required "
        "operator-provisioned secret handle of every example carries a localDefault.",
    )


def _run(args: argparse.Namespace) -> int:
    """Run the gate.

    Returns:
        0 = every handle seeded (or a successful ``--self-test``), 1 = at least
        one unseeded handle, a failed wrapper seam check, or package installs
        that are not current, 2 = self-test failure, empty corpus, or a config
        that fails to parse or resolve.
    """
    if not packages_current():
        return EXIT_FAIL
    if not args.debug:
        # The config loader narrates every profile resolution at INFO; only
        # this gate's verdict lines are the report.
        logging.getLogger("datrix_common").setLevel(logging.WARNING)

    problems = run_self_test()
    if problems:
        logger.error("NON-VACUITY SELF-TEST FAILED -- aborting before any real check:")
        for problem in problems:
            logger.error("  %s", problem)
        return EXIT_USAGE
    logger.info("non-vacuity self-test: PASS")

    if args.self_test:
        return wrappers.run_self_test(
            [], wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=wrappers.REPO_HYGIENE_GATES_DIR
        )

    try:
        return check_example_secret_seeds()
    except (
        DcfgSyntaxError,
        DcfgResolutionError,
        ConfigValidationError,
        OSError,
    ) as exc:
        logger.error("ERROR: %s", exc)
        return EXIT_USAGE


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
