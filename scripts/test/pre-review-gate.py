#!/usr/bin/env python3
"""Repo-level gate for the first-pass pre-review (``scripts/library/git/pre_review.py``).

Plain checks in the shape of ``shared-library-gate.py``: each builds real git
repositories in a fresh temporary directory and runs the real review over them; the
model-review checks talk to a real HTTP server on loopback. No mocks.

``--only PREFIX`` runs the checks whose name starts with PREFIX. ``--harness-self-test``
proves the harness reports a deliberately failing check as failed.

Exit codes: 0 = every check passed, 1 = at least one check failed, 2 = usage error.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

_SCRIPT_DIR = Path(__file__).resolve().parent
_LIBRARY_DIR = _SCRIPT_DIR.parent / "library"
if str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from git.pre_review import (  # noqa: E402
    RULE_BARE_EXCEPT,
    RULE_EXCEPT_PASS,
    RULE_GET_NONE,
    RULE_PLACEHOLDER,
    RULE_TODO,
    RULE_UNTYPED_DEF,
    ChangedFile,
    UnreadableAnswer,
    added_lines_by_path,
    changed_python_files,
    definite_findings,
    parse_model_findings,
    review,
)
from shared.local_llm import LocalLlmPool, LocalLlmSettings  # noqa: E402

CheckFunc = Callable[[], None]

_GREEN = "\033[92m"
_RED = "\033[91m"
_RESET = "\033[0m"
_LOOPBACK = "127.0.0.1"
_GIT_IDENTITY = ("-c", "user.name=pre-review-gate", "-c", "user.email=gate@example.invalid",
                 "-c", "commit.gpgsign=false")

# Every definite rule on an ADDED line (2-19), and each rule once more on an unchanged
# line (21-33) where it must NOT be reported. Line numbers are asserted below.
_REVIEWED = '''"""Fixture module."""
def untyped(value):
    return value
def lookup(table: dict[str, int]) -> int | None:
    return table.get("k", None)
def guarded() -> None:
    try:
        pass
    except:
        pass
def placeholder() -> None:
    """Only a docstring."""
# TODO: finish
class Shape:
    def area(self) -> float:
        raise NotImplementedError
    @staticmethod
    def make(size: int) -> "Shape":
        return Shape()
PADDING = 1
def old_untyped(value):
    return value
def old_lookup(table: dict[str, int]) -> int | None:
    return table.get("k", None)
class Readable(Protocol):
    def read(self) -> bytes: ...
class Base(ABC):
    @abstractmethod
    def run(self) -> None:
        pass
def old_placeholder() -> None:
    pass
# FIXME: old
'''
_ADDED = frozenset(range(2, 20))


def _ok(msg: str) -> None:
    print(f"{_GREEN}[OK]{_RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"{_RED}[FAIL]{_RESET} {msg}")


def run_checks(checks: list[CheckFunc]) -> bool:
    all_passed = True
    for check in checks:
        try:
            check()
        except AssertionError as exc:
            _fail(f"{check.__name__}: {exc}")
            all_passed = False
        else:
            _ok(check.__name__)
    return all_passed


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *_GIT_IDENTITY, "-C", str(repo), *args], check=True, capture_output=True)


def _write(root: Path, files: dict[str, str]) -> None:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _repo(workspace: Path, name: str, committed: dict[str, str]) -> Path:
    repo = workspace / name
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _write(repo, {**committed, ".gitignore": "ignored/\n"})
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fixture")
    return repo


def check_diff_parser_maps_added_lines_per_path() -> None:
    diff = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
        "@@ -3,0 +4,2 @@\n+x\n+y\n"
        "@@ -9 +11 @@\n-old\n+new\n"
        "@@ -20,3 +23,0 @@\n-gone\n"
        "diff --git a/b.py b/b.py\n--- a/b.py\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-a\n-b\n"
    )
    assert added_lines_by_path(diff) == {"a.py": {4, 5, 11}}, added_lines_by_path(diff)


def check_definite_rules_fire_on_added_lines_only() -> None:
    changed = ChangedFile("alpha", "src/mod.py", Path("unused"), _ADDED)
    found = {(f.line, f.rule) for f in definite_findings(changed, _REVIEWED)}
    expected = {
        (2, RULE_UNTYPED_DEF),
        (5, RULE_GET_NONE),
        (9, RULE_BARE_EXCEPT), (9, RULE_EXCEPT_PASS),
        (11, RULE_PLACEHOLDER),
        (13, RULE_TODO),
        (15, RULE_PLACEHOLDER),
    }
    assert found == expected, f"definite findings differ:\n  got      {sorted(found)}\n  expected {sorted(expected)}"
    everywhere = ChangedFile("alpha", "src/mod.py", Path("unused"), frozenset(range(1, 40)))
    all_rules = {(f.line, f.rule) for f in definite_findings(everywhere, _REVIEWED)}
    assert {(21, RULE_UNTYPED_DEF), (24, RULE_GET_NONE), (31, RULE_PLACEHOLDER), (33, RULE_TODO)} <= all_rules, \
        f"the matchers must find the planted old violations when their lines count as added: {sorted(all_rules)}"
    assert not {line for line, _ in all_rules} & {26, 29}, \
        f"Protocol and @abstractmethod declarations must be exempt: {sorted(all_rules)}"
    assert (15, RULE_UNTYPED_DEF) not in all_rules and (18, RULE_UNTYPED_DEF) not in all_rules, \
        "self and a fully annotated staticmethod need no further annotation"


def check_pending_changes_come_from_git() -> None:
    with TemporaryDirectory() as temp:
        workspace = Path(temp)
        repo = _repo(workspace, "alpha", {"src/mod.py": "A = 1\nB = 2\n"})
        _write(repo, {"src/mod.py": "A = 1\nNEW = 3\nB = 2\n", "src/fresh.py": "X = 1\nY = 2\n",
                      "ignored/skip.py": "Z = 1\n", "notes.md": "text\n"})
        files = {f.path: set(f.added) for f in changed_python_files(repo)}
        assert files == {"src/mod.py": {2}, "src/fresh.py": {1, 2}}, files


def check_model_findings_must_be_grounded() -> None:
    changed = ChangedFile("alpha", "src/mod.py", Path("unused"), frozenset({2, 3}))
    lines = ["x = 1", "value = config.get('k') or 'default'", "y = 2", "z = 3"]

    def answer(**item: object) -> str:
        return json.dumps({"findings": [{"rule": "silent-fallback", "explanation": "e", "confidence": "high",
                                         "line": 2, "quote": "or 'default'", **item}]})

    kept, dropped = parse_model_findings(answer(), changed, lines)
    assert [(f.line, f.rule) for f in kept] == [(2, "silent-fallback")] and dropped == 0, (kept, dropped)
    for bad in ({"quote": "not in the line"}, {"confidence": "medium"}, {"line": 4, "quote": "z = 3"},
                {"rule": "no-such-rule"}):
        kept, dropped = parse_model_findings(answer(**bad), changed, lines)
        assert not kept and dropped == 1, f"{bad} must be dropped: {kept}"
    for unreadable in ("not json", json.dumps({"other": []})):
        try:
            parse_model_findings(unreadable, changed, lines)
        except UnreadableAnswer:
            continue
        raise AssertionError(f"{unreadable!r} must raise UnreadableAnswer")


def _closed_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((_LOOPBACK, 0))
        return int(sock.getsockname()[1])


class _ModelServer:
    """An OpenAI-compatible server on loopback answering every chat with ``answer``."""

    def __init__(self, answer: str) -> None:
        self.prompts: list[str] = []
        prompts = self.prompts

        class _Handler(BaseHTTPRequestHandler):
            def _send(self, payload: object) -> None:
                data = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802 -- http.server's dispatch name
                self._send({"data": [{"id": "gate-model"}]})

            def do_POST(self) -> None:  # noqa: N802 -- http.server's dispatch name
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
                if body.get("max_tokens") != 1:
                    prompts.append(str(body["messages"][-1]["content"]))
                self._send({"choices": [{"message": {"content": answer}, "finish_reason": "stop"}]})

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                return

        self._httpd = ThreadingHTTPServer((_LOOPBACK, 0), _Handler)
        self.port = int(self._httpd.server_address[1])
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def __enter__(self) -> _ModelServer:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


def check_model_review_is_advisory_and_skips_tests() -> None:
    answer = json.dumps({"findings": [{"line": 2, "rule": "silent-fallback", "quote": "or 'd'",
                                       "explanation": "defaulted", "confidence": "high"}]})
    with TemporaryDirectory() as temp, _ModelServer(answer) as server:
        workspace = Path(temp)
        repo = _repo(workspace, "alpha", {"src/mod.py": "A = 1\n"})
        _write(repo, {"src/mod.py": "A = 1\nB = cfg.get('k') or 'd'\n", "tests/test_mod.py": "C = 1\n"})
        settings = LocalLlmSettings(machines=(_LOOPBACK,), reachable_timeout_ms=2000, generate_timeout_ms=5000,
                                    ollama_port=_closed_port(), openai_ports=(server.port,))
        result = review(workspace, LocalLlmPool(settings, report=lambda _: None), workers=2, max_chars=4000)
        assert [(f.file, f.line) for f in result.advisory] == [("alpha/src/mod.py", 2)], result.advisory
        assert not result.definite, result.definite
        assert len(server.prompts) == 1 and "alpha/src/mod.py" in server.prompts[0], \
            f"only the non-test file may be sent: {server.prompts}"
        offline = review(workspace, None, workers=2, max_chars=4000)
        assert not offline.advisory and "not run" in offline.advisory_note, offline.advisory_note


def _deliberately_failing_check() -> None:
    assert False, "deliberately failing check for --harness-self-test"


def harness_self_test() -> bool:
    print("=== Harness self-test: a deliberately-failing check must be reported FAILED ===")
    if run_checks([_deliberately_failing_check]):
        _fail("harness self-test: the deliberately-failing check was NOT reported as failed")
        return False
    _ok("harness self-test: the deliberately-failing check was correctly reported FAILED")
    return True


_ALL_CHECKS: list[CheckFunc] = [
    check_diff_parser_maps_added_lines_per_path,
    check_definite_rules_fire_on_added_lines_only,
    check_pending_changes_come_from_git,
    check_model_findings_must_be_grounded,
    check_model_review_is_advisory_and_skips_tests,
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Behaviour checks for the first-pass pre-review.")
    parser.add_argument("--harness-self-test", action="store_true",
                        help="Run only the harness self-test (a deliberately-failing dummy check).")
    parser.add_argument("--only", metavar="PREFIX", help="Run only the checks whose name starts with PREFIX.")
    args = parser.parse_args()
    if args.harness_self_test:
        return 0 if harness_self_test() else 1
    checks = _ALL_CHECKS
    if args.only:
        checks = [check for check in _ALL_CHECKS if check.__name__.startswith(args.only)]
        if not checks:
            print(f"Error: no check name starts with {args.only!r}. Checks: "
                  f"{', '.join(c.__name__ for c in _ALL_CHECKS)}.", file=sys.stderr)
            return 2
    print(f"Running {len(checks)} pre-review behaviour checks...\n")
    passed = run_checks(checks)
    print()
    if passed:
        print(f"{_GREEN}GATE PASSED{_RESET}: all {len(checks)} pre-review behaviour checks passed.")
        return 0
    print(f"{_RED}GATE FAILED{_RESET}: see the failures above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
