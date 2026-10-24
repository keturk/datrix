"""Sort the findings files lying directly in the findings folder into one level of area subfolders, by name.

``scripts/skill/organize-findings.ps1`` (and its ``.sh`` twin) runs this module. It never reads a file's
content: the area of a finding comes from its file name alone.

NAME
    A name in the merged scheme ``NNNN-<area>-<slug>.md`` carries its area. Any other name (a timestamped
    ``YYYYMMDD-HHMMSS-<slug>.md``, ``consolidated-NNN-<slug>.md`` or a bare slug) is read by the first word of
    its slug: an area name or one of its aliases (``azure-...``, ``ts-...``, ``gate-...``).

LOCAL MODEL
    A name whose first word names no area is sent, by name only, to a local model that picks one of the
    areas for it. Every answer is checked: a file the model was not asked about, or an area outside the set,
    is dropped and the file stays where it is. A name carrying a registered customer term is not sent.
    ``--no-model`` sends nothing.

MOVE
    Each file moves to ``<folder>/<area>/<same name>``. Only ``*.md`` files directly in the folder are
    looked at: nothing already inside a subfolder is touched and no subfolder is ever created inside
    another, so there is exactly one level. A move never overwrites: when the target name exists, the file
    stays and the run fails.

The areas are those of /merge-findings, in its order. A finding that names the sorted folder's files keeps
its pointers (they name the file stem, not a path), but ``finding-select``, ``finding-close`` and the
skills' inbox scans read ``*.md`` directly in one folder: point them at an area subfolder with ``--dir``.

Exit codes: 0 every file is sorted (or a dry run found nothing wrong); 1 the folder cannot be read or a move
failed; 2 some files stayed put (a withheld name, or no valid model answer for them); 3 a model was needed
and none answered. When several apply, 1 wins over 3 and 3 over 2.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from datrix_scripts.customer_domain_isolation import hash_term
from datrix_scripts.gate_harness import write_file, write_files
from datrix_scripts.local_llm import (
    LocalLlmPool,
    LocalLlmSettings,
    LocalLlmUnavailable,
    add_wrapper_llm_arguments,
    wrapper_llm_settings,
)
from datrix_scripts.local_llm_loopback import LOOPBACK, LoopbackOllama, answering
from datrix_scripts.logging_utils import ColorCodes, say
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.skill.common import (
    EXIT_CHECK_FAILED,
    EXIT_FAILED,
    EXIT_NO_MODEL,
    EXIT_OK,
    AssistError,
    ContentFilter,
    NoModelAnswer,
    ask_json,
    object_list,
    parallel,
)
from datrix_scripts.skill.finding_inbox import findings_dir
from datrix_scripts.test.wrappers import SKILL_SCRIPTS_DIR, module_main, run_self_test

LOG = logging.getLogger(__name__)

MODULE: Final = "datrix_scripts.skill.organize_findings"
WRAPPER: Final = "organize-findings"
LLM_TIMEOUT_SECONDS: Final = 300
CALLER: Final = "organize-findings"
NAMES_PER_REQUEST: Final = 40

# The areas of /merge-findings in its order, each with what it holds (sent to the model with the names).
AREAS: Final[dict[str, str]] = {
    "python": "the Python backend generator (FastAPI)",
    "typescript": "the TypeScript backend generator (NestJS / Express) and the shared TypeScript core",
    "backends": "both backend languages, or the shared language layer (transpiler, profiles, context builders)",
    "clients": "the Angular and Flutter client targets",
    "language": "the parser, semantic analysis and the DSL",
    "migration": "schema snapshots, the migration ledger and migration adapters",
    "seed": "seed data",
    "kernel": "shared generation, secrets, hosting, pooling, observability export",
    "docker": "the Docker Compose platform generator",
    "aws": "the AWS CloudFormation platform generator",
    "azure": "the Azure Bicep / ARM platform generator",
    "component": "the platform-agnostic component generator (docs, config, scripts)",
    "tests": "red or weak test suites",
    "tooling": "scripts, gates, skills and the harness",
    "docs": "documentation",
}
# First word of a slug -> area, besides the area names themselves.
ALIASES: Final[dict[str, str]] = {
    "ts": "typescript", "angular": "clients", "flutter": "clients", "migrations": "migration",
    "test": "tests", "script": "tooling", "scripts": "tooling", "gate": "tooling", "gates": "tooling",
    "skill": "tooling", "skills": "tooling", "doc": "docs",
}
_TIMESTAMPED: Final = re.compile(r"^\d{8}-\d{6}-(.+)$")
_CONSOLIDATED: Final = re.compile(r"^consolidated-\d{3}-(.+)$")
_MERGED: Final = re.compile(r"^\d{4}-([a-z]+)-.+$")
PLACE_SYSTEM: Final = (
    "You file findings about Datrix, a multi-language code generator, into folders by area. You see only "
    "file names, each ending in a slug that describes the defect. For each file name, answer the one area "
    "whose code owns the fix. Areas: " + "; ".join(f"{area} ({what})" for area, what in AREAS.items())
    + ". Use the most specific area; a defect seen on several targets with one shared remedy goes to the "
    "shared area. Answer every file name exactly as given, once.")
PLACE_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {"files": {"type": "array", "items": {
        "type": "object",
        "properties": {"file": {"type": "string"}, "area": {"type": "string", "enum": list(AREAS)}},
        "required": ["file", "area"]}}},
    "required": ["files"],
}


@dataclass
class Plan:
    """Where each loose findings file goes, and why the others stay."""

    moves: dict[str, str] = field(default_factory=dict)
    from_model: set[str] = field(default_factory=set)
    stays: dict[str, str] = field(default_factory=dict)
    model_missing: bool = False


def loose_findings(directory: Path) -> list[Path]:
    """The ``*.md`` files directly in ``directory`` (never inside a subfolder), by name."""
    if not directory.is_dir():
        raise AssistError(f"Findings folder '{directory}' does not exist. Pass --dir with an existing folder.")
    return sorted(path for path in directory.glob("*.md") if path.is_file())


def area_from_name(name: str) -> str:
    """The area a file name states: the merged scheme's area, else the first word of the slug when it names
    an area or an alias; empty when the name states none."""
    stem = name.removesuffix(".md")
    merged = _MERGED.match(stem)
    if merged and merged.group(1) in AREAS:
        return merged.group(1)
    for pattern in (_TIMESTAMPED, _CONSOLIDATED):
        found = pattern.match(stem)
        if found:
            stem = found.group(1)
            break
    word = stem.split("-", 1)[0]
    return word if word in AREAS else ALIASES.get(word, "")


def valid_placements(answer: dict[str, object], asked: Sequence[str]) -> dict[str, str]:
    """The ``file -> area`` pairs of a model's answer that name a file it was asked about and an area of the
    set; the first answer for a file wins and every other entry is dropped."""
    placed: dict[str, str] = {}
    for item in object_list(answer.get("files")):
        name, area = str(item.get("file", "")), str(item.get("area", ""))
        if name in asked and area in AREAS and name not in placed:
            placed[name] = area
    return placed


def ask_areas(pool: LocalLlmPool, names: Sequence[str]) -> dict[str, str]:
    """The model's area for each of ``names`` (one request); files it left out or misplaced are absent."""
    answer = ask_json(pool, PLACE_SYSTEM, "\n".join(names), PLACE_SCHEMA)
    return valid_placements(answer, names)


