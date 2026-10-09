#!/usr/bin/env python3
"""Skill assists: the mechanical phases of agent skills, done by scripts and local models
(wrapped by scripts/skill/skill-assist.ps1). Each command writes its output under <workspace>/.tmp/assist/ and
prints the path with a one-line summary.

Commands:
    context-digest     --phase N                 the implementers' shared-context digest (code index)
    readiness          --phase N                 readiness-audit evidence (exact checks + model leads)
    findings-index     [--dir D]                 atomic-finding index of the findings inbox (model, checked)
    findings-check     --delete F... [--dir D]   would deleting F lose a citation? (exact)
    checklist          --design PATH             conformance checklist draft (model, checked)
    absorb-transfer    --design PATH --target T  is each design section in the target docs? (model leads)
    absorb-references  --design PATH [--also P]  every line that names the design (exact)
    bug-resolution     --report R --repo P ...   the Resolution section for a fixed bug report

Exit codes: 0 done; 1 the request could not be carried out; 2 the check found something to act on;
3 no local model answered (do the phase yourself, as before the assist).
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from absorb import (
    VERDICT_PRESENT,
    find_references,
    render_references,
    render_transfer,
    transfer_check,
)
from bug_resolution import (
    STATUS_RESOLVED,
    STATUS_UNRESOLVED,
    ResolutionFacts,
    append_resolution,
    build_resolution,
    parse_verification,
)
from checklist import draft_checklist
from checklist import render as render_checklist
from common import (
    EXIT_CHECK_FAILED,
    EXIT_FAILED,
    EXIT_NO_MODEL,
    EXIT_OK,
    AssistError,
    NoModelAnswer,
    workspace_label,
    write_output,
)
from context_digest import build_digest
from datrix_scripts.code_index.queries import QueryError
from datrix_scripts.local_llm import (
    LocalLlmPool,
    LocalLlmUnavailable,
    add_local_llm_arguments,
    local_llm_settings,
)
from datrix_scripts.local_reading import ReadScopeError
from datrix_scripts.task_metadata import format_phase
from datrix_scripts.venv import get_datrix_root
from findings import build_index, check_consolidation, render_check, render_index
from phase_tasks import phase_tasks
from readiness import (
    VERDICT_SATISFIED,
    ReadinessEvidence,
    missing_edges,
    satisfied_leads,
    unresolved_modules,
)
from readiness import render as render_readiness

LOG = logging.getLogger(__name__)

FINDINGS_DIR_PARTS = ("reports", "finding")
CALLER_PREFIX = "skill-assist"


def _pool(args: argparse.Namespace) -> LocalLlmPool:
    settings = replace(local_llm_settings(args), caller=f"{CALLER_PREFIX}:{args.command}")
    return LocalLlmPool(settings, report=lambda line: LOG.info("%s", line))


def _workspace(args: argparse.Namespace) -> Path:
    return Path(args.workspace).resolve() if args.workspace else get_datrix_root()


def _design(workspace: Path, spec: str) -> Path:
    path = Path(spec)
    path = path if path.is_absolute() else workspace / path
    if not path.is_file():
        raise AssistError(f"Design document '{spec}' not found (resolved to {path}). Pass the path of a file "
                          "in the workspace's design folder, absolute or workspace-relative.")
    return path.resolve()


def _done(path: Path, summary: str) -> int:
    print(summary)
    print(f"Written: {path}")
    return EXIT_OK


def cmd_context_digest(args: argparse.Namespace) -> int:
    workspace = _workspace(args)
    tasks = phase_tasks(workspace, args.phase, pending_only=True)
    if not tasks:
        raise AssistError(f"Every task of phase {format_phase(args.phase)} is completed; there is nothing to digest.")
    digest = build_digest(workspace, args.phase, tasks)
    path = write_output(workspace, f"phase-{format_phase(args.phase)}-context.md", digest.text)
    trimmed = " (modules not named by a task listed without descriptions, to fit)" if digest.trimmed else ""
    return _done(path, f"{digest.lines} lines: {digest.packages} package(s), {digest.directories} director(ies)"
                       f"{trimmed}.")


def cmd_readiness(args: argparse.Namespace) -> int:
    workspace = _workspace(args)
    every = phase_tasks(workspace, args.phase, pending_only=False)
    pending = [task for task in every if not task.meta.is_completed]
    evidence = ReadinessEvidence(len(pending), missing_edges(workspace, every, pending),
                                 unresolved_modules(workspace, pending, every))
    if args.no_model:
        evidence.lead_note = "Skipped (--no-model): judge already-satisfied tasks yourself."
    else:
        try:
            evidence.leads = satisfied_leads(workspace, _pool(args), pending)
        except LocalLlmUnavailable as exc:
            evidence.lead_note = f"No local model answered, so judge already-satisfied tasks yourself: {exc}"
    path = write_output(workspace, f"phase-{format_phase(args.phase)}-readiness.md",
                        render_readiness(evidence, format_phase(args.phase)))
    satisfied = sum(1 for lead in evidence.leads if lead.verdict == VERDICT_SATISFIED)
    return _done(path, f"{len(pending)} pending task(s): {len(evidence.edges)} missing edge(s), "
                       f"{len(evidence.modules)} unresolvable name(s), {satisfied} task(s) a model reads as "
                       f"already satisfied.")


def _findings_dir(workspace: Path, spec: str | None) -> Path:
    directory = Path(spec) if spec else workspace.joinpath(*FINDINGS_DIR_PARTS)
    if not directory.is_dir():
        raise AssistError(f"Findings folder {directory} does not exist. Pass --dir with the folder to read.")
    return directory


def cmd_findings_index(args: argparse.Namespace) -> int:
    workspace = _workspace(args)
    extractions = build_index(workspace, _pool(args), _findings_dir(workspace, args.dir))
    if not extractions:
        print("The findings folder holds no *.md file.")
        return EXIT_OK
    path = write_output(workspace, "findings-index.md", render_index(extractions))
    flagged = sum(1 for e in extractions if e.unassigned or e.invented or not e.findings)
    return _done(path, f"{len(extractions)} file(s), {sum(len(e.findings) for e in extractions)} atomic "
                       f"finding(s); {flagged} file(s) to check yourself.")


def cmd_findings_check(args: argparse.Namespace) -> int:
    workspace = _workspace(args)
    directory = _findings_dir(workspace, args.dir)
    delete = [Path(spec) if Path(spec).is_absolute() else directory / spec for spec in args.delete]
    missing = [str(path) for path in delete if not path.is_file()]
    if missing:
        raise AssistError(f"Not files in the findings folder: {', '.join(missing)}. Pass the names of files "
                          "you are about to delete.")
    result = check_consolidation(directory, delete)
    print(render_check(result), end="")
    return EXIT_OK if result.passed else EXIT_CHECK_FAILED


def cmd_checklist(args: argparse.Namespace) -> int:
    workspace = _workspace(args)
    design = _design(workspace, args.design)
    checklist = draft_checklist(workspace, _pool(args), design)
    path = write_output(workspace, f"checklist-{design.stem}.md", render_checklist(checklist))
    return _done(path, f"{len(checklist.requirements)} requirement(s); {len(checklist.uncovered)} requirement-"
                       f"bearing line(s) no item covers; {len(checklist.unverified)} item(s) with an unverified "
                       f"quote.")


def cmd_absorb_transfer(args: argparse.Namespace) -> int:
    workspace = _workspace(args)
    design = _design(workspace, args.design)
    checks = transfer_check(workspace, _pool(args), design, args.target)
    label = workspace_label(workspace, design)
    path = write_output(workspace, f"transfer-{design.stem}.md", render_transfer(label, checks))
    short = sum(1 for check in checks if check.verdict != VERDICT_PRESENT)
    _done(path, f"{len(checks)} section(s); {short} partial or missing.")
    return EXIT_CHECK_FAILED if short else EXIT_OK


def cmd_absorb_references(args: argparse.Namespace) -> int:
    workspace = _workspace(args)
    design = _design(workspace, args.design)
    references = find_references(workspace, design, [Path(p).resolve() for p in args.also])
    print(render_references(workspace_label(workspace, design), references), end="")
    return EXIT_CHECK_FAILED if references else EXIT_OK


def cmd_bug_resolution(args: argparse.Namespace) -> int:
    workspace = _workspace(args)
    report = Path(args.report).resolve()
    facts = ResolutionFacts(args.status, args.fix_type or "", tuple(args.exhibiting), tuple(args.reached),
                            tuple(parse_verification(spec) for spec in args.verification), args.reason or "",
                            args.notes or "")
    pool = None if args.no_model else _pool(args)
    section = build_resolution(workspace, pool, facts, [Path(r).resolve() for r in args.repo], set(args.file))
    if args.append:
        append_resolution(report, section)
        print(f"Appended the Resolution to {report}")
        return EXIT_OK
    path = write_output(workspace, f"resolution-{report.stem}.md", section)
    return _done(path, "Draft written; review it, then run again with --append to add it to the report.")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workspace", help="Workspace root (default: this checkout's workspace)")
    parser.add_argument("--verbose", action="store_true", help="Show model-server progress")
    commands = parser.add_subparsers(dest="command", required=True)

    def command(name: str, handler: Callable[[argparse.Namespace], int], model: bool) -> argparse.ArgumentParser:
        sub = commands.add_parser(name)
        sub.set_defaults(handler=handler)
        if model:
            add_local_llm_arguments(sub)
        return sub

    sub = command("context-digest", cmd_context_digest, model=False)
    sub.add_argument("--phase", type=int, required=True)
    sub = command("readiness", cmd_readiness, model=True)
    sub.add_argument("--phase", type=int, required=True)
    sub.add_argument("--no-model", action="store_true", help="Exact checks only; no already-satisfied leads")
    sub = command("findings-index", cmd_findings_index, model=True)
    sub.add_argument("--dir", help="Findings folder (default: <workspace>/reports/finding)")
    sub = command("findings-check", cmd_findings_check, model=False)
    sub.add_argument("--dir", help="Findings folder (default: <workspace>/reports/finding)")
    sub.add_argument("--delete", nargs="+", action="extend", required=True, help="The files you are about to delete")
    sub = command("checklist", cmd_checklist, model=True)
    sub.add_argument("--design", required=True)
    sub = command("absorb-transfer", cmd_absorb_transfer, model=True)
    sub.add_argument("--design", required=True)
    sub.add_argument(
        "--target", nargs="+", action="extend", required=True, help="Target docs (workspace-relative paths or globs)"
    )
    sub = command("absorb-references", cmd_absorb_references, model=False)
    sub.add_argument("--design", required=True)
    sub.add_argument("--also", nargs="*", action="extend", default=[], help="Extra files or folders to search (e.g. the memory dir)")
    sub = command("bug-resolution", cmd_bug_resolution, model=True)
    sub.add_argument("--report", required=True)
    sub.add_argument("--repo", nargs="+", action="extend", default=[], help="Repositories the fix changed")
    sub.add_argument(
        "--file", nargs="*", action="extend", default=[], help="Only these repo-relative files (default: every change)"
    )
    sub.add_argument("--status", choices=(STATUS_RESOLVED, STATUS_UNRESOLVED), default=STATUS_RESOLVED)
    sub.add_argument("--fix-type", help="App Definition | Generator/Template | Both")
    sub.add_argument("--exhibiting", nargs="*", action="extend", default=[], help="Profiles exhibiting the bug")
    sub.add_argument("--reached", nargs="*", action="extend", default=[], help="Profiles the fix reaches")
    sub.add_argument(
        "--verification",
        nargs="*",
        action="extend",
        default=[],
        help="profile|regenerated|artifact|result rows (the flag may repeat; every row is kept)",
    )
    sub.add_argument("--reason", help="Unresolved: why the bug could not be fixed")
    sub.add_argument("--notes", help="Unresolved: what was examined and why the fix could not be applied")
    sub.add_argument("--append", action="store_true", help="Append to the report instead of writing a draft")
    sub.add_argument("--no-model", action="store_true", help="Describe changes from the diff shape only")
    return parser


def main() -> int:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")
    try:
        return int(args.handler(args))
    except (AssistError, ReadScopeError, QueryError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_FAILED
    except (LocalLlmUnavailable, NoModelAnswer) as exc:
        print(f"NO LOCAL MODEL: {exc}\nDo this phase yourself, as the skill did before this assist.", file=sys.stderr)
        return EXIT_NO_MODEL


if __name__ == "__main__":
    sys.exit(main())
