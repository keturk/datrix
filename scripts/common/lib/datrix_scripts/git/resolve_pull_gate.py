"""Repo-level gate for the pull-over-local-work script (``datrix_scripts.git.resolve_pull``).

The module behind ``git/resolve-pull-gate.ps1`` (and its ``.sh`` twin), in gate mode: its run ends on the
``[GATE] resolve-pull PASSED|FAILED exit=<n> log=<path>`` verdict line. Each check builds an origin
repository and a clone of it in a fresh temporary directory, commits upstream, edits the clone, and runs the
real resolution over the clone: the clean reapply, a conflict left for a hand merge with its packet, the
finish refusing markers and dropped local lines, a set-aside untracked file, a line-ending-only overlap, and
the merge draft checked against both sides (against a real loopback model server). No mocks; no real
checkout is touched.

``--only PREFIX`` runs the checks whose name starts with PREFIX. ``--harness-self-test`` proves the
harness reports a deliberately failing check as failed. ``--self-test`` runs that and the wrapper seam
checks.

Exit codes: 0 = every check passed, 1 = at least one check failed, 2 = usage error.
"""

from __future__ import annotations

import argparse
import itertools
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from datrix_scripts.customer_domain_isolation import TermCorpus, hash_term
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, CheckFunc, check_list_main, check_list_parser
from datrix_scripts.gate_log import run_as_gate
from datrix_scripts.git.resolve_pull import (
    OUTCOME_FINISHED,
    OUTCOME_NEEDS_MERGE,
    OUTCOME_UP_TO_DATE,
    Hunk,
    MergeDrafter,
    finish_repo,
    parse_diff3,
    resolve_repo,
)
from datrix_scripts.local_llm import LocalLlmPool, LocalLlmSettings
from datrix_scripts.local_llm_loopback import LOOPBACK, LoopbackOllama, answering
from datrix_scripts.local_llm_usage import GATE_USAGE_LOG
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import GIT_SCRIPTS_DIR, seam_checks

MODULE: Final = "datrix_scripts.git.resolve_pull_gate"
WRAPPER: Final = "resolve-pull-gate"
GATE: Final = "resolve-pull"

_IDENTITY = {"user.name": "resolve-pull-gate", "user.email": "gate@example.invalid", "commit.gpgsign": "false",
             "core.autocrlf": "false"}
_LINES = [f"line {n}" for n in range(1, 21)]
_BASE = "\n".join(_LINES) + "\n"
_NAMES = itertools.count(1)
_GATE_TERM = "zzgateterm"
_MIN_TERM_LENGTH = 3


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    return result.stdout.decode("utf-8")


def _configure(repo: Path) -> None:
    for key, value in _IDENTITY.items():
        _git(repo, "config", key, value)


def _plant(root: Path, files: dict[str, str]) -> None:
    """Write each file's exact bytes: text mode would turn every LF into CRLF on Windows."""
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))


def _with_line(number: int, text: str, base: str = _BASE) -> str:
    lines = base.splitlines()
    lines[number - 1] = text
    return "\n".join(lines) + "\n"


def _commit_upstream(origin: Path, files: dict[str, str]) -> None:
    _plant(origin, files)
    _git(origin, "add", "-A")
    _git(origin, "commit", "-q", "-m", "upstream change")


@contextmanager
def _clone(files: dict[str, str]) -> Iterator[tuple[Path, Path]]:
    """An origin holding ``files`` and a clone of it (named uniquely: its state lives in the workspace .tmp)."""
    with TemporaryDirectory() as tmp:
        origin = Path(tmp) / "origin"
        origin.mkdir()
        _git(origin, "init", "-q", "-b", "main")
        _configure(origin)
        _commit_upstream(origin, files)
        clone = Path(tmp) / f"resolve-pull-gate-{os.getpid()}-{next(_NAMES)}"
        subprocess.run(["git", "-c", "core.autocrlf=false", "clone", "-q", str(origin), str(clone)], check=True,
                       capture_output=True)
        _configure(clone)
        try:
            yield origin, clone
        finally:
            shutil.rmtree(WORKSPACE_DIR / ".tmp" / "resolve-conflicts" / clone.name, ignore_errors=True)


