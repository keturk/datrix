"""How much agents use the code index, against the searches it could have answered.

Reads the log the PostToolUse hook ``record-search-usage.py`` appends on this machine and
compares index tool calls with the grep, file-read and shell-search calls they replace.
Sizes are the characters each answer put into context; "tokens" is that divided by four,
an estimate good enough to compare approaches, not a bill.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from code_index.sources import USAGE_LOG_NAME, index_dir

CHARS_PER_TOKEN = 4
# A whole-file read this large is one an outline plus a ranged read would have answered
# for a fraction of the cost (about 2,000 tokens and up).
LARGE_READ_CHARS = 8000
TOP_READS = 10

CATEGORY_INDEX = "index"
CATEGORY_GREP = "grep"
CATEGORY_READ = "read"
CATEGORY_SHELL_SEARCH = "shell_search"

# A grep for one identifier (optionally a dotted path, a word boundary, a def/class prefix,
# or a trailing call paren): a definition or reference lookup find_symbol/find_references answers.
_IDENTIFIER_PATTERN = re.compile(
    r"^(?:def\s+|class\s+|\\b)?[A-Za-z_][A-Za-z0-9_]*(?:\\?\.[A-Za-z_][A-Za-z0-9_]*)*(?:\\b|\\\(|\()?$"
)


@dataclass
class Tally:
    calls: int = 0
    chars: int = 0

    def add(self, chars: int) -> None:
        self.calls += 1
        self.chars += chars

    def render(self) -> str:
        return f"{self.calls} calls, ~{self.chars // CHARS_PER_TOKEN:,} tokens"


@dataclass
class UsageReport:
    since: str
    sessions: int
    unreadable_lines: int
    categories: dict[str, Tally] = field(default_factory=dict)
    index_tools: Counter[str] = field(default_factory=Counter)
    identifier_greps: Tally = field(default_factory=Tally)
    large_full_reads: Tally = field(default_factory=Tally)
    top_full_reads: Counter[str] = field(default_factory=Counter)

    @property
    def replaceable(self) -> int:
        """Calls the index could have answered: identifier greps, large whole-file reads, shell searches."""
        shell = self.categories.get(CATEGORY_SHELL_SEARCH, Tally()).calls
        return self.identifier_greps.calls + self.large_full_reads.calls + shell

    def render(self) -> str:
        index_calls = self.categories.get(CATEGORY_INDEX, Tally()).calls
        total = index_calls + self.replaceable
        share = f"{100 * index_calls // total}%" if total else "n/a"
        lines = [f"Code-search usage since {self.since} ({self.sessions} sessions)"]
        lines.extend(f"  {name:13} {tally.render()}" for name, tally in sorted(self.categories.items()))
        tools = ", ".join(f"{name} {count}" for name, count in self.index_tools.most_common()) or "none"
        lines.append(f"Index tools used: {tools}")
        lines.append(f"Index could have answered: identifier greps {self.identifier_greps.render()}; "
                     f"whole reads of large .py files {self.large_full_reads.render()}")
        lines.append(f"Index share of answerable lookups: {share} ({index_calls} of {total})")
        if self.top_full_reads:
            lines.append("Most-read large files (read whole, not by range):")
            lines.extend(f"  {count:3}  {path}" for path, count in self.top_full_reads.most_common(TOP_READS))
        if self.unreadable_lines:
            lines.append(f"Unreadable log lines skipped: {self.unreadable_lines}")
        return "\n".join(lines)


def usage_log(workspace: Path) -> Path:
    return index_dir(workspace) / USAGE_LOG_NAME


def _relative(path: str, workspace: Path) -> str:
    normalized = path.replace("\\", "/")
    prefix = str(workspace).replace("\\", "/").rstrip("/") + "/"
    return normalized[len(prefix):] if normalized.lower().startswith(prefix.lower()) else normalized


def _record(report: UsageReport, entry: dict[str, object], chars: int, workspace: Path) -> None:
    category = str(entry.get("category", ""))
    report.categories.setdefault(category, Tally()).add(chars)
    detail = str(entry.get("detail", ""))
    if category == CATEGORY_INDEX:
        report.index_tools[str(entry.get("tool", ""))] += 1
    elif category == CATEGORY_GREP and _IDENTIFIER_PATTERN.match(detail):
        report.identifier_greps.add(chars)
    elif category == CATEGORY_READ and not entry.get("ranged") and chars >= LARGE_READ_CHARS:
        report.large_full_reads.add(chars)
        report.top_full_reads[_relative(detail, workspace)] += 1


def usage_report(workspace: Path, days: int) -> UsageReport:
    """Summarize the last ``days`` days of the usage log (0 = everything logged)."""
    cutoff = datetime.now(UTC) - timedelta(days=days) if days else None
    report = UsageReport(since=cutoff.date().isoformat() if cutoff else "the first logged call", sessions=0,
                         unreadable_lines=0)
    log = usage_log(workspace)
    if not log.exists():
        return report
    sessions: set[str] = set()
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
            when = datetime.fromisoformat(str(entry["ts"]))
            chars = int(entry["response_chars"])
        except (ValueError, KeyError, TypeError):
            report.unreadable_lines += 1
            continue
        if cutoff and when < cutoff:
            continue
        sessions.add(str(entry.get("session", "")))
        _record(report, entry, chars, workspace)
    report.sessions = len(sessions)
    return report
