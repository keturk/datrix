#!/usr/bin/env python3
"""A short digest of a red test run: its failure groups, what changed, and a local model's reading.

``test.ps1`` runs this for every package whose run failed and prints the result under its
summary table, so whoever ran the tests reads a dozen lines instead of a log. The digest is
built from three sources, each named in it:

- the run's ``index.json`` clusters, grouped into families by ``collect_failure_data``
  (which also writes ``failure-data.json`` beside it) -- the deterministic part: every
  group's count, pattern, source location, an example test and its re-run command;
- ``classify_run_delta`` against the newest earlier run of the same package with the same
  test selection -- which tests are new failures, still failing, or fixed;
- a local model (``datrix_scripts.local_llm``, resident models only, never a cold load): one hint per
  group from the group's traceback and the source around it, and, when there are several
  groups, one reading of which groups share a cause and which to fix first.

The model text is a lead, never a finding: it is labelled with the model that wrote it. When
no model server answers, the digest says so in one line and carries the deterministic part
alone. The digest is written to ``digest.txt`` in the run directory and printed.

Usage:
  python -m datrix_scripts.run_digest <run-dir | index.json>   (PYTHONPATH=scripts/common/lib)
  python -m datrix_scripts.run_digest --self-test

Exit codes: 0 = digest written (or self-test passed), 1 = self-test failed,
2 = usage / input error.
"""

from __future__ import annotations

import argparse
import dataclasses
import io
import json
import re
import socket
import sys
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Final

if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from datrix_scripts import classify_run_delta, collect_failure_data  # noqa: E402
from datrix_scripts.customer_domain_isolation import corpus_path, hash_term  # noqa: E402
from datrix_scripts.local_llm import (  # noqa: E402
    ADVISORY_UNAVAILABLE_SOURCE,
    ChatRequest,
    LocalLlmPool,
    LocalLlmSettings,
    LocalLlmUnavailable,
    add_local_llm_arguments,
    local_llm_settings,
)
from datrix_scripts.local_reading import (  # noqa: E402
    WITHHELD_LINE,
    ReadScopeError,
    load_workspace_term_corpus,
    withhold_customer_lines,
)
from datrix_scripts.venv import get_datrix_root  # noqa: E402

DIGEST_FILENAME: Final = "digest.txt"
CALLER: Final = "test-digest"

_INDEX_JSON_NAME: Final = "index.json"
_RUN_DIR_GLOB: Final = "test-results-*"
_EXIT_OK: Final = 0
_EXIT_SELF_TEST_FAILED: Final = 1
_EXIT_USAGE: Final = 2

# Each hint is one request to a resident model; a digest that waits minutes is not read.
_GENERATE_TIMEOUT_MS: Final = 60000
_MAX_GROUPS_SHOWN: Final = 8
_MAX_PATTERN_CHARS: Final = 200
_MAX_MODEL_CHARS: Final = 480
_MAX_REASON_CHARS: Final = 160
_READING_MAX_TOKENS: Final = 250
_READING_TEMPERATURE: Final = 0.1
_INDENT: Final = "  "
_DETAIL_INDENT: Final = "        "

_KIND_LABELS: Final = {"error": "E", "failure": "F"}
_KIND_NOUNS: Final = {"error": "error(s)", "failure": "failure(s)"}

_READING_SYSTEM_PROMPT: Final = (
    "You read the failure groups of one test run of the Datrix code generator. Use ONLY the "
    "groups given. Answer in at most 3 sentences, plain text, no code: which groups most "
    "likely share one root cause (name them by label, e.g. E1+F2) and why, and which group "
    "to fix first. Never invent a file, line or group."
)

_WHITESPACE: Final = re.compile(r"\s+")


class DigestError(Exception):
    """The run cannot be digested: no index.json, or one this module cannot read."""


@dataclass(frozen=True)
class _Group:
    """One failure family as the digest shows it."""

    label: str
    kind: str
    pattern: str
    test_count: int
    source_location: str | None
    example: str | None
    rerun: str | None
    hint_source: str
    hint_text: str


@dataclass(frozen=True)
class Digest:
    """The rendered digest and where it was written."""

    path: Path
    text: str


# ---------------------------------------------------------------------------
# Reading the bundle
# ---------------------------------------------------------------------------


def _one_line(text: str, limit: int) -> str:
    """``text`` on one line, cut at ``limit`` characters with a marker when longer."""
    flat = _WHITESPACE.sub(" ", text).strip()
    return flat if len(flat) <= limit else flat[: limit - 3] + "..."