def _stashes(repo: Path) -> list[str]:
    return [line for line in _git(repo, "stash", "list").splitlines() if line]


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_clean_reapply_shelves_only_the_overlap_and_drops_the_entry() -> None:
    with _clone({"a.txt": _BASE, "b.txt": _BASE, "new.txt": "x\n"}) as (origin, clone):
        _git(origin, "rm", "-q", "new.txt")
        _git(origin, "commit", "-q", "-m", "drop new")
        _git(clone, "pull", "-q")
        _commit_upstream(origin, {"a.txt": _with_line(1, "upstream 1"), "added.txt": "same\n"})
        _plant(clone, {"a.txt": _with_line(15, "local 15"), "b.txt": _with_line(3, "local 3"),
                            "added.txt": "same\n"})
        report = resolve_repo(clone, None)
        _expect(report.outcome == OUTCOME_FINISHED, f"expected finished, got {report.outcome}: {report.lines}")
        text = (clone / "a.txt").read_text(encoding="utf-8")
        _expect("upstream 1" in text and "local 15" in text, f"both edits must survive in a.txt:\n{text}")
        _expect("local 3" in (clone / "b.txt").read_text(encoding="utf-8"), "an edit outside the overlap moved")
        _expect(_stashes(clone) == [], f"the stash entry must be dropped: {_stashes(clone)}")
        _expect(resolve_repo(clone, None).outcome == OUTCOME_UP_TO_DATE, "a second run must find nothing to pull")


def check_conflict_keeps_markers_writes_a_packet_and_finish_refuses_until_merged() -> None:
    with _clone({"a.txt": _BASE}) as (origin, clone):
        _commit_upstream(origin, {"a.txt": _with_line(5, "upstream 5")})
        _plant(clone, {"a.txt": _with_line(5, "local 5")})
        report = resolve_repo(clone, None)
        _expect(report.outcome == OUTCOME_NEEDS_MERGE, f"expected a hand merge, got {report.outcome}")
        packet = next(Path(line.split("packet: ", 1)[1]) for line in report.lines if line.startswith("packet: "))
        body = packet.read_text(encoding="utf-8")
        _expect("### Hunk 1" in body and "local 5" in body and "upstream 5" in body and "line 5" in body,
                f"the packet must carry local, base and incoming:\n{body}")
        _expect(len(_stashes(clone)) == 1, "the stash entry is the safety copy until finish")
        refused = finish_repo(clone, merged=set())
        _expect(refused.outcome == OUTCOME_NEEDS_MERGE and any("conflict marker" in line for line in refused.lines),
                f"finish must refuse markers: {refused.lines}")
        _plant(clone, {"a.txt": _with_line(5, "upstream 5\nlocal 5")})
        done = finish_repo(clone, merged=set())
        _expect(done.outcome == OUTCOME_FINISHED, f"expected finished, got {done.outcome}: {done.lines}")
        _expect(_stashes(clone) == [], "finish drops the entry")
        _expect("a.txt" not in _git(clone, "diff", "--cached", "--name-only"), "finish leaves nothing staged")


def check_finish_refuses_a_dropped_local_line_unless_named_merged() -> None:
    with _clone({"a.txt": _BASE}) as (origin, clone):
        _commit_upstream(origin, {"a.txt": _with_line(5, "upstream 5")})
        _plant(clone, {"a.txt": _with_line(5, "local 5")})
        resolve_repo(clone, None)
        _plant(clone, {"a.txt": _with_line(5, "upstream 5")})
        refused = finish_repo(clone, merged=set())
        _expect(any("local line not in the working tree: local 5" in line for line in refused.lines),
                f"a dropped local line must refuse the drop: {refused.lines}")
        _expect(len(_stashes(clone)) == 1, "a refused finish keeps the entry")
        done = finish_repo(clone, merged={"a.txt"})
        _expect(done.outcome == OUTCOME_FINISHED and any("local 5" in line for line in done.lines),
                f"a path named merged finishes and reports the line: {done.lines}")


def check_untracked_collision_is_set_aside_and_must_be_merged_back() -> None:
    with _clone({"a.txt": _BASE}) as (origin, clone):
        _commit_upstream(origin, {"notes.txt": "upstream note\n"})
        _plant(clone, {"notes.txt": "my local note\n"})
        report = resolve_repo(clone, None)
        _expect(report.outcome == OUTCOME_NEEDS_MERGE and any("notes.txt" in line for line in report.lines),
                f"a differing untracked collision needs a merge: {report.lines}")
        _expect((clone / "notes.txt").read_text(encoding="utf-8") == "upstream note\n", "the pull brings its copy")
        refused = finish_repo(clone, merged=set())
        _expect(any("my local note" in line for line in refused.lines),
                f"the set-aside line must be merged: {refused.lines}")
        _plant(clone, {"notes.txt": "upstream note\nmy local note\n"})
        _expect(finish_repo(clone, merged=set()).outcome == OUTCOME_FINISHED, "merged back, finish completes")


