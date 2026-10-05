"""The Resolution section /fix-bug-report appends to each bug report, assembled from the change on disk.

The skill supplies what only it knows -- the fix type, the profiles, the per-profile verification it
ran, or why a bug stayed unresolved. The script supplies the rest: the "Changes Made" table, one row
per changed file in the repositories named, from ``git diff HEAD`` and the untracked files.

A row's description comes from the diff. For a framework repository it is a one-line summary by a
local model of that file's diff (lines carrying a registered customer term are withheld first, and a
diff carrying one is never sent). For any other repository -- a product's app definition -- nothing is
sent anywhere: the row says how many lines changed and in which functions, from the diff's own hunk
headers.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from shared.framework_repos import framework_repos
from shared.local_llm import ChatRequest, LocalLlmPool, LocalLlmUnavailable

from assist.common import AssistError, ContentFilter, parallel, read_text, workspace_label

LOG = logging.getLogger(__name__)

RESOLUTION_HEADING = "## Resolution"
STATUS_RESOLVED = "Resolved"
STATUS_UNRESOLVED = "Unresolved"
FIX_TYPES = ("App Definition", "Generator/Template", "Both")
MAX_DIFF_CHARS = 12000
MAX_CONTEXTS = 4
MAX_CONTEXT_CHARS = 60
DESCRIBE_TEMPERATURE = 0.1
DESCRIBE_MAX_TOKENS = 120
VERIFICATION_FIELDS = 4
GIT_TIMEOUT_SECONDS = 60
DESCRIBE_SYSTEM = (
    "You describe a code change for a bug report's 'Changes Made' table. Given one file's diff, answer in "
    "ONE line of at most 25 words: what the change does to behaviour, not how the diff looks. No preamble.")


@dataclass(frozen=True)
class ChangedFile:
    repo: Path
    path: str
    diff: str
    framework: bool


@dataclass(frozen=True)
class VerificationRow:
    profile: str
    regenerated: str
    artifact: str
    result: str


def parse_verification(spec: str) -> VerificationRow:
    """``profile|regenerated|artifact|result`` (the four columns of the Per-Profile Verification table)."""
    parts = [part.strip() for part in spec.split("|")]
    if len(parts) != VERIFICATION_FIELDS or not all(parts):
        raise AssistError(
            f"--verification '{spec}' must be four non-empty fields separated by '|': "
            "profile|regenerated (yes/no -- why not)|artifact checked|result, e.g. "
            "'aws|yes|.generated/aws/svc/app.py|defect gone'.")
    return VerificationRow(*parts)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=GIT_TIMEOUT_SECONDS, check=False)


def _diff(repo: Path, path: str, tracked: bool) -> str:
    if tracked:
        result = _git(repo, "diff", "HEAD", "--", path)
    else:
        result = _git(repo, "diff", "--no-index", "--", os.devnull, path)
    if result.returncode not in (0, 1):
        raise AssistError(f"git diff of {path} in {repo} failed: {result.stderr.strip()}")
    return result.stdout


def _names(repo: Path, *args: str) -> list[str]:
    result = _git(repo, *args)
    if result.returncode != 0:
        raise AssistError(f"git {' '.join(args)} failed in {repo}: {result.stderr.strip()}")
    return [name.strip() for name in result.stdout.splitlines() if name.strip()]


def changed_files(workspace: Path, repo: Path, only: set[str]) -> list[ChangedFile]:
    """Every file changed against HEAD in ``repo`` (tracked and untracked), or only those in ``only``."""
    if not (repo / ".git").exists():
        raise AssistError(f"{repo} is not a git repository. Pass the root of a repository with --repo.")
    if _git(repo, "rev-parse", "--verify", "-q", "HEAD").returncode == 0:
        tracked = _names(repo, "diff", "--name-only", "HEAD")
        new = _names(repo, "ls-files", "--others", "--exclude-standard")
    else:  # no commit yet: every file in the index or the working tree is new
        tracked = []
        new = _names(repo, "ls-files", "--cached", "--others", "--exclude-standard")
    framework = repo.resolve() in {r.resolve() for r in framework_repos(workspace)}
    rows: list[ChangedFile] = []
    for names, is_tracked in ((tracked, True), (new, False)):
        for name in names:
            if only and name not in only:
                continue
            rows.append(ChangedFile(repo, name, _diff(repo, name, is_tracked), framework))
    return rows


def _mechanical(diff: str) -> str:
    added = sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---"))
    headers = [line.split("@@", 2)[2].strip() for line in diff.splitlines()
               if line.startswith("@@") and line.count("@@") >= 2]
    contexts = list(dict.fromkeys(h.split("(", 1)[0].rstrip(":").strip()[:MAX_CONTEXT_CHARS] for h in headers if h))
    where = f" in {'; '.join(f'`{c}`' for c in contexts[:MAX_CONTEXTS])}" if contexts else ""
    return f"+{added} / -{removed} lines{where}"


def describe(pool: LocalLlmPool | None, content: ContentFilter, change: ChangedFile) -> str:
    """One line for the Changes Made table: a model's summary for a framework file, else the diff's shape."""
    shape = _mechanical(change.diff)
    if pool is None or not change.framework or content.carries_term(change.diff):
        return shape
    try:
        reply = pool.chat(ChatRequest(system=DESCRIBE_SYSTEM, user=change.diff[:MAX_DIFF_CHARS],
                                      temperature=DESCRIBE_TEMPERATURE, max_tokens=DESCRIBE_MAX_TOKENS))
    except LocalLlmUnavailable as exc:
        LOG.warning("No local model for the change description of %s: %s", change.path, exc)
        return shape
    line = reply.text.strip().splitlines()[0].strip() if reply.text.strip() else ""
    return f"{line} ({shape})" if line else shape


@dataclass(frozen=True)
class ResolutionFacts:
    status: str
    fix_type: str
    exhibiting: tuple[str, ...]
    reached: tuple[str, ...]
    verification: tuple[VerificationRow, ...]
    reason: str
    notes: str


def render_resolution(workspace: Path, facts: ResolutionFacts, rows: list[tuple[ChangedFile, str]]) -> str:
    today = date.today().isoformat()
    if facts.status == STATUS_UNRESOLVED:
        return "\n".join(["", "---", "", RESOLUTION_HEADING, "", f"**Date**: {today}", f"**Status**: {STATUS_UNRESOLVED}",
                          f"**Reason**: {facts.reason}", "", "### Investigation Notes", "", facts.notes, ""])
    table = ["| File | Changes |", "|------|---------|"]
    table += [f"| `{workspace_label(workspace, change.repo / change.path)}` | {text.replace('|', '/')} |"
              for change, text in rows]
    checks = ["| Profile | Regenerated | Artifact checked | Result |", "|---------|-------------|------------------|--------|"]
    checks += [f"| `{v.profile}` | {v.regenerated} | `{v.artifact}` | {v.result} |" for v in facts.verification]
    return "\n".join([
        "", "---", "", RESOLUTION_HEADING, "", f"**Date**: {today}", f"**Status**: {STATUS_RESOLVED}",
        f"**Fix Type**: {facts.fix_type}", f"**Profiles exhibiting**: {', '.join(facts.exhibiting)}",
        f"**Profiles reached by the fix**: {', '.join(facts.reached)}", "", "### Changes Made", "", *table, "",
        "### Per-Profile Verification", "", *checks, ""])


def validate_facts(facts: ResolutionFacts) -> None:
    """Refuse a Resolution that would be missing what the skill must state."""
    if facts.status == STATUS_UNRESOLVED:
        if not facts.reason or not facts.notes:
            raise AssistError("An Unresolved resolution needs --reason and --notes (what was examined and why "
                              "the fix could not be applied).")
        return
    if facts.fix_type not in FIX_TYPES:
        raise AssistError(f"--fix-type '{facts.fix_type}' is not one of: {', '.join(FIX_TYPES)}.")
    if not facts.exhibiting or not facts.reached or not facts.verification:
        raise AssistError("A Resolved resolution needs --exhibiting, --reached and at least one --verification "
                          "row (one per profile the fix reaches).")


def build_resolution(workspace: Path, pool: LocalLlmPool | None, facts: ResolutionFacts, repos: list[Path],
                     only: set[str]) -> str:
    """The Resolution section text for the facts given and the changes on disk."""
    validate_facts(facts)
    if facts.status == STATUS_UNRESOLVED:
        return render_resolution(workspace, facts, [])
    changes = [change for repo in repos for change in changed_files(workspace, repo, only)]
    if not changes:
        raise AssistError("No changed file found in the repositories named (git diff HEAD and untracked files "
                          "are both empty). Pass the repositories the fix changed with --repo.")
    content = ContentFilter(workspace)
    described = parallel(changes, lambda change: describe(pool, content, change))
    return render_resolution(workspace, facts, list(zip(changes, described, strict=True)))


def append_resolution(report: Path, section: str) -> None:
    """Append ``section`` to the report, refusing one that already has a Resolution."""
    text = read_text(report)
    if any(line.strip() == RESOLUTION_HEADING for line in text.splitlines()):
        raise AssistError(f"{report} already has a '{RESOLUTION_HEADING}' section. The original report is never "
                          "modified, and one resolution is appended once.")
    with report.open("a", encoding="utf-8") as handle:
        handle.write(("" if text.endswith("\n") else "\n") + section)