def _clusters_by_key(payload: dict[str, object]) -> dict[tuple[str, int], dict[str, object]]:
    clusters = payload["clusters"]
    if not isinstance(clusters, list):
        raise DigestError("failure-data.json 'clusters' is not a list; re-run collect-failure-data.ps1.")
    return {(str(c["kind"]), int(str(c["cluster_id"]))): c for c in clusters if isinstance(c, dict)}


def _group_of(family: dict[str, object], label: str, head: dict[str, object]) -> _Group:
    representative = head["representative"]
    if not isinstance(representative, dict):
        raise DigestError(f"cluster {head['cluster_id']} has no representative object in failure-data.json.")
    hint = family["hint"]
    if not isinstance(hint, dict):
        raise DigestError(f"family {family['family_id']} has no hint object in failure-data.json.")
    location = head["source_location"]
    example = representative.get("test_id")
    rerun = head.get("test_command")
    return _Group(
        label=label,
        kind=str(family["kind"]),
        pattern=str(family["pattern"]),
        test_count=int(str(family["test_count"])),
        source_location=None if location is None else str(location),
        example=None if example is None else str(example),
        rerun=None if rerun is None else str(rerun),
        hint_source=str(hint["source"]),
        hint_text=str(hint["text"]),
    )


def _groups(payload: dict[str, object]) -> list[_Group]:
    """The bundle's families, labelled E1.. / F1.. in the bundle's order (errors first)."""
    families = payload["families"]
    if not isinstance(families, list):
        raise DigestError("failure-data.json 'families' is not a list; re-run collect-failure-data.ps1.")
    clusters = _clusters_by_key(payload)
    numbers: dict[str, int] = {}
    groups: list[_Group] = []
    for family in families:
        if not isinstance(family, dict):
            raise DigestError("failure-data.json holds a family that is not an object.")
        kind = str(family["kind"])
        numbers[kind] = numbers.get(kind, 0) + 1
        cluster_ids = family["cluster_ids"]
        if not isinstance(cluster_ids, list) or not cluster_ids:
            raise DigestError(f"family {family['family_id']} names no cluster in failure-data.json.")
        head = clusters[(kind, int(str(cluster_ids[0])))]
        groups.append(_group_of(family, f"{_KIND_LABELS[kind]}{numbers[kind]}", head))
    return groups


def _discard_report(_line: str) -> None:
    """Drop the pool's server-discovery lines: the digest states the outcome itself."""


def _answered(group: _Group) -> bool:
    return group.hint_source not in (ADVISORY_UNAVAILABLE_SOURCE, collect_failure_data.HINT_SKIPPED_SOURCE)


# ---------------------------------------------------------------------------
# The earlier run to compare with
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DigestError(f"Cannot read {path}: {exc}. Expected a structured test-results index.json.") from exc
    if not isinstance(data, dict):
        raise DigestError(f"{path} is not a JSON object. Expected a structured test-results index.json.")
    return data


def previous_comparable_run(run_dir: Path, index: dict[str, object]) -> Path | None:
    """The newest earlier run of this package with the same test selection; None when there is none.

    Runs with a different selection (another ``-Specific`` file, another tag) answer a
    different question, so a test absent from one of them is not "fixed". A run whose
    index.json is missing or unreadable is still in flight or broken, and is skipped.
    """
    selection = index.get("selection")
    timestamp = str(index["timestamp"])
    if selection is None:
        return None
    best: tuple[str, Path] | None = None
    for sibling in run_dir.parent.glob(_RUN_DIR_GLOB):
        candidate_index = sibling / _INDEX_JSON_NAME
        if sibling == run_dir or not candidate_index.is_file():
            continue
        try:
            other = _load_json(candidate_index)
        except DigestError:
            continue
        other_stamp = str(other.get("timestamp", ""))
        if other.get("selection") != selection or not other_stamp or other_stamp >= timestamp:
            continue
        if best is None or other_stamp > best[0]:
            best = (other_stamp, sibling)
    return None if best is None else best[1]


def _change_line(run_dir: Path, index: dict[str, object]) -> tuple[str, set[str], set[str]]:
    """The 'versus the earlier run' line, and the (new, persisting) cluster patterns."""
    previous = previous_comparable_run(run_dir, index)
    if previous is None:
        return "No earlier run of this package with the same test selection to compare with.", set(), set()
    try:
        delta = classify_run_delta.classify_delta(previous, run_dir)
    except classify_run_delta.UsageError as exc:
        return f"No comparison with {previous.name}: {_one_line(str(exc), _MAX_REASON_CHARS)}", set(), set()
    new_patterns = _patterns(delta.payload["new_clusters"])
    persisting = _patterns(delta.payload["persisting_clusters"])
    line = (f"Versus {previous.name} (same selection): {delta.new} new failing test(s), "
            f"{delta.still_failing} still failing, {delta.fixed} fixed.")
    return line, new_patterns, persisting


