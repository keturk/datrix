#!/usr/bin/env python3
"""Shared parsing for Datrix task files and phase-level dependencies.md documents.

Imported by the sibling scripts phase_status.py, plan_waves.py and
validate_dependencies.py. Task files are DATA: this module only reads them.

Parsing rules (derived from the real task corpus and from
d:/datrix/datrix/claude-config/.claude/agent-templates/dependencies-format.md):

- The task ID comes from the FILENAME: ``task-{NN}-{TT}[-slug].md`` -> ``task-NN-TT``.
- The first markdown heading carries the status prefix (``# COMPLETED: Task ...``);
  a plain ``# Task ...`` heading is PENDING; any other ALL-CAPS prefix is kept verbatim.
- Header metadata fields (``**Package:**``, ``**Category:**``, ``**Depends on:**``,
  ``**Design reference:**``, ``**Design acceptance property:**``) may span multiple
  lines; a field's text ends at the next known field label, the next markdown
  heading, or EOF. Only the FIRST occurrence of each field is used (task bodies
  repeat ``**Package:**`` inside ``## Targeted Tests``). Fenced code blocks are
  never scanned for labels.
- ``Depends on`` is free text (``31-05``, ``task-31-05``, backticked, with
  parenthetical prose, or ``None``); task IDs are extracted by token pattern and
  normalized to ``task-NN-TT``. Text after an inline bold label such as
  ``**Blocks:**`` is not scanned (those IDs are not dependencies).
- File lists are extracted from ``## Files to ...`` sections: backticked
  path-like tokens on ``###`` sub-headings and list-item lines (never from
  fenced code blocks). ``## Files to Review Before Starting`` feeds
  ``files_to_review``; every other ``## Files to ...`` variant (Create, Modify,
  Create / Modify, Migrate, Delete, Update, ...) feeds ``files_to_create_modify``.
- ``targeted_tests`` are the command lines inside fenced code blocks of the
  ``## Targeted Tests`` section (ready-to-run invocations).
"""

from __future__ import annotations

import importlib.util
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_LIBRARY_DIR = Path(__file__).resolve().parent.parent

PENDING_STATUS = "PENDING"
COMPLETED_STATUS = "COMPLETED"

DEPENDENCIES_FORMAT_JSON = "json"
DEPENDENCIES_FORMAT_LEGACY = "legacy"

_LINE_ROLE_TEXT = "text"
_LINE_ROLE_CODE = "code"
_LINE_ROLE_DELIMITER = "delimiter"

_FIELD_PACKAGE = "Package"
_FIELD_CATEGORY = "Category"
_FIELD_DEPENDS_ON = "Depends on"
_FIELD_DESIGN_REFERENCE = "Design reference"
_FIELD_DESIGN_ACCEPTANCE = "Design acceptance property"
_KNOWN_FIELDS = (
    _FIELD_PACKAGE,
    _FIELD_CATEGORY,
    _FIELD_DEPENDS_ON,
    _FIELD_DESIGN_REFERENCE,
    _FIELD_DESIGN_ACCEPTANCE,
)

_SECTION_FILES_PREFIX = "files to "
_SECTION_FILES_REVIEW_PREFIX = "files to review"
_SECTION_TARGETED_TESTS_PREFIX = "targeted tests"

_QUALITY_GATE_CATEGORY_MARKER = "quality gate"

# Canonical red-flag markers per CLAUDE.md "Task Orchestration" (a How-Solved
# section containing any of these must never be auto-completed).
HOW_SOLVED_REDFLAG_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("BLOCKED", re.compile(r"\bblocked\b", re.IGNORECASE)),
    ("partial", re.compile(r"\bpartial(?:ly)?\b", re.IGNORECASE)),
    ("out of scope", re.compile(r"\bout of scope\b", re.IGNORECASE)),
    ("workaround", re.compile(r"\bworkaround", re.IGNORECASE)),
    ("dual path", re.compile(r"\bdual[ -]path", re.IGNORECASE)),
    ("not yet wired", re.compile(r"\bnot yet wired\b", re.IGNORECASE)),
)

