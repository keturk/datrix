#!/usr/bin/env python
"""Instruction-surface gate: no agent-facing document may prescribe a
whole-suite test run -- a whole-suite `test.ps1` form or any `affected-gate.ps1`
sweep.

WHY THIS EXISTS
---------------
`guard-full-suite-runs.py` blocks an agent from EXECUTING a whole-suite run,
but nothing made the PRESCRIPTION visible: skills and the top-level CLAUDE.md
told an agent, in prose and command examples, to run a bare `test.ps1 {package}`
or an `affected-gate.ps1` sweep inside a fix loop or at a phase boundary -- the
guard then blocked the agent that obeyed, but the instruction itself never
showed up anywhere Jon could read and drive to zero. This gate is that census.

WHAT IT SCANS AND HOW
----------------------
Every fenced code block (``` ... ```) and inline code span (`...`) inside
`claude-config/.claude/CLAUDE.md`, the four read-when docs under
`claude-config/.claude/docs/` that CLAUDE.md routes to, and
`claude-config/.claude/skills/**/*.md` (including `_shared/`) -- parsed with a
real Markdown tokenizer (Python's stdlib has none; this module walks fence and
backtick delimiters directly, which is the same "no line regex" discipline
`ignored_source.py` applies to git's ignore rules: eyeballing text with a regex
misses a code span that crosses a line-wrap or shares a line with prose,
exactly the shape a false negative here would take).

Every code fragment found is classified with `_suite_invocation.py` (the SAME
module `guard-full-suite-runs.py` loads as a sibling) -- loaded here by path
through `datrix_scripts.hook_modules.load_suite_invocation`, so the gate and
the hook it audits share one definition. A fragment classified whole-suite (bare
package, several packages, `-All`, `-Rerun`, a tier switch with none of
`-Specific`/`-Keyword`/`-Tag`, or any `affected-gate.ps1` invocation other than
`-SelfTest`) is a hit UNLESS an HTML comment
`<!-- forbidden-example -->` sits on the same line, or the line immediately
before (for a fenced block: the line before the OPENING fence) -- the
orchestrator's own "this is FORBIDDEN here" illustrative blocks are the
carve-out this exemption exists for.

Exit codes: 0 = zero un-exempted whole-suite hits (or a successful `-self-test`
run); 1 = at least one hit, the self-test failed, or a wrapper seam check
failed; 2 = usage error, or a dependency module could not be loaded.

Run it through `gates/repo-hygiene/instruction-surface-gate.ps1` or its `.sh`
twin; it runs in gate mode (`datrix_scripts.gate_log.run_as_gate`) and prints
the `[GATE] instruction-surface PASSED|FAILED exit=<n> log=<path>` verdict last.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Final

from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.gates.repo_hygiene.gate_options import self_test_gate_parser
from datrix_scripts.hook_modules import HookModuleError, load_suite_invocation
from datrix_scripts.paths import SHOWCASE_DIR
from datrix_scripts.test import wrappers

DATRIX_ROOT = SHOWCASE_DIR

logger = logging.getLogger(__name__)

GATE: Final = "instruction-surface"
MODULE: Final = "datrix_scripts.gates.repo_hygiene.instruction_surface_gate"
WRAPPER: Final = "instruction-surface-gate"

FORBIDDEN_EXAMPLE_MARKER = "<!-- forbidden-example -->"

#: The document set this gate owns. `_shared/` is a subdirectory of `skills/`,
#: already covered by the `**/*.md` glob -- listed separately in the design
#: purely for emphasis, not because it needs its own glob.
SCAN_GLOBS: tuple[str, ...] = (
    "claude-config/.claude/CLAUDE.md",
    "claude-config/.claude/docs/design-and-docs.md",
    "claude-config/.claude/docs/harness-guards.md",
    "claude-config/.claude/docs/repo-boundaries.md",
    "claude-config/.claude/docs/task-orchestration.md",
    "claude-config/.claude/skills/**/*.md",
)


@dataclass(frozen=True)
class Hit:
    """One un-exempted whole-suite `test.ps1`/`affected-gate.ps1` fragment."""

    path: Path
    line: int
    text: str

    def render(self, root: Path) -> str:
        return f"{self.path.relative_to(root)}:{self.line}: {self.text.strip()}"


@dataclass(frozen=True)
class ScanResult:
    hits: tuple[Hit, ...]
    exempted_count: int


# ---------------------------------------------------------------------------
# Markdown tokenization: fenced blocks + inline code spans, with line numbers.
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")


@dataclass(frozen=True)
class CodeFragment:
    """One fenced block's full text, or one inline code span's text -- with the
    1-based line the fragment (or its containing line, for an inline span)
    starts on, and whether an exemption comment applies to it."""

    text: str
    line: int
    exempted: bool


def _line_is_exempt(lines: list[str], zero_based_index: int) -> bool:
    """`<!-- forbidden-example -->` on this line, or the line immediately before."""
    for candidate in (zero_based_index, zero_based_index - 1):
        if 0 <= candidate < len(lines) and FORBIDDEN_EXAMPLE_MARKER in lines[candidate]:
            return True
    return False


def _find_closing_fence(
    lines: list[str], body_start: int, fence_marker: str, fence_len: int, indent: str
) -> int | None:
    """The 0-based index of the line that closes a fence opened with `indent`
    leading whitespace, or `None` if none exists before EOF.

    Tries an exact-indent match first (the line closing THIS fence should be
    indented exactly as far as the line that opened it -- the same convention
    a numbered-list continuation's own nested fence follows one level deeper).
    A markdown skill/task-template document routinely shows a WHOLE nested
    example -- a task-file template, itself containing its own fenced command
    block -- inside an outer fence of the SAME marker and length; matching the
    first same-or-greater-length fence at ANY indentation (a naive walk) closes
    the OUTER block on the INNER example's fence instead, silently truncating
    everything after it. Falling back to the indent-agnostic match only when no
    same-indent close exists keeps ordinary (non-nested) fences working exactly
    as before.
    """
    pattern = re.compile(rf"^\s*{re.escape(fence_marker * fence_len)}+\s*$")
    exact_pattern = re.compile(rf"^{re.escape(indent)}{re.escape(fence_marker * fence_len)}+\s*$")
    loose_close: int | None = None
    for scan in range(body_start, len(lines)):
        if exact_pattern.match(lines[scan]) is not None:
            return scan
        if loose_close is None and pattern.match(lines[scan]) is not None:
            loose_close = scan
    return loose_close


def _extract_fenced_block(
    lines: list[str], open_line: int, fence_marker: str, fence_len: int, indent: str
) -> tuple[CodeFragment, int]:
    """Extract one fenced block starting at `open_line` (its opening-fence line,
    0-based). Returns the fragment and the 0-based index to resume scanning from.
    """
    body_start = open_line + 1
    close_index = _find_closing_fence(lines, body_start, fence_marker, fence_len, indent)
    body_end = close_index if close_index is not None else len(lines)
    block_text = "\n".join(lines[body_start:body_end])
    fragment = CodeFragment(
        text=block_text,
        line=body_start + 1,
        # `_line_is_exempt(lines, open_line)` checks both the opening-fence
        # line itself ("on the same line") and the line immediately before it
        # ("the line immediately before" -- for a fenced block, the line
        # before the OPENING fence, not before the first body line).
        exempted=_line_is_exempt(lines, open_line),
    )
    resume_at = (close_index + 1) if close_index is not None else len(lines)
    return fragment, resume_at


def extract_fragments(markdown_text: str) -> list[CodeFragment]:
    """Every fenced code block and inline code span in `markdown_text`, each
    tagged with its 1-based start line and whether the forbidden-example
    exemption applies -- a real fence/backtick walk, never a line regex over
    the whole document (a fence's content must not be re-scanned for inline
    backticks, and an inline span sharing a prose line must still be found).
    """
    lines = markdown_text.splitlines()
    fragments: list[CodeFragment] = []
    index = 0
    while index < len(lines):
        fence_match = _FENCE_RE.match(lines[index])
        if fence_match is not None:
            indent = fence_match.group(1)
            fence_marker = fence_match.group(2)[0]
            fence_len = len(fence_match.group(2))
            fragment, index = _extract_fenced_block(lines, index, fence_marker, fence_len, indent)
            fragments.append(fragment)
            continue
        for span_match in _INLINE_CODE_RE.finditer(lines[index]):
            fragments.append(
                CodeFragment(
                    text=span_match.group(1),
                    line=index + 1,
                    exempted=_line_is_exempt(lines, index),
                )
            )
        index += 1
    return fragments


# ---------------------------------------------------------------------------
# Classification + scan.
# ---------------------------------------------------------------------------


def classify_fragment(text: str, suite_invocation: ModuleType) -> list[str]:
    """Every whole-suite `test.ps1`/`affected-gate.ps1` invocation TAIL in one fragment.

    Tails come from `_suite_invocation.invocation_tails` and whole-suite-ness from its
    `runs_no_test`/`is_targeted` -- never a private regex here, so this gate and
    `guard-full-suite-runs.py` share one notion of "whole-suite": whatever the hook
    blocks, this gate flags when a document prescribes it. A tail exists only where the
    fragment EXECUTES the runner (its statement starts with the script, a PowerShell
    host or a call operator running it), so a `test.ps1:529` line citation or a prose
    line inside a fence that merely names the runner is no invocation.

    A VACUOUS tail (no argument after the script -- the entire fragment is just the
    bare word `test.ps1`) is never a hit. A prescription to run a whole
    suite must name enough to actually run -- at least a package, `-All`, or a tier
    switch; a prose reference to the script's own NAME, with nothing after it (e.g.
    "the `test.ps1` script", "never invoke `affected-gate.ps1`"), is not an invocation
    at all, and treating it as one is indistinguishable from flagging every mention of
    the tool's name in running text.
    """
    hits: list[str] = []
    for tail in suite_invocation.invocation_tails(text):
        if not tail.strip():
            continue
        if suite_invocation.runs_no_test(tail):
            continue
        if suite_invocation.is_targeted(tail):
            # A targeted form can still prescribe a SWEEP: a wide `-Tag` list, or a
            # `-Keyword` spanning packages. The hook blocks those commands, so a
            # document must not put them in an agent's hands either -- the
            # "{every task's tags, comma-separated}" template in a quality-gate
            # skill is exactly how one phase gate grew into a multi-hour sweep.
            if _sweep_tail_reason(tail, suite_invocation) is not None:
                hits.append(tail)
            continue
        hits.append(tail)
    return hits


def _sweep_tail_reason(tail: str, suite_invocation: ModuleType) -> str | None:
    """Why a targeted-looking tail prescribes a sweep, or None. Ceilings come from
    the hook module, so the gate cannot drift from what the hook enforces."""
    tags = suite_invocation.tag_names(tail)
    if len(tags) > suite_invocation.MAX_TAGS_PER_RUN:
        return f"-Tag names {len(tags)} tags"
    if (
        suite_invocation.has_keyword(tail)
        and len(suite_invocation.packages(tail)) > suite_invocation.MAX_PACKAGES_PER_KEYWORD_RUN
    ):
        return "-Keyword across several packages"
    return None


def scan_file(path: Path, suite_invocation: ModuleType) -> ScanResult:
    text = path.read_text(encoding="utf-8")
    hits: list[Hit] = []
    exempted_count = 0
    for fragment in extract_fragments(text):
        tails = classify_fragment(fragment.text, suite_invocation)
        if not tails:
            continue
        if fragment.exempted:
            exempted_count += len(tails)
            continue
        for tail in tails:
            hits.append(Hit(path=path, line=fragment.line, text=tail))
    return ScanResult(hits=tuple(hits), exempted_count=exempted_count)


def discover_documents(datrix_root: Path) -> list[Path]:
    found: list[Path] = []
    for pattern in SCAN_GLOBS:
        found.extend(sorted(datrix_root.glob(pattern)))
    # De-duplicate while preserving order (CLAUDE.md matches only its own glob;
    # skills/**/*.md and skills/_shared/*.md never overlap another pattern).
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in found:
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


def run_scan(datrix_root: Path, suite_invocation: ModuleType) -> int:
    documents = discover_documents(datrix_root)
    print(f"Scanning {len(documents)} instruction document(s) for a prescribed whole-suite run")
    all_hits: list[Hit] = []
    total_exempted = 0
    for path in documents:
        result = scan_file(path, suite_invocation)
        all_hits.extend(result.hits)
        total_exempted += result.exempted_count
    if not all_hits:
        print(
            f"\nINSTRUCTION-SURFACE GATE PASSED: zero un-exempted whole-suite test.ps1/"
            f"affected-gate.ps1 forms ({total_exempted} exempted occurrence(s))."
        )
        return 0
    print(
        f"\nINSTRUCTION-SURFACE GATE FAILED: {len(all_hits)} whole-suite form(s) prescribed "
        f"outside a <!-- forbidden-example --> context ({total_exempted} exempted occurrence(s)):"
    )
    for hit in sorted(all_hits, key=lambda h: (str(h.path), h.line)):
        print(f"  {hit.render(datrix_root)}")
    return 1


# ---------------------------------------------------------------------------
# Self-test: plant/observe non-vacuity proof (runs before every real scan).
# ---------------------------------------------------------------------------

_PLANT_BARE = 'powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-common\n'
_PLANT_SPECIFIC = (
    'powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-common '
    '-Specific "tests/unit/test_a.py"\n'
)
_PLANT_AFFECTED_GATE = (
    'powershell -File "d:/datrix/datrix/scripts/test/affected-gate.ps1" -Projects datrix-common\n'
)
_PLANT_TAG = (
    'powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-codegen-python '
    "datrix-codegen-typescript -Tag gateway\n"
)
_PLANT_LIST_TAGS = 'powershell -File "d:/datrix/datrix/scripts/test/test.ps1" -All -ListTags\n'
_PLANT_WIDE_TAG = (
    'powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-codegen-python '
    "-Tag pubsub,outbox,storage,jobs,resilience\n"
)
_PLANT_CROSS_PACKAGE_KEYWORD = (
    'powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-codegen-common '
    'datrix-codegen-typescript -Keyword "decorator"\n'
)


def _write_fixture(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def _check_bare_form(root: Path, suite_invocation: ModuleType) -> str | None:
    doc = _write_fixture(root, "bare.md", f"# Example\n\n```\n{_PLANT_BARE}```\n")
    result = scan_file(doc, suite_invocation)
    if len(result.hits) != 1:
        return f"self-test: bare test.ps1 form expected 1 hit, got {len(result.hits)}"
    return None


def _check_specific_form(root: Path, suite_invocation: ModuleType) -> str | None:
    doc = _write_fixture(root, "specific.md", f"# Example\n\n```\n{_PLANT_SPECIFIC}```\n")
    result = scan_file(doc, suite_invocation)
    if result.hits:
        return f"self-test: -Specific form expected 0 hits, got {len(result.hits)}"
    return None


def _check_exempted_form(root: Path, suite_invocation: ModuleType) -> str | None:
    doc = _write_fixture(
        root,
        "exempt.md",
        f"# Example\n\n{FORBIDDEN_EXAMPLE_MARKER}\n```\n{_PLANT_BARE}```\n",
    )
    result = scan_file(doc, suite_invocation)
    if result.hits or result.exempted_count != 1:
        return (
            f"self-test: exempted bare form expected 0 hits/1 exempted, got "
            f"{len(result.hits)} hits/{result.exempted_count} exempted"
        )
    return None


def _check_affected_gate_form(root: Path, suite_invocation: ModuleType) -> str | None:
    doc = _write_fixture(root, "gate.md", f"# Example\n\n```\n{_PLANT_AFFECTED_GATE}```\n")
    result = scan_file(doc, suite_invocation)
    if len(result.hits) != 1:
        return (
            f"self-test: affected-gate.ps1 -Projects form is a whole-suite sweep and "
            f"expected 1 hit, got {len(result.hits)}"
        )
    return None


def _check_tag_and_list_tags_forms(root: Path, suite_invocation: ModuleType) -> str | None:
    doc = _write_fixture(
        root, "tags.md", f"# Example\n\n```\n{_PLANT_TAG}```\n\n```\n{_PLANT_LIST_TAGS}```\n"
    )
    result = scan_file(doc, suite_invocation)
    if result.hits:
        return (
            f"self-test: a -Tag run and a -ListTags listing are targeted / run nothing and "
            f"expected 0 hits, got {len(result.hits)}"
        )
    return None


def _check_sweep_forms(root: Path, suite_invocation: ModuleType) -> str | None:
    """A wide `-Tag` list and a cross-package `-Keyword` are sweeps wearing a
    targeting flag: the hook blocks the commands, so a document must not
    prescribe them either."""
    doc = _write_fixture(
        root,
        "sweeps.md",
        f"# Example\n\n```\n{_PLANT_WIDE_TAG}```\n\n```\n{_PLANT_CROSS_PACKAGE_KEYWORD}```\n",
    )
    result = scan_file(doc, suite_invocation)
    if len(result.hits) != 2:
        return (
            f"self-test: a 5-tag run and a cross-package -Keyword run are sweeps and expected "
            f"2 hits, got {len(result.hits)}"
        )
    return None


def _check_inline_span_form(root: Path, suite_invocation: ModuleType) -> str | None:
    doc = _write_fixture(
        root,
        "inline.md",
        'Run `powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-common` '
        "before continuing.\n",
    )
    result = scan_file(doc, suite_invocation)
    if len(result.hits) != 1:
        return (
            f"self-test: inline code span sharing a prose line expected 1 hit, got "
            f"{len(result.hits)}"
        )
    return None


def _check_bare_word_form(root: Path, suite_invocation: ModuleType) -> str | None:
    doc = _write_fixture(
        root,
        "bare-word.md",
        "Always use `test.ps1` / `test-single.ps1`, never call pytest directly.\n",
    )
    result = scan_file(doc, suite_invocation)
    if result.hits:
        return (
            f"self-test: a bare `test.ps1` mention with no argument at all "
            f"(naming the tool, not prescribing a run) expected 0 hits, got {len(result.hits)}"
        )
    return None


def _check_line_citation_form(root: Path, suite_invocation: ModuleType) -> str | None:
    doc = _write_fixture(
        root,
        "citation.md",
        "`test.ps1` loops projects in the foreground "
        "(`datrix/scripts/test/test.ps1:529,547-548`), so a sweep pays the full cost.\n",
    )
    result = scan_file(doc, suite_invocation)
    if result.hits:
        return (
            f"self-test: a `test.ps1:529`-shaped line citation names the runner and "
            f"executes nothing, expected 0 hits, got {len(result.hits)}"
        )
    return None


def _check_named_not_run_form(root: Path, suite_invocation: ModuleType) -> str | None:
    """A runner command held as data by another program -- a `python -c` source string,
    an `echo` -- or inside a `#` comment runs no suite; the hook allows it, so the gate
    must not flag it."""
    doc = _write_fixture(
        root,
        "named-not-run.md",
        f"# Example\n\n```\npython -c \"print('{_PLANT_BARE.strip()}')\"\n"
        f"echo '{_PLANT_BARE.strip()}'\n"
        "# A bare `test.ps1 {package-name}` is a whole suite.\n```\n",
    )
    result = scan_file(doc, suite_invocation)
    if result.hits:
        return (
            f"self-test: a whole-suite command held as another program's argument "
            f"executes nothing, expected 0 hits, got {len(result.hits)}"
        )
    return None


_SELF_TEST_CHECKS = (
    _check_bare_form,
    _check_specific_form,
    _check_exempted_form,
    _check_affected_gate_form,
    _check_tag_and_list_tags_forms,
    _check_sweep_forms,
    _check_inline_span_form,
    _check_bare_word_form,
    _check_line_citation_form,
    _check_named_not_run_form,
)


def self_test(suite_invocation: ModuleType) -> list[str]:
    """Plant ten fixtures and prove the gate finds exactly what each demands."""
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="instruction-surface-selftest-") as tmp:
        root = Path(tmp)
        for check in _SELF_TEST_CHECKS:
            failure = check(root, suite_invocation)
            if failure is not None:
                failures.append(failure)
    return failures


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/repo-hygiene/instruction-surface-gate.ps1``: one per wrapper parameter,
    spelled exactly."""
    return self_test_gate_parser(WRAPPER, __doc__.splitlines()[0])


def _run(args: argparse.Namespace) -> int:
    """Run the gate; returns 0 (no hit / self-test passed), 1 (a hit, a failed self-test, or a failed
    wrapper seam check), 2 (the hook's suite-invocation module could not be loaded)."""
    try:
        suite_invocation = load_suite_invocation()
    except HookModuleError as exc:
        print(f"INSTRUCTION-SURFACE GATE CANNOT RUN: {exc}", file=sys.stderr)
        return 2

    failures = self_test(suite_invocation)
    if failures:
        print("INSTRUCTION-SURFACE GATE CANNOT BE TRUSTED: non-vacuity self-test failed.")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("Self-test passed: the scanner still detects a planted whole-suite form.")

    if args.self_test:
        return wrappers.run_self_test(
            [], wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=wrappers.REPO_HYGIENE_GATES_DIR
        )
    return run_scan(DATRIX_ROOT, suite_invocation)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
