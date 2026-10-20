"""Scan Python sources and emit a grouped Markdown report of symbols plus duplicate top-level names.

``scripts/metrics/code-analyzer.ps1`` (and its ``.sh`` twin) runs this module. It resolves scan packages
with the same ``datrix-*`` rule as metrics ``-All`` (not the broader ``datrix*`` glob used by
``find_constants``). Report path defaults to ``./code-structure-report.md`` under the process current
working directory.

Exit codes: 0 = report written (or nothing to scan); 1 = no project given, no valid project, a project that
does not exist, or a failed self-test check. The advisory model request never changes the exit code.

Usage:
    python -m datrix_scripts.metrics.code_analyzer datrix-common   (PYTHONPATH=scripts/common/lib)
    python -m datrix_scripts.metrics.code_analyzer --all --tests
    python -m datrix_scripts.metrics.code_analyzer --all --src --tests --output my-report.md
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import io
import logging
import re
import sys
import tempfile
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from datrix_scripts.framework_repos import workspace_package_dirs
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, write_files
from datrix_scripts.local_llm import (
    AdvisoryText,
    ChatRequest,
    LocalLlmSettings,
    add_wrapper_llm_arguments,
    advisory_reply,
    wrapper_llm_settings,
)
from datrix_scripts.metrics.find_constants import iter_python_files
from datrix_scripts.metrics.projects import (
    SHOWCASE,
    add_project_arguments,
    plant_workspace,
    requested_projects,
)
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import METRICS_SCRIPTS_DIR, module_main, run_self_test

LOGGER: Final = logging.getLogger(__name__)

MODULE: Final = "datrix_scripts.metrics.code_analyzer"
WRAPPER: Final = "code-analyzer"

EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
BANNER: Final = "Python code structure analyzer (AST)..."
USAGE_LINES: Final = (
    "Usage:",
    "  .\\code-analyzer.ps1 <project> [project2 ...] [-Src] [-Tests] [-Output path] [-Dbg]",
    "  .\\code-analyzer.ps1 -All [-Src] [-Tests] [-Output path] [-Dbg]",
    "",
    "Default: src/ only. -Tests alone: tests/ only. -Src and -Tests: both trees.",
    "Report defaults to .\\code-structure-report.md (cwd). Use Get-Help for full help.",
)
NO_VALID_PROJECTS: Final = f"ERROR: No valid projects ({SHOWCASE} meta folder is excluded)."

DUPLICATE_TRIAGE_PURPOSE: Final = "Duplicate-name triage"
DEFAULT_LLM_LIMIT: Final = 20
DEFAULT_LLM_TIMEOUT_SECONDS: Final = 180
LLM_NUM_PREDICT: Final = 4096
LLM_TEMPERATURE: Final = 0.1
# The triage section's source when no model was asked.
NOT_ASKED_SOURCE: Final = "no model asked (no duplicate group)"
# A name the triage answer puts in backticks (only names; a backticked path holds a '/' or '.').
_BACKTICKED_NAME_RE: Final = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")

CONSTANT_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9_]*$")
DEFAULT_REPORT_NAME = "code-structure-report.md"


@dataclass(frozen=True)
class MethodEntry:
    """One callable under a class (possibly nested)."""

    name: str
    lineno: int
    role: str


@dataclass(frozen=True)
class ClassEntry:
    """A module-level class and its methods."""

    name: str
    lineno: int
    methods: tuple[MethodEntry, ...]


@dataclass(frozen=True)
class FuncEntry:
    """Module-level function or nested qualified name."""

    name: str
    lineno: int
    is_async: bool


@dataclass(frozen=True)
class ConstEntry:
    name: str
    lineno: int


@dataclass(frozen=True)
class AliasEntry:
    name: str
    lineno: int


@dataclass(frozen=True)
class FileSymbols:
    """Parsed symbols for one ``.py`` file."""

    rel_posix: str
    classes: tuple[ClassEntry, ...]
    module_functions: tuple[FuncEntry, ...]
    constants: tuple[ConstEntry, ...]
    type_aliases: tuple[AliasEntry, ...]


@dataclass
class PublicNameRef:
    """One module-level class or function site for duplicate detection."""

    name: str
    project: str
    rel_posix: str
    lineno: int
    kind: str


def _decorator_role(deco: ast.expr) -> str | None:
    if isinstance(deco, ast.Name):
        if deco.id in ("staticmethod", "classmethod", "property"):
            return deco.id
        return None
    if isinstance(deco, ast.Attribute) and isinstance(deco.value, ast.Name):
        if deco.attr in ("staticmethod", "classmethod", "property"):
            return deco.attr
    return None


def _method_role(decorators: list[ast.expr]) -> str:
    for d in decorators:
        role = _decorator_role(d)
        if role is not None:
            return role
    return "method"


def _collect_nested_functions(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    prefix: str,
) -> list[FuncEntry]:
    nested: list[FuncEntry] = []
    for child in node.body:
        if isinstance(child, ast.FunctionDef):
            qual = f"{prefix}.{child.name}"
            nested.append(FuncEntry(qual, child.lineno, False))
            nested.extend(_collect_nested_functions(child, qual))
        elif isinstance(child, ast.AsyncFunctionDef):
            qual = f"{prefix}.{child.name}"
            nested.append(FuncEntry(qual, child.lineno, True))
            nested.extend(_collect_nested_functions(child, qual))
    return nested


def _collect_nested_methods(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    prefix: str,
) -> list[MethodEntry]:
    out: list[MethodEntry] = []
    for child in node.body:
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            qual = f"{prefix}.{child.name}"
            out.append(MethodEntry(qual, child.lineno, "method"))
            out.extend(_collect_nested_methods(child, qual))
    return out


def _class_methods(class_node: ast.ClassDef) -> tuple[MethodEntry, ...]:
    methods: list[MethodEntry] = []
    for child in class_node.body:
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            role = _method_role(child.decorator_list)
            methods.append(MethodEntry(child.name, child.lineno, role))
            methods.extend(_collect_nested_methods(child, child.name))
    methods.sort(key=lambda m: m.name.lower())
    return tuple(methods)


def _is_constant_assign_targets(targets: list[ast.expr]) -> bool:
    if not targets:
        return False
    for t in targets:
        if not isinstance(t, ast.Name):
            return False
        if not CONSTANT_NAME_RE.match(t.id):
            return False
    return True


def _parse_module(
    tree: ast.Module,
    rel_posix: str,
    public_refs: list[PublicNameRef],
    project: str,
) -> FileSymbols:
    classes: list[ClassEntry] = []
    module_functions: list[FuncEntry] = []
    constants: list[ConstEntry] = []
    type_aliases: list[AliasEntry] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(
                ClassEntry(
                    name=node.name,
                    lineno=node.lineno,
                    methods=_class_methods(node),
                )
            )
            if not node.name.startswith("_"):
                public_refs.append(
                    PublicNameRef(
                        name=node.name,
                        project=project,
                        rel_posix=rel_posix,
                        lineno=node.lineno,
                        kind="class",
                    )
                )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_async = isinstance(node, ast.AsyncFunctionDef)
            module_functions.append(
                FuncEntry(node.name, node.lineno, is_async),
            )
            module_functions.extend(_collect_nested_functions(node, node.name))
            if not node.name.startswith("_"):
                public_refs.append(
                    PublicNameRef(
                        name=node.name,
                        project=project,
                        rel_posix=rel_posix,
                        lineno=node.lineno,
                        kind="function",
                    )
                )
        elif isinstance(node, ast.Assign):
            if _is_constant_assign_targets(node.targets):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        constants.append(ConstEntry(t.id, node.lineno))
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and CONSTANT_NAME_RE.match(node.target.id):
                constants.append(ConstEntry(node.target.id, node.lineno))
        elif hasattr(ast, "TypeAlias") and isinstance(node, ast.TypeAlias):
            if isinstance(node.name, ast.Name):
                type_aliases.append(AliasEntry(node.name.id, node.lineno))

    classes.sort(key=lambda c: c.name.lower())
    module_functions.sort(key=lambda f: f.name.lower())
    constants.sort(key=lambda c: c.name.lower())
    type_aliases.sort(key=lambda a: a.name.lower())

    return FileSymbols(
        rel_posix=rel_posix,
        classes=tuple(classes),
        module_functions=tuple(module_functions),
        constants=tuple(constants),
        type_aliases=tuple(type_aliases),
    )


def parse_python_file(
    scan_root: Path,
    py_path: Path,
    project: str,
    public_refs: list[PublicNameRef],
) -> FileSymbols | None:
    rel = py_path.resolve().relative_to(scan_root.resolve())
    rel_posix = rel.as_posix()
    try:
        text = py_path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        print(f"Warning: could not read {py_path}: {exc}", file=sys.stderr)
        return None
    try:
        tree = ast.parse(text, filename=str(py_path))
    except SyntaxError as exc:
        print(f"Warning: syntax error in {py_path}: {exc}", file=sys.stderr)
        return None
    if not isinstance(tree, ast.Module):
        return None
    return _parse_module(tree, rel_posix, public_refs, project)


def resolve_scan_roots(
    datrix_root: Path,
    project_names: list[str],
    scan_all: bool,
    *,
    include_src: bool,
    include_tests: bool,
) -> list[tuple[str, str, Path]]:
    """Return ``(project_name, root_label, path)`` for each scan root.

    ``root_label`` is ``src`` or ``tests``. ``scan_all`` uses only directories named
    ``datrix-*`` (metrics glob), excluding the bare ``datrix`` package folder.
    """
    pairs: list[tuple[str, str, Path]] = []
    if scan_all:
        for d in workspace_package_dirs(datrix_root):
            if include_src:
                src_dir = d / "src"
                if src_dir.is_dir():
                    pairs.append((d.name, "src", src_dir))
                else:
                    print(
                        f"Warning: {d.name} has no src/ directory; skipped for src scan.",
                        file=sys.stderr,
                    )
            if include_tests:
                tests_dir = d / "tests"
                if tests_dir.is_dir():
                    pairs.append((d.name, "tests", tests_dir))
                else:
                    print(
                        f"Warning: {d.name} has no tests/ directory; skipped for tests scan.",
                        file=sys.stderr,
                    )
        return pairs

    available = [x.name for x in workspace_package_dirs(datrix_root)]
    for clean in project_names:
        name = clean.rstrip("/\\")
        project_dir = datrix_root / name
        if not project_dir.is_dir():
            raise FileNotFoundError(
                f"Project '{name}' not found under {datrix_root}. Available: {available}"
            )
        if include_src:
            src_dir = project_dir / "src"
            if src_dir.is_dir():
                pairs.append((name, "src", src_dir))
            else:
                print(
                    f"Warning: {name} has no src/ directory; skipped for src scan.",
                    file=sys.stderr,
                )
        if include_tests:
            tests_dir = project_dir / "tests"
            if tests_dir.is_dir():
                pairs.append((name, "tests", tests_dir))
            else:
                print(
                    f"Warning: {name} has no tests/ directory; skipped for tests scan.",
                    file=sys.stderr,
                )
    return pairs


def resolve_output_path(output: Path | None) -> Path:
    """Resolve report path against ``Path.cwd()`` unless ``output`` is absolute."""
    cwd = Path.cwd()
    if output is None:
        return (cwd / DEFAULT_REPORT_NAME).resolve()
    if output.is_absolute():
        return output.resolve()
    return (cwd / output).resolve()


def duplicate_groups(refs: list[PublicNameRef]) -> list[tuple[str, list[PublicNameRef]]]:
    """Each name defined under at least two distinct file paths, with its sites, sorted by name."""
    by_name: dict[str, list[PublicNameRef]] = defaultdict(list)
    for r in refs:
        by_name[r.name].append(r)
    return [
        (name, sorted(by_name[name], key=lambda e: (e.project, e.rel_posix, e.lineno)))
        for name in sorted(by_name.keys(), key=str.lower)
        if len({(e.project, e.rel_posix) for e in by_name[name]}) >= 2
    ]


def build_duplicate_section(groups: list[tuple[str, list[PublicNameRef]]]) -> list[str]:
    """Markdown lines listing every duplicate group's sites."""
    lines: list[str] = []
    for name, entries in groups:
        lines.append(f"### `{name}`")
        lines.append("")
        for e in entries:
            lines.append(f"- **{e.kind}** `{e.project}/{e.rel_posix}` line {e.lineno}")
        lines.append("")
    return lines


