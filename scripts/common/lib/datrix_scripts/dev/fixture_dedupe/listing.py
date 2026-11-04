"""The ``-DryRun`` listing of a dedupe plan, and its exit code."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from datrix_scripts.dev.fixture_dedupe.follow import FollowedReferences
from datrix_scripts.dev.fixture_dedupe.plan import FilePlacement, LiteralPlacement, Plan, build_plan
from datrix_scripts.dev.fixture_dedupe.secret_screen import ScreenError
from datrix_scripts.dev.fixture_dedupe.sites import LITERAL_SITE, PAIR_SITE, PATH_SITE, SitePlan
from datrix_scripts.gate_harness import EXIT_PASS, EXIT_USAGE, EXIT_VIOLATION, report_step
from datrix_scripts.gates.ratchet.fixture_budget_gate import FixtureScanError


def _shown(path: Path, base_dir: Path) -> str:
    return path.relative_to(base_dir).as_posix()


def _one_line(written: str) -> str:
    """*written* with its line breaks and indentation collapsed to single spaces, for a one-line listing."""
    return " ".join(written.split())


def _print_file(placement: FilePlacement, base_dir: Path) -> None:
    if placement.target is not None and placement.source is not None:
        print(f"  {placement.group.kind} -> {_shown(placement.target, base_dir)}")
        print(f"    move   {_shown(placement.source, base_dir)}")
    else:
        print(f"  {placement.group.kind} stays: {placement.refusal}")
    for path in placement.deleted:
        print(f"    delete {_shown(path, base_dir)}")
    for kept in placement.kept:
        print(f"    keep   {_shown(kept.path, base_dir)} ({kept.reason})")


def _print_literal(placement: LiteralPlacement, base_dir: Path) -> None:
    if placement.target is not None:
        print(f"  {placement.group.kind} -> {_shown(placement.target, base_dir)}")
    else:
        print(f"  {placement.group.kind} stays: {placement.refusal}")
    for site in placement.rewritten:
        print(f"    rewrite {_shown(site.module, base_dir)}:{site.line} {site.name}")
    for refused in placement.refused:
        print(f"    refuse  {_shown(refused.site.module, base_dir)}:{refused.site.line} ({refused.reason})")
    if placement.target is None and not placement.refused:
        for site in placement.group.members:
            print(f"    keep    {_shown(site.module, base_dir)}:{site.line} {site.name}")


def _print_context(plan: Plan) -> None:
    base_dir = plan.base_dir
    report_step(f"Split groups: normalized-equal files whose references differ ({len(plan.splits)})")
    for split in plan.splits:
        print(f"  {split.kind}")
        for part in split.parts:
            print(f"    one fixture: {', '.join(_shown(path, base_dir) for path in part)}")
    report_step(f"Directories read whole ({len(plan.walks.directories)})")
    for walked in plan.walks.directories:
        print(f"  {_shown(walked.path, base_dir)} ({walked.describe(base_dir)})")
    report_step(f"Walk sites that cannot be evaluated ({len(plan.refused_walks)})")
    for refused in plan.refused_walks:
        print(f"  {_shown(refused.site.module, base_dir)}:{refused.site.line} {refused.site.text} ({refused.reason})")
    report_step(
        "Corpus screens over the would-be corpus: the formatter's walk, and the capture (secret findings, refused loads) "
        f"of {', '.join(plan.screened) or 'no package'}"
    )
    for key, findings in plan.screen_findings.items():
        print(f"  {key}: {len(findings)} finding(s)")


def print_plan(plan: Plan) -> None:
    """Print *plan*: the groups with their placements, the context the plan rests on, and the totals."""
    base_dir = plan.base_dir
    moving = [placement for placement in plan.files if placement.target is not None]
    report_step(f"File groups ({len(plan.files)}; {len(moving)} move)")
    for placement in plan.files:
        _print_file(placement, base_dir)
    rewritten = [placement for placement in plan.literals if placement.target is not None]
    report_step(f"Literal groups ({len(plan.literals)}; {len(rewritten)} move)")
    for literal in plan.literals:
        _print_literal(literal, base_dir)
    _print_context(plan)
    deleted = sum(len(placement.deleted) for placement in plan.files)
    kept = sum(len(placement.kept) for placement in plan.files)
    sites = sum(len(placement.rewritten) for placement in plan.literals)
    refused = sum(len(placement.refused) for placement in plan.literals)
    print(
        f"\nSummary: file groups {len(plan.files)} (move {len(moving)}, delete {deleted}, keep {kept}); "
        f"literal groups {len(plan.literals)} (move {len(rewritten)}, rewrite {sites}, refused {refused}); "
        f"split groups {len(plan.splits)}; refused walk sites {len(plan.refused_walks)}"
    )


def print_followed(followed: FollowedReferences, base_dir: Path) -> None:
    """Print the references rewritten to follow their file, and the ones that cannot."""
    report_step(
        f"References following their file ({len(followed.rewrites)} rewritten, {len(followed.refused)} refused, "
        f"of {followed.read} read; {len(followed.moves)} copies leave their tree)"
    )
    for rewrite in followed.rewrites:
        print(f"  rewrite {_shown(rewrite.placed, base_dir)}: '{rewrite.reference.literal}' -> '{rewrite.literal}'")
    for refused in followed.refused:
        print(f"  refuse  {_shown(refused.placed, base_dir)}: '{refused.reference.literal}' ({refused.reason})")
    print(f"References: rewritten {len(followed.rewrites)}, refused {len(followed.refused)}")


def print_sites(sites: SitePlan, base_dir: Path) -> None:
    """Print the test-module sites rewritten to read the shared copies, and the ones left for a hand edit."""
    rewrites = sites.rewrites
    kinds = Counter(rewrite.kind for rewrite in rewrites)
    report_step(
        f"Test sites reading a copy that leaves ({len(rewrites)} rewritten, {len(sites.refused)} refused, "
        f"of {sites.read} modules read; {len(sites.edits)} modules edited)"
    )
    for rewrite in rewrites:
        if rewrite.kind != LITERAL_SITE:
            print(f"  rewrite {_shown(rewrite.module, base_dir)}:{rewrite.line} {_one_line(rewrite.written)} -> {rewrite.replacement}")
    for refused in sites.refused:
        print(f"  refuse  {_shown(refused.module, base_dir)}:{refused.line} {_one_line(refused.written)} ({refused.reason})")
    print(
        f"Test sites: rewritten {len(rewrites)} (path {kinds[PATH_SITE]}, pair {kinds[PAIR_SITE]}, "
        f"literal {kinds[LITERAL_SITE]}), refused {len(sites.refused)}"
    )


def dry_run(base_dir: Path) -> int:
    """Build and print the plan of *base_dir* and where its references land; the exit code of the listing."""
    try:
        plan = build_plan(base_dir)
    except (FixtureScanError, ScreenError) as exc:
        print(f"\nERROR: {exc}")
        return EXIT_USAGE
    return list_plan(plan)


def list_plan(plan: Plan) -> int:
    """Print *plan*, where its references land and its test sites; ``EXIT_VIOLATION`` when the plan cannot
    be proven (a walk site that cannot be evaluated, a staying reference a placed copy shadows), else
    ``EXIT_PASS``."""
    base_dir = plan.base_dir
    print_plan(plan)
    followed = plan.followed
    print_followed(followed, base_dir)
    print_sites(plan.sites, base_dir)
    if plan.refused_walks:
        print(
            "\nFAILED: a walk site cannot be evaluated, so the plan cannot prove which copies its directory read "
            "needs. Fix: write its directory as a path the text shows (a Path(__file__) chain, a constant)."
        )
        return EXIT_VIOLATION
    if followed.refused:
        print(
            "\nFAILED: a reference whose file and reader both stay cannot be read back over the moved tree (a "
            "copy placed nearer its base names another file), so the moved tree would not resolve. Fix: write "
            "the reference as a path from its own base that no shared copy shadows."
        )
        return EXIT_VIOLATION
    return EXIT_PASS