def _patterns(entries: object) -> set[str]:
    if not isinstance(entries, list):
        raise DigestError("run-delta.json cluster list is not a list.")
    return {str(entry["pattern"]) for entry in entries if isinstance(entry, dict)}


# ---------------------------------------------------------------------------
# The model's reading across groups
# ---------------------------------------------------------------------------


def _reading_prompt(project: str, groups: list[_Group]) -> str:
    lines = [f"Project: {project}", ""]
    for group in groups:
        lines.append(f"{group.label}: {group.test_count} {_KIND_NOUNS[group.kind]} - {group.pattern}")
        lines.append(f"  location: {group.source_location or 'unknown'}")
        if _answered(group):
            lines.append(f"  triage note: {_one_line(group.hint_text, _MAX_MODEL_CHARS)}")
    return "\n".join(lines)


def _reading(project: str, groups: list[_Group], settings: LocalLlmSettings, workspace: Path) -> str:
    """The model's reading across the groups, as one labelled line; empty when it is not wanted.

    Asked only when there are several groups (one group's hint already says everything) and
    at least one hint was answered (no server answered moments ago; asking again would only
    wait out the same timeouts). Every prompt line carrying a registered customer term is
    withheld before it is sent.
    """
    shown = groups[:_MAX_GROUPS_SHOWN]
    if len(shown) < 2 or not any(_answered(group) for group in shown):
        return ""
    try:
        lines, _withheld = withhold_customer_lines(_reading_prompt(project, shown),
                                                   load_workspace_term_corpus(workspace))
    except ReadScopeError as exc:
        return f"Model reading: withheld ({_one_line(str(exc), _MAX_REASON_CHARS)})"
    try:
        reply = LocalLlmPool(settings, report=_discard_report).chat(ChatRequest(
            system=_READING_SYSTEM_PROMPT,
            user="\n".join(lines),
            temperature=_READING_TEMPERATURE,
            max_tokens=_READING_MAX_TOKENS,
        ))
    except LocalLlmUnavailable as exc:
        return f"Model reading: unavailable ({_one_line(str(exc), _MAX_REASON_CHARS)})"
    return f"Model reading ({reply.host.model}): {_one_line(reply.text, _MAX_MODEL_CHARS)}"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _counts_text(payload: dict[str, object]) -> str:
    counts = payload["counts"]
    if not isinstance(counts, dict):
        raise DigestError("failure-data.json 'counts' is not an object.")
    return ", ".join(f"{value} {key}" for key, value in counts.items() if value)


def _group_lines(group: _Group, new_patterns: set[str], persisting: set[str]) -> list[str]:
    marker = " [new]" if group.pattern in new_patterns else " [seen before]" if group.pattern in persisting else ""
    lines = [f"{_INDENT}{group.label:<4}{group.test_count} {_KIND_NOUNS[group.kind]}{marker}: "
             f"{_one_line(group.pattern, _MAX_PATTERN_CHARS)}"]
    if group.source_location:
        lines.append(f"{_DETAIL_INDENT}at {group.source_location}")
    # The re-run command names the example test, so it replaces the example line.
    if group.rerun:
        lines.append(f"{_DETAIL_INDENT}rerun: {group.rerun}")
    elif group.example:
        lines.append(f"{_DETAIL_INDENT}e.g. {group.example}")
    if _answered(group):
        lines.append(f"{_DETAIL_INDENT}model: {_one_line(group.hint_text, _MAX_MODEL_CHARS)}")
    return lines


def _model_status(groups: list[_Group]) -> str:
    """One line when no requested hint was answered; empty otherwise."""
    requested = [group for group in groups if group.hint_source != collect_failure_data.HINT_SKIPPED_SOURCE]
    if not requested or any(_answered(group) for group in requested):
        return ""
    return (f"Model: no hint ({_one_line(requested[0].hint_text, _MAX_REASON_CHARS)}); "
            f"the groups below come from index.json alone.")


