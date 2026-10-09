"""A record of every request a local model server was sent, and the report over it.

Before this log existed, whether a local model had been used at all could only be guessed
from server-side counters, which reset whenever a server restarts. ``LocalLlmPool``
appends one JSON line per request to ``<workspace>/.local-llm/usage.jsonl`` on the machine
that sent it: who asked (the script, hook or MCP tool), which server and model answered, how
much text went each way, how long it took, and whether it failed. Text itself is never
recorded -- only its size.

``local-llm.ps1 -Usage`` (and the MCP tool ``local_models``) renders the report.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from datrix_scripts.capped_log import append_line, read_lines
from datrix_scripts.venv import get_datrix_root

USAGE_DIR_NAME = ".local-llm"
USAGE_LOG_NAME = "usage.jsonl"
# About 25,000 requests per file (a line is ~200 bytes); with the rotated file, weeks of history.
USAGE_LOG_MAX_BYTES = 5 * 1024 * 1024

OUTCOME_OK = "ok"
OUTCOME_FAILED = "failed"
OUTCOME_UNAVAILABLE = "unavailable"

MAX_ERROR_CHARS = 300
# Roughly four characters per token for English prose and source code.
CHARS_PER_TOKEN = 4

# Points the log somewhere else. Gates and hook tests set it to a temporary file so the requests
# their own loopback servers answer never count as real use of the machines.
USAGE_LOG_VARIABLE = "DATRIX_LOCAL_LLM_USAGE_LOG"


def default_usage_log() -> Path:
    override = os.environ.get(USAGE_LOG_VARIABLE, "")
    if override:
        return Path(override)
    return get_datrix_root() / USAGE_DIR_NAME / USAGE_LOG_NAME


def invoking_script() -> str:
    """The name of the script this process runs, as the default caller label."""
    name = os.path.splitext(os.path.basename(sys.argv[0]))[0] if sys.argv and sys.argv[0] else ""
    return name or "python"


@dataclass(frozen=True)
class UsageEntry:
    caller: str
    outcome: str
    model: str
    base_url: str
    prompt_chars: int
    answer_chars: int
    seconds: float
    error: str

    def as_json(self) -> str:
        record = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "caller": self.caller,
            "outcome": self.outcome,
            "model": self.model,
            "base_url": self.base_url,
            "prompt_chars": self.prompt_chars,
            "answer_chars": self.answer_chars,
            "seconds": round(self.seconds, 2),
            "error": self.error[:MAX_ERROR_CHARS],
        }
        return json.dumps(record, ensure_ascii=False)


def record_usage(log: Path, entry: UsageEntry) -> None:
    """Append one entry, within the log's size cap. A failure to write is reported on stderr,
    never raised: losing a log line must not fail the request it describes."""
    try:
        append_line(log, entry.as_json(), USAGE_LOG_MAX_BYTES)
    except OSError as exc:
        print(f"local-llm usage: could not append to {log}: {exc}", file=sys.stderr)


@dataclass
class _Tally:
    requests: int = 0
    failed: int = 0
    prompt_chars: int = 0
    answer_chars: int = 0
    seconds: float = 0.0

    def add(self, outcome: str, prompt_chars: int, answer_chars: int, seconds: float) -> None:
        self.requests += 1
        if outcome != OUTCOME_OK:
            self.failed += 1
        self.prompt_chars += prompt_chars
        self.answer_chars += answer_chars
        self.seconds += seconds

    def line(self, label: str) -> str:
        failed = f", {self.failed} failed" if self.failed else ""
        return (f"  {label}: {self.requests} requests{failed}, ~{self.prompt_chars // CHARS_PER_TOKEN:,} tokens in, "
                f"~{self.answer_chars // CHARS_PER_TOKEN:,} out, {self.seconds:,.0f} s")


@dataclass
class UsageReport:
    since: str
    by_caller: dict[str, _Tally] = field(default_factory=dict)
    by_server: dict[str, _Tally] = field(default_factory=dict)
    unavailable: Counter[str] = field(default_factory=Counter)
    last_ts: str = ""
    unreadable_lines: int = 0

    @property
    def requests(self) -> int:
        return sum(tally.requests for tally in self.by_caller.values())

    def render(self) -> str:
        lines = [f"Local model requests since {self.since}: {self.requests}"
                 + (f" (last at {self.last_ts})" if self.last_ts else "")]
        if self.by_caller:
            lines.append("By caller:")
            lines.extend(self.by_caller[name].line(name) for name in sorted(self.by_caller))
            lines.append("By server:")
            lines.extend(self.by_server[name].line(name) for name in sorted(self.by_server))
        if self.unavailable:
            lines.append("No server could answer: " + ", ".join(
                f"{caller} x{count}" for caller, count in sorted(self.unavailable.items())))
        if self.unreadable_lines:
            lines.append(f"Unreadable log lines skipped: {self.unreadable_lines}")
        return "\n".join(lines)


def usage_report(log: Path, days: int) -> UsageReport:
    """Summarize the last ``days`` days of the log (0 = everything logged)."""
    cutoff = datetime.now(UTC) - timedelta(days=days) if days else None
    report = UsageReport(since=cutoff.date().isoformat() if cutoff else "the first logged request")
    for line in read_lines(log):
        try:
            entry = json.loads(line)
            when = datetime.fromisoformat(str(entry["ts"]))
            caller, outcome = str(entry["caller"]), str(entry["outcome"])
            prompt, answer, seconds = int(entry["prompt_chars"]), int(entry["answer_chars"]), float(entry["seconds"])
            server = f"{entry['model']} at {entry['base_url']}"
        except (ValueError, KeyError, TypeError):
            report.unreadable_lines += 1
            continue
        if cutoff and when < cutoff:
            continue
        report.last_ts = str(entry["ts"])
        if outcome == OUTCOME_UNAVAILABLE:
            report.unavailable[caller] += 1
            continue
        report.by_caller.setdefault(caller, _Tally()).add(outcome, prompt, answer, seconds)
        report.by_server.setdefault(server, _Tally()).add(outcome, prompt, answer, seconds)
    return report
