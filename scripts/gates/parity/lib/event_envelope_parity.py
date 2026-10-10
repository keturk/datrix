"""Cross-language pubsub event-envelope parity gate.

A topic may have producers and consumers in different languages, so every
registered `datrix.languages` plugin must put ONE envelope shape on the wire and
read the same shape back: the same envelope keys, and for every event the same
payload keys. This gate generates the shared pubsub example once per registered
language and compares what each language's own generated producers write and
consumers read, as its `LanguageConformanceProbes.event_envelopes` reports them.

The declared keys are `datrix_codegen_kernel.generation.event_envelope`'s --
called, never restated -- and the payload keys of every event must be the
declared parameters' wire names (`event_payload_wire_name`), the same in every
language.

Per language: at least one envelope is published (a census that finds nothing
proves nothing); every envelope carries exactly the declared keys; every
payload carries exactly the event's wire names; every key a consumer reads is a
key the language writes. Across languages: every event published by two
languages has one payload key set.

Target set is NEVER hardcoded: languages are enumerated from the installed
`datrix.languages` entry points at run time, and the self-test proves this
module names none.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_cli.generation.validation_level import ValidationLevel
from datrix_cli.pipeline.contract import PipelineConfig, PipelineResult
from datrix_cli.pipeline.generation import GenerationPipeline
from datrix_codegen_kernel.generation.event_envelope import (
    EVENT_ENVELOPE_GLOBALS,
    event_payload_wire_name,
)
from datrix_codegen_kernel.parity.conformance_probes import (
    EventEnvelopeCensus,
    PublishedEventEnvelope,
    language_conformance_probes,
)
from datrix_common.errors.plugin import PluginValidationError
from datrix_common.plugin.identity import LanguageId
from datrix_common.utils.text import PolyString
from datrix_language.parser.tree_sitter_datrix.parser import TreeSitterParser
from datrix_language.registration import register_all

from datrix_scripts.paths import SHOWCASE_DIR
from datrix_scripts.registered_targets import (
    registered_language_names,
    self_test_gate_names_no_target,
)

logger = logging.getLogger(__name__)

# `GenerationPipeline.run()` parses real `.dtrx` source, which needs the stdlib
# parser protocol registered first -- normally done by `datrix_cli.main`.
register_all()

EXAMPLE_SOURCE: Path = (
    SHOWCASE_DIR / "examples" / "02-features" / "02-service-architecture" / "pubsub" / "system.dtrx"
)
#: Generation scratch space -- never inside a package repo.
_GATE_OUTPUT_ROOT: Path = SHOWCASE_DIR.parent / ".tmp" / "event-envelope-parity-gate"
_EXAMPLE_PROFILE: Final[str] = "test"

#: A cross-language comparison over 0 or 1 language is vacuous.
_MIN_LANGUAGES_FOR_COMPARISON: Final[int] = 2
_INSUFFICIENT_TARGETS_EXIT_CODE: Final[int] = 2

#: The declared envelope keys every producer writes.
DECLARED_ENVELOPE_KEYS: Final[frozenset[str]] = frozenset(EVENT_ENVELOPE_GLOBALS.values())

_SELF_TEST_LANGUAGE: Final[str] = "self_test_lang"
_SELF_TEST_OTHER_LANGUAGE: Final[str] = "self_test_other_lang"


@dataclass(frozen=True)
class LanguageEnvelopes:
    """One language's census, with the payload keys its events must carry.

    Attributes:
        language: The `datrix.languages` entry-point name.
        census: What the language's probe read off its generated tree.
        declared_payloads: Event name -> the wire names of its declared parameters.
    """

    language: str
    census: EventEnvelopeCensus
    declared_payloads: Mapping[str, frozenset[str]]


def configure_logging(debug: bool = False) -> None:
    """Configure logging output."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def _envelope_violations(language: str, envelope: PublishedEventEnvelope, declared: Mapping[str, frozenset[str]]) -> list[str]:
    problems: list[str] = []
    if envelope.envelope_keys != DECLARED_ENVELOPE_KEYS:
        problems.append(
            f"{language}: {envelope.file_path} publishes {envelope.event_name!r} under envelope keys "
            f"{sorted(envelope.envelope_keys)}, expected {sorted(DECLARED_ENVELOPE_KEYS)}. Fix: render the "
            "envelope keys from the EVENT_ENVELOPE_* template globals."
        )
    expected = declared.get(envelope.event_name)
    if expected is None:
        problems.append(
            f"{language}: {envelope.file_path} publishes {envelope.event_name!r}, which the example "
            f"declares nowhere. Declared events: {sorted(declared)}."
        )
    elif envelope.payload_keys != expected:
        problems.append(
            f"{language}: {envelope.file_path} publishes {envelope.event_name!r} with payload keys "
            f"{sorted(envelope.payload_keys)}, expected the parameters' wire names {sorted(expected)}. "
            "Fix: name each payload field with event_payload_wire_name."
        )
    return problems