def place_by_model(settings: LocalLlmSettings, workspace: Path, names: Sequence[str], plan: Plan) -> None:
    """Fill ``plan`` for ``names`` from a local model: a name carrying a registered customer term is withheld,
    the rest are sent ``NAMES_PER_REQUEST`` at a time."""
    content = ContentFilter(workspace)
    sendable = [name for name in names if not content.carries_term(name)]
    for name in names:
        if name not in sendable:
            plan.stays[name] = "its name carries a registered customer term, so it is not sent to a model"
    pool = LocalLlmPool(replace(settings, caller=CALLER), report=lambda line: LOG.info("%s", line))
    chunks = [sendable[start:start + NAMES_PER_REQUEST] for start in range(0, len(sendable), NAMES_PER_REQUEST)]
    for chunk, answered in zip(chunks, parallel(chunks, lambda chunk: ask_areas(pool, chunk)), strict=True):
        for name in chunk:
            if name in answered:
                plan.moves[name] = answered[name]
                plan.from_model.add(name)
            else:
                plan.stays[name] = "the model gave no valid area for it"


def build_plan(directory: Path, workspace: Path, settings: LocalLlmSettings | None) -> Plan:
    """The plan for every loose file of ``directory``; ``settings`` None means no model is asked."""
    plan = Plan()
    unnamed: list[str] = []
    for path in loose_findings(directory):
        area = area_from_name(path.name)
        if area:
            plan.moves[path.name] = area
        else:
            unnamed.append(path.name)
    if not unnamed:
        return plan
    if settings is None:
        plan.stays.update({name: "its name states no area and --no-model was given" for name in unnamed})
        return plan
    try:
        place_by_model(settings, workspace, unnamed, plan)
    except (LocalLlmUnavailable, NoModelAnswer) as exc:
        plan.model_missing = True
        LOG.warning("No local model answered: %s", exc)
        plan.stays.update({name: "no local model answered" for name in unnamed if name not in plan.stays})
    return plan


