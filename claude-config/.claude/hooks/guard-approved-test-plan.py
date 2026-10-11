"""PreToolUse hook: a new test module needs Jon's approval while a test rebuild is armed.

THE FAILURE MODE: a rebuild planned as "inventory the records, have the plan approved, then
write one table per decision source" drifted, over a long run, into writing one replacement
module per old module, reading every old test body. The plan lived only in prose, so nothing
stopped the drift. This hook makes the approval step mechanical: while a rebuild is armed,
the agent cannot create a test module that the approved plan does not name.

The gate lives in ``D:\\datrix\\.tmp\\approval-gate\\``:

  armed.json      ``{"session_id": "<id>", "tests_root": "<absolute tests dir>"}``. Arms the
                  gate for that one session (another session editing the same package is
                  never affected). The agent may create it; it may not change or remove it.
  <name>.approved One path per line, relative to ``tests_root`` (``unit/auth/test_x.py``);
                  ``#`` starts a comment. Only Jon writes these, from his own terminal.

While armed, for the armed session only:
  - Write of a ``test_*.py`` that does not exist yet under ``tests_root`` is refused unless
    some ``*.approved`` file lists it. Editing or overwriting an existing module is allowed.
  - Write/Edit of anything in the gate directory is refused, except creating ``armed.json``
    when it does not exist.
  - A Bash/PowerShell command naming the gate directory is refused, so an approval cannot be
    written, copied in, or the gate disarmed from a shell. Reading uses the Read tool.

Fails open: no armed.json, an unreadable one, or a payload without the expected fields
allows the call.

Exit codes:
  0 -- allow
  2 -- block (stderr becomes feedback to Claude)
"""

import json
import os
import sys
from typing import Final

#: The directory holding the arming file and Jon's approvals.
GATE_DIR: Final[str] = "d:/datrix/.tmp/approval-gate"
#: The arming file's name inside ``GATE_DIR``.
ARMED_FILE: Final[str] = "armed.json"
#: The suffix of an approval file inside ``GATE_DIR``.
APPROVAL_SUFFIX: Final[str] = ".approved"
#: The basename shape of a test module the gate polices.
TEST_PREFIX: Final[str] = "test_"
TEST_SUFFIX: Final[str] = ".py"
#: Tools that write files.
FILE_TOOLS: Final[frozenset[str]] = frozenset({"Write", "Edit", "NotebookEdit"})
#: Tools that run shell commands.
SHELL_TOOLS: Final[frozenset[str]] = frozenset({"Bash", "PowerShell"})
#: The hook protocol's allow exit code; a refusal exits 2, spelled literally so the
#: hook-config test classifies this hook as blocking.
EXIT_ALLOW: Final[int] = 0
#: The comment marker in an approval file.
COMMENT_MARKER: Final[str] = "#"


def normalize(path: str) -> str:
    """Return ``path`` with forward slashes, lower-cased, without a trailing slash."""
    return path.replace("\\", "/").lower().rstrip("/")


def block(message: str) -> None:
    """Refuse the tool call with ``message`` as Claude's feedback."""
    sys.stderr.write(f"BLOCKED (approval gate): {message}\n")
    sys.exit(2)


def read_armed(gate_dir: str) -> dict[str, str] | None:
    """Return the arming record, or None when the gate is not armed or the record is unreadable."""
    armed_path = os.path.join(gate_dir, ARMED_FILE)
    try:
        with open(armed_path, encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(record, dict):
        return None
    session_id = record.get("session_id")
    tests_root = record.get("tests_root")
    if not isinstance(session_id, str) or not isinstance(tests_root, str):
        return None
    return {"session_id": session_id, "tests_root": normalize(tests_root)}


def approved_paths(gate_dir: str) -> set[str]:
    """Every tests-root-relative path listed in an approval file, normalized."""
    approved: set[str] = set()
    try:
        names = os.listdir(gate_dir)
    except OSError:
        return approved
    for name in names:
        if not name.endswith(APPROVAL_SUFFIX):
            continue
        try:
            with open(os.path.join(gate_dir, name), encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        except OSError:
            continue
        for line in lines:
            entry = line.split(COMMENT_MARKER, 1)[0].strip()
            if entry:
                approved.add(normalize(entry))
    return approved


def check_gate_dir_write(tool_name: str, raw_path: str, path: str, gate_dir: str) -> None:
    """Refuse every write into the gate directory except creating a missing arming file."""
    if not path.startswith(gate_dir + "/"):
        return
    creates_arming = (
        tool_name == "Write"
        and path == f"{gate_dir}/{ARMED_FILE}"
        and not os.path.exists(raw_path)
    )
    if creates_arming:
        return
    block(
        f"`{raw_path}` is in the approval gate directory. Approvals are Jon's: he writes "
        f"`*{APPROVAL_SUFFIX}` files from his own terminal, and the arming file cannot be "
        "changed or removed by the agent. Put the proposed plan elsewhere under "
        "D:\\datrix\\.tmp\\ and ask Jon to approve it."
    )


def check_new_test_module(raw_path: str, path: str, gate_dir: str, session_id: str) -> None:
    """Refuse creating an unapproved test module under the armed tests root."""
    armed = read_armed(gate_dir)
    if armed is None or armed["session_id"] != session_id:
        return
    tests_root = armed["tests_root"]
    if not path.startswith(tests_root + "/"):
        return
    basename = path.rsplit("/", 1)[-1]
    if not (basename.startswith(TEST_PREFIX) and basename.endswith(TEST_SUFFIX)):
        return
    if os.path.exists(raw_path):
        return
    relative = path[len(tests_root) + 1:]
    if relative in approved_paths(gate_dir):
        return
    block(
        f"`{relative}` is a new test module under the armed tests root `{tests_root}`, and no "
        f"approval file in {GATE_DIR} lists it. Write the inventory and the proposed module "
        "list for this cluster, stop, and ask Jon to approve it. If the module belongs in an "
        "approved one, add the rows there instead."
    )


def check_shell(command: str, gate_dir: str) -> None:
    """Refuse a shell command that names the gate directory."""
    if gate_dir in normalize(command):
        block(
            "a shell command may not touch the approval gate directory: approvals are written "
            "by Jon, and the gate is not disarmed from a shell. Use the Read tool to read it."
        )


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(EXIT_ALLOW)
    if not isinstance(data, dict):
        sys.exit(EXIT_ALLOW)
    tool_name = data.get("tool_name")
    tool_input = data.get("tool_input")
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        sys.exit(EXIT_ALLOW)
    gate_dir = os.environ.get("DATRIX_APPROVAL_GATE_DIR") or GATE_DIR
    gate_dir = normalize(gate_dir)

    if tool_name in SHELL_TOOLS:
        command = tool_input.get("command")
        if isinstance(command, str):
            check_shell(command, gate_dir)
        sys.exit(EXIT_ALLOW)

    if tool_name not in FILE_TOOLS:
        sys.exit(EXIT_ALLOW)
    raw_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(raw_path, str) or not raw_path:
        sys.exit(EXIT_ALLOW)
    path = normalize(raw_path)
    check_gate_dir_write(tool_name, raw_path, path, gate_dir)
    session_id = data.get("session_id")
    if tool_name == "Write" and isinstance(session_id, str):
        check_new_test_module(raw_path, path, gate_dir, session_id)
    sys.exit(EXIT_ALLOW)


if __name__ == "__main__":
    main()