def duplicate_triage_request(groups: list[tuple[str, list[PublicNameRef]]], limit: int) -> ChatRequest:
    """One request ranking which same-named definitions are one concept with two homes."""
    parts = [
        "These module-level classes and functions share a name across files of the Datrix framework.",
        "Rank the groups by how likely the definitions are ONE concept with two homes (one should be",
        "hoisted to a shared module and the copies deleted), most likely first. Mark a group",
        "'coincidental' when the name is shared but the concepts differ (a per-target implementation",
        "of a shared protocol, a test helper). Advisory only: base each call on the names, kinds and",
        "paths shown, and say what to read to confirm it.",
        "",
        "Return markdown: a table with columns rank, name, verdict (one concept / coincidental /",
        "unclear), rationale, files to compare.",
        "",
        "Groups:",
    ]
    for name, entries in groups[: max(0, limit)]:
        parts.append("")
        parts.append(f"### {name}")
        parts.extend(f"- {e.kind} {e.project}/{e.rel_posix}:{e.lineno}" for e in entries)
    if not groups:
        parts.append("No duplicate names.")
    return ChatRequest(
        system=("You triage duplicate-name findings of a static code report. You do not edit code; you "
                "produce advisory markdown only."),
        user="\n".join(parts),
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_NUM_PREDICT,
    )


