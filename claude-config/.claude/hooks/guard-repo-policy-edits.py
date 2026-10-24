"""PreToolUse hook (Write|Edit): four repo policies that were prose rules, now blocks.

1. NO GITHUB ACTIONS. CLAUDE.md: "No GitHub Actions." A file under `.github/workflows/` is a
   CI pipeline this project does not use and must never grow. Third-party sources parked in
   `.tmp/` are not ours and are left alone.

2. A TASK IS COMPLETED BY `complete.ps1`, NEVER BY EDITING ITS HEADING. task-orchestration.md:
   "Always use complete.ps1. Never edit the task heading directly -- Edit/Write bypass the
   validation hook complete.ps1 enforces." The failure it prevents is real: a task was once
   marked COMPLETED while its own `## How Solved` said `Status: BLOCKED`. An edit that ADDS a
   `# COMPLETED: Task ...` heading to a task file is refused; editing the rest of the file, or
   a file that already carries the heading, is not.

3. AGENTS NEVER CREATE A PHASE. task-orchestration.md: creating a `.tasks/phase-NN/` directory
   that does not already exist is a planning act reserved to Jon and to the planning skills he
   invokes by name (`/generate-tasks`, `/operationalize-design`). A phase that appears on its own
   silently seeds the next orchestration run with work nobody scheduled. Writing a file into a
   phase directory that does not exist is how an agent creates one, so that is what is refused
   -- unless the skill recorded for this session (`record-active-skill.py`) is one of the two
   planning skills. An unreadable record cannot prove a planning skill is active, and the block
   stays: a phase is cheap to ask for and expensive to unschedule.

4. A PARITY FACT OVER GENERATED ARTIFACTS IS A PARITY ROW, NEVER A NEW GATE MODULE. A fact read
   through a conformance probe ("every language answers this route with this contract") is one
   row of `datrix/scripts/gates/parity/cases/<area>.parity.yaml`, read on every registered target
   by `parity-cases-gate.ps1`; each probe-backed gate module rewrote the discovery, the fixture,
   the comparison and the self-test, and compared targets only with each other. A Write creating a
   new gate module (`datrix/scripts/gates/<family>/lib/*.py`, or
   `datrix/scripts/common/lib/datrix_scripts/gates/<family>/*.py` for a family whose wrappers are
   rendered from the entrypoint template) that imports
   `datrix_codegen_kernel.parity.conformance_probes`, or a new gate wrapper (`.ps1` or its `.sh`
   twin) whose `lib\\` module or `datrix_scripts.gates.*` module does, is refused; a source-census
   gate imports no probe and passes. The parity runner's own modules are the one carrier and pass.

5. EVERY DESIGN ANSWERS THE DESIGN GUIDELINES. design-and-docs.md: a design doc under `design/`
   carries a `## Design guidelines conformance` section with one bullet per binding guideline
   (`- G1: ...` through the last one `design-principles.md` defines), each with text after the
   colon. A Write of a design doc without every bullet is refused, and so is an Edit that drops
   a bullet the doc carried. The guideline ids are read from `design-principles.md` itself, so a
   guideline added there is required here with no edit to this hook. The design index
   (`000-*.md`) is not a design and passes.

All five fail OPEN on anything the hook cannot evaluate (unparseable input, unreadable file).

Exit codes:
  0 -- allow
  2 -- block (stderr becomes feedback to Claude)
"""

import json
import os
import re
import sys
from typing import Final

_REPO_ROOT: Final = "d:/datrix"
_STATE_DIR: Final = os.path.join(_REPO_ROOT, ".claude", "hooks", ".state")

# Planning skills Jon invokes by name; the only callers allowed to open a new phase.
_PHASE_PLANNING_SKILLS: Final = frozenset({"generate-tasks", "operationalize-design"})

_WORKFLOW_RE: Final = re.compile(r"(?:^|/)\.github/workflows/[^/]+$")
# Third-party checkouts and tooling the project does not own.
_THIRD_PARTY_SEGMENTS: Final = ("/.tmp/", "/node_modules/", "/.venv/", "/site-packages/", "/.git/")

_TASK_FILE_RE: Final = re.compile(r"(?:^|/)\.tasks/phase-(\d+)/task-[^/]+\.md$")
_PHASE_DIR_RE: Final = re.compile(r"^(.*?/\.tasks/phase-\d+)/")
_COMPLETED_HEADING_RE: Final = re.compile(r"^#\s+COMPLETED:\s+Task\b", re.MULTILINE)