def render(data: collect_failure_data.FailureData, change: str, new_patterns: set[str],
           persisting: set[str], reading: str) -> str:
    """The digest text: header, change line, model status, groups, reading, pointer."""
    payload = data.payload
    groups = _groups(payload)
    lines = [f"Failure digest: {payload['project']} {payload['result']} ({_counts_text(payload)})",
             f"{_INDENT}{change}"]
    status = _model_status(groups)
    if status:
        lines.append(f"{_INDENT}{status}")
    lines.append(f"{_INDENT}{len(groups)} failure group(s):")
    for group in groups[:_MAX_GROUPS_SHOWN]:
        lines.extend(_group_lines(group, new_patterns, persisting))
    hidden = len(groups) - _MAX_GROUPS_SHOWN
    if hidden > 0:
        lines.append(f"{_INDENT}... and {hidden} more group(s) in failure-data.json")
    if reading:
        lines.append(f"{_INDENT}{reading}")
    lines.append(f"{_INDENT}Model text is a lead to confirm, not a finding. All groups and tracebacks: {data.path}")
    return "\n".join(lines) + "\n"


def write_digest(run_dir: Path, workspace: Path, settings: LocalLlmSettings) -> Digest:
    """Collect the run's failure data, compare it with the earlier run, ask the model, write the digest."""
    index = _load_json(run_dir / _INDEX_JSON_NAME)
    try:
        data = collect_failure_data.write_failure_data(run_dir, workspace, settings=settings,
                                                       report=_discard_report)
    except collect_failure_data.UsageError as exc:
        raise DigestError(str(exc)) from exc
    change, new_patterns, persisting = _change_line(run_dir, index)
    reading = _reading(str(data.payload["project"]), _groups(data.payload), settings, workspace)
    text = render(data, change, new_patterns, persisting, reading)
    path = run_dir / DIGEST_FILENAME
    path.write_text(text, encoding="utf-8")
    return Digest(path=path, text=text)


def digest_settings(args: argparse.Namespace) -> LocalLlmSettings:
    """The shared local-model flags, narrowed to resident models and recorded as this digest."""
    return dataclasses.replace(local_llm_settings(args), allow_load=False, caller=CALLER)


# ---------------------------------------------------------------------------
# Self-test: a real workspace in a temp directory, a real model server on loopback
# ---------------------------------------------------------------------------

_LOOPBACK: Final = "127.0.0.1"
_HINT_ANSWER: Final = "Defect site catalog/request.py:31; the module was renamed. Check the import."
_READING_ANSWER: Final = "E1 and F1 share the renamed module; fix E1 first."


class _ModelServer:
    """OpenAI-compatible server on loopback: the reading prompt gets one answer, every hint another."""

    def __init__(self) -> None:
        self.chats = 0
        self.prompts: list[str] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, payload: object) -> None:
                data = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802
                self._send({"data": [{"id": "digest-model"}]})

            def do_POST(self) -> None:  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
                system = str(body["messages"][0]["content"])
                if body.get("max_tokens") != 1:
                    server.chats += 1
                    server.prompts.append(str(body["messages"][-1]["content"]))
                answer = _READING_ANSWER if system == _READING_SYSTEM_PROMPT else _HINT_ANSWER
                self._send({"choices": [{"message": {"content": answer}, "finish_reason": "stop"}]})

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                return

        self.httpd = ThreadingHTTPServer((_LOOPBACK, 0), Handler)
        self.port = int(self.httpd.server_address[1])
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


def _closed_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((_LOOPBACK, 0))
        return int(sock.getsockname()[1])


def _settings_for(port: int, usage_log: Path) -> LocalLlmSettings:
    return LocalLlmSettings(machines=(_LOOPBACK,), reachable_timeout_ms=2000, generate_timeout_ms=5000,
                            allow_load=False, ollama_port=_closed_port(), openai_ports=(port,),
                            usage_log=usage_log, caller=CALLER)


def _entry(entry_id: int, test: str, message: str) -> dict[str, object]:
    return {"id": entry_id, "test_id": f"tests.unit.test_shop.TestOrder::{test}",
            "file": "tests/unit/test_shop.py", "error_type": message.split(":", 1)[0],
            "error_message": message, "log_file": f"failures/{entry_id:03d}.txt"}