def invented_names(text: str, groups: list[tuple[str, list[PublicNameRef]]]) -> list[str]:
    """Backticked names in the answer that are no duplicate group: the model made them up."""
    known = {name for name, _ in groups}
    return sorted({name for name in _BACKTICKED_NAME_RE.findall(text) if name not in known})


def duplicate_triage(
    groups: list[tuple[str, list[PublicNameRef]]], limit: int, settings: LocalLlmSettings
) -> AdvisoryText:
    """The advisory triage section's body; a missing answer is reported in it, never as a failure.

    With no duplicate group nothing is asked (a model asked to rank nothing invents groups), and a
    name the answer ranks that is not a duplicate group is called out under it.
    """
    if not groups:
        return AdvisoryText("No duplicate names: nothing to triage.", NOT_ASKED_SOURCE)
    reply = advisory_reply(settings, duplicate_triage_request(groups, limit), DUPLICATE_TRIAGE_PURPOSE)
    invented = invented_names(reply.text, groups)
    if not invented:
        return reply
    note = f"\n\n**Not in the duplicate list (the model made these up):** {', '.join(invented)}"
    return AdvisoryText(reply.text + note, reply.source)


def write_report(
    out_path: Path,
    *,
    sections: list[tuple[str, str, list[FileSymbols]]],
    duplicate_lines: list[str],
    datrix_root: Path,
    projects_scanned: list[str],
    scan_scope_label: str,
    files_parsed: int,
    duplicate_name_count: int,
    triage: AdvisoryText | None,
) -> None:
    local_ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    cwd = Path.cwd().resolve()
    lines: list[str] = [
        "# Python code structure report",
        "",
        "## Summary",
        "",
        f"- **Generated (local):** {local_ts}",
        f"- **Working directory:** `{cwd}`",
        f"- **Datrix root:** `{datrix_root}`",
        f"- **Projects (distinct):** {', '.join(projects_scanned)}",
        f"- **Scan scope:** {scan_scope_label}",
        f"- **Python files parsed:** {files_parsed}",
        f"- **Duplicate top-level names (cross-file):** {duplicate_name_count}",
        "",
        "---",
        "",
    ]

    for project, root_label, files in sections:
        if not files:
            continue
        lines.append(f"## {project} ({root_label})")
        lines.append("")
        for fs in files:
            lines.append(f"### `{fs.rel_posix}`")
            lines.append("")
            if fs.classes:
                lines.append("**Classes**")
                lines.append("")
                for c in fs.classes:
                    lines.append(f"- **{c.name}** (line {c.lineno})")
                    for m in c.methods:
                        lines.append(f"  - `{m.name}` ({m.role}) L{m.lineno}")
                lines.append("")
            if fs.module_functions:
                lines.append("**Module functions**")
                lines.append("")
                for f in fs.module_functions:
                    async_prefix = "async " if f.is_async else ""
                    lines.append(f"- `{async_prefix}{f.name}` L{f.lineno}")
                lines.append("")
            if fs.constants:
                lines.append("**Constants**")
                lines.append("")
                for c in fs.constants:
                    lines.append(f"- `{c.name}` L{c.lineno}")
                lines.append("")
            if fs.type_aliases:
                lines.append("**Type aliases**")
                lines.append("")
                for a in fs.type_aliases:
                    lines.append(f"- `{a.name}` L{a.lineno}")
                lines.append("")

    lines.append("## Duplicate top-level class/function names")
    lines.append("")
    lines.append(
        "Names that appear as a module-level **class** or **function** in at least "
        "**two different files** (leading `_` excluded). Same name in one file only is omitted.",
    )
    lines.append("")
    if duplicate_lines:
        lines.extend(duplicate_lines)
    else:
        lines.append("*No cross-file duplicates found in the scanned set.*")
        lines.append("")
    if triage is not None:
        lines += [f"## {DUPLICATE_TRIAGE_PURPOSE} (advisory, local model)", "",
                  f"*Source: {triage.source}. Advisory only: it never changes the exit code.*", "",
                  triage.text, ""]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _planted_refs() -> list[PublicNameRef]:
    return [
        PublicNameRef("resolve_key", "datrix-alpha", "a/keys.py", 3, "function"),
        PublicNameRef("resolve_key", "datrix-beta", "b/keys.py", 9, "function"),
        PublicNameRef("Loader", "datrix-alpha", "a/load.py", 1, "class"),
        PublicNameRef("Loader", "datrix-alpha", "a/load.py", 40, "class"),
    ]