# A gate module: in its family's `lib/`, or -- for a family whose wrappers are rendered from the
# entrypoint template -- in that family's `datrix_scripts.gates.<family>` package.
_GATE_LIB_RE: Final = re.compile(
    r"(?:^|/)datrix/scripts/(?:gates/[^/]+/lib|common/lib/datrix_scripts/gates/[^/]+)/[^/]+\.py$"
)
_GATE_WRAPPER_RE: Final = re.compile(r"(?:^|/)datrix/scripts/gates/[^/]+/[^/]+\.(?:ps1|sh)$")
# The module a rendered wrapper (or its `.sh` twin) runs, quoted: `-Module "datrix_scripts.gates.x.y"`.
_WRAPPER_MODULE_RE: Final = re.compile(r"[\"'](datrix_scripts\.gates(?:\.[A-Za-z0-9_]+)+)[\"']")
_SCRIPTS_LIB: Final = ("common", "lib")
_PROBE_IMPORT_RE: Final = re.compile(
    r"^[ \t]*(?:from|import)[ \t]+datrix_codegen_kernel\.parity\.conformance_probes\b"
    r"|^[ \t]*from[ \t]+datrix_codegen_kernel\.parity[ \t]+import[ \t][^\n]*\bconformance_probes\b",
    re.MULTILINE,
)
_WRAPPER_LIB_RE: Final = re.compile(r"lib[\\/]([A-Za-z0-9_]+\.py)")
# The parity cases runner: the one carrier of probe-read parity facts.
_PARITY_RUNNER_MODULES: Final = frozenset(
    {
        "datrix/scripts/common/lib/datrix_scripts/gates/parity/parity_cases_gate.py",
        "datrix/scripts/common/lib/datrix_scripts/gates/parity/parity_cases.py",
        "datrix/scripts/common/lib/datrix_scripts/gates/parity/parity_cases_cli.py",
        "datrix/scripts/common/lib/datrix_scripts/gates/parity/parity_observers.py",
    }
)

# A numbered design doc in a `design/` folder; the `000-` index is not a design.
_DESIGN_DOC_RE: Final = re.compile(r"(?:^|/)design/(?!000-)\d{3,4}-[^/]+\.md$")
_GUIDELINES_DOC: Final = os.path.join(_REPO_ROOT, "datrix", "docs", "architecture", "design-principles.md")
# A guideline's definition in design-principles.md: `**G7. Secure by default ...`.
_GUIDELINE_DEFINITION_RE: Final = re.compile(r"^\*\*G(\d+)\.", re.MULTILINE)
_CONFORMANCE_HEADING: Final = "## Design guidelines conformance"
_CONFORMANCE_SECTION_RE: Final = re.compile(
    r"^##[ \t]+Design guidelines conformance[ \t]*$(.*?)(?=^##[ \t]|\Z)", re.MULTILINE | re.DOTALL | re.IGNORECASE
)
# One answered bullet: `- G3: <text>` (bold id allowed).
_CONFORMANCE_BULLET_RE: Final = re.compile(r"^[ \t]*[-*][ \t]+\**G(\d+)\**[ \t]*:\**[ \t]*\S", re.MULTILINE)


def _normalize(path: str) -> str:
    return path.replace("\\", "/")


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _block(message: str) -> None:
    sys.stderr.write(message)
    sys.exit(2)


def _active_skill(session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "unknown")
    try:
        with open(os.path.join(_STATE_DIR, f"skill-{safe}.json"), encoding="utf-8") as handle:
            return str(json.load(handle).get("skill", "")).lower()
    except (OSError, ValueError):
        return ""


def _check_workflow(path: str) -> None:
    lowered = path.lower()
    if not _WORKFLOW_RE.search(lowered) or any(seg in lowered for seg in _THIRD_PARTY_SEGMENTS):
        return
    _block(
        f"BLOCKED: `{path}` is a GitHub Actions workflow; this project uses none (CLAUDE.md). "
        "Put the check in a script under `datrix/scripts/`, a hook, or a test in the owning package."
    )


def _adds_completed_heading(tool: str, tool_input: dict[str, object], path: str) -> bool:
    if tool == "Write":
        content = str(tool_input.get("content", ""))
        return bool(_COMPLETED_HEADING_RE.search(content)) and not _COMPLETED_HEADING_RE.search(_read(path))
    new = str(tool_input.get("new_string", ""))
    old = str(tool_input.get("old_string", ""))
    return bool(_COMPLETED_HEADING_RE.search(new)) and not _COMPLETED_HEADING_RE.search(old)


def _check_task_heading(tool: str, tool_input: dict[str, object], path: str) -> None:
    if not _TASK_FILE_RE.search(path.lower()) or not _adds_completed_heading(tool, tool_input, path):
        return
    _block(
        f"BLOCKED: this edit marks `{path}` COMPLETED by hand, skipping `complete.ps1`'s validation "
        "(.claude/docs/task-orchestration.md). Call `complete.ps1` "
        "(`datrix/scripts/tasks/quick-reference.md`); the rest of the task file stays editable."
    )


def _check_new_phase(path: str, session_id: str) -> None:
    lowered = path.lower()
    match = _PHASE_DIR_RE.match(lowered)
    if not match or any(seg in lowered for seg in _THIRD_PARTY_SEGMENTS):
        return
    phase_dir = path[: len(match.group(1))]
    if os.path.isdir(phase_dir):
        return
    if _active_skill(session_id) in _PHASE_PLANNING_SKILLS:
        return
    _block(
        f"BLOCKED: writing `{path}` would create the phase directory `{phase_dir}`; agents never open "
        "a phase (.claude/docs/task-orchestration.md). A defect your task does not need is a findings "
        "file under `d:\\datrix\\reports\\finding\\`; a follow-up task goes in the existing phase you are "
        "executing (`validate-dependencies.ps1 -Phase {NN} -NextTaskNumber`)."
    )