def check_line_ending_only_overlap_is_restored_not_shelved() -> None:
    with _clone({"a.txt": _BASE}) as (origin, clone):
        _commit_upstream(origin, {"a.txt": _with_line(2, "upstream 2")})
        (clone / "a.txt").write_bytes(_BASE.replace("\n", "\r\n").encode("utf-8"))
        report = resolve_repo(clone, None)
        _expect(report.outcome == OUTCOME_FINISHED, f"expected finished, got {report.outcome}: {report.lines}")
        _expect((clone / "a.txt").read_bytes() == _with_line(2, "upstream 2").encode("utf-8"),
                "the line-ending-only file must take the incoming content")


def check_diff3_parser_reads_two_and_three_sided_hunks() -> None:
    three = parse_diff3(["keep", "<<<<<<< local", "mine", "||||||| base", "old", "=======", "theirs",
                         ">>>>>>> incoming", "tail"])
    _expect(three == [Hunk(2, ("mine",), ("old",), ("theirs",))], f"three-sided: {three}")
    two = parse_diff3(["<<<<<<< local", "mine", "=======", "theirs", ">>>>>>> incoming"])
    _expect(two == [Hunk(1, ("mine",), (), ("theirs",))], f"two-sided: {two}")


def _drafter(server: LoopbackOllama, repo: str) -> MergeDrafter:
    settings = LocalLlmSettings(machines=(LOOPBACK,), reachable_timeout_ms=2000, generate_timeout_ms=5000,
                                allow_load=False, ollama_port=server.port, caller="gate")
    corpus = TermCorpus(frozenset({hash_term(_GATE_TERM)}), _MIN_TERM_LENGTH)
    return MergeDrafter(LocalLlmPool(settings, report=lambda _line: None), corpus, {repo})


def check_merge_draft_is_checked_against_both_sides() -> None:
    hunk = Hunk(1, ("a = 1", "local = 2"), ("a = 1",), ("a = 1", "incoming = 3"))
    repo = Path("datrix-alpha")
    with LoopbackOllama(answering("a = 1\nlocal = 2\nincoming = 3")) as server:
        _expect("CHECKED" in _drafter(server, repo.name).draft(repo, hunk), "a draft with both sides is checked")
    with LoopbackOllama(answering("a = 1\nincoming = 3")) as server:
        verdict = _drafter(server, repo.name).draft(repo, hunk)
        _expect("UNCHECKED" in verdict and "local = 2" in verdict, f"a dropped line is named: {verdict}")
    with LoopbackOllama(answering("EXCLUSIVE both set the same constant")) as server:
        _expect("mutually exclusive" in _drafter(server, repo.name).draft(repo, hunk), "EXCLUSIVE is reported")
    with LoopbackOllama(answering("never sent")) as server:
        verdict = _drafter(server, "datrix-alpha").draft(Path("customer-product"), hunk)
        _expect(verdict.startswith("no draft") and not server.chats, "a non-framework repo is never sent")
        termed = Hunk(1, (f"name = '{_GATE_TERM}'",), (), ("name = 'x'",))
        verdict = _drafter(server, repo.name).draft(repo, termed)
        _expect(verdict.startswith("no draft") and not server.chats, "a hunk carrying a customer term is never sent")


_ALL_CHECKS: list[CheckFunc] = [
    check_clean_reapply_shelves_only_the_overlap_and_drops_the_entry,
    check_conflict_keeps_markers_writes_a_packet_and_finish_refuses_until_merged,
    check_finish_refuses_a_dropped_local_line_unless_named_merged,
    check_untracked_collision_is_set_aside_and_must_be_merged_back,
    check_line_ending_only_overlap_is_restored_not_shelved,
    check_diff3_parser_reads_two_and_three_sided_hunks,
    check_merge_draft_is_checked_against_both_sides,
]


def build_parser() -> argparse.ArgumentParser:
    """The options of ``git/resolve-pull-gate.ps1``: one per wrapper parameter, spelled exactly."""
    return check_list_parser("Behaviour checks for the pull-over-local-work script.", debug_flag=WRAPPER_DEBUG_FLAG,
                             allow_abbrev=False)


def _gate(argv: Sequence[str] | None) -> int:
    # --self-test: the harness reports a deliberate failure, and the wrapper is the template rendered
    # with this parser's options. The checks' own loopback model servers must never count as real use
    # of the machines.
    parser = build_parser()
    return check_list_main(
        parser.description or "",
        "resolve-pull behaviour",
        _ALL_CHECKS,
        self_test=seam_checks(wrapper=WRAPPER, module=MODULE, parser=parser, folder=GIT_SCRIPTS_DIR),
        argv=argv,
        parser=parser,
        temp_file_variable=GATE_USAGE_LOG,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the verdict, in gate mode."""
    return run_as_gate(GATE, MODULE, _gate, argv)


if __name__ == "__main__":
    sys.exit(main())