def language_violations(envelopes: LanguageEnvelopes) -> list[str]:
    """Every way one language's census departs from the declared envelope."""
    census = envelopes.census
    if not census.published:
        return [
            f"{envelopes.language}: the probe read no published envelope off the generated example; a "
            "census that finds nothing proves nothing. Fix: make event_envelopes read the producers "
            "the language generates."
        ]
    problems: list[str] = []
    for envelope in census.published:
        problems.extend(_envelope_violations(envelopes.language, envelope, envelopes.declared_payloads))
    for path, keys in sorted(census.consumed_keys.items()):
        unknown = keys - DECLARED_ENVELOPE_KEYS
        if unknown:
            problems.append(
                f"{envelopes.language}: {path} reads envelope keys {sorted(unknown)} no producer writes. "
                f"Expected a subset of {sorted(DECLARED_ENVELOPE_KEYS)}."
            )
    return problems


def cross_language_violations(languages: Sequence[LanguageEnvelopes]) -> list[str]:
    """Every event two languages publish with different payload keys."""
    seen: dict[str, tuple[str, frozenset[str]]] = {}
    problems: list[str] = []
    for entry in languages:
        for envelope in entry.census.published:
            first = seen.setdefault(envelope.event_name, (entry.language, envelope.payload_keys))
            if first[1] != envelope.payload_keys:
                problems.append(
                    f"event {envelope.event_name!r}: {first[0]} publishes payload keys {sorted(first[1])}, "
                    f"{entry.language} publishes {sorted(envelope.payload_keys)}. A consumer in one "
                    "language cannot read the other's event."
                )
    return problems


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def _fixture(language: str, envelope_keys: frozenset[str], payload_keys: frozenset[str], consumed: frozenset[str]) -> LanguageEnvelopes:
    published = PublishedEventEnvelope(
        event_name="OrderPlaced",
        envelope_keys=envelope_keys,
        payload_keys=payload_keys,
        file_path=Path(f"{language}/producer"),
    )
    return LanguageEnvelopes(
        language=language,
        census=EventEnvelopeCensus(published=(published,), consumed_keys={Path(f"{language}/consumer"): consumed}),
        declared_payloads={"OrderPlaced": frozenset({"orderId", "customerEmail"})},
    )


def run_self_test() -> list[str]:
    """Prove the gate names no target and its comparators catch each forced divergence.

    Returns:
        A list of failure descriptions -- empty means the comparators are sound.
    """
    problems: list[str] = list(self_test_gate_names_no_target(__file__))
    if problems:
        return problems
    payload = frozenset({"orderId", "customerEmail"})
    good = _fixture(_SELF_TEST_LANGUAGE, DECLARED_ENVELOPE_KEYS, payload, DECLARED_ENVELOPE_KEYS)
    if language_violations(good):
        problems.append("self-test: a conformant census was reported as a violation -- over-triggering.")
    snake_key = _fixture(
        _SELF_TEST_LANGUAGE,
        frozenset({"event_type", "published_at", "payload"}),
        payload,
        frozenset({"event_type"}),
    )
    if len(language_violations(snake_key)) != 2:
        problems.append(
            "self-test: a census writing and reading 'event_type' was not reported for both the "
            "producer and the consumer."
        )
    snake_payload = _fixture(
        _SELF_TEST_OTHER_LANGUAGE, DECLARED_ENVELOPE_KEYS, frozenset({"order_id", "customer_email"}), DECLARED_ENVELOPE_KEYS
    )
    if not language_violations(snake_payload):
        problems.append("self-test: a snake_case payload was not reported against the declared wire names.")
    if not cross_language_violations([good, snake_payload]):
        problems.append("self-test: two languages publishing different payload keys were not reported.")
    empty = LanguageEnvelopes(
        language=_SELF_TEST_LANGUAGE,
        census=EventEnvelopeCensus(published=(), consumed_keys={}),
        declared_payloads={},
    )
    if not language_violations(empty):
        problems.append("self-test: an empty census passed -- a census that finds nothing must fail.")
    for insufficient in ([], sorted(registered_language_names())[:1]):
        code = check_event_envelope_parity(insufficient)
        if code != _INSUFFICIENT_TARGETS_EXIT_CODE:
            problems.append(
                f"self-test: check_event_envelope_parity did NOT refuse a target set of "
                f"{len(insufficient)} ({insufficient!r}); returned {code}."
            )
    return problems