def _check_groups_need_two_distinct_files() -> None:
    groups = duplicate_groups(_planted_refs())
    assert [name for name, _ in groups] == ["resolve_key"], "a name defined twice in ONE file is no duplicate"
    assert build_duplicate_section(groups)[0] == "### `resolve_key`"


def _check_no_group_asks_no_model() -> None:
    unreachable = LocalLlmSettings(machines=("127.0.0.1",), ollama_port=1, reachable_timeout_ms=200)
    triage = duplicate_triage([], DEFAULT_LLM_LIMIT, unreachable)
    assert (triage.source, triage.text) == (NOT_ASKED_SOURCE, "No duplicate names: nothing to triage."), triage


def _check_the_request_carries_at_most_the_limit() -> None:
    groups = duplicate_groups(_planted_refs() + [PublicNameRef("Other", "p", "x.py", 1, "class"),
                                                PublicNameRef("Other", "q", "y.py", 1, "class")])
    user = duplicate_triage_request(groups, 1).user
    assert "### Other" in user and "### resolve_key" not in user, user


def _check_invented_names_are_called_out() -> None:
    groups = duplicate_groups(_planted_refs())
    answer = "| 1 | `resolve_key` | one concept |\n| 2 | `Matrix` | one concept | `a/keys.py` |"
    assert invented_names(answer, groups) == ["Matrix"], "a path in backticks is not a name"