def _is_parity_runner(path: str) -> bool:
    lowered = path.lower()
    return any(lowered.endswith(module) for module in _PARITY_RUNNER_MODULES)


def _probe_reading_modules(path: str, content: str) -> list[str]:
    """The probe-importing gate modules a new gate file *path* with *content* would add or run."""
    lowered = path.lower()
    if _GATE_LIB_RE.search(lowered):
        return [path] if _PROBE_IMPORT_RE.search(content) and not _is_parity_runner(path) else []
    if not _GATE_WRAPPER_RE.search(lowered):
        return []
    family_dir = os.path.dirname(path)
    scripts_dir = os.path.dirname(os.path.dirname(family_dir))
    lib_modules = [os.path.join(family_dir, "lib", name) for name in _WRAPPER_LIB_RE.findall(content)]
    package_modules = [
        os.path.join(scripts_dir, *_SCRIPTS_LIB, *dotted.split(".")) + ".py"
        for dotted in _WRAPPER_MODULE_RE.findall(content)
    ]
    found: list[str] = []
    for module in sorted({_normalize(candidate) for candidate in lib_modules + package_modules}):
        if _PROBE_IMPORT_RE.search(_read(module)) and not _is_parity_runner(module):
            found.append(module)
    return found


def _check_probe_gate(tool_input: dict[str, object], path: str) -> None:
    if os.path.exists(path) or any(seg in path.lower() for seg in _THIRD_PARTY_SEGMENTS):
        return
    modules = _probe_reading_modules(path, str(tool_input.get("content", "")))
    if not modules:
        return
    _block(
        f"BLOCKED: `{path}` would add a gate that reads targets through conformance probes "
        f"({', '.join(modules)} imports datrix_codegen_kernel.parity.conformance_probes).\n"
        "A parity fact is a row in `datrix/scripts/gates/parity/cases/<area>.parity.yaml` "
        "(`parity-cases.ps1 observe` / `new`); a reading no probe returns yet is a kernel probe method plus a "
        "facet in `datrix_scripts.gates.parity.parity_observers`. Only a source census is a new gate module."
    )


def _guideline_ids() -> frozenset[int]:
    """The guideline ids design-principles.md defines; empty when it cannot be read (fail open)."""
    return frozenset(int(found) for found in _GUIDELINE_DEFINITION_RE.findall(_read(_GUIDELINES_DOC)))


def _answered_guidelines(content: str) -> frozenset[int]:
    section = _CONFORMANCE_SECTION_RE.search(content)
    if not section:
        return frozenset()
    return frozenset(int(found) for found in _CONFORMANCE_BULLET_RE.findall(section.group(1)))


def _edited_content(tool_input: dict[str, object], current: str) -> str:
    old = str(tool_input.get("old_string", ""))
    new = str(tool_input.get("new_string", ""))
    if not old:
        return current
    return current.replace(old, new) if tool_input.get("replace_all") else current.replace(old, new, 1)


def _check_design_conformance(tool: str, tool_input: dict[str, object], path: str) -> None:
    if not _DESIGN_DOC_RE.search(path.lower()) or any(seg in path.lower() for seg in _THIRD_PARTY_SEGMENTS):
        return
    required = _guideline_ids()
    if not required:
        return
    if tool == "Write":
        missing = required - _answered_guidelines(str(tool_input.get("content", "")))
    else:
        current = _read(path)
        carried = _answered_guidelines(current) & required
        missing = carried - _answered_guidelines(_edited_content(tool_input, current))
    if not missing:
        return
    ids = ", ".join(f"G{number}" for number in sorted(missing))
    _block(
        f"BLOCKED: design doc `{path}` would lack an answer for {ids} in its "
        f"`{_CONFORMANCE_HEADING}` section.\n"
        "Read `datrix/docs/architecture/design-principles.md` § Design Guidelines, then answer every one of "
        f"G{min(required)}..G{max(required)} as `- G1: <how>` or `- G1: N/A: <why>`. A design that breaks one "
        "is a defective draft: change the design, never the answer."
    )


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    tool = data.get("tool_name", "")
    if tool not in ("Write", "Edit"):
        sys.exit(0)
    tool_input = data.get("tool_input") or {}
    raw_path = str(tool_input.get("file_path", ""))
    if not raw_path:
        sys.exit(0)

    path = _normalize(raw_path)
    _check_workflow(path)
    _check_task_heading(tool, tool_input, path)
    _check_design_conformance(tool, tool_input, path)
    if tool == "Write":
        _check_new_phase(path, str(data.get("session_id", "")))
        _check_probe_gate(tool_input, path)
    sys.exit(0)


if __name__ == "__main__":
    main()