def _index(stamp: str, selection: dict[str, object], failures: list[tuple[str, str]],
           errors: list[tuple[str, str]]) -> dict[str, object]:
    """A package-schema index.json: one cluster per distinct message, failures then errors."""
    index: dict[str, object] = {
        "project": "datrix-alpha", "timestamp": stamp, "result": "FAILED" if failures or errors else "PASSED",
        "counts": {"passed": 5, "failed": len(failures), "error": len(errors), "skipped": 0},
        "selection": selection,
    }
    for kind, key, items, offset in (("failure", "failures", failures, 0), ("error", "errors", errors, 100)):
        entries = [_entry(offset + n, test, message) for n, (test, message) in enumerate(items, start=1)]
        index[key] = entries
        clusters: list[dict[str, object]] = []
        for message in dict.fromkeys(message for _, message in items):
            ids = [e["id"] for e in entries if e["error_message"] == message]
            clusters.append({"cluster_id": len(clusters) + 1, "pattern": message,
                             "source_location": "src/shop/order.py:31", "count": len(ids),
                             f"{kind}_ids": ids, f"representative_{kind}_id": ids[0]})
        index[f"{kind}_clusters"] = clusters
    return index


def _write_run(package: Path, name: str, index: dict[str, object]) -> Path:
    run = package / ".test_results" / name
    (run / "failures").mkdir(parents=True)
    for key in ("failures", "errors"):
        entries = index[key]
        assert isinstance(entries, list)
        for entry in entries:
            (run / str(entry["log_file"])).write_text(
                f'File "src/shop/order.py", line 31, in place\n{entry["error_message"]}\n', encoding="utf-8")
    (run / _INDEX_JSON_NAME).write_text(json.dumps(index), encoding="utf-8")
    return run


def _check(problems: list[str], label: str, ok: bool) -> None:
    print(f"[{'OK' if ok else 'FAIL'}] {label}")
    if not ok:
        problems.append(label)


_TARGETED: Final = {"kind": "targeted", "specific": ["tests/unit/test_shop.py"]}
_OTHER: Final = {"kind": "targeted", "specific": ["tests/unit/test_other.py"]}
_RENAMED: Final = "ModuleNotFoundError: No module named shop.order_lines"
_SETUP: Final = "fixture 'warehouse' not found"
_OLD: Final = "AssertionError: assert 2 == 3"
# A fictional registered customer term, on the source line just above the traceback frame.
_TERM: Final = "zorbleflux"


def _make_workspace(root: Path) -> tuple[Path, Path, Path]:
    """(package, current red run, its earlier run with the same selection)."""
    corpus = corpus_path(root / "datrix")
    corpus.parent.mkdir(parents=True)
    corpus.write_text(json.dumps({"algorithm": "sha256", "min_token_length": 5,
                                  "terms": [{"hash": hash_term(_TERM), "hint": "self-test"}]}), encoding="utf-8")
    package = root / "datrix-alpha"
    (package / "src" / "shop").mkdir(parents=True)
    (package / "tests" / "unit").mkdir(parents=True)
    (package / "src" / "shop" / "order.py").write_text(
        "".join(f"gateway = '{_TERM}'\n" if n == 30 else f"line_{n} = {n}\n" for n in range(1, 40)),
        encoding="utf-8")
    previous = _write_run(package, "test-results-20261001-100000", _index(
        "2026-10-01T10:00:00", _TARGETED, [("test_total", _OLD), ("test_lines", _RENAMED)], []))
    _write_run(package, "test-results-20261002-100000", _index(
        "2026-10-02T10:00:00", _OTHER, [("test_unrelated", _OLD)], []))
    current = _write_run(package, "test-results-20261003-100000", _index(
        "2026-10-03T10:00:00", _TARGETED, [("test_lines", _RENAMED), ("test_lines_again", _RENAMED)],
        [("test_stock", _SETUP)]))
    _write_run(package, "test-results-20261004-100000", _index(
        "2026-10-04T10:00:00", _TARGETED, [("test_later", _OLD)], []))
    return package, current, previous