def move_files(directory: Path, plan: Plan, *, dry_run: bool) -> list[str]:
    """Move each planned file into ``<directory>/<area>/``; the names of the files that could not move, each
    taken out of ``plan.moves`` into ``plan.stays`` with its reason. A target that exists is never overwritten
    and a subfolder is only ever created directly in ``directory``."""
    failed: dict[str, str] = {}
    for name, area in plan.moves.items():
        target_dir, target = directory / area, directory / area / name
        if target.exists():
            failed[name] = f"{area}/{name} already exists, so the file stays"
        elif target_dir.exists() and not target_dir.is_dir():
            failed[name] = f"'{target_dir}' exists and is not a folder"
        elif not dry_run:
            try:
                target_dir.mkdir(exist_ok=True)
                (directory / name).rename(target)
            except OSError as exc:
                failed[name] = str(exc)
    for name, reason in failed.items():
        del plan.moves[name]
        plan.stays[name] = f"FAILED, {reason}"
    return list(failed)


def report(plan: Plan, failures: Sequence[str], *, dry_run: bool) -> None:
    """Print each move, grouped by area, then each file that stays."""
    verb = "would move" if dry_run else "moved"
    for area in AREAS:
        names = [name for name, planned in plan.moves.items() if planned == area]
        if names:
            say(f"{area}/ ({len(names)})", ColorCodes.CYAN)
        for name in names:
            source = " (model)" if name in plan.from_model else ""
            say(f"  {verb} {name}{source}")
    for name, reason in plan.stays.items():
        say(f"  left {name}: {reason}", ColorCodes.RED if name in failures else ColorCodes.YELLOW)
    say(f"{verb} {len(plan.moves)}, left {len(plan.stays)}.")


def exit_code(plan: Plan, failures: Sequence[str]) -> int:
    """1 when a move failed, 3 when a model was needed and none answered, 2 when files stay, else 0."""
    if failures:
        return EXIT_FAILED
    if plan.model_missing:
        return EXIT_NO_MODEL
    return EXIT_CHECK_FAILED if plan.stays else EXIT_OK


def organize(directory: Path, workspace: Path, settings: LocalLlmSettings | None, *, dry_run: bool) -> int:
    """Plan, move and report; the exit code."""
    plan = build_plan(directory, workspace, settings)
    failures = move_files(directory, plan, dry_run=dry_run)
    report(plan, failures, dry_run=dry_run)
    return exit_code(plan, failures)


