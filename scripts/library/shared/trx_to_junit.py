#!/usr/bin/env python3
"""Convert a Microsoft Testing Platform (MTP) ``.trx`` report to JUnit XML.

The .NET generators run their tests through the xunit.v3 MTP runner, whose
native machine-readable report is the VSTest ``.trx`` schema
(``Microsoft.Testing.Extensions.TrxReport``). The repo's structured-output /
AI-triage pipeline, however, consumes the JUnit XML shape produced by pytest's
``--junit-xml`` (parsed by ``GeneratedTestLogWriter.add_service_junit_xml``).

This module bridges the two: it reads a ``.trx`` and emits a JUnit
``<testsuite>`` whose ``<testcase classname name>`` / ``<failure>`` /
``<skipped>`` elements match exactly what that writer expects, so a dotnet
service's results flow through the same structured pipeline as python/typescript.

The dependency direction is deliberately one-way (JUnit is the lingua franca of
the pipeline); no other language emits TRX.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import NamedTuple
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

#: TRX outcomes that count as a skipped (not-run) test. Everything that is not
#: ``Passed`` and not one of these is treated as a failure (``Failed``,
#: ``Error``, ``Timeout``, ``Aborted``, ...), so a novel non-pass outcome fails
#: loud rather than being silently counted as a pass.
_SKIPPED_OUTCOMES = frozenset({"NotExecuted", "Skipped"})
_PASSED_OUTCOME = "Passed"


class TrxCounts(NamedTuple):
    """Aggregate test counts derived from a ``.trx`` report."""

    passed: int
    failed: int
    skipped: int

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.skipped


def _local(tag: str) -> str:
    """Return an element's local name, stripping any ``{namespace}`` prefix."""
    return tag.rsplit("}", 1)[-1]


def _find_child(element: ET.Element, name: str) -> ET.Element | None:
    """Return the first direct child with local name *name*, ignoring namespace."""
    for child in element:
        if _local(child.tag) == name:
            return child
    return None


def _iter_descendants(root: ET.Element, name: str) -> list[ET.Element]:
    """Return all descendants with local name *name*, ignoring namespace."""
    return [el for el in root.iter() if _local(el.tag) == name]


def _build_test_method_index(root: ET.Element) -> dict[str, tuple[str, str]]:
    """Map ``testId`` -> ``(class_name, method_name)`` from ``<TestDefinitions>``.

    A ``<UnitTest id=...>`` wraps a ``<TestMethod className=... name=... />``.
    The class name gives the JUnit ``classname`` and the method name the
    JUnit ``name`` -- matching pytest's ``classname``/``name`` split so the
    downstream writer's ``{classname}::{name}`` test id reads naturally.
    """
    index: dict[str, tuple[str, str]] = {}
    for unit_test in _iter_descendants(root, "UnitTest"):
        test_id = unit_test.get("id")
        if not test_id:
            continue
        method = _find_child(unit_test, "TestMethod")
        if method is None:
            continue
        class_name = method.get("className", "")
        method_name = method.get("name", "")
        index[test_id] = (class_name, method_name)
    return index


def _split_test_name(test_name: str) -> tuple[str, str]:
    """Fallback ``(class_name, method_name)`` split from a fully-qualified name.

    Used only when a result has no matching ``<UnitTest>`` definition. Splits on
    the last ``.`` (``A.B.C.Method`` -> ``("A.B.C", "Method")``).
    """
    if "." in test_name:
        class_name, method_name = test_name.rsplit(".", 1)
        return class_name, method_name
    return "", test_name


def _extract_failure(result: ET.Element) -> tuple[str, str]:
    """Return ``(message, stack_trace)`` for a failed ``<UnitTestResult>``.

    TRX carries these under ``<Output><ErrorInfo><Message>/<StackTrace>``.
    Missing pieces degrade to empty strings rather than raising -- a failure
    with no captured message is still a failure.
    """
    output = _find_child(result, "Output")
    if output is None:
        return "", ""
    error_info = _find_child(output, "ErrorInfo")
    if error_info is None:
        return "", ""
    message_el = _find_child(error_info, "Message")
    stack_el = _find_child(error_info, "StackTrace")
    message = (message_el.text or "").strip() if message_el is not None else ""
    stack = (stack_el.text or "").strip() if stack_el is not None else ""
    return message, stack


