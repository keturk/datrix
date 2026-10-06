#!/usr/bin/env python3
"""Repo-level gate for the skill assists (skill/lib/, including skill_assist.py, and datrix_scripts.evaluate_reports).

Every check builds a real workspace in a temporary directory -- git repositories, task files under
.tasks/phase-NN, a findings folder, a design folder -- and talks to a real OpenAI-compatible HTTP server
on loopback whose answers depend on the prompt it receives. Nothing here contacts the network's model
servers, and every request is recorded in a temporary usage log, never the machine's own.

Run through skill/skill-assist-gate.ps1.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from absorb import VERDICT_MISSING, VERDICT_PRESENT, find_references, transfer_check
from bug_resolution import (
    STATUS_RESOLVED,
    ResolutionFacts,
    VerificationRow,
    append_resolution,
    build_resolution,
)
from checklist import draft_checklist
from common import EXIT_NO_MODEL, AssistError, ContentFilter
from context_digest import build_digest
from datrix_scripts.customer_domain_isolation import hash_term
from datrix_scripts.evaluate_reports import render_project_quick_report, render_service_mechanical
from datrix_scripts.local_llm import LocalLlmPool, LocalLlmSettings
from datrix_scripts.local_llm_usage import USAGE_LOG_VARIABLE
from datrix_scripts.local_reading import WITHHELD_LINE
from datrix_scripts.paths import script_env
from findings import check_consolidation, extract_file
from phase_tasks import phase_tasks
from readiness import VERDICT_SATISFIED, missing_edges, satisfied_leads, unresolved_modules

CheckFunc = Callable[[], None]

_GREEN = "\033[92m"
_RED = "\033[91m"
_RESET = "\033[0m"
_LOOPBACK = "127.0.0.1"
# TEST-NET-1 (RFC 5737): never routed, so no model server can answer there.
_UNROUTABLE = "192.0.2.1"
_CLI = Path(__file__).resolve().parent / "skill_assist.py"
_PHASE = 7
_GATE_TERM = "zzgateterm"
_REPOS = ("datrix", "datrix-alpha")
_CORE = '"""Core helpers for alpha."""\n\nHELPERS = ("one", "two")\n'


def _ok(msg: str) -> None:
    print(f"{_GREEN}[OK]{_RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"{_RED}[FAIL]{_RESET} {msg}")


def run_checks(checks: list[CheckFunc]) -> bool:
    """Run every check, catching only AssertionError. Returns True iff all passed."""
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


# ===========================================================================
# fixtures
# ===========================================================================


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=gate", "-c", "user.email=gate@example.invalid",
                    *args], check=True, capture_output=True)


@contextmanager
def _workspace() -> Iterator[Path]:
    """Framework repositories (git), real Python, and a customer-term corpus registering one term."""
    with TemporaryDirectory(prefix="skill-assist-gate-") as temp:
        root = Path(temp)
        for repo in _REPOS:
            (root / repo).mkdir()
            _git(root / repo, "init", "-q")
        _write(root / "datrix-alpha/src/datrix_alpha/__init__.py", "")
        _write(root / "datrix-alpha/src/datrix_alpha/core.py", _CORE)
        _write(root / "datrix-alpha/src/datrix_alpha/other.py", '"""Other things."""\n\nVALUE = 1\n')
        _write(root / "datrix/scripts/config/customer-term-hashes.json", json.dumps({
            "algorithm": "sha256", "min_token_length": 5,
            "terms": [{"hash": hash_term(_GATE_TERM), "hint": "gate fixture"}]}))
        yield root


def _task(root: Path, number: int, *, depends: str = "None", review: tuple[str, ...] = (),
          create: tuple[str, ...] = (), context: str = "", prop: str = "the change holds") -> Path:
    reviews = "".join(f"{n}. `{path}` -- read\n" for n, path in enumerate(review, start=1))
    creates = "".join(f"### {n}. `{path}` -- purpose\n\nText.\n\n" for n, path in enumerate(create, start=1))
    text = (f"# Task {_PHASE:02d}-{number:02d}: Fixture task {number}\n\n## Overview\n\nA fixture.\n\n"
            f"**Package:** `datrix-alpha` (`{root / 'datrix-alpha'}`)\n**Design reference:** none\n"
            f"**Design acceptance property:** {prop}\n**Depends on:** {depends}\n\n"
            f"## Codebase Context\n\n{context}\n\n## Files to Review Before Starting\n\n{reviews}\n"
            f"## Files to Create\n\n{creates}## Success Criteria\n\n1. It works.\n")
    return _write(root / "datrix-alpha/.tasks" / f"phase-{_PHASE:02d}" /
                  f"task-{_PHASE:02d}-{number:02d}-fixture-{number}.md", text)


Responder = Callable[[str, str], str]


class _ModelServer:
    """An OpenAI-compatible server on loopback: ``respond(system, user)`` writes every answer."""

    def __init__(self, respond: Responder) -> None:
        self.requests: list[tuple[str, str]] = []
        requests = self.requests

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
                if body.get("max_tokens") == 1:
                    self._send({"choices": [{"message": {"content": "pong"}}]})
                    return
                system, user = (str(m["content"]) for m in body["messages"])
                requests.append((system, user))
                self._send({"choices": [{"message": {"content": respond(system, user)}, "finish_reason": "stop"}]})

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


def _closed_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((_LOOPBACK, 0))
        return int(sock.getsockname()[1])


def _pool(server: _ModelServer) -> LocalLlmPool:
    settings = LocalLlmSettings(machines=(_LOOPBACK,), reachable_timeout_ms=2000, generate_timeout_ms=5000,
                                allow_load=False, ollama_port=_closed_port(), openai_ports=(server.port,),
                                caller="gate")
    return LocalLlmPool(settings, report=lambda _line: None)


# ===========================================================================
# context digest and readiness
# ===========================================================================


def check_context_digest_maps_touched_directories_from_the_index() -> None:
    with _workspace() as root:
        _task(root, 1, review=("datrix-alpha/src/datrix_alpha/core.py",),
              create=("datrix-alpha/src/datrix_alpha/new_mod.py",))
        tasks = phase_tasks(root, _PHASE, pending_only=True)
        digest = build_digest(root, _PHASE, tasks)
        assert "## Package: datrix-alpha" in digest.text, digest.text
        assert "`core.py` **(named by a task)** -- Core helpers for alpha" in digest.text, digest.text
        assert "`other.py` -- Other things" in digest.text, digest.text
        assert "`new_mod.py` **(named by a task)** (does not exist yet" in digest.text, digest.text
        assert digest.lines <= 400 and not digest.trimmed, (digest.lines, digest.trimmed)


def check_readiness_finds_missing_edges_and_unresolvable_names_exactly() -> None:
    with _workspace() as root:
        new_mod = "datrix-alpha/src/datrix_alpha/new_mod.py"
        _task(root, 1, create=(new_mod,))
        _task(root, 2, review=(new_mod,), context="Uses `datrix_alpha.core` and `datrix_alpha.ghost`.")
        _task(root, 3, depends="task-07-01", review=(new_mod,), context="Uses `datrix_alpha.new_mod.thing`.")
        _task(root, 4, create=(new_mod,), depends="None")
        every = phase_tasks(root, _PHASE, pending_only=False)
        edges = missing_edges(root, every, every)
        pairs = {(e.task_id, e.needs) for e in edges}
        assert ("task-07-02", ("task-07-01", "task-07-04")) in pairs, edges
        assert not any(e.task_id == "task-07-03" for e in edges), "task-07-03 depends on its creator: " + str(edges)
        assert ("task-07-04", ("task-07-01",)) in pairs and ("task-07-01", ("task-07-04",)) in pairs, edges
        modules = unresolved_modules(root, every, every)
        names = {(m.task_id, m.name) for m in modules}
        assert names == {("task-07-02", "datrix_alpha.ghost")}, names


def check_readiness_satisfied_lead_reads_the_verdict_and_checks_citations() -> None:
    with _workspace() as root:
        _task(root, 1, create=("datrix-alpha/src/datrix_alpha/core.py",), prop="core exposes HELPERS")
        _task(root, 2, create=("datrix-alpha/src/datrix_alpha/missing.py",), prop="missing exists")
        answer = "SATISFIED\nHELPERS is defined at datrix-alpha/src/datrix_alpha/core.py:3 and at nowhere.py:9."
        with _ModelServer(lambda _s, _u: answer) as server:
            pending = phase_tasks(root, _PHASE, pending_only=True)
            leads = satisfied_leads(root, _pool(server), pending)
        assert [lead.task_id for lead in leads] == ["task-07-01"], "only a task whose edit sites exist is asked"
        assert leads[0].verdict == VERDICT_SATISFIED, leads[0]
        assert "nowhere.py:9" in leads[0].answer.split("---", 1)[1], "an unsent citation must be called out"


# ===========================================================================
# findings
# ===========================================================================


def check_findings_extraction_maps_tails_reports_invented_and_unassigned_citations() -> None:
    with _workspace() as root:
        source = _write(root / "reports/finding/20261001-000000-x.md",
                        "# X\n\nSee `datrix-alpha/src/x.py:3` and `datrix-alpha/src/y.py:9`.\n")
        reply = json.dumps({"findings": [{"title": "T", "seam": "s", "packages": ["datrix-alpha"], "defect": "d",
                                          "citations": ["x.py:3", "made/up.py:1"]}]})
        with _ModelServer(lambda _s, _u: reply) as server:
            result = extract_file(root, _pool(server), ContentFilter(root), source)
        assert result.findings[0].citations == ("datrix-alpha/src/x.py:3",), result.findings
        assert result.invented == ["made/up.py:1"], result.invented
        assert result.unassigned == ["datrix-alpha/src/y.py:9"], result.unassigned


def check_findings_never_send_a_registered_customer_term() -> None:
    with _workspace() as root:
        source = _write(root / "reports/finding/20261001-000000-t.md",
                        f"# T\n\nThe {_GATE_TERM} service breaks.\nPlain line.\n")
        reply = json.dumps({"findings": []})
        with _ModelServer(lambda _s, _u: reply) as server:
            extract_file(root, _pool(server), ContentFilter(root), source)
        sent = " ".join(user for _system, user in server.requests)
        assert _GATE_TERM not in sent, "a registered customer term reached the model"
        assert WITHHELD_LINE in sent and "Plain line." in sent, sent


def check_findings_check_refuses_a_lost_citation_and_a_dangling_related_pointer() -> None:
    with _workspace() as root:
        folder = root / "reports/finding"
        raw = _write(folder / "20261001-000000-r.md", "# R\n\nAt `a/b.py:1`.\n")
        kept = _write(folder / "consolidated-001-theme.md", "# Theme\n\n**Related:** consolidated-002-gone\n")
        failed = check_consolidation(folder, [raw])
        assert failed.lost == {raw.name: ["a/b.py:1"]}, failed.lost
        assert failed.dangling_related == {kept.name: ["consolidated-002"]}, failed.dangling_related
        _write(kept, "# Theme\n\n## 1. R\n\nAt `a/b.py:1`.\n")
        passed = check_consolidation(folder, [raw])
        assert passed.passed, passed


# ===========================================================================
# checklist and absorb
# ===========================================================================

_DESIGN = (
    "# 042: A Fixture Design With A Long Enough Title\n\n"
    "## D1 Guards\n\nEvery route guard must fail closed when the token is absent.\n\n"
    "## D2 Names\n\nThe emitter must never emit a reserved name.\n\n"
    "## Background\n\nSome history that states no rule.\n"
)


def check_checklist_verifies_quotes_and_lists_uncovered_requirement_lines() -> None:
    with _workspace() as root:
        design = _write(root / "design/042-fixture-design.md", _DESIGN)
        reply = json.dumps({"requirements": [
            {"id": "D1", "requirement": "Guards fail closed.", "surfaces": ["routes"], "first_line": 5,
             "last_line": 5, "quote": "route guard must fail closed when the token"},
            {"id": "", "requirement": "Invented.", "surfaces": [], "first_line": 9, "last_line": 9,
             "quote": "this sentence is not in the design at all"},
        ]})
        with _ModelServer(lambda _s, _u: reply) as server:
            checklist = draft_checklist(root, _pool(server), design)
        verified = [r.ident for r in checklist.requirements if r.quote_found]
        assert verified == ["D1"], checklist.requirements
        assert [n for n, _text in checklist.uncovered] == [9], checklist.uncovered


def check_absorb_references_find_name_number_and_title_but_not_task_folders() -> None:
    with _workspace() as root:
        design = _write(root / "design/042-fixture-design.md", _DESIGN)
        _write(root / "datrix-alpha/docs/a.md", "See design 042 for the details.\nUnrelated 042 count.\n")
        _write(root / "datrix-alpha/docs/b.md", "From 042-fixture-design.md and A Fixture Design With A Long "
                                                "Enough Title.\n")
        _write(root / "datrix-alpha/.tasks/phase-07/task-07-01-x.md", "Design reference: design 042\n")
        found = {(r.file, r.line) for r in find_references(root, design, [])}
        assert found == {("datrix-alpha/docs/a.md", 1), ("datrix-alpha/docs/b.md", 1)}, found


def check_absorb_transfer_gives_a_verdict_per_section() -> None:
    with _workspace() as root:
        design = _write(root / "design/042-fixture-design.md", _DESIGN)
        _write(root / "datrix-alpha/docs/guards.md", "# Guards\n\nRoute guards fail closed.\n")

        def respond(_system: str, user: str) -> str:
            return "PRESENT\ndatrix-alpha/docs/guards.md:3" if "D1 Guards" in user else "MISSING"

        with _ModelServer(respond) as server:
            checks = transfer_check(root, _pool(server), design, ["datrix-alpha/docs/guards.md"])
        verdicts = {c.heading: c.verdict for c in checks}
        assert verdicts["D1 Guards"] == VERDICT_PRESENT and verdicts["D2 Names"] == VERDICT_MISSING, verdicts


# ===========================================================================
# bug resolution
# ===========================================================================


def _facts() -> ResolutionFacts:
    return ResolutionFacts(STATUS_RESOLVED, "Both", ("aws",), ("aws",),
                           (VerificationRow("aws", "yes", ".generated/aws/x.py", "defect gone"),), "", "")


def check_bug_resolution_describes_framework_diffs_only_and_appends_once() -> None:
    with _workspace() as root:
        alpha = root / "datrix-alpha"
        _git(alpha, "add", "-A")
        _git(alpha, "commit", "-q", "-m", "base")
        _write(alpha / "src/datrix_alpha/core.py", _CORE + "EXTRA = 2\n")
        shop = root / "acme-shop"
        shop.mkdir()
        _git(shop, "init", "-q")
        _write(shop / "app.dtrx", "service Shop {}\n")
        report = _write(root / "acme-shop/bugs/bug.md", "# Bug: x\n\n## Summary\nBroken.\n")
        with _ModelServer(lambda _s, _u: "Adds an EXTRA constant to the core helpers.") as server:
            section = build_resolution(root, _pool(server), _facts(), [alpha, shop], {"src/datrix_alpha/core.py",
                                                                                     "app.dtrx"})
        sent = " ".join(user for _system, user in server.requests)
        assert "service Shop" not in sent, "a non-framework repository's diff reached the model"
        assert "Adds an EXTRA constant" in section and "`acme-shop/app.dtrx` | +1 / -0 lines" in section, section
        append_resolution(report, section)
        try:
            append_resolution(report, section)
        except AssistError:
            assert report.read_text(encoding="utf-8").count("## Resolution") == 1
            return
        raise AssertionError("a second Resolution was appended to a report that already had one")


def check_bug_resolution_refuses_incomplete_facts() -> None:
    with _workspace() as root:
        incomplete = ResolutionFacts(STATUS_RESOLVED, "Both", (), ("aws",), (), "", "")
        try:
            build_resolution(root, None, incomplete, [root / "datrix-alpha"], set())
        except AssistError as exc:
            assert "--exhibiting" in str(exc), exc
            return
        raise AssertionError("a Resolution without the exhibiting profiles and verification rows was built")


# ===========================================================================
# evaluation reports and the command line
# ===========================================================================


def check_quick_report_renders_every_scan_fact() -> None:
    payload: dict[str, object] = {
        "system_name": "Shop", "generated_at": "2026-10-05T10:00", "source": "s/system.dtrx",
        "generated_root": "g", "language": "Python", "platform": "Docker", "service_count": 2,
        "generated_service_count": 1, "missing_service_count": 1,
        "services": [{"qualified_name": "shop.A", "dtrx_path": "a.dtrx", "expected_dir": "shop_a",
                      "expected_dir_exists": True},
                     {"qualified_name": "shop.B", "dtrx_path": "b.dtrx", "expected_dir": "shop_b",
                      "expected_dir_exists": False}],
        "manifests": [{"target": "python", "file_count": 12, "missing_on_disk": ["x"], "generated_at": "t1"}],
        "infra": {"env_example": {"exists": False, "path": "g/.env.example"},
                  "nginx_conf": {"exists": True, "path": "g/nginx.conf"}},
        "docker_compose": {"exists": True, "path": "g/docker-compose.yml", "missing_service_entries": ["b"],
                           "infra_containers": {"nginx": True, "prometheus": True}},
        "gateway_enabled": True, "critical_blockers": ["No services generated"], "warnings": ["w1"],
        "prompt_files": ["e/service-a.prompt.md"],
    }
    text = render_project_quick_report(payload)
    for expected in ("**Project Readiness:** NOT READY -- 1 blocker(s)", "| shop.B | `b.dtrx` | `shop_b` | MISSING |",
                     "| python.json | 12 | 1 | t1 |", "| All services defined | FAIL | `b` |",
                     "| .env.example exists | FAIL |", "1. No services generated", "1. w1",
                     "[service-a.prompt.md](e/service-a.prompt.md)", "| Prometheus | Yes |"):
        assert expected in text, f"missing {expected!r} in:\n{text}"


def check_service_mechanical_renders_checks_and_dead_code() -> None:
    payload: dict[str, object] = {
        "generated_dir": "g/shop_a", "generated_at": "now",
        "service": {"qualified_name": "shop.A", "dir_convention_ok": False, "expected_dir": "shop_a",
                    "actual_dir": "a"},
        "artifact_check_summary": {"pass": 1, "fail": 1},
        "artifact_checks": [{"scope": "rdbms", "check": "orm_model", "status": "FAIL", "matched": []}],
        "manifest_subset": [{"target": "python", "service_file_count": 3, "missing_on_disk": []}],
        "dead_code": {"unused_module_dirs": [{"dir_name": "redis", "paths": ["src/redis"], "requires_block": "cache"}],
                      "orphaned_entity_artifacts": [], "suspect_dependencies": []},
        "dockerfile": {"exists": True, "matches": ["Dockerfile"]}, "migrations": {"migration_dirs": []},
        "env_var_references": {"DB_URL": ["main.py"]}, "env_var_files_scanned": 2, "dependencies": ["fastapi"],
    }
    text = render_service_mechanical(payload)
    for expected in ("MISMATCH (expected `shop_a`, found `a`)", "| rdbms | orm_model | FAIL | none |",
                     "| redis | `src/redis` | cache |", "| Migration dirs | FAIL | none |", "- `DB_URL`: `main.py`"):
        assert expected in text, f"missing {expected!r} in:\n{text}"


def check_cli_exits_3_when_no_local_model_answers() -> None:
    with _workspace() as root:
        design = _write(root / "design/042-fixture-design.md", _DESIGN)
        result = subprocess.run(
            [sys.executable, str(_CLI), "--workspace", str(root), "checklist", "--design", str(design),
             "--local-machine", _UNROUTABLE, "--local-reachable-timeout-ms", "300"],
            capture_output=True, text=True, check=False, env=script_env())
        assert result.returncode == EXIT_NO_MODEL, (result.returncode, result.stdout, result.stderr)
        assert "Do this phase yourself" in result.stderr, result.stderr


# ===========================================================================
# harness
# ===========================================================================


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
    check_context_digest_maps_touched_directories_from_the_index,
    check_readiness_finds_missing_edges_and_unresolvable_names_exactly,
    check_readiness_satisfied_lead_reads_the_verdict_and_checks_citations,
    check_findings_extraction_maps_tails_reports_invented_and_unassigned_citations,
    check_findings_never_send_a_registered_customer_term,
    check_findings_check_refuses_a_lost_citation_and_a_dangling_related_pointer,
    check_checklist_verifies_quotes_and_lists_uncovered_requirement_lines,
    check_absorb_references_find_name_number_and_title_but_not_task_folders,
    check_absorb_transfer_gives_a_verdict_per_section,
    check_bug_resolution_describes_framework_diffs_only_and_appends_once,
    check_bug_resolution_refuses_incomplete_facts,
    check_quick_report_renders_every_scan_fact,
    check_service_mechanical_renders_checks_and_dead_code,
    check_cli_exits_3_when_no_local_model_answers,
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Behaviour checks for the skill assists.")
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
    print(f"Running {len(checks)} skill-assist checks...\n")
    with TemporaryDirectory(prefix="skill-assist-gate-usage-") as temp:
        os.environ[USAGE_LOG_VARIABLE] = str(Path(temp) / "usage.jsonl")
        passed = run_checks(checks)
    print()
    if passed:
        print(f"{_GREEN}GATE PASSED{_RESET}: all {len(checks)} skill-assist checks passed.")
        return 0
    print(f"{_RED}GATE FAILED{_RESET}: see the failures above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