def _check_with_a_model(problems: list[str], root: Path, current: Path, previous: Path) -> None:
    server = _ModelServer()
    usage = root / "usage.jsonl"
    try:
        digest = write_digest(current, root, _settings_for(server.port, usage))
    finally:
        server.httpd.shutdown()
    text = digest.text
    _check(problems, "the earlier run is the newest older run with the same selection",
           previous_comparable_run(current, _load_json(current / _INDEX_JSON_NAME)) == previous)
    _check(problems, "the change line counts new, still failing and fixed tests",
           f"Versus {previous.name} (same selection): 2 new failing test(s), 1 still failing, 1 fixed." in text)
    _check(problems, "groups are labelled errors first, then failures",
           text.index("E1  1 error(s) [new]: " + _SETUP) < text.index("F1  2 failure(s) [seen before]: " + _RENAMED))
    _check(problems, "each group carries its location, a re-run command for its example and the model's hint",
           "at src/shop/order.py:31" in text and '"tests/unit/test_shop.py::TestOrder::test_stock"' in text
           and "e.g. " not in text and f"model: {_HINT_ANSWER}" in text)
    _check(problems, "several groups get one reading across them, labelled with its model",
           f"Model reading (digest-model): {_READING_ANSWER}" in text)
    _check(problems, "the digest is written beside index.json with failure-data.json",
           digest.path.read_text(encoding="utf-8") == text and (current / "failure-data.json").is_file())
    callers = {json.loads(line)["caller"] for line in usage.read_text(encoding="utf-8").splitlines()}
    _check(problems, "every model request is recorded under the digest's name", callers == {CALLER})
    _check(problems, "one hint per group plus one reading reached the model", server.chats == 3)
    _check(problems, "a line carrying a registered customer term is withheld from every prompt",
           not any(_TERM in prompt for prompt in server.prompts)
           and any(WITHHELD_LINE in prompt for prompt in server.prompts))


def _check_without_a_corpus(problems: list[str], root: Path, current: Path) -> None:
    corpus = corpus_path(root / "datrix")
    saved = corpus.read_text(encoding="utf-8")
    corpus.unlink()
    server = _ModelServer()
    try:
        text = write_digest(current, root, _settings_for(server.port, root / "usage.jsonl")).text
    finally:
        server.httpd.shutdown()
        corpus.write_text(saved, encoding="utf-8")
    _check(problems, "no customer-term corpus: nothing is sent to the model", server.chats == 0)
    _check(problems, "no customer-term corpus: one line says why there is no model text",
           text.count("Model: no hint (Nothing is sent to a local model without the customer-term corpus") == 1)


def _check_without_a_model(problems: list[str], root: Path, current: Path) -> None:
    dead = _settings_for(_closed_port(), root / "usage.jsonl")
    text = write_digest(current, root, dead).text
    _check(problems, "no model server: one line says so", text.count("Model: no hint (") == 1)
    _check(problems, "no model server: no model text and no second attempt at a reading",
           "model: " not in text and "Model reading" not in text)
    _check(problems, "no model server: the groups are still listed", "E1" in text and "F1" in text)


def _check_without_an_earlier_run(problems: list[str], root: Path, package: Path) -> None:
    lone = _write_run(package, "test-results-20260901-100000", _index(
        "2026-09-01T10:00:00", _TARGETED, [("test_total", _OLD)], []))
    dead = _settings_for(_closed_port(), root / "usage.jsonl")
    text = write_digest(lone, root, dead).text
    _check(problems, "the first run of a selection says there is nothing to compare with",
           "No earlier run of this package with the same test selection" in text and "[new]" not in text)


def _run_self_test() -> int:
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="run-digest-") as temp:
        root = Path(temp)
        package, current, previous = _make_workspace(root)
        checks: tuple[Callable[[], None], ...] = (
            lambda: _check_with_a_model(problems, root, current, previous),
            lambda: _check_without_a_corpus(problems, root, current),
            lambda: _check_without_a_model(problems, root, current),
            lambda: _check_without_an_earlier_run(problems, root, package),
        )
        for check in checks:
            check()
    if problems:
        print(f"SELF-TEST FAILED: {len(problems)} check(s)")
        return _EXIT_SELF_TEST_FAILED
    print("SELF-TEST PASSED")
    return _EXIT_OK


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write and print a short digest of a red test run.")
    parser.add_argument("path", nargs="?", help="Run directory or its index.json")
    parser.add_argument("--self-test", action="store_true", help="Check the digest against a temp workspace")
    add_local_llm_arguments(parser, generate_timeout_ms=_GENERATE_TIMEOUT_MS)
    return parser.parse_args()


def main() -> int:
    """Entry point."""
    args = _parse_args()
    if args.self_test:
        return _run_self_test()
    if not args.path:
        print("ERROR: pass a test-results run directory or its index.json (or --self-test).", file=sys.stderr)
        return _EXIT_USAGE
    try:
        run_dir = collect_failure_data.resolve_run_dir_from_path(args.path)
        digest = write_digest(run_dir, get_datrix_root(), digest_settings(args))
    except (collect_failure_data.UsageError, DigestError) as exc:
        print(f"ERROR: no failure digest: {exc}", file=sys.stderr)
        return _EXIT_USAGE
    print(digest.text, end="")
    return _EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