def _append_testcase(
    suite: ET.Element,
    result: ET.Element,
    method_index: dict[str, tuple[str, str]],
) -> str:
    """Append one ``<testcase>`` for *result*; return its outcome bucket.

    Returns one of ``"passed"``, ``"failed"``, ``"skipped"``.
    """
    test_id = result.get("testId", "")
    test_name = result.get("testName", "")
    class_name, method_name = method_index.get(test_id, _split_test_name(test_name))
    outcome = result.get("outcome", "")

    testcase = ET.SubElement(
        suite,
        "testcase",
        {"classname": class_name, "name": method_name},
    )
    duration = result.get("duration")
    if duration:
        testcase.set("time", _duration_to_seconds(duration))

    if outcome == _PASSED_OUTCOME:
        return "passed"
    if outcome in _SKIPPED_OUTCOMES:
        ET.SubElement(testcase, "skipped")
        return "skipped"

    message, stack = _extract_failure(result)
    failure = ET.SubElement(
        testcase,
        "failure",
        {"type": outcome or "Failed", "message": message},
    )
    failure.text = stack or message
    return "failed"


def _duration_to_seconds(duration: str) -> str:
    """Convert a TRX ``hh:mm:ss.fffffff`` duration to a JUnit seconds string."""
    parts = duration.split(":")
    try:
        if len(parts) == 3:
            hours, minutes, seconds = (float(p) for p in parts)
            return f"{hours * 3600 + minutes * 60 + seconds:.3f}"
    except ValueError:
        pass
    return "0.000"


def convert_trx_to_junit(trx_path: Path, suite_name: str) -> tuple[ET.ElementTree, TrxCounts]:
    """Convert a ``.trx`` file to a JUnit ``ElementTree`` plus aggregate counts.

    Args:
        trx_path: Path to the ``.trx`` report emitted by the MTP TRX reporter.
        suite_name: ``name`` attribute for the emitted ``<testsuite>`` (the
            service/project name).

    Returns:
        ``(tree, counts)`` where ``tree`` is a JUnit ``<testsuite>`` document
        parseable by ``GeneratedTestLogWriter.add_service_junit_xml`` and
        ``counts`` are the passed/failed/skipped totals.

    Raises:
        FileNotFoundError: If *trx_path* does not exist.
        ValueError: If *trx_path* is not well-formed XML.
    """
    if not trx_path.exists():
        raise FileNotFoundError(f"TRX report not found at {trx_path}.")

    try:
        trx_root = ET.parse(str(trx_path)).getroot()  # noqa: S314 -- trusted local test output
    except ET.ParseError as exc:
        raise ValueError(f"TRX report at {trx_path} is not well-formed XML: {exc}") from exc

    method_index = _build_test_method_index(trx_root)

    suite = ET.Element("testsuite", {"name": suite_name})
    passed = failed = skipped = 0
    for results_el in (el for el in trx_root if _local(el.tag) == "Results"):
        for result in results_el:
            if _local(result.tag) != "UnitTestResult":
                continue
            bucket = _append_testcase(suite, result, method_index)
            if bucket == "passed":
                passed += 1
            elif bucket == "failed":
                failed += 1
            else:
                skipped += 1

    counts = TrxCounts(passed=passed, failed=failed, skipped=skipped)
    suite.set("tests", str(counts.total))
    suite.set("failures", str(failed))
    suite.set("errors", "0")
    suite.set("skipped", str(skipped))

    logger.info(
        "trx_to_junit_converted trx=%s suite=%s passed=%d failed=%d skipped=%d",
        trx_path,
        suite_name,
        passed,
        failed,
        skipped,
    )
    return ET.ElementTree(suite), counts


def write_junit_from_trx(trx_path: Path, junit_path: Path, suite_name: str) -> TrxCounts:
    """Convert *trx_path* and write JUnit XML to *junit_path*; return counts.

    Creates *junit_path*'s parent directory if needed.
    """
    tree, counts = convert_trx_to_junit(trx_path, suite_name)
    junit_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(junit_path), encoding="utf-8", xml_declaration=True)
    return counts


__all__ = [
    "TrxCounts",
    "convert_trx_to_junit",
    "write_junit_from_trx",
]