_TASK_FILENAME_PATTERN = re.compile(r"^task-(\d{2,})-(\d{2,}[a-z]?)(?=[-.])")
_TASK_ID_PATTERN = re.compile(r"^task-(\d{2,})-(\d{2,}[a-z]?)$")
# Token extraction from free text: `31-05`, `task-31-05`, `task-31-05-slug`,
# `09-15b`. The lookbehind rejects tokens embedded in words, paths, decimals
# and ISO dates (e.g. `2026-07-13`); the lookahead rejects longer digit runs.
_TASK_ID_TOKEN_PATTERN = re.compile(
    r"(?<![\w./\\-])(?:task-)?(\d{2})-(\d{2}[a-z]?)(?!\d)"
)
_INLINE_BOLD_LABEL_PATTERN = re.compile(r"\*\*[A-Z][^*\n]{0,80}:\*\*")
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_STATUS_PREFIX_PATTERN = re.compile(r"^([A-Z][A-Z0-9_-]*):\s+(.*)$")
_TASK_TITLE_PATTERN = re.compile(r"^Task\s+\d{2,}-\d{2,}[a-z]?\s*:\s*(.*)$")
_FIELD_LABEL_PATTERN = re.compile(
    r"^\*\*(" + "|".join(re.escape(name) for name in _KNOWN_FIELDS) + r"):\*\*\s*(.*)$"
)
_LIST_ITEM_PATTERN = re.compile(r"^\s*(?:[-*+]|\d+\.)\s")
# 'How Solved' appears both as '## How Solved' and as a '### How Solved'
# sub-heading of '## Implementation Notes' in the real corpus — match any level.
_HOW_SOLVED_HEADING_PATTERN = re.compile(r"^#{2,6}\s+How Solved", re.IGNORECASE)
_BACKTICK_TOKEN_PATTERN = re.compile(r"`([^`]+)`")
_TRAILING_LINE_REF_PATTERN = re.compile(r":\d[\d,:~-]*$")
_GROUP_HEADER_PATTERN = re.compile(r"^Group\s+(\d+)$")
_LEADING_INT_PATTERN = re.compile(r"^\d+")

_PATH_FORBIDDEN_CHARS = frozenset('(){}<>*?"\' \t')
_NONE_DEPENDS_PATTERN = re.compile(r"^\s*None\b", re.IGNORECASE)