def build_parser() -> argparse.ArgumentParser:
    """The options of ``skill/organize-findings.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description="Sort the findings files directly in the findings folder into one level of area subfolders.",
        allow_abbrev=False,
    )
    parser.add_argument("--dir", default="", help="The findings folder. Default: <workspace>/reports/finding.")
    parser.add_argument("--dry-run", action="store_true", help="Print the moves; make none.")
    parser.add_argument("--no-model", action="store_true",
                        help="Never ask a local model: a name that states no area stays where it is.")
    add_wrapper_llm_arguments(parser, timeout_seconds=LLM_TIMEOUT_SECONDS)
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the name, plan, move and model checks and the wrapper seam checks.")
    parser.set_defaults(debug=False)
    return parser


# ===========================================================================
# self-test
# ===========================================================================

_TERM = "zorbquix"


@contextmanager
def _workspace() -> Iterator[Path]:
    """A temp workspace holding a findings folder and a customer-term corpus registering one term."""
    with TemporaryDirectory(prefix="organize-findings-") as temp:
        root = Path(temp)
        write_file(root / "datrix/scripts/config/customer-term-hashes.json", json.dumps({
            "algorithm": "sha256", "min_token_length": 5,
            "terms": [{"hash": hash_term(_TERM), "hint": "self-test"}]}))
        (root / "reports" / "finding").mkdir(parents=True)
        yield root


def _model_settings(server: LoopbackOllama) -> LocalLlmSettings:
    return LocalLlmSettings(machines=(LOOPBACK,), reachable_timeout_ms=2000, generate_timeout_ms=5000,
                            allow_load=False, ollama_port=server.port, caller=CALLER)


def _check_a_name_states_its_area() -> None:
    cases = {
        "20261024-110447-azure-search-endpoint-never-seeded.md": "azure",
        "20261023-203101-thin-entrypoint-gate-red-on-five-wrappers.md": "",
        "20261023-203101-gate-red-on-five-wrappers.md": "tooling",
        "20261024-120700-ts-tests-import-removed-mysql-names.md": "typescript",
        "0007-docker-cosmosdb-emulator.md": "docker",
        "0007-nonsense-cosmosdb-emulator.md": "",
        "consolidated-012-python-regex.md": "python",
        "migration-ledger.md": "migration",
        "20261024-110446-aws.md": "aws",
        "notes.md": "",
    }
    for name, area in cases.items():
        assert area_from_name(name) == area, (name, area_from_name(name), area)


def _check_only_valid_model_answers_are_kept() -> None:
    asked = ["a.md", "b.md", "c.md", "d.md"]
    answer = {"files": [{"file": "a.md", "area": "docker"}, {"file": "a.md", "area": "aws"},
                        {"file": "b.md", "area": "nowhere"}, {"file": "z.md", "area": "docs"},
                        {"file": "c.md", "area": "docs"}, "text"]}
    assert valid_placements(answer, asked) == {"a.md": "docker", "c.md": "docs"}, valid_placements(answer, asked)
    assert valid_placements({"files": "x"}, asked) == {}


def _check_files_move_one_level_and_nothing_else_is_touched() -> None:
    with _workspace() as root:
        inbox = root / "reports" / "finding"
        write_files(inbox, {"20261024-100000-azure-a.md": "a", "20261024-110447-azure-a.md": "a",
                            "0002-python-b.md": "b", "stray-slug.md": "s", "notes.txt": "t",
                            "docs/kept.md": "k", "python/old.md": "o"})
        assert organize(inbox, root, None, dry_run=True) == EXIT_CHECK_FAILED
        assert not (inbox / "azure").exists(), "a dry run makes no folder"
        assert organize(inbox, root, None, dry_run=False) == EXIT_CHECK_FAILED
        assert (inbox / "azure" / "20261024-110447-azure-a.md").read_text() == "a"
        assert (inbox / "python" / "0002-python-b.md").is_file() and (inbox / "python" / "old.md").is_file()
        assert (inbox / "stray-slug.md").is_file() and (inbox / "notes.txt").is_file()
        assert (inbox / "docs" / "kept.md").is_file()
        nested = [p for p in inbox.rglob("*") if p.is_dir() and p.parent != inbox]
        assert not nested, nested


def _check_a_move_never_overwrites() -> None:
    with _workspace() as root:
        inbox = root / "reports" / "finding"
        write_files(inbox, {"0001-azure-x.md": "new", "azure/0001-azure-x.md": "old"})
        assert organize(inbox, root, None, dry_run=False) == EXIT_FAILED
        assert (inbox / "azure" / "0001-azure-x.md").read_text() == "old"
        assert (inbox / "0001-azure-x.md").read_text() == "new"
        write_files(inbox, {"0002-docker-y.md": "y", "docker": "a file in the way"})
        assert organize(inbox, root, None, dry_run=False) == EXIT_FAILED
        assert (inbox / "0002-docker-y.md").is_file()


def _check_the_model_places_only_what_the_name_leaves_open() -> None:
    names = ["20261024-100001-pdf-geospatial-overlay.md", "20261024-100002-whatever-else.md",
             f"20261024-100003-{_TERM}-thing.md", "20261024-100004-azure-known.md"]

    reply = json.dumps({"files": [{"file": names[0], "area": "tooling"}, {"file": names[1], "area": "bogus"}]})
    with _workspace() as root:
        inbox = root / "reports" / "finding"
        write_files(inbox, {name: "x" for name in names})
        with LoopbackOllama(answering(reply)) as server:
            code = organize(inbox, root, _model_settings(server), dry_run=False)
            assert len(server.chats) == 1, server.chats
            sent = server.chats[0].user.splitlines()
        assert sent == names[:2], sent
        assert code == EXIT_CHECK_FAILED, code
        assert (inbox / "tooling" / names[0]).is_file() and (inbox / "azure" / names[3]).is_file()
        assert (inbox / names[1]).is_file() and (inbox / names[2]).is_file()


def _check_no_model_leaves_the_open_names_and_says_so() -> None:
    with _workspace() as root:
        inbox = root / "reports" / "finding"
        write_files(inbox, {"20261024-100005-pdf-overlay.md": "x", "20261024-100006-azure-a.md": "y"})
        with LoopbackOllama(answering("{}"), models=()) as server:
            code = organize(inbox, root, _model_settings(server), dry_run=False)
        assert code == EXIT_NO_MODEL, code
        assert (inbox / "20261024-100005-pdf-overlay.md").is_file() and (inbox / "azure").is_dir()


def _check_a_missing_folder_is_refused() -> None:
    with _workspace() as root:
        try:
            loose_findings(root / "absent")
        except AssistError as exc:
            assert "does not exist" in str(exc), exc
        else:
            raise AssertionError("a missing folder must be refused")
        assert findings_dir(root, "") == root / "reports" / "finding"


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_a_name_states_its_area, _check_only_valid_model_answers_are_kept,
                  _check_files_move_one_level_and_nothing_else_is_touched, _check_a_move_never_overwrites,
                  _check_the_model_places_only_what_the_name_leaves_open,
                  _check_no_model_leaves_the_open_names_and_says_so, _check_a_missing_folder_is_refused]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=SKILL_SCRIPTS_DIR)
    try:
        directory = findings_dir(WORKSPACE_DIR, args.dir)
        settings = None if args.no_model else wrapper_llm_settings(args)
        return organize(directory, WORKSPACE_DIR, settings, dry_run=args.dry_run)
    except AssistError as exc:
        say(f"ERROR: {exc}", ColorCodes.RED)
        return EXIT_FAILED


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