# ---------------------------------------------------------------------------
# Real run
# ---------------------------------------------------------------------------


def declared_payloads(source: Path) -> Mapping[str, frozenset[str]]:
    """Event name -> the wire names of its declared parameters, for every event *source* publishes."""
    application = TreeSitterParser().parse_file(source)
    return {
        str(event.name): frozenset(event_payload_wire_name(PolyString(str(p.name))) for p in event.parameters)
        for service in application.services.values()
        for block in service.pubsub_blocks.values()
        for topic in block.topics.values()
        for event in topic.events.values()
    }


def _generate_example_for_language(language: str) -> Path:
    """Generate the pubsub example for *language* into a scratch dir.

    Raises:
        RuntimeError: The pipeline reports failure.
    """
    output_dir = _GATE_OUTPUT_ROOT / language
    config = PipelineConfig(
        target_language=LanguageId(language),
        profile=_EXAMPLE_PROFILE,
        validation_level=ValidationLevel.FAST,
    )
    result: PipelineResult = GenerationPipeline().run(
        source_path=EXAMPLE_SOURCE, output_dir=output_dir, config=config
    )
    if not result.success:
        raise RuntimeError(
            f"Generating the event-envelope example for language {language!r} failed: {result.errors}"
        )
    return output_dir


def check_event_envelope_parity(languages: Sequence[str] | None = None) -> int:
    """Run the gate over every registered language.

    Args:
        languages: ``None`` -- the production value -- resolves the installed
            ``datrix.languages`` entry points; an explicit list exists so the
            self-test can drive the insufficient-target refusal with a real
            short list.

    Returns:
        0 = one envelope shape everywhere, 1 = a divergence or a language without
        probes, 2 = fewer than two languages registered.
    """
    names = sorted(registered_language_names() if languages is None else languages)
    if len(names) < _MIN_LANGUAGES_FOR_COMPARISON:
        logger.error(
            "Event-envelope parity gate CANNOT RUN: only %d language(s) registered (%s); at least %d "
            "are required.", len(names), names, _MIN_LANGUAGES_FOR_COMPARISON,
        )
        return _INSUFFICIENT_TARGETS_EXIT_CODE
    shutil.rmtree(_GATE_OUTPUT_ROOT, ignore_errors=True)
    declared = declared_payloads(EXAMPLE_SOURCE)
    problems: list[str] = []
    collected: list[LanguageEnvelopes] = []
    for language in names:
        output_dir = _generate_example_for_language(language)
        try:
            probes = language_conformance_probes(language)
        except PluginValidationError as exc:
            problems.append(str(exc))
            continue
        entry = LanguageEnvelopes(language, probes.event_envelopes(output_dir), declared)
        problems.extend(language_violations(entry))
        collected.append(entry)
    problems.extend(cross_language_violations(collected))
    for problem in problems:
        logger.error("EVENT ENVELOPE VIOLATION: %s", problem)
    if problems:
        return 1
    logger.info(
        "One event envelope shape across %d languages (%s): keys %s, payloads keyed by wire name.",
        len(names), names, sorted(DECLARED_ENVELOPE_KEYS),
    )
    return 0


def main() -> int:
    """Entry point.

    Returns:
        0 = conformant, 1 = a divergence, 2 = the self-test failed or fewer than
        two languages are registered.
    """
    parser = argparse.ArgumentParser(
        description="Prove every registered datrix.languages plugin writes and reads one pubsub event envelope."
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--self-test", action="store_true", help="Run only the non-vacuity self-test")
    args = parser.parse_args()
    configure_logging(debug=args.debug)
    problems = run_self_test()
    if problems:
        logger.error("Non-vacuity self-test FAILED:")
        for problem in problems:
            logger.error("  %s", problem)
        return 2
    logger.info("Non-vacuity self-test passed.")
    if args.self_test:
        return 0
    return check_event_envelope_parity()


if __name__ == "__main__":
    sys.exit(main())