def build_parser() -> argparse.ArgumentParser:
    """The options of ``metrics/code-analyzer.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description=(
            "Build a Markdown report of Python classes, functions, constants, and type "
            "aliases under each package src/ or tests/ tree. Default output path is "
            f"{DEFAULT_REPORT_NAME} under the current working directory; relative --output "
            "is resolved against the cwd."
        ),
        allow_abbrev=False,
    )
    add_project_arguments(parser)
    parser.add_argument(
        "--src",
        action="store_true",
        help="Include each package's src/ tree (default when --tests is not used alone).",
    )
    parser.add_argument(
        "--tests",
        action="store_true",
        help="Include each package's tests/ tree (use alone for tests-only scan).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            f"Report file (default: ./{DEFAULT_REPORT_NAME} under cwd). "
            "Relative paths are resolved against the current working directory."
        ),
    )
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Log the scan roots at DEBUG level.")
    parser.add_argument(
        "--llm-review",
        action="store_true",
        help=(f"Add an advisory '{DUPLICATE_TRIAGE_PURPOSE}' section: a local model ranks which duplicate "
              "names are one concept with two homes. Never changes the exit code."),
    )
    parser.add_argument(
        "--llm-limit",
        type=int,
        default=DEFAULT_LLM_LIMIT,
        metavar="N",
        help=f"Maximum duplicate groups sent to the local model (default: {DEFAULT_LLM_LIMIT}).",
    )
    add_wrapper_llm_arguments(parser, timeout_seconds=DEFAULT_LLM_TIMEOUT_SECONDS)
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the duplicate-triage checks (planted sites, no model) and the wrapper seam checks.")
    return parser


def _scan_scope(src: bool, tests: bool) -> tuple[bool, bool, str]:
    """(include src, include tests, label) for the ``--src`` / ``--tests`` switches; neither means src only."""
    if tests and not src:
        return False, True, "tests only"
    if src and tests:
        return True, True, "src and tests"
    return True, False, "src only"


def _collect_sections(
    scan_triples: list[tuple[str, str, Path]], public_refs: list[PublicNameRef]
) -> tuple[list[tuple[str, str, list[FileSymbols]]], int]:
    """The parsed files grouped by consecutive (project, root label), and how many files were parsed.

    Every module-level public class and function site is appended to *public_refs*.
    """
    sections: list[tuple[str, str, list[FileSymbols]]] = []
    files_parsed = 0
    current_key: tuple[str, str] | None = None
    current_files: list[FileSymbols] = []

    for project, root_label, root in scan_triples:
        key = (project, root_label)
        if current_key != key:
            if current_key is not None:
                sections.append((current_key[0], current_key[1], current_files))
            current_key = key
            current_files = []
        for py_file in sorted(iter_python_files(root), key=lambda p: str(p).lower()):
            fs = parse_python_file(root, py_file, project, public_refs)
            if fs is not None:
                current_files.append(fs)
                files_parsed += 1
    if current_key is not None:
        sections.append((current_key[0], current_key[1], current_files))
    return sections, files_parsed


def _scan(args: argparse.Namespace, projects: list[str], datrix_root: Path) -> int:
    """Scan *projects* (every package under ``--all``) of *datrix_root* and write the report."""
    include_src, include_tests, scan_scope_label = _scan_scope(args.src, args.tests)
    try:
        scan_triples = resolve_scan_roots(
            datrix_root,
            projects,
            args.all,
            include_src=include_src,
            include_tests=include_tests,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_FAILED

    if not scan_triples:
        print("No scan directories found (missing src/ and/or tests/ per flags).")
        return EXIT_OK

    for proj, label, root in scan_triples:
        LOGGER.debug("scan %s (%s) -> %s", proj, label, root)

    public_refs: list[PublicNameRef] = []
    sections, files_parsed = _collect_sections(scan_triples, public_refs)

    groups = duplicate_groups(public_refs)
    dup_count = len(groups)
    triage = duplicate_triage(groups, args.llm_limit, wrapper_llm_settings(args)) if args.llm_review else None
    out_path = resolve_output_path(args.output)
    projects_distinct = sorted({p for p, _, _ in scan_triples})

    write_report(
        out_path,
        sections=sections,
        duplicate_lines=build_duplicate_section(groups),
        datrix_root=datrix_root,
        projects_scanned=projects_distinct,
        scan_scope_label=scan_scope_label,
        files_parsed=files_parsed,
        duplicate_name_count=dup_count,
        triage=triage,
    )

    print(
        f"Wrote report: {out_path} ({files_parsed} file(s) parsed, "
        f"{dup_count} duplicate top-level name(s) across files).",
        flush=True,
    )
    return EXIT_OK


def _printed_by_main(argv: Sequence[str]) -> tuple[int, list[str]]:
    """The exit code of ``main(argv)`` and the lines it printed to stdout."""
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        code = main(argv)
    return code, printed.getvalue().splitlines()


def _check_showcase_alone_is_refused() -> None:
    code, lines = _printed_by_main([SHOWCASE])
    assert code == EXIT_FAILED, code
    assert lines == [NO_VALID_PROJECTS], lines


def _check_nothing_given_prints_the_wrapper_usage() -> None:
    code, lines = _printed_by_main([])
    assert code == EXIT_FAILED, code
    assert lines == list(USAGE_LINES), lines


def _check_planted_duplicate_name_reaches_the_report() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = plant_workspace(Path(raw))
        write_files(root, {"datrix-a/src/one.py": "def f() -> int:\n    return 1\n",
                           "datrix-a/src/two.py": "def f() -> int:\n    return 2\n"})
        report = root / "report.md"
        args = build_parser().parse_args(["datrix-a", f"--output={report}"])
        with contextlib.redirect_stdout(io.StringIO()):
            code = _scan(args, ["datrix-a"], root)
        text = report.read_text(encoding="utf-8")
    assert code == EXIT_OK, code
    section = text.split("## Duplicate top-level class/function names", 1)[1]
    assert "### `f`" in section, section
    for path in ("one.py", "two.py"):
        assert f"**function** `datrix-a/{path}` line 1" in section, section


_SELF_TEST_CHECKS: Final = (
    _check_groups_need_two_distinct_files,
    _check_no_group_asks_no_model,
    _check_the_request_carries_at_most_the_limit,
    _check_invented_names_are_called_out,
    _check_showcase_alone_is_refused,
    _check_nothing_given_prints_the_wrapper_usage,
    _check_planted_duplicate_name_reaches_the_report,
)


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test(
            _SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=METRICS_SCRIPTS_DIR
        )
    given = [*args.positional_projects, *args.projects]
    if not given and not args.all:
        for line in USAGE_LINES:
            print(line)
        return EXIT_FAILED
    projects = [] if args.all else requested_projects(args)
    if not args.all and not projects:
        print(NO_VALID_PROJECTS)
        return EXIT_FAILED
    print(BANNER)
    print()
    return _scan(args, projects, WORKSPACE_DIR)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
