"""Repo-level gate for the skill assists (the ``datrix_scripts.skill`` assist modules, their command line
``datrix_scripts.skill.assist_cli``, and ``datrix_scripts.evaluate_reports``).

Every check builds a real workspace in a temporary directory -- git repositories, task files under
.tasks/phase-NN, a findings folder, a design folder -- and talks to a real Ollama-shaped HTTP server on
loopback (datrix_scripts.local_llm_loopback) whose answers depend on the prompt it receives. Nothing here contacts the network's model
servers, and every request is recorded in a temporary usage log, never the machine's own.

The module behind ``scripts/skill/skill-assist-gate.ps1`` (and its ``.sh`` twin), in gate mode: its run ends on
the ``[GATE] skill-assist PASSED|FAILED exit=<n> log=<path>`` verdict line.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from datrix_scripts.customer_domain_isolation import hash_term
from datrix_scripts.evaluate_reports import render_project_quick_report, render_service_mechanical
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, CheckFunc, check_list_main, check_list_parser, write_file
from datrix_scripts.gate_log import run_as_gate
from datrix_scripts.local_llm import LocalLlmPool, LocalLlmSettings
from datrix_scripts.local_llm_loopback import LOOPBACK, Chat, LoopbackOllama, answering
from datrix_scripts.local_llm_usage import GATE_USAGE_LOG
from datrix_scripts.local_reading import WITHHELD_LINE
from datrix_scripts.paths import script_env
from datrix_scripts.skill.absorb import (
    ALTERNATIVES_SYSTEM,
    VERDICT_MISSING,
    VERDICT_PARTIAL,
    VERDICT_PRESENT,
    UnitCheck,
    find_references,
    render_transfer,
    transfer_check,
)
from datrix_scripts.skill.assist_cli import build_parser as assist_cli_parser
from datrix_scripts.skill.bug_resolution import (
    STATUS_RESOLVED,
    ResolutionFacts,
    VerificationRow,
    append_resolution,
    build_resolution,
)
from datrix_scripts.skill.checklist import draft_checklist
from datrix_scripts.skill.common import EXIT_NO_MODEL, MAP_WORKERS, AssistError, ContentFilter
from datrix_scripts.skill.context_digest import build_digest
from datrix_scripts.skill.design_check import check_designs, close_findings
from datrix_scripts.skill.design_inventory import free_gaps, load_designs, next_number, registered_targets
from datrix_scripts.skill.design_plan import VERDICT_HOLDS, VERDICT_UNCLEAR, draft_shapes, verify_units
from datrix_scripts.skill.design_xref import build_xref
from datrix_scripts.skill.finding_inbox import EXIT_DELETED, EXIT_KEPT, EXIT_UNUSABLE, finding_files, test_runs
from datrix_scripts.skill.findings import build_index, check_consolidation, extract_file
from datrix_scripts.skill.findings_redundant import (
    VERDICT_SAME,
    Proposal,
    Redundancy,
    delete_redundant,
    find_redundant,
)
from datrix_scripts.skill.findings_redundant import VERDICT_UNCLEAR as PAIR_UNCLEAR
from datrix_scripts.skill.findings_redundant import plan_json as redundant_plan_json
from datrix_scripts.skill.findings_source import load_sources, parse_source
from datrix_scripts.skill.phase_tasks import phase_tasks
from datrix_scripts.skill.readiness import VERDICT_SATISFIED, missing_edges, satisfied_leads, unresolved_modules
from datrix_scripts.skill.rule_names import STATUS_OK, STATUS_WITHHELD, apply_names, propose_names
from datrix_scripts.test.wrappers import SKILL_SCRIPTS_DIR, seam_checks

MODULE: Final = "datrix_scripts.skill.skill_assist_gate"
WRAPPER: Final = "skill-assist-gate"
GATE: Final = "skill-assist"
CLI_MODULE: Final = "datrix_scripts.skill.assist_cli"

# TEST-NET-1 (RFC 5737): never routed, so no model server can answer there.
_UNROUTABLE = "192.0.2.1"
_CLI: Final = ("-m", CLI_MODULE)
_PHASE = 7
_GATE_TERM = "zzgateterm"
_REPOS = ("datrix", "datrix-alpha")
_CORE = '"""Core helpers for alpha."""\n\nHELPERS = ("one", "two")\n'


# ===========================================================================
# fixtures
# ===========================================================================


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
        write_file(root / "datrix-alpha/src/datrix_alpha/__init__.py", "")
        write_file(root / "datrix-alpha/src/datrix_alpha/core.py", _CORE)
        write_file(root / "datrix-alpha/src/datrix_alpha/other.py", '"""Other things."""\n\nVALUE = 1\n')
        write_file(root / "datrix/scripts/config/customer-term-hashes.json", json.dumps({
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
    return write_file(root / "datrix-alpha/.tasks" / f"phase-{_PHASE:02d}" /
                  f"task-{_PHASE:02d}-{number:02d}-fixture-{number}.md", text)


def _pool(server: LoopbackOllama) -> LocalLlmPool:
    settings = LocalLlmSettings(machines=(LOOPBACK,), reachable_timeout_ms=2000, generate_timeout_ms=5000,
                                allow_load=False, ollama_port=server.port, caller="gate")
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
        with LoopbackOllama(answering(answer)) as server:
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
        source = write_file(root / "findings/20261001-000000-x.md",
                        "# X\n\nSee `datrix-alpha/src/x.py:3` and `datrix-alpha/src/y.py:9`.\n")
        reply = json.dumps({"findings": [{"title": "T", "seam": "s", "packages": ["datrix-alpha"], "defect": "d",
                                          "citations": ["x.py:3", "made/up.py:1"]}]})
        with LoopbackOllama(answering(reply)) as server:
            result = extract_file(root, _pool(server), ContentFilter(root), source)
        assert result.findings[0].citations == ("datrix-alpha/src/x.py:3",), result.findings
        assert result.invented == ["made/up.py:1"], result.invented
        assert result.unassigned == ["datrix-alpha/src/y.py:9"], result.unassigned


def check_findings_index_reads_every_file_before_the_first_model_call() -> None:
    with _workspace() as root:
        folder = root / "findings"
        # One file more than the worker threads: a lazy reader reaches the last one only after a chat.
        files = [write_file(folder / f"consolidated-{n:03d}-f.md", f"# F{n}\n\nAt `datrix-alpha/src/f{n}.py:{n}`.\n")
                 for n in range(1, MAP_WORKERS + 2)]
        last = files[-1]
        reply = json.dumps({"findings": [{"title": "T", "seam": "s", "packages": [], "defect": "d",
                                          "citations": []}]})

        def rename_during_the_run(_chat: Chat) -> str:
            if last.exists():
                last.rename(folder / "renamed-mid-run.md")
            return reply

        with LoopbackOllama(rename_during_the_run) as server:
            extractions = build_index(root, _pool(server), folder)
        assert [e.source for e in extractions] == [path.name for path in files], extractions
        assert extractions[-1].unassigned == [f"datrix-alpha/src/f{len(files)}.py:{len(files)}"], extractions[-1]


def check_findings_never_send_a_registered_customer_term() -> None:
    with _workspace() as root:
        source = write_file(root / "findings/20261001-000000-t.md",
                        f"# T\n\nThe {_GATE_TERM} service breaks.\nPlain line.\n")
        reply = json.dumps({"findings": []})
        with LoopbackOllama(answering(reply)) as server:
            extract_file(root, _pool(server), ContentFilter(root), source)
        sent = " ".join(chat.user for chat in server.chats)
        assert _GATE_TERM not in sent, "a registered customer term reached the model"
        assert WITHHELD_LINE in sent and "Plain line." in sent, sent


def check_findings_check_refuses_a_lost_citation_and_a_dangling_related_pointer() -> None:
    with _workspace() as root:
        folder = root / "findings"
        raw = write_file(folder / "20261001-000000-r.md", "# R\n\nAt `a/b.py:1`.\n")
        kept = write_file(folder / "consolidated-001-theme.md", "# Theme\n\n**Related:** consolidated-002-gone\n")
        failed = check_consolidation(folder, [raw])
        assert failed.lost == {raw.name: ["a/b.py:1"]}, failed.lost
        assert failed.dangling_related == {kept.name: ["consolidated-002"]}, failed.dangling_related
        write_file(kept, "# Theme\n\n## 1. R\n\nAt `a/b.py:1`.\n")
        passed = check_consolidation(folder, [raw])
        assert passed.passed, passed


def check_findings_check_keep_raw_allows_a_surviving_raw_file_but_not_a_lost_citation() -> None:
    with _workspace() as root:
        folder = root / "findings"
        survivor = write_file(folder / "20261001-000000-same.md", "# Same\n\nAt `a/b.py:1`.\n")
        duplicate = write_file(folder / "20261001-000001-same-again.md", "# Same\n\nAt `a/b.py:1` and `a/c.py:2`.\n")
        strict = check_consolidation(folder, [duplicate])
        assert strict.raw_left == [survivor.name], strict.raw_left
        lost = check_consolidation(folder, [duplicate], raw_may_remain=True)
        assert lost.lost == {duplicate.name: ["a/c.py:2"]} and not lost.raw_left, lost
        write_file(survivor, "# Same\n\nAt `a/b.py:1` and `a/c.py:2`.\n")
        passed = check_consolidation(folder, [duplicate], raw_may_remain=True)
        assert passed.passed, passed


def check_findings_parse_repairs_mojibake_and_nests_raw_headings() -> None:
    with _workspace() as root:
        raw = write_file(root / "findings/20261001-000000-m.md",
                         "# Mojibake\n\n## Detail\n\nA â€” B\n")
        unit = parse_source(raw).units[0]
        assert unit.title == "Mojibake" and unit.body == ("### Detail", "", "A — B"), unit.body


_HEADER_QUOTE = "The emitter drops the header"


def _redundancy_reply(chat: Chat) -> str:
    first = chat.user.split("SECOND (stays):")[0]
    if "Caches miss" in first:
        return json.dumps({"verdict": "SAME", "unique_in_first": [], "quote_first": "a line the file never had",
                           "quote_second": _HEADER_QUOTE, "reason": "claims a match"})
    return json.dumps({"verdict": "SAME", "unique_in_first": [], "quote_first": _HEADER_QUOTE,
                       "quote_second": _HEADER_QUOTE, "reason": "the same header defect"})


def _redundancy_folder(root: Path) -> Path:
    folder = root / "findings"
    write_file(folder / "20261001-000000-keep.md",
               f"# Keep\n\n{_HEADER_QUOTE} at `datrix-alpha/src/a.py:1` and `datrix-alpha/src/b.py:2`.\n")
    write_file(folder / "20261001-000001-dup.md", f"# Dup\n\n{_HEADER_QUOTE} at `datrix-alpha/src/a.py:1`.\n")
    write_file(folder / "20261001-000002-extra.md",
               "# Extra\n\nSchema export skips indexes at `datrix-alpha/src/a.py:1` and `datrix-alpha/src/z.py:9`.\n")
    write_file(folder / "20261001-000003-fake.md", "# Fake\n\nCaches miss at `datrix-alpha/src/b.py:2`.\n")
    write_file(folder / "20261001-000004-term.md",
               f"# Term\n\nThe {_GATE_TERM} header at `datrix-alpha/src/a.py:1`.\n")
    return folder


def check_findings_redundant_proposes_only_what_a_checked_same_verdict_and_the_citations_prove() -> None:
    with _workspace() as root:
        folder = _redundancy_folder(root)
        with LoopbackOllama(_redundancy_reply) as server:
            result = find_redundant(folder, [folder], _pool(server), ContentFilter(root))
        proposed = {p.doomed: p for p in result.proposals}
        assert list(proposed) == ["20261001-000001-dup.md"], list(proposed)
        dup = proposed["20261001-000001-dup.md"]
        assert dup.delete and dup.verdict == VERDICT_SAME and (folder / dup.survivor).is_file(), dup
        # A citation no other file carries leaves a file without a candidate; a model quote that is not in the
        # file, or a withheld line, never stands as SAME.
        assert "20261001-000002-extra.md" not in {k.file for k in result.kept} | set(proposed), result.kept
        fake = [k for k in result.kept if k.file == "20261001-000003-fake.md"]
        assert fake and all(k.verdict == PAIR_UNCLEAR for k in fake), result.kept
        assert "20261001-000004-term.md" not in proposed, proposed
        sent = " ".join(chat.user for chat in server.chats)
        assert _GATE_TERM not in sent and WITHHELD_LINE in sent, "a registered customer term reached the model"


def check_findings_redundant_delete_proves_every_condition_before_it_removes_a_file() -> None:
    with _workspace() as root:
        folder = _redundancy_folder(root)
        with LoopbackOllama(_redundancy_reply) as server:
            proposals = find_redundant(folder, [folder], _pool(server), ContentFilter(root)).proposals
        dup = folder / "20261001-000001-dup.md"
        original = dup.read_text(encoding="utf-8")
        write_file(dup, original + "\nA detail added after the judgement.\n")
        changed = delete_redundant(folder, proposals)
        assert not changed.passed and "changed since" in changed.problems[0] and dup.exists(), changed
        write_file(dup, original)
        referrer = write_file(folder / "20261001-000009-ref.md", f"# Ref\n\nSee {dup.stem}.\n")
        named = delete_redundant(folder, proposals)
        assert not named.passed and "named by" in named.problems[0] and dup.exists(), named
        referrer.unlink()
        proposals[0].delete = False
        assert delete_redundant(folder, proposals).deleted == [] and dup.exists()
        proposals[0].delete = True
        done = delete_redundant(folder, proposals)
        assert done.passed and done.deleted == [dup.name] and not dup.exists(), done
        assert (folder / "20261001-000000-keep.md").exists()


def check_findings_redundant_pairs_by_text_but_never_deletes_what_the_survivor_does_not_cite() -> None:
    with _workspace() as root:
        folder = root / "findings"
        write_file(folder / "20261001-000000-orig.md",
                   f"# Orig\n\n{_HEADER_QUOTE} at `datrix-alpha/src/a.py:1` and `datrix-alpha/src/b.py:2`.\n")
        near = write_file(folder / "20261001-000001-near.md",
                          f"# Near\n\n{_HEADER_QUOTE} at `datrix-alpha/src/c.py:7`.\n")
        with LoopbackOllama(_redundancy_reply) as server:
            proposals = find_redundant(folder, [folder], _pool(server), ContentFilter(root)).proposals
        assert [p.doomed for p in proposals] == [near.name], proposals
        assert not proposals[0].delete and "c.py:7" in proposals[0].exact, proposals[0]
        proposals[0].delete = True
        refused = delete_redundant(folder, proposals)
        assert not refused.passed and "does not cite" in refused.problems[0] and near.exists(), refused
        write_file(folder / "20261001-000000-orig.md",
                   f"# Orig\n\n{_HEADER_QUOTE} at `datrix-alpha/src/a.py:1`, `datrix-alpha/src/b.py:2` and "
                   "`datrix-alpha/src/c.py:7`.\n")
        assert delete_redundant(folder, proposals).deleted == [near.name] and not near.exists()


def check_findings_redundant_compares_one_folder_only_and_names_files_by_relative_path() -> None:
    with _workspace() as root:
        inbox = root / "findings"
        keep = write_file(inbox / "azure/20261001-000000-keep.md",
                          f"# Keep\n\n{_HEADER_QUOTE} at `datrix-alpha/src/a.py:1` and `datrix-alpha/src/b.py:2`.\n")
        write_file(inbox / "docker/20261001-000001-dup.md",
                   f"# Dup\n\n{_HEADER_QUOTE} at `datrix-alpha/src/a.py:1`.\n")
        folders = [inbox / "azure", inbox / "docker", inbox / "tooling"]
        with LoopbackOllama(_redundancy_reply) as server:
            other = find_redundant(inbox, [inbox / "azure", inbox / "docker"], _pool(server), ContentFilter(root))
        assert other.files == 2 and not other.proposals and not other.candidates, other
        dup = write_file(inbox / "azure/20261001-000001-dup.md",
                         f"# Dup\n\n{_HEADER_QUOTE} at `datrix-alpha/src/a.py:1`.\n")
        pointer = write_file(inbox / "tooling/20261001-000002-ref.md", f"# Ref\n\nSee {dup.stem}.\n")
        with LoopbackOllama(_redundancy_reply) as server:
            proposals = find_redundant(inbox, folders, _pool(server), ContentFilter(root)).proposals
        assert [(p.doomed, p.survivor) for p in proposals] == [
            ("azure/20261001-000001-dup.md", "azure/20261001-000000-keep.md")], proposals
        assert proposals[0].referrers == ["tooling/20261001-000002-ref.md"], proposals[0].referrers
        blocked = delete_redundant(inbox, proposals)
        assert not blocked.passed and "named by tooling/" in blocked.problems[0] and dup.exists(), blocked
        outside = write_file(root / "reports/outside.md", "# Outside\n")
        escape = Proposal("../outside.md", proposals[0].survivor, "", VERDICT_SAME, "", "", "0", True)
        escaped = delete_redundant(inbox, [escape])
        assert not escaped.passed and "outside the findings folder" in escaped.problems[0] and outside.exists()
        pointer.unlink()
        done = delete_redundant(inbox, proposals)
        assert done.deleted == ["azure/20261001-000001-dup.md"] and not dup.exists() and keep.exists(), done


def check_findings_redundant_candidates_need_the_survivor_to_hold_the_keywords_of_the_file() -> None:
    with _workspace() as root:
        folder = root / "findings"
        write_file(folder / "20261001-000000-keep.md",
                   "# Keep\n\nThe emitter drops `alpha_table`, `BetaThing` and `gamma_idx` at "
                   "`datrix-alpha/src/a.py:1`, and also `delta_x` shows the same.\n")
        write_file(folder / "20261001-000001-inside.md",
                   "# Inside\n\nThe emitter drops `alpha_table`, `BetaThing` and `gamma_idx`.\n")
        write_file(folder / "20261001-000002-outside.md",
                   "# Outside\n\nThe emitter drops `alpha_table`, `BetaThing` and `zeta_q`.\n")
        result = find_redundant(folder, [folder], None, None)
        pairs = sorted((k.file, k.other) for k in result.unjudged)
        assert pairs == [("20261001-000001-inside.md", "20261001-000000-keep.md")], pairs
        # A Keywords line is the file's keywords; the prose around it adds none.
        other = root / "findings/second"
        write_file(other / "20261001-000000-keep.md",
                   "# Keep\n\nThe emitter drops `alpha_table`, `BetaThing` and `gamma_idx`, and also `delta_x`, "
                   "`epsilon_y` and `zeta_q` at `datrix-alpha/src/a.py:1`.\n")
        write_file(other / "20261001-000001-authored.md",
                   "# Authored\n\n- **Keywords:** `alpha_table`, `BetaThing`, `gamma_idx`\n\n"
                   "The emitter drops them; also see `omega_q`, `sigma_z` and `tau_w`.\n")
        listed = find_redundant(folder, [other], None, None).unjudged
        assert [(k.file, k.other) for k in listed] == [
            ("second/20261001-000001-authored.md", "second/20261001-000000-keep.md")], listed


def check_findings_redundant_commands_exit_with_the_assist_codes() -> None:
    with _workspace() as root:
        folder = _redundancy_folder(root)
        base = [sys.executable, *_CLI, "--workspace", str(root)]
        listed = subprocess.run([*base, "findings-redundant", "--no-model"], capture_output=True, text=True,
                                check=False, env=script_env())
        assert listed.returncode == 0 and "nothing proposed" in listed.stdout, (listed.returncode, listed.stdout)
        nothing = subprocess.run([*base, "findings-redundant-delete"], capture_output=True, text=True, check=False,
                                 env=script_env())
        assert nothing.returncode == 0 and "Deleted 0" in nothing.stdout, (nothing.returncode, nothing.stdout)
        ghost = Proposal("20261001-009999-ghost.md", "20261001-000000-keep.md", "", VERDICT_SAME, "", "", "0",
                         True)
        plan = write_file(root / "plan.json", redundant_plan_json(Redundancy(proposals=[ghost])))
        refused = subprocess.run([*base, "findings-redundant-delete", "--plan", str(plan)], capture_output=True,
                                 text=True, check=False, env=script_env())
        assert refused.returncode == 2 and "does not exist" in refused.stdout, (refused.returncode, refused.stdout)
        assert len(list(folder.glob("*.md"))) == 5, "a refused delete removed a file"


# ===========================================================================
# implement-finding
# ===========================================================================

_TEST_PS1 = 'powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-alpha'
_GATE_PS1 = 'powershell -File "d:/datrix/datrix/scripts/test/shared-library-gate.ps1"'
_GATE_VERDICT_LINE = "[GATE] shared-library {} exit={} log=D:\\datrix\\.test-output\\gates\\shared-library\\run.log"


def _shell_call(call_id: str, command: str, background: bool = False) -> str:
    tool_input: dict[str, object] = {"command": command, "description": "d"}
    if background:
        tool_input["run_in_background"] = True
    block = {"type": "tool_use", "id": call_id, "name": "PowerShell", "input": tool_input}
    return json.dumps({"type": "assistant", "message": {"content": [block]}})


def _shell_result(call_id: str, text: str, is_error: bool = False) -> str:
    block = {"type": "tool_result", "tool_use_id": call_id, "is_error": is_error, "content": text}
    return json.dumps({"type": "user", "message": {"content": [block]}})


def _close(root: Path, finding: Path, session_log: Path | None = None) -> subprocess.CompletedProcess[str]:
    log_args = ["--session-log", str(session_log)] if session_log else []
    return subprocess.run(
        [sys.executable, *_CLI, "--workspace", str(root), "finding-close", "--finding", str(finding), *log_args],
        capture_output=True, text=True, check=False, env=script_env())


def check_implement_finding_selects_the_first_files_by_name() -> None:
    with _workspace() as root:
        folder = root / "findings"
        for name in ("20261002-000000-b.md", "consolidated-001-c.md", "20261001-000000-a.md", "notes.txt"):
            write_file(folder / name, "# X\n")
        assert [p.name for p in finding_files(folder, 2)] == ["20261001-000000-a.md", "20261002-000000-b.md"]
        assert len(finding_files(folder, 10)) == 3


def _select(root: Path, *args: str) -> list[str]:
    done = subprocess.run([sys.executable, *_CLI, "--workspace", str(root), "finding-select", *args],
                          capture_output=True, text=True, check=True, env=script_env())
    return [Path(line).relative_to(root / "findings").as_posix() for line in done.stdout.splitlines()]


def check_finding_select_and_close_work_the_inbox_subfolders() -> None:
    with _workspace() as root:
        folder = root / "findings"
        for name in ("docs/d1.md", "azure/a2.md", "azure/a1.md", "python/p1.md", "loose.md"):
            write_file(folder / name, "# X\n")
        write_file(folder / "azure/a2.md", "# X\nnames d1\n")
        assert _select(root) == ["python/p1.md", "azure/a1.md", "azure/a2.md", "docs/d1.md", "loose.md"]
        assert _select(root, "--count", "2") == ["python/p1.md", "azure/a1.md"]
        assert _select(root, "--dir", "azure") == ["azure/a1.md", "azure/a2.md"]
        assert _select(root, "--dir", str(folder / "docs")) == ["docs/d1.md"]
        kept = _close(root, folder / "docs/d1.md")
        assert kept.returncode == EXIT_KEPT and "azure/a2.md still names it" in kept.stdout, kept.stdout
        assert _close(root, folder / "azure/a2.md").returncode == 0
        assert _close(root, folder / "docs/d1.md").returncode == 0


def check_implement_finding_test_runs_reads_foreground_test_ps1_results_only() -> None:
    with _workspace() as root:
        log = write_file(root / ".tmp/step.stream.jsonl", "\n".join([
            _shell_call("a", f"{_TEST_PS1} -ListTags"), _shell_result("a", "tags"),
            _shell_call("b", f"{_TEST_PS1} -Tag x", background=True), _shell_result("b", "started"),
            _shell_call("c", "git status"), _shell_result("c", "clean"),
            "not json",
            _shell_call("d", f"{_TEST_PS1} -Tag x"), _shell_result("d", "Exit code 1", is_error=True),
            _shell_call("e", f"{_TEST_PS1} -Tag x | Select-Object -Last 5"), _shell_result("e", "12 passed"),
            _shell_call("g", f"{_TEST_PS1} -Tag x; {_TEST_PS1} -Tag y"),
            _shell_result("g", "[FAIL] Tests failed for datrix-alpha\n[PASS] Tests passed for datrix-alpha"),
            _shell_call("h", 'powershell -File "test-single.ps1" "t.py::x"'), _shell_result("h", "ok"),
            _shell_call("f", f"{_TEST_PS1} -Specific a.py || exit 1"), _shell_result("f", "12 passed, 0 failed"),
            _shell_call("i", f"{_TEST_PS1} -Tag x 2>&1 | tail -6"),
            _shell_result("i", "[PASS] : datrix-alpha\n\nTotal: 1 | Passed: 1 | Failed: 0"),
            _shell_call("j", f"{_TEST_PS1} -Tag x 2>&1 | tail -6"),
            _shell_result("j", "[FAIL] : datrix-alpha\n\nTotal: 2 | Passed: 1 | Failed: 1"),
            _shell_call("k", f"({_TEST_PS1} -Tag x; {_TEST_PS1} -Tag y) 2>&1 | tail -3"),
            _shell_result("k", "Total: 1 | Passed: 1 | Failed: 0"),
            _shell_call("l", f"{_TEST_PS1} -Tag x 2>&1 | head -3"), _shell_result("l", "Running datrix-alpha"),
        ]) + "\n")
        runs = test_runs(log)
        assert [run.passed for run in runs] == [False, False, False, True, True, False, False, False], runs
        assert runs[3].command.endswith("-Specific a.py || exit 1"), runs
        assert "piped" in runs[-1].failure and "exited non-zero" in runs[0].failure, runs


def check_implement_finding_test_runs_judges_a_gate_run_by_its_verdict_line() -> None:
    passed = f"[FAIL] fixture check expected\n1 failed\n{_GATE_VERDICT_LINE.format('PASSED', 0)}"
    with _workspace() as root:
        log = write_file(root / ".tmp/step.stream.jsonl", "\n".join([
            _shell_call("a", f"{_GATE_PS1} -SelfTest"), _shell_result("a", _GATE_VERDICT_LINE.format("PASSED", 0)),
            _shell_call("b", f"{_GATE_PS1} -HarnessSelfTest"), _shell_result("b", "ok"),
            _shell_call("c", _GATE_PS1, background=True), _shell_result("c", "started"),
            _shell_call("d", _GATE_PS1), _shell_result("d", passed),
            _shell_call("e", f"{_GATE_PS1} -Only check_x 2>&1 | tail -3"),
            _shell_result("e", _GATE_VERDICT_LINE.format("FAILED", 1)),
            _shell_call("f", f"{_GATE_PS1} 2>&1 | head -3"), _shell_result("f", "Running checks"),
            _shell_call("g", f"{_GATE_PS1}; {_GATE_PS1} -Only check_y"),
            _shell_result("g", _GATE_VERDICT_LINE.format("PASSED", 0)),
            _shell_call("h", _GATE_PS1), _shell_result("h", "Exit code 1", is_error=True),
            _shell_call("i", f"{_TEST_PS1} -Tag x; {_GATE_PS1}"),
            _shell_result("i", f"Total: 1 | Passed: 1 | Failed: 0\n{_GATE_VERDICT_LINE.format('PASSED', 0)}"),
        ]) + "\n")
        runs = test_runs(log)
        assert [run.passed for run in runs] == [True, False, False, False, False, True], runs
        assert "reports FAILED" in runs[1].failure and "verdict line for each gate call" in runs[2].failure, runs
        assert "verdict line for each gate call" in runs[3].failure and "exited non-zero" in runs[4].failure, runs
        folder = root / "findings"
        finding = write_file(folder / "20261001-000000-a.md", "# A\n")
        write_file(log, "\n".join([_shell_call("p", _GATE_PS1), _shell_result("p", passed)]) + "\n")
        result = _close(root, finding, log)
        assert result.returncode == EXIT_DELETED and not finding.exists(), (result.returncode, result.stdout)


def check_implement_finding_close_deletes_only_an_unreferenced_finding_with_a_passing_last_test_run() -> None:
    with _workspace() as root:
        folder = root / "findings"
        finding = write_file(folder / "20261001-000000-a.md", "# A\n")
        referrer = write_file(folder / "consolidated-001-x.md", "# X\n\n**Related:** 20261001-000000-a\n")
        log = write_file(root / ".tmp/step.stream.jsonl", _shell_call("a", "git status") + "\n")
        result = _close(root, finding, log)
        assert result.returncode == EXIT_KEPT and finding.exists(), (result.returncode, result.stdout)
        assert "consolidated-001-x.md still names it" in result.stdout and "ran no foreground" in result.stdout, \
            result.stdout
        write_file(referrer, "# X\n")
        write_file(log, "\n".join([_shell_call("p", f"{_TEST_PS1} -Tag x"), _shell_result("p", "4 passed"),
                               _shell_call("f", f"{_TEST_PS1} -Tag x"), _shell_result("f", "1 failed")]) + "\n")
        result = _close(root, finding, log)
        assert result.returncode == EXIT_KEPT and "last test run did not pass (its output reports failed" in result.stdout, result.stdout
        write_file(log, _shell_call("p", f"{_TEST_PS1} -Tag x") + "\n" + _shell_result("p", "4 passed") + "\n")
        result = _close(root, finding, log)
        assert result.returncode == EXIT_DELETED and not finding.exists(), (result.returncode, result.stdout)
        write_file(finding, "# A\n")
        result = _close(root, finding)
        assert result.returncode == EXIT_DELETED and not finding.exists(), (result.returncode, result.stdout)
        result = _close(root, finding)
        assert result.returncode == EXIT_UNUSABLE, (result.returncode, result.stdout)


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
        design = write_file(root / "design/042-fixture-design.md", _DESIGN)
        reply = json.dumps({"requirements": [
            {"id": "D1", "requirement": "Guards fail closed.", "surfaces": ["routes"], "first_line": 5,
             "last_line": 5, "quote": "route guard must fail closed when the token"},
            {"id": "", "requirement": "Invented.", "surfaces": [], "first_line": 9, "last_line": 9,
             "quote": "this sentence is not in the design at all"},
        ]})
        with LoopbackOllama(answering(reply)) as server:
            checklist = draft_checklist(root, _pool(server), design)
        verified = [r.ident for r in checklist.requirements if r.quote_found]
        assert verified == ["D1"], checklist.requirements
        assert [n for n, _text in checklist.uncovered] == [9], checklist.uncovered


def check_absorb_references_find_name_number_and_title_but_not_task_folders() -> None:
    with _workspace() as root:
        design = write_file(root / "design/042-fixture-design.md", _DESIGN)
        write_file(root / "datrix-alpha/docs/a.md", "See design 042 for the details.\nUnrelated 042 count.\n")
        write_file(root / "datrix-alpha/docs/b.md", "From 042-fixture-design.md and A Fixture Design With A Long "
                                                "Enough Title.\n")
        write_file(root / "datrix-alpha/.tasks/phase-07/task-07-01-x.md", "Design reference: design 042\n")
        write_file(root / "design/050-later-design.md", "Port 1042, version 042.5, v042x.\nBuilds on 042 D1.\n"
                                                        "Keeps 042's gate.\nSee `builder.py:042-109`, "
                                                        "`b.py:042`, `c.py:30-042`.\n"
                                                        "Each design stays under 042 lines.\n"
                                                        "Keep it under 042\nlines.\n")
        found = {(r.file, r.line) for r in find_references(root, design, [])}
        assert found == {("datrix-alpha/docs/a.md", 1), ("datrix-alpha/docs/b.md", 1),
                         ("design/050-later-design.md", 2), ("design/050-later-design.md", 3)}, found


def _absorb_delete(root: Path, design: Path, *licence: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *_CLI, "--workspace", str(root), "absorb-delete", "--design", str(design), *licence],
        capture_output=True, text=True, check=False, env=script_env())


def check_absorb_delete_deletes_only_a_licensed_unreferenced_design() -> None:
    with _workspace() as root:
        design = write_file(root / "design/042-fixture-design.md", _DESIGN)
        proof = root / ".tmp/verify-proven-042-fixture-design.md"
        result = _absorb_delete(root, design, "--verified", str(proof))
        assert result.returncode == EXIT_KEPT and "does not exist" in result.stdout, result.stdout
        write_file(proof, "Design conformance: PROVEN\n\nMore work.\n\nDesign conformance: INCOMPLETE\n")
        result = _absorb_delete(root, design, "--verified", str(proof))
        assert result.returncode == EXIT_KEPT and "not PROVEN" in result.stdout, result.stdout
        other = write_file(root / ".tmp/verify-proven-043-other.md", "Design conformance: PROVEN\n")
        result = _absorb_delete(root, design, "--verified", str(other))
        assert result.returncode == EXIT_KEPT and "names another design" in result.stdout, result.stdout
        result = _absorb_delete(root, design)
        assert result.returncode == EXIT_KEPT and "it has no Status line" in result.stdout, result.stdout
        not_markdown = write_file(root / "design/042-fixture-design.txt", _DESIGN)
        result = _absorb_delete(root, not_markdown, "--knowledge-only")
        assert result.returncode == EXIT_UNUSABLE and not_markdown.exists(), result.stdout
        misspelled = write_file(root / "desing_042/043-misfiled-design.md", _DESIGN)
        result = _absorb_delete(root, misspelled, "--knowledge-only")
        assert result.returncode == EXIT_DELETED and not misspelled.exists(), result.stdout
        write_file(proof, "Design conformance: INCOMPLETE\n\nDesign conformance: PROVEN\n")
        reference = write_file(root / "datrix-alpha/docs/a.md", "See design 042 for the details.\n")
        result = _absorb_delete(root, design, "--verified", str(proof))
        assert result.returncode == EXIT_KEPT and "datrix-alpha/docs/a.md:1" in result.stdout, result.stdout
        assert design.exists(), result.stdout
        write_file(reference, "Guards fail closed.\n")
        result = _absorb_delete(root, design, "--verified", str(proof))
        assert result.returncode == EXIT_DELETED and not design.exists(), result.stdout
        write_file(design, f"# 042: Fixture\n\n**Status:** Implemented in phase 7.\n\n{_DESIGN}")
        result = _absorb_delete(root, design)
        assert result.returncode == EXIT_DELETED and not design.exists(), result.stdout
        write_file(design, _DESIGN)
        result = _absorb_delete(root, design, "--knowledge-only")
        assert result.returncode == EXIT_DELETED and not design.exists(), result.stdout


_NO_ALTERNATIVES = json.dumps({"alternatives": []})


def _transfer_answer(judge: Callable[[Chat], str], alternatives: str = _NO_ALTERNATIVES) -> Callable[[Chat], str]:
    """The stand-in model of the transfer check: ``alternatives`` answers the request for other search words,
    ``judge`` the PRESENT / PARTIAL / MISSING question."""
    return lambda chat: alternatives if ALTERNATIVES_SYSTEM in chat.system else judge(chat)


def _judgements(server: LoopbackOllama) -> list[str]:
    """The PRESENT / PARTIAL / MISSING questions the server was asked (not the requests for other words)."""
    return [chat.user for chat in server.chats if ALTERNATIVES_SYSTEM not in chat.system]


def check_absorb_transfer_gives_a_verdict_per_section() -> None:
    with _workspace() as root:
        design = write_file(root / "design/042-fixture-design.md", _DESIGN)
        write_file(root / "datrix-alpha/docs/guards.md",
                   "# Guards\n\nRoute guards: every route guard must fail closed when the token is absent, always.\n")

        def judge(chat: Chat) -> str:
            return "PRESENT\ndatrix-alpha/docs/guards.md:3" if "D1 Guards" in chat.user else "MISSING"

        with LoopbackOllama(_transfer_answer(judge)) as server:
            checks = transfer_check(root, _pool(server), design, ["datrix-alpha/docs/guards.md"])
        verdicts = {c.heading: c.verdict for c in checks}
        assert verdicts["D1 Guards"] == VERDICT_PRESENT and verdicts["D2 Names"] == VERDICT_MISSING, verdicts


_COPIED_LINE = "Every route guard must fail closed when the token is absent."


def check_absorb_transfer_settles_a_copied_section_without_a_model_and_reports_progress() -> None:
    with _workspace() as root:
        design = write_file(root / "design/042-fixture-design.md", _DESIGN)
        write_file(root / "datrix-alpha/docs/guards.md", f"# Guards\n\n- {_COPIED_LINE}\n")
        snapshots: list[tuple[int, int, int]] = []
        partial: list[list[UnitCheck]] = []
        with LoopbackOllama(_transfer_answer(lambda _chat: "MISSING")) as server:
            def progress(done: list[UnitCheck], total: int) -> None:
                snapshots.append((len(done), total, len(server.chats)))
                partial.append(list(done))

            checks = transfer_check(root, _pool(server), design, ["datrix-alpha/docs/guards.md"], progress)
        copied = next(c for c in checks if c.heading == "D1 Guards")
        assert copied.verdict == VERDICT_PRESENT and "datrix-alpha/docs/guards.md:3" in copied.answer, copied
        asked = _judgements(server)
        everything = [chat.user for chat in server.chats]
        assert len(checks) == 3 and len(asked) == 2 and not any("D1 Guards" in user for user in everything), everything
        assert snapshots[0] == (1, 3, 0), "the copied section must be reported before any model is asked"
        assert [s[0] for s in snapshots] == [1, 2, 3] and snapshots[-1] == (3, 3, 2), snapshots
        label = "design/042-fixture-design.md"
        assert "IN PROGRESS" in render_transfer(label, partial[0], 3) and "1 of 3" in render_transfer(label, partial[0], 3)
        assert "IN PROGRESS" not in render_transfer(label, checks), "a complete report must not read as in progress"


def check_absorb_transfer_sends_only_the_target_parts_sharing_terms() -> None:
    with _workspace() as root:
        design = write_file(root / "design/042-fixture-design.md", _DESIGN)
        write_file(root / "datrix-alpha/docs/guards.md",
                   "# Guards\n\n## Naming\n\nThe emitter rejects every reserved name it meets.\n\n"
                   "## Zebras\n\nZebras graze on the savanna.\n")
        with LoopbackOllama(_transfer_answer(lambda _chat: "PRESENT\nnothing cited")) as server:
            checks = transfer_check(root, _pool(server), design, ["datrix-alpha/docs/guards.md"])
        sent = next(user for user in _judgements(server) if "D2 Names" in user)
        assert "reserved name" in sent and "savanna" not in sent, sent
        names = next(c for c in checks if c.heading == "D2 Names")
        assert "Sent 1 of 3 target part(s)" in names.answer, names.answer
        asked_for_words = [chat.user for chat in server.chats if ALTERNATIVES_SYSTEM in chat.system]
        assert asked_for_words and not any("savanna" in user or "it meets" in user for user in asked_for_words), \
            "a request for other search words carried target text"


_INVENTED_DESIGN = (
    "# 042: A Fixture Design With A Long Enough Title\n\n"
    "## D1 Guards\n\nRoute guards fail closed when the token is absent. Retries use exponential backoff with jitter.\n"
)
_REWORDED_DESIGN = (
    "# 042: A Fixture Design With A Long Enough Title\n\n"
    "## D1 Guards\n\nRoute guards fail closed when the token is absent. Retries also use exponential backoff.\n"
)


def check_absorb_transfer_does_not_accept_present_while_terms_stay_unfound() -> None:
    with _workspace() as root:
        design = write_file(root / "design/042-fixture-design.md", _INVENTED_DESIGN)
        write_file(root / "datrix-alpha/docs/guards.md", "# Guards\n\nRoute guards fail closed when the token is absent.\n")
        with LoopbackOllama(_transfer_answer(lambda _chat: "PRESENT\ndatrix-alpha/docs/guards.md:3")) as server:
            checks = transfer_check(root, _pool(server), design, ["datrix-alpha/docs/guards.md"])
        guards = next(c for c in checks if c.heading == "D1 Guards")
        assert guards.verdict == VERDICT_PARTIAL, guards
        assert "PRESENT is not accepted" in guards.answer, guards.answer
        for term in ("retries", "exponential", "backoff", "jitter"):
            assert term in guards.answer.split("- not found:")[1].split("\n")[0], (term, guards.answer)


def check_absorb_transfer_asks_for_other_words_only_when_the_model_called_a_section_present() -> None:
    with _workspace() as root:
        design = write_file(root / "design/042-fixture-design.md", _INVENTED_DESIGN)
        write_file(root / "datrix-alpha/docs/guards.md", "# Guards\n\nRoute guards fail closed when the token is absent.\n")
        with LoopbackOllama(_transfer_answer(lambda _chat: "MISSING")) as server:
            checks = transfer_check(root, _pool(server), design, ["datrix-alpha/docs/guards.md"])
        guards = next(c for c in checks if c.heading == "D1 Guards")
        assert guards.verdict == VERDICT_MISSING, guards
        assert "absent (no other words searched): " in guards.answer and "jitter" in guards.answer, guards.answer
        assert all(ALTERNATIVES_SYSTEM not in chat.system for chat in server.chats), "other words were asked for"


def check_absorb_transfer_finds_a_reworded_term_by_the_words_a_model_offers() -> None:
    with _workspace() as root:
        design = write_file(root / "design/042-fixture-design.md", _REWORDED_DESIGN)
        write_file(root / "datrix-alpha/docs/guards.md",
                   "# Guards\n\nRoute guards fail closed when the token is absent.\n\n"
                   "Failed calls are re-attempted after a growing delay.\n")
        offer = json.dumps({"alternatives": [
            {"term": "retries", "alternatives": ["re-attempted"], "filler": False},
            {"term": "exponential", "alternatives": ["growing"], "filler": False},
            {"term": "backoff", "alternatives": ["delay"], "filler": False},
            {"term": "also", "alternatives": [], "filler": True},
        ]})
        with LoopbackOllama(_transfer_answer(lambda _chat: "PRESENT\ndatrix-alpha/docs/guards.md:3", offer)) as server:
            checks = transfer_check(root, _pool(server), design, ["datrix-alpha/docs/guards.md"])
        guards = next(c for c in checks if c.heading == "D1 Guards")
        assert guards.verdict == VERDICT_PRESENT, guards
        assert 'retries -> "re-attempted" at datrix-alpha/docs/guards.md:5' in guards.answer, guards.answer
        assert "set aside by the model as filler" in guards.answer, guards.answer
        asked_for_words = [chat.user for chat in server.chats if ALTERNATIVES_SYSTEM in chat.system]
        assert len(asked_for_words) == 1, "one request for other words per section with absent terms"


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
        write_file(alpha / "src/datrix_alpha/core.py", _CORE + "EXTRA = 2\n")
        shop = root / "acme-shop"
        shop.mkdir()
        _git(shop, "init", "-q")
        write_file(shop / "app.dtrx", "service Shop {}\n")
        report = write_file(root / "acme-shop/bugs/bug.md", "# Bug: x\n\n## Summary\nBroken.\n")
        with LoopbackOllama(answering("Adds an EXTRA constant to the core helpers.")) as server:
            section = build_resolution(root, _pool(server), _facts(), [alpha, shop], {"src/datrix_alpha/core.py",
                                                                                     "app.dtrx"})
        sent = " ".join(chat.user for chat in server.chats)
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


def check_bug_resolution_keeps_every_row_of_a_repeated_flag() -> None:
    """A second ``--verification`` (or ``--exhibiting``, ``--file``, ...) adds rows; it never replaces the first."""
    args = assist_cli_parser().parse_args([
        "bug-resolution", "--report", "r.md", "--repo", "a", "--repo", "b",
        "--file", "x.py", "--file", "y.py", "--exhibiting", "p1", "--exhibiting", "p2",
        "--reached", "p1", "--reached", "p2",
        "--verification", "p1|yes|f|gone", "--verification", "p2|no -- why|f|unchanged",
    ])
    assert args.repo == ["a", "b"], args.repo
    assert args.file == ["x.py", "y.py"], args.file
    assert args.exhibiting == ["p1", "p2"], args.exhibiting
    assert args.reached == ["p1", "p2"], args.reached
    assert args.verification == ["p1|yes|f|gone", "p2|no -- why|f|unchanged"], args.verification


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


# ===========================================================================
# designs
# ===========================================================================

_PRINCIPLES = "# Principles\n\n**G1. One.** text\n\n**G2. Two.** text\n"
_TARGET_GROUPS = (("python", "datrix.languages"), ("typescript", "datrix.languages"),
                  ("aws", "datrix.platforms"), ("docker", "datrix.platforms"))


def _design_workspace(root: Path) -> None:
    """The guidelines document and four registered targets: two languages, two platforms."""
    write_file(root / "datrix/docs/architecture/design-principles.md", _PRINCIPLES)
    for key, group in _TARGET_GROUPS:
        write_file(root / f"datrix-codegen-{key}/pyproject.toml",
                   f'[project]\nname = "datrix-codegen-{key}"\n\n[project.entry-points."{group}"]\n{key} = "x:y"\n')


def _design_text(title: str, *, depends: str = "none", body: str = "", answers: tuple[str, ...] = ("G1", "G2")) -> str:
    bullets = "".join(f"- {guideline}: answered\n" for guideline in answers)
    return (f"# {title}\n\nStatus: Draft\nDepends on: {depends}\n\n## Problem\n\n{body}\n\n"
            f"## Design guidelines conformance\n{bullets}")


def _write_design(root: Path, stem: str, text: str) -> Path:
    return write_file(root / "design" / f"{stem}.md", text)


def check_design_inventory_reads_targets_from_registration_and_numbers_the_gaps() -> None:
    with _workspace() as root:
        _design_workspace(root)
        _write_design(root, "010-base", _design_text("Base"))
        _write_design(root, "020-next", _design_text("Next", depends="010-base"))
        _write_design(root, "040-late", _design_text("Late", depends="020-next"))
        write_file(root / ".tmp/implement-direct-040-late.md", "- [ ] unit\n")
        assert registered_targets(root) == {"language": ("python", "typescript"), "platform": ("aws", "docker"),
                                            "generator": ()}, registered_targets(root)
        designs = load_designs(root, root / "design")
        assert [d.extendable for d in designs] == [True, True, False], "a design with a ledger is being implemented"
        assert designs[1].depends == ("010-base",), designs[1]
        assert next_number(designs) == 50 and next_number([]) == 10
        gaps = free_gaps(designs)
        assert [(low, high, free[0]) for low, high, free in gaps] == [(10, 20, 15), (20, 40, 25)], gaps


def check_design_check_refuses_each_malformed_design_and_checks_target_consistency_as_a_set() -> None:
    with _workspace() as root:
        _design_workspace(root)
        reached = "Changes `datrix-codegen-python/src/x.py` and `datrix-codegen-aws/src/y.py`."
        _write_design(root, "010-base", _design_text("Base"))
        _write_design(root, "020-forward", _design_text("Forward", depends="030-later", body="Needs 030-later."))
        _write_design(root, "030-later", _design_text("Later"))
        _write_design(root, "040-gaps", _design_text(
            "Gaps", body="TBD. From consolidated-013 section 1. Takes 3 days.", answers=("G1",)))
        _write_design(root, "050-long", _design_text("Long", body="\n".join(["line"] * 100)))
        _write_design(root, "060-targets", _design_text("Targets", body=reached)
                      + "\n## Target consistency\n\npython and aws rows only.\n")
        _write_design(root, "070-complete", _design_text("Complete", body=reached)
                      + "\n## Target consistency\n\npython, typescript, aws, docker: all realize it.\n")
        _write_design(root, "080-a", _design_text("A"))
        _write_design(root, "080-b", _design_text("B"))
        problems = check_designs(root, root / "design")
        messages ={p.design: " | ".join(q.message for q in problems if q.design == p.design) for p in problems}
        assert "030-later, which is not lower-numbered" in messages["020-forward"], messages
        assert "names 030-later, which has an equal or higher number" in messages["020-forward"], messages
        assert "lacks answers for G2" in messages["040-gaps"] and "placeholder or deferral 'TBD'" in messages["040-gaps"]
        assert "consolidated-013" in messages["040-gaps"] and "effort figure '3 days'" in messages["040-gaps"], messages
        assert [p.review for p in problems if "effort figure" in p.message] == [True]
        assert "lines; at most 100" in messages["050-long"], messages
        assert "omits registered language target(s): typescript" in messages["060-targets"], messages
        assert "omits registered platform target(s): docker" in messages["060-targets"], messages
        assert "shares number 080" in messages["080-b"], messages
        assert not {"010-base", "030-later", "070-complete"} & set(messages), messages


def check_design_headers_read_bold_labels_and_wrapped_dependencies() -> None:
    with _workspace() as root:
        _design_workspace(root)
        _write_design(root, "010-base", _design_text("Base"))
        bold = _design_text("Bold").replace(
            "Status: Draft\nDepends on: none\n",
            "**Status:** Draft\n**Depends on:** 010-base (its renderer),\n015-missing\n**Series:** the series\n")
        _write_design(root, "020-bold", bold)
        designs = load_designs(root, root / "design")
        assert designs[1].status == "Draft" and designs[1].depends == ("010-base", "015-missing"), designs[1]
        messages = [p.message for p in check_designs(root, root / "design") if p.design == "020-bold"]
        assert messages == ["depends on 015-missing, which does not exist"], messages


def check_design_xref_checks_decision_references_and_allocations() -> None:
    with _workspace() as root:
        _design_workspace(root)
        _write_design(root, "010-a", _design_text("A", body=(
            "### D1. One\n\nSee 020 D1 and `CHECK_ADDED`.\n\n## 4. Size\n\nOne diagnostic, `DBO001`.\n")))
        _write_design(root, "020-b", _design_text("B", depends="010-a", body=(
            "### D1. Two\n\nAs 010 D2 and 010 D1 say; 999 D1 too.\n\n## 4. Size\n\n`DBO001` and `CHECK_ADDED`.\n")))
        xref = build_xref(root, root / "design")
        errors = [f"{p.design}: {p.message}" for p in xref.errors]
        assert any("020-b" in e and "'010 D2'" in e and "no '### D2' heading" in e for e in errors), errors
        assert any("020-b" in e and "'999 D1'" in e and "no file" in e for e in errors), errors
        assert any(e.startswith("020-b: allocates DBO001") for e in errors), errors
        assert any(e.startswith("010-a: names CHECK_ADDED before 020-b") for e in errors), errors
        assert not any("'010 D1'" in e for e in errors), "a reference to an existing decision is no error"
        assert [p.design for p in xref.pointers] == ["010-a"], xref.pointers
        entry = next(e for e in xref.names if e.name == "DBO001")
        assert entry.allocated_by == ("010-a", "020-b") and entry.named_in == ("010-a", "020-b"), entry


_RULES = ("entity Product {\n    Decimal price;\n    validate {\n"
          "        if (price < 0) ValidationError(\"Price cannot be negative\");\n"
          "        price <= 1000 : \"Too expensive\";\n        price != 7 : \"No sevens\";\n"
          "        price != 8 : \"No eights\";\n"
          f"        price != 9 : \"No {_GATE_TERM}\";\n    }}\n}}\n")


def _rule_reply(_chat: Chat) -> str:
    return json.dumps({"names": [{"line": 4, "name": "positivePrice"}, {"line": 5, "name": "price"},
                                 {"line": 6, "name": "Bad Name"}, {"line": 7, "name": "positivePrice"}]})


def check_rule_names_checks_every_proposal_and_applies_only_unchanged_lines() -> None:
    with _workspace() as root:
        rules = write_file(root / "datrix-alpha/examples/shop.dtrx", _RULES)
        specs = [f"datrix-alpha/examples/shop.dtrx:{line}" for line in (4, 5, 6, 7, 8)]
        with LoopbackOllama(_rule_reply) as server:
            proposals = propose_names(root, _pool(server), specs)
        sent = " ".join(chat.user for chat in server.chats)
        assert _GATE_TERM not in sent and len(server.chats) == 1, "one request per file, never a customer term"
        status = {p.site.line: p.status for p in proposals}
        assert status[4] == STATUS_OK and "collides" in status[5] and "camelCase" in status[6], status
        assert "repeats" in status[7] and status[8] == STATUS_WITHHELD, status
        assert apply_names(proposals) == [f"{rules.resolve()}:4"]
        lines = rules.read_text(encoding="utf-8").split("\n")
        assert lines[3] == '        positivePrice: if (price < 0) ValidationError("Price cannot be negative");', lines[3]
        try:
            apply_names(proposals)
        except AssistError as exc:
            assert "changed since the proposal" in str(exc), exc
        else:
            raise AssertionError("a proposal for a changed line was applied")


def _consolidated(root: Path) -> Path:
    return write_file(root / "findings/consolidated-001-alpha.md",
                      "# Alpha seam\n\n**Scope:** alpha\n\n## 1. First\n\nAt `datrix-alpha/src/a.py:1`.\n\n"
                      "## 2. Second\n\nAt `datrix-alpha/src/b.py:2`.\n\n## 3. Third\n\nCites nothing.\n")


def check_design_close_deletes_only_when_the_designs_pass_and_carry_every_unfixed_section() -> None:
    with _workspace() as root:
        _design_workspace(root)
        finding = _consolidated(root)
        folder, designs = finding.parent, root / "design"
        for name in ("a.py", "b.py"):
            write_file(root / f"datrix-alpha/src/{name}", "VALUE = 1\n")
        carried = _design_text("Base", body="Fixes `datrix-alpha/src/a.py` in the shared layer.")
        _write_design(root, "010-base", carried)
        result = close_findings(root, designs, [finding], set(), apply=True)
        assert result.uncarried == {"C001.2": ["datrix-alpha/src/b.py"]} and not result.deleted, result
        assert result.uncheckable == ["C001.3 (consolidated-001-alpha.md): cites no file that exists"], \
            result.uncheckable
        assert finding.exists(), "a defect no design carries must keep its finding"
        assert close_findings(root, designs, [finding], {"C001.2"}, apply=False).passed and finding.exists()
        try:
            close_findings(root, designs, [finding], {"C001.9"}, apply=False)
        except AssistError as exc:
            assert "C001.9" in str(exc), exc
        else:
            raise AssertionError("a --fixed id that is in no given file was accepted")
        _write_design(root, "020-broken", _design_text("Broken", body="TBD", answers=("G1",)))
        blocked = close_findings(root, designs, [finding], {"C001.2"}, apply=True)
        assert blocked.design_problems and finding.exists(), "a failing design must keep the finding"
        (designs / "020-broken.md").unlink()
        done = close_findings(root, designs, [finding], {"C001.2"}, apply=True)
        assert done.deleted == ["consolidated-001-alpha.md"] and not finding.exists() and folder.is_dir(), done


def _design_reply(chat: Chat) -> str:
    if "review the fix shapes" in chat.system:
        return json.dumps({"merges": [], "extends": [{"shape": "S1", "design": "010-base"},
                                                       {"shape": "S2", "design": "999-nope"}]})
    if "group the defect sections" in chat.system:
        return json.dumps({"shapes": [{"title": "Alpha core", "units": ["C001.1", "C001.9"]},
                                      {"title": "Alpha gone", "units": ["C001.2"]}]})
    return "STILL HOLDS\nHELPERS is defined at datrix-alpha/src/datrix_alpha/core.py:3."


def check_design_verify_and_plan_check_every_answer_and_never_send_a_customer_term() -> None:
    with _workspace() as root:
        _write_design(root, "010-base", _design_text("Base"))
        write_file(root / "findings/consolidated-001-alpha.md", (
            "# Alpha seam\n\n**Scope:** alpha\n\n"
            "## 1. First\n\nAt `datrix-alpha/src/datrix_alpha/core.py:3` and `datrix-alpha/src/gone.py:1`.\n\n"
            "## 2. Second\n\nOnly `datrix-alpha/src/gone.py:2`.\n\n"
            f"## 3. Third\n\nThe {_GATE_TERM} line at `datrix-alpha/src/datrix_alpha/core.py:1`.\n"))
        sources = load_sources(root / "findings")
        with LoopbackOllama(_design_reply) as server:
            results = {r.unit_id: r for r in verify_units(root, _pool(server), sources)}
            shapes = draft_shapes(root, _pool(server), sources, load_designs(root, root / "design"))
        asked = [chat for chat in server.chats if "A report claims" in chat.user]
        assert len(asked) == 2, "the section whose cited files are all gone must not reach a model"
        assert results["C001.1"].verdict == VERDICT_HOLDS and results["C001.1"].gone == ("datrix-alpha/src/gone.py",)
        assert results["C001.2"].verdict == VERDICT_UNCLEAR and "no cited file" in results["C001.2"].evidence
        sent = " ".join(chat.user for chat in server.chats)
        assert _GATE_TERM not in sent and "Third" in sent, "a registered customer term reached the model"
        by_title = {shape.title: shape for shape in shapes}
        assert by_title["Alpha core"].units == ["C001.1"], "an invented section id must be dropped"
        assert by_title["Alpha core"].extends == "010-base" and by_title["Alpha gone"].extends == ""
        third = by_title["Third"]
        assert third.units == ["C001.3"] and "no shape" in " ".join(third.review), third


def check_design_commands_exit_with_the_assist_codes() -> None:
    with _workspace() as root:
        _design_workspace(root)
        _consolidated(root)
        _write_design(root, "010-base", _design_text("Base", body="TBD", answers=("G1",)))

        def run(*arguments: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([sys.executable, *_CLI, "--workspace", str(root), *arguments],
                                  capture_output=True, text=True, check=False, env=script_env())

        assert run("design-inventory").returncode == 0 and (root / ".tmp/assist/design-inventory.md").is_file()
        plan = run("design-plan", "--no-model")
        assert plan.returncode == 0 and (root / ".tmp/assist/design-plan.md").is_file(), plan.stderr
        check = run("design-check")
        assert check.returncode == 2 and "lacks answers for G2" in check.stdout, (check.returncode, check.stdout)
        close = run("design-close", "--finding", "consolidated-001-alpha.md", "--apply")
        assert close.returncode == 2 and (root / "findings/consolidated-001-alpha.md").is_file(), close.stdout


def check_cli_exits_3_when_no_local_model_answers() -> None:
    with _workspace() as root:
        design = write_file(root / "design/042-fixture-design.md", _DESIGN)
        result = subprocess.run(
            [sys.executable, *_CLI, "--workspace", str(root), "checklist", "--design", str(design),
             "--local-machine", _UNROUTABLE, "--local-reachable-timeout-ms", "300"],
            capture_output=True, text=True, check=False, env=script_env())
        assert result.returncode == EXIT_NO_MODEL, (result.returncode, result.stdout, result.stderr)
        assert "Do this phase yourself" in result.stderr, result.stderr


# ===========================================================================
# harness
# ===========================================================================


_ALL_CHECKS: list[CheckFunc] = [
    check_context_digest_maps_touched_directories_from_the_index,
    check_readiness_finds_missing_edges_and_unresolvable_names_exactly,
    check_readiness_satisfied_lead_reads_the_verdict_and_checks_citations,
    check_findings_extraction_maps_tails_reports_invented_and_unassigned_citations,
    check_findings_index_reads_every_file_before_the_first_model_call,
    check_findings_never_send_a_registered_customer_term,
    check_findings_check_refuses_a_lost_citation_and_a_dangling_related_pointer,
    check_findings_check_keep_raw_allows_a_surviving_raw_file_but_not_a_lost_citation,
    check_findings_parse_repairs_mojibake_and_nests_raw_headings,
    check_findings_redundant_proposes_only_what_a_checked_same_verdict_and_the_citations_prove,
    check_findings_redundant_delete_proves_every_condition_before_it_removes_a_file,
    check_findings_redundant_pairs_by_text_but_never_deletes_what_the_survivor_does_not_cite,
    check_findings_redundant_candidates_need_the_survivor_to_hold_the_keywords_of_the_file,
    check_findings_redundant_compares_one_folder_only_and_names_files_by_relative_path,
    check_findings_redundant_commands_exit_with_the_assist_codes,
    check_implement_finding_selects_the_first_files_by_name,
    check_finding_select_and_close_work_the_inbox_subfolders,
    check_implement_finding_test_runs_reads_foreground_test_ps1_results_only,
    check_implement_finding_test_runs_judges_a_gate_run_by_its_verdict_line,
    check_implement_finding_close_deletes_only_an_unreferenced_finding_with_a_passing_last_test_run,
    check_checklist_verifies_quotes_and_lists_uncovered_requirement_lines,
    check_absorb_references_find_name_number_and_title_but_not_task_folders,
    check_absorb_delete_deletes_only_a_licensed_unreferenced_design,
    check_absorb_transfer_gives_a_verdict_per_section,
    check_absorb_transfer_settles_a_copied_section_without_a_model_and_reports_progress,
    check_absorb_transfer_sends_only_the_target_parts_sharing_terms,
    check_absorb_transfer_does_not_accept_present_while_terms_stay_unfound,
    check_absorb_transfer_asks_for_other_words_only_when_the_model_called_a_section_present,
    check_absorb_transfer_finds_a_reworded_term_by_the_words_a_model_offers,
    check_bug_resolution_describes_framework_diffs_only_and_appends_once,
    check_bug_resolution_refuses_incomplete_facts,
    check_bug_resolution_keeps_every_row_of_a_repeated_flag,
    check_quick_report_renders_every_scan_fact,
    check_service_mechanical_renders_checks_and_dead_code,
    check_design_inventory_reads_targets_from_registration_and_numbers_the_gaps,
    check_design_check_refuses_each_malformed_design_and_checks_target_consistency_as_a_set,
    check_design_headers_read_bold_labels_and_wrapped_dependencies,
    check_design_xref_checks_decision_references_and_allocations,
    check_rule_names_checks_every_proposal_and_applies_only_unchanged_lines,
    check_design_close_deletes_only_when_the_designs_pass_and_carry_every_unfixed_section,
    check_design_verify_and_plan_check_every_answer_and_never_send_a_customer_term,
    check_design_commands_exit_with_the_assist_codes,
    check_cli_exits_3_when_no_local_model_answers,
]


def build_parser() -> argparse.ArgumentParser:
    """The options of ``skill/skill-assist-gate.ps1``: one per wrapper parameter, spelled exactly."""
    return check_list_parser("Behaviour checks for the skill assists.", debug_flag=WRAPPER_DEBUG_FLAG,
                             allow_abbrev=False)


def _gate(argv: Sequence[str] | None) -> int:
    # --self-test: the harness reports a deliberate failure, and the wrapper is the template rendered
    # with this parser's options.
    parser = build_parser()
    return check_list_main(
        parser.description or "",
        GATE,
        _ALL_CHECKS,
        self_test=seam_checks(wrapper=WRAPPER, module=MODULE, parser=parser, folder=SKILL_SCRIPTS_DIR),
        argv=argv,
        parser=parser,
        temp_file_variable=GATE_USAGE_LOG,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the verdict, in gate mode."""
    return run_as_gate(GATE, MODULE, _gate, argv)


if __name__ == "__main__":
    sys.exit(main())