def _load_get_datrix_root() -> Callable[[], Path]:
    """Load get_datrix_root from shared/venv.py without importing shared.__init__."""
    venv_module_path = _LIBRARY_DIR / "shared" / "venv.py"
    spec = importlib.util.spec_from_file_location(
        "_task_metadata_shared_venv", venv_module_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(
            f"Could not load module spec from {venv_module_path}. Expected the "
            "shared venv helpers at scripts/library/shared/venv.py."
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    func = getattr(module, "get_datrix_root")
    if not callable(func):
        raise ImportError(
            f"{venv_module_path} does not define a callable get_datrix_root()."
        )
    return cast(Callable[[], Path], func)


get_datrix_root: Callable[[], Path] = _load_get_datrix_root()


@dataclass
class TaskMetadata:
    """Metadata parsed from a single task markdown file."""

    task_id: str
    task_path: str
    repo: str
    title: str
    status: str
    is_completed: bool
    package: str | None
    category: str | None
    depends_on: list[str]
    design_reference: str | None
    design_acceptance_property: str | None
    files_to_review: list[str]
    files_to_create_modify: list[str]
    targeted_tests: list[str]
    has_how_solved: bool
    how_solved_redflags: list[str]
    languages: list[str]

    @property
    def is_quality_gate(self) -> bool:
        """True when the task's category marks it as a quality gate."""
        return (
            self.category is not None
            and _QUALITY_GATE_CATEGORY_MARKER in self.category.lower()
        )

    def to_dict(self) -> dict[str, object]:
        """JSON-serializable representation."""
        return {
            "task_id": self.task_id,
            "task_path": self.task_path,
            "repo": self.repo,
            "title": self.title,
            "status": self.status,
            "is_completed": self.is_completed,
            "package": self.package,
            "category": self.category,
            "depends_on": list(self.depends_on),
            "design_reference": self.design_reference,
            "design_acceptance_property": self.design_acceptance_property,
            "files_to_review": list(self.files_to_review),
            "files_to_create_modify": list(self.files_to_create_modify),
            "targeted_tests": list(self.targeted_tests),
            "has_how_solved": self.has_how_solved,
            "how_solved_redflags": list(self.how_solved_redflags),
            "languages": list(self.languages),
        }


@dataclass
class DependencyEntry:
    """One task entry from a phase dependencies.md document."""

    task_id: str
    task_path: str | None
    title: str | None
    is_completed: bool | None
    package: str | None
    dependencies: list[str] | None
    category: str | None
    group: int | None

    def to_dict(self) -> dict[str, object]:
        """JSON-serializable representation."""
        return {
            "task_id": self.task_id,
            "task_path": self.task_path,
            "title": self.title,
            "is_completed": self.is_completed,
            "package": self.package,
            "dependencies": None if self.dependencies is None else list(self.dependencies),
            "category": self.category,
            "group": self.group,
        }


@dataclass
class DependenciesDoc:
    """A parsed phase-level dependencies.md (JSON or legacy Group format)."""

    path: str
    doc_format: str
    phase: int | None
    provenance: dict[str, object] | None
    entries: list[DependencyEntry]


def format_phase(phase: int) -> str:
    """Zero-padded two-digit phase label (e.g. 5 -> '05')."""
    return f"{phase:02d}"


def normalize_task_id(token: str) -> str:
    """Normalize '31-05' / 'task-31-05' / 'task-31-05-slug' to 'task-31-05'."""
    match = _TASK_ID_TOKEN_PATTERN.search(token)
    if match is None:
        raise ValueError(
            f"'{token}' is not a task ID. Expected 'NN-TT' or 'task-NN-TT' "
            "(two-digit phase and task numbers, e.g. 'task-31-05')."
        )
    return f"task-{match.group(1)}-{match.group(2)}"


def task_id_phase(task_id: str) -> int:
    """Phase number of a normalized task ID ('task-31-05' -> 31)."""
    match = _TASK_ID_PATTERN.match(task_id)
    if match is None:
        raise ValueError(
            f"'{task_id}' is not a normalized task ID. Expected 'task-NN-TT'; "
            "normalize with normalize_task_id() first."
        )
    return int(match.group(1))


def task_id_number(task_id: str) -> int:
    """Numeric task number of a normalized task ID ('task-31-05' -> 5)."""
    match = _TASK_ID_PATTERN.match(task_id)
    if match is None:
        raise ValueError(
            f"'{task_id}' is not a normalized task ID. Expected 'task-NN-TT'."
        )
    leading = _LEADING_INT_PATTERN.match(match.group(2))
    if leading is None:  # unreachable: TT always starts with digits
        raise ValueError(f"Task ID '{task_id}' has a non-numeric task number.")
    return int(leading.group(0))


def extract_dependency_ids(depends_text: str) -> list[str]:
    """Extract normalized task IDs from a '**Depends on:**' field value.

    Text after an inline bold label (e.g. '**Blocks:** 09-15b') is not
    scanned. 'None' (with or without punctuation) yields an empty list.
    Wildcard references such as '06-*' are not resolvable IDs and are skipped.
    """
    if _NONE_DEPENDS_PATTERN.match(depends_text):
        return []
    label = _INLINE_BOLD_LABEL_PATTERN.search(depends_text)
    scan = depends_text[: label.start()] if label else depends_text
    ids: list[str] = []
    for match in _TASK_ID_TOKEN_PATTERN.finditer(scan):
        task_id = f"task-{match.group(1)}-{match.group(2)}"
        if task_id not in ids:
            ids.append(task_id)
    return ids


def _classify_lines(lines: list[str]) -> list[str]:
    """Classify each line as text, code (inside a fence), or fence delimiter."""
    roles: list[str] = []
    in_fence = False
    for line in lines:
        if line.lstrip().startswith("```"):
            roles.append(_LINE_ROLE_DELIMITER)
            in_fence = not in_fence
        elif in_fence:
            roles.append(_LINE_ROLE_CODE)
        else:
            roles.append(_LINE_ROLE_TEXT)
    return roles


def _parse_heading_status(heading: str) -> tuple[str, str]:
    """Split a task heading into (status, title).

    '# COMPLETED: Task 31-05: Foo' -> ('COMPLETED', 'Foo');
    '# Task 31-16: Bar' -> ('PENDING', 'Bar').
    """
    status = PENDING_STATUS
    rest = heading.strip()
    prefix_match = _STATUS_PREFIX_PATTERN.match(rest)
    if prefix_match is not None and prefix_match.group(2).lstrip().startswith("Task"):
        status = prefix_match.group(1)
        rest = prefix_match.group(2).lstrip()
    title_match = _TASK_TITLE_PATTERN.match(rest)
    title = title_match.group(1).strip() if title_match else rest
    return status, title


def _find_first_heading(lines: list[str], roles: list[str], task_path: Path) -> str:
    for line, role in zip(lines, roles):
        if role != _LINE_ROLE_TEXT:
            continue
        match = _HEADING_PATTERN.match(line.lstrip("﻿"))
        if match is not None:
            return match.group(2)
    raise ValueError(
        f"No markdown heading found in {task_path}. Task files must start with "
        "'# Task NN-TT: Title' (optionally status-prefixed, e.g. '# COMPLETED: Task ...')."
    )


def _collect_fields(lines: list[str], roles: list[str]) -> dict[str, str]:
    """Collect the first occurrence of each known metadata field.

    A field's text runs until the next known field label, the next markdown
    heading, or EOF. Fenced code lines neither terminate nor extend a field.
    """
    collected: dict[str, list[str]] = {}
    current: str | None = None
    for line, role in zip(lines, roles):
        if role != _LINE_ROLE_TEXT:
            continue
        if line.startswith("#"):
            current = None
            continue
        label_match = _FIELD_LABEL_PATTERN.match(line)
        if label_match is not None:
            name = label_match.group(1)
            if name in collected:
                current = None  # later duplicates (e.g. in Targeted Tests) end any open field
                continue
            collected[name] = [label_match.group(2)]
            current = name
            continue
        if current is not None:
            collected[current].append(line)
    return {name: "\n".join(parts).strip() for name, parts in collected.items()}


def _split_sections(lines: list[str], roles: list[str]) -> list[tuple[str, int, int]]:
    """Return (lowercased '## ' heading text, body start index, body end index)."""
    heads: list[tuple[int, str]] = []
    for index, (line, role) in enumerate(zip(lines, roles)):
        if role == _LINE_ROLE_TEXT and line.startswith("## "):
            heads.append((index, line[3:].strip().lower()))
    sections: list[tuple[str, int, int]] = []
    for position, (index, name) in enumerate(heads):
        end = heads[position + 1][0] if position + 1 < len(heads) else len(lines)
        sections.append((name, index + 1, end))
    return sections


def _clean_path_token(token: str) -> str | None:
    """Return a cleaned path if the backticked token looks like one, else None."""
    cleaned = token.strip().strip(",;").strip()
    cleaned = _TRAILING_LINE_REF_PATTERN.sub("", cleaned)
    if not cleaned or "::" in cleaned:
        return None
    if any(char in _PATH_FORBIDDEN_CHARS for char in cleaned):
        return None
    if "/" not in cleaned and "\\" not in cleaned:
        return None
    return cleaned


def _extract_section_paths(
    lines: list[str], roles: list[str], start: int, end: int
) -> list[str]:
    """Extract path-like backticked tokens from sub-headings and list items."""
    paths: list[str] = []
    for index in range(start, end):
        if roles[index] != _LINE_ROLE_TEXT:
            continue
        line = lines[index]
        if not (line.startswith("###") or _LIST_ITEM_PATTERN.match(line)):
            continue
        for token in _BACKTICK_TOKEN_PATTERN.findall(line):
            cleaned = _clean_path_token(token)
            if cleaned is not None and cleaned not in paths:
                paths.append(cleaned)
    return paths


def _how_solved_line_indices(lines: list[str], roles: list[str]) -> tuple[bool, list[int]]:
    """Line indices of every 'How Solved' report in the file.

    A report starts at a 'How Solved' heading of ANY level (##..######) and
    runs until the next '## ' section heading (or EOF): completion reports
    filed as '### How Solved' inside '## Implementation Notes' typically own
    the sibling sub-headings that follow them (Status, Tests, ...).
    """
    indices: set[int] = set()
    found = False
    for head, (line, role) in enumerate(zip(lines, roles)):
        if role != _LINE_ROLE_TEXT or not _HOW_SOLVED_HEADING_PATTERN.match(line):
            continue
        found = True
        for index in range(head + 1, len(lines)):
            if roles[index] == _LINE_ROLE_TEXT and lines[index].startswith("## "):
                break
            indices.add(index)
    return found, sorted(indices)


def _extract_code_lines(
    lines: list[str], roles: list[str], start: int, end: int
) -> list[str]:
    """Non-empty lines inside fenced code blocks of a section."""
    commands: list[str] = []
    for index in range(start, end):
        if roles[index] != _LINE_ROLE_CODE:
            continue
        stripped = lines[index].strip()
        if stripped:
            commands.append(stripped)
    return commands


def _first_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _extract_package(field_text: str | None) -> str | None:
    if field_text is None:
        return None
    first = _first_line(field_text)
    if first is None:
        return None
    backticked = _BACKTICK_TOKEN_PATTERN.search(first)
    if backticked is not None:
        return backticked.group(1).strip()
    words = first.split()
    return words[0].rstrip(".,;:") if words else None


def _extract_category(field_text: str | None) -> str | None:
    if field_text is None:
        return None
    first = _first_line(field_text)
    if first is None:
        return None
    return first.rstrip(" .")


def _extension_of(path_str: str) -> str | None:
    normalized = path_str.replace("\\", "/").rstrip("/")
    name = normalized.rsplit("/", 1)[-1]
    if "." not in name:
        return None
    extension = name.rsplit(".", 1)[1].lower()
    return f".{extension}" if extension else None


def _languages_of(paths: list[str]) -> list[str]:
    extensions: list[str] = []
    for path_str in paths:
        extension = _extension_of(path_str)
        if extension is not None and extension not in extensions:
            extensions.append(extension)
    return sorted(extensions)


def _redflags_in(text: str) -> list[str]:
    return [name for name, pattern in HOW_SOLVED_REDFLAG_MARKERS if pattern.search(text)]


def task_id_from_filename(task_path: Path) -> str:
    """Derive the normalized task ID from a task file name."""
    match = _TASK_FILENAME_PATTERN.match(task_path.name)
    if match is None:
        raise ValueError(
            f"Task file name '{task_path.name}' (at {task_path}) does not match "
            "the expected 'task-<NN>-<TT>[-slug].md' pattern. Rename the file or "
            "remove it from the phase folder."
        )
    return f"task-{match.group(1)}-{match.group(2)}"


def parse_task_file(task_path: Path) -> TaskMetadata:
    """Parse one task markdown file into TaskMetadata. Read-only."""
    task_id = task_id_from_filename(task_path)
    text = task_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    roles = _classify_lines(lines)

    heading = _find_first_heading(lines, roles, task_path)
    status, title = _parse_heading_status(heading)

    fields = _collect_fields(lines, roles)
    depends_text = fields.get(_FIELD_DEPENDS_ON)
    depends_on = extract_dependency_ids(depends_text) if depends_text is not None else []

    files_to_review: list[str] = []
    files_to_create_modify: list[str] = []
    targeted_tests: list[str] = []
    for name, start, end in _split_sections(lines, roles):
        if name.startswith(_SECTION_FILES_REVIEW_PREFIX):
            files_to_review.extend(_extract_section_paths(lines, roles, start, end))
        elif name.startswith(_SECTION_FILES_PREFIX):
            files_to_create_modify.extend(_extract_section_paths(lines, roles, start, end))
        elif name.startswith(_SECTION_TARGETED_TESTS_PREFIX):
            targeted_tests.extend(_extract_code_lines(lines, roles, start, end))
    has_how_solved, how_solved_indices = _how_solved_line_indices(lines, roles)
    how_solved_lines = [lines[index] for index in how_solved_indices]

    design_reference_text = fields.get(_FIELD_DESIGN_REFERENCE)
    design_reference = (
        _first_line(design_reference_text) if design_reference_text is not None else None
    )
    acceptance_text = fields.get(_FIELD_DESIGN_ACCEPTANCE)

    return TaskMetadata(
        task_id=task_id,
        task_path=str(task_path.resolve()),
        repo=_repo_of(task_path),
        title=title,
        status=status,
        is_completed=status == COMPLETED_STATUS,
        package=_extract_package(fields.get(_FIELD_PACKAGE)),
        category=_extract_category(fields.get(_FIELD_CATEGORY)),
        depends_on=depends_on,
        design_reference=design_reference,
        design_acceptance_property=acceptance_text if acceptance_text else None,
        files_to_review=files_to_review,
        files_to_create_modify=files_to_create_modify,
        targeted_tests=targeted_tests,
        has_how_solved=has_how_solved,
        how_solved_redflags=_redflags_in("\n".join(how_solved_lines)),
        languages=_languages_of(files_to_create_modify),
    )


def _repo_of(task_path: Path) -> str:
    """Repo folder name owning a '.tasks/phase-NN/task-*.md' file."""
    resolved = task_path.resolve()
    for parent in resolved.parents:
        if parent.name == ".tasks":
            return parent.parent.name
    return resolved.parent.name


def discover_phase_dirs(base_dir: Path, phase: int) -> list[Path]:
    """All '<repo>/.tasks/phase-NN' directories under base_dir (repos = datrix*)."""
    label = format_phase(phase)
    dirs: list[Path] = []
    for child in sorted(base_dir.iterdir()):
        if not child.is_dir() or not child.name.startswith("datrix"):
            continue
        phase_dir = child / ".tasks" / f"phase-{label}"
        if phase_dir.is_dir():
            dirs.append(phase_dir)
    return dirs


def discover_phase_task_files(base_dir: Path, phase: int) -> list[Path]:
    """All task-*.md files of a phase across every repo, sorted by name then path."""
    files: list[Path] = []
    for phase_dir in discover_phase_dirs(base_dir, phase):
        files.extend(phase_dir.glob("task-*.md"))
    return sorted(files, key=lambda path: (path.name, str(path)))


def find_task_file(base_dir: Path, task_id: str) -> Path | None:
    """Locate a task file by normalized ID in its own phase's folders (any repo)."""
    phase = task_id_phase(task_id)
    exact_name = f"{task_id}.md"
    slug_prefix = f"{task_id}-"
    for phase_dir in discover_phase_dirs(base_dir, phase):
        for candidate in sorted(phase_dir.glob(f"{task_id}*.md")):
            if candidate.name == exact_name or candidate.name.startswith(slug_prefix):
                return candidate
    return None


def dependencies_md_path(base_dir: Path, phase: int) -> Path:
    """Phase-level dependencies.md location (always under the datrix showcase repo)."""
    return base_dir / "datrix" / ".tasks" / f"phase-{format_phase(phase)}" / "dependencies.md"


def _require_str(data: dict[str, object], key: str, context: str) -> str:
    if key not in data:
        raise ValueError(
            f"{context}: missing required key '{key}'. Expected the JSON "
            "dependencies.md schema from claude-config/.claude/agent-templates/"
            "dependencies-format.md; regenerate the file with /generate-tasks."
        )
    value = data[key]
    if not isinstance(value, str):
        raise ValueError(
            f"{context}: key '{key}' must be a string, got {type(value).__name__}."
        )
    return value


def _require_bool(data: dict[str, object], key: str, context: str) -> bool:
    if key not in data:
        raise ValueError(
            f"{context}: missing required key '{key}'. Expected the JSON "
            "dependencies.md schema; regenerate the file with /generate-tasks."
        )
    value = data[key]
    if not isinstance(value, bool):
        raise ValueError(
            f"{context}: key '{key}' must be a boolean, got {type(value).__name__}."
        )
    return value


def _require_str_list(data: dict[str, object], key: str, context: str) -> list[str]:
    if key not in data:
        raise ValueError(
            f"{context}: missing required key '{key}'. Expected the JSON "
            "dependencies.md schema; regenerate the file with /generate-tasks."
        )
    value = data[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(
            f"{context}: key '{key}' must be a list of strings, got {value!r}."
        )
    return [str(item) for item in value]


def _parse_dependencies_json(data: dict[str, object], path: Path) -> DependenciesDoc:
    context = f"dependencies.md at {path}"
    tasks_value = data.get("tasks")
    if not isinstance(tasks_value, list):
        raise ValueError(
            f"{context}: top-level 'tasks' must be a list of task entries. "
            "See dependencies-format.md for the schema."
        )
    entries: list[DependencyEntry] = []
    for index, item in enumerate(tasks_value):
        if not isinstance(item, dict):
            raise ValueError(
                f"{context}: tasks[{index}] must be an object, got {type(item).__name__}."
            )
        entry_data = cast(dict[str, object], item)
        entry_context = f"{context}, tasks[{index}]"
        entries.append(
            DependencyEntry(
                task_id=normalize_task_id(_require_str(entry_data, "task_id", entry_context)),
                task_path=_require_str(entry_data, "task_path", entry_context),
                title=_require_str(entry_data, "title", entry_context),
                is_completed=_require_bool(entry_data, "is_completed", entry_context),
                package=_require_str(entry_data, "package", entry_context),
                dependencies=[
                    normalize_task_id(dep)
                    for dep in _require_str_list(entry_data, "dependencies", entry_context)
                ],
                category=_require_str(entry_data, "category", entry_context),
                group=None,
            )
        )
    phase_value = data.get("phase")
    provenance_value = data.get("provenance")
    provenance: dict[str, object] | None = None
    if provenance_value is not None:
        if not isinstance(provenance_value, dict):
            raise ValueError(
                f"{context}: 'provenance' must be an object when present, "
                f"got {type(provenance_value).__name__}."
            )
        provenance = cast(dict[str, object], provenance_value)
    return DependenciesDoc(
        path=str(path),
        doc_format=DEPENDENCIES_FORMAT_JSON,
        phase=phase_value if isinstance(phase_value, int) else None,
        provenance=provenance,
        entries=entries,
    )


def _parse_dependencies_legacy(text: str, path: Path) -> DependenciesDoc:
    entries: list[DependencyEntry] = []
    group: int | None = None
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        group_match = _GROUP_HEADER_PATTERN.match(line)
        if group_match is not None:
            group = int(group_match.group(1))
            continue
        if group is None:
            raise ValueError(
                f"dependencies.md at {path}, line {line_number}: content appears "
                "before the first 'Group N' header. Expected either the JSON "
                "format or the legacy 'Group N' text format from "
                "dependencies-format.md."
            )
        task_path = Path(line)
        entries.append(
            DependencyEntry(
                task_id=task_id_from_filename(task_path),
                task_path=line,
                title=None,
                is_completed=None,
                package=None,
                dependencies=None,
                category=None,
                group=group,
            )
        )
    if not entries:
        raise ValueError(
            f"dependencies.md at {path} is neither valid JSON nor the legacy "
            "'Group N' text format. See dependencies-format.md; regenerate with "
            "/generate-tasks."
        )
    return DependenciesDoc(
        path=str(path),
        doc_format=DEPENDENCIES_FORMAT_LEGACY,
        phase=None,
        provenance=None,
        entries=entries,
    )


def parse_dependencies_md(path: Path) -> DependenciesDoc:
    """Parse a phase dependencies.md: JSON preferred, legacy 'Group N' fallback."""
    text = path.read_text(encoding="utf-8")
    try:
        data: object = json.loads(text)
    except json.JSONDecodeError:
        return _parse_dependencies_legacy(text, path)
    if not isinstance(data, dict):
        raise ValueError(
            f"dependencies.md at {path} parses as JSON but is not an object. "
            "Expected the schema from dependencies-format.md."
        )
    return _parse_dependencies_json(cast(dict[str, object], data), path)


def default_output_path(category: str, file_name: str) -> Path:
    """Stable cross-cutting output location: <workspace>/.tmp/<category>/<name>."""
    return get_datrix_root() / ".tmp" / category / file_name


def write_json_output(payload: dict[str, object], output_path: Path) -> None:
    """Write a JSON payload, creating parent directories."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
