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

  <name>.cases.approved
                  Jon's approval of one declarative-case migration proposal (``cases.ps1
                  migrate``): ``proposal: <file name>`` (a JSON proposal in the proposals
                  directory), ``sha256: <hex>`` of its bytes, then one security or ``not in``
                  row id per line.

While armed, for the armed session only:
  - Write of a ``test_*.py`` that does not exist yet under ``tests_root`` is refused unless
    some ``*.approved`` file lists it. Editing or overwriting an existing module is allowed.
  - Write/Edit of a ``*.cases.yaml`` under ``tests_root`` that adds a case id no approved
    proposal holds is refused, so a direct edit of a case file cannot bypass ``cases.ps1
    accept``. A proposal approves nothing when its bytes no longer match its approval's hash,
    or when the approval does not name every security or ``not in`` row it holds (a row is a
    security row when its record is flagged or its own tags hold a security tag). Case ids are
    the ``id`` of every row the file parses to as YAML, plus every ``id:`` key the case-id
    grammar (``<area>.<slug>``) matches in the raw text; reading more only refuses more.
  - Write/Edit of a ``.dtrx`` under ``tests_root`` that adds an annotation or directive line
    (``// @expect ...``, ``// @tags ...``) -- or creates a per-code fixture holding one -- is
    refused unless an approved, unchanged annotation proposal (``cases.ps1 migrate
    -Annotations``) writes that line to that file, so a hand edit cannot bypass ``cases.ps1
    accept``. An annotation proposal approves nothing when its approval does not name every
    security record by id.
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

import hashlib
import json
import os
import re
import sys
from collections import Counter
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
#: A case file, and the approval of a case-migration proposal.
CASE_FILE_SUFFIX: Final[str] = ".cases.yaml"
CASES_APPROVAL_SUFFIX: Final[str] = ".cases.approved"
#: Where ``cases.ps1 migrate`` writes its JSON proposals.
PROPOSALS_DIR: Final[str] = "d:/datrix/.tmp/case-proposals"
#: The test library holding the closed security-tag list (stdlib only, importable by this interpreter).
_TESTING_SRC: Final[str] = "d:/datrix/datrix-testing/src"
#: Every case id a case file's text holds: the value of each ``id:`` key in the case-id grammar.
CASE_ID_RE: Final[re.Pattern[str]] = re.compile(
    r"""(?:^|[\s{,-])["']?id["']?[ \t]*:[ \t]*["']?([a-z0-9]+(?:-[a-z0-9]+)*(?:\.[a-z0-9]+(?:-[a-z0-9]+)*)+)""",
    re.MULTILINE,
)
_CASE_DISPOSITION: Final[str] = "case"
#: An annotation proposal's disposition of a test whose fact moves onto a fixture line.
_ANNOTATE: Final[str] = "annotate"
#: A fixture, and a line carrying an annotation or a directive (``// @expect ...``).
DTRX_SUFFIX: Final[str] = ".dtrx"
ANNOTATION_LINE_RE: Final[re.Pattern[str]] = re.compile(r"//[ \t]*@[a-z]")


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
        if not name.endswith(APPROVAL_SUFFIX) or name.endswith(CASES_APPROVAL_SUFFIX):
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


def _approval_fields(path: str) -> tuple[str, str, set[str]] | None:
    """The ``(proposal, sha256, named row ids)`` a case approval holds, or None when it names no proposal."""
    fields: dict[str, str] = {}
    named: set[str] = set()
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return None
    for line in lines:
        entry = line.split(COMMENT_MARKER, 1)[0].strip()
        key, separator, value = entry.partition(":")
        if separator and key.strip() in ("proposal", "sha256"):
            fields[key.strip()] = value.strip()
        elif entry:
            named.add(entry)
    if "proposal" not in fields or "sha256" not in fields:
        return None
    return fields["proposal"], fields["sha256"].lower(), named


def _security_tags() -> frozenset[str]:
    """The closed security-tag list from its one home, or empty when the test library is not importable."""
    if _TESTING_SRC not in sys.path:
        sys.path.insert(0, _TESTING_SRC)
    try:
        from datrix_testing.cases.security import SECURITY_TAGS
    except ImportError:
        return frozenset()
    return SECURITY_TAGS


def _row_id_and_protection(record: dict[str, object], security_tags: frozenset[str]) -> tuple[str | None, bool]:
    """A ``case`` record's row id, and whether the approval must name it (security or ``not in``)."""
    case = record.get("case")
    if isinstance(case, dict) and isinstance(case.get("id"), str):
        tags = case.get("tags")
        tagged = isinstance(tags, list) and bool(security_tags.intersection(str(tag) for tag in tags))
        return case["id"], bool(record.get("security")) or bool(record.get("not_in")) or tagged
    existing = record.get("existing")
    if isinstance(existing, str):
        return existing, bool(record.get("security")) or bool(record.get("not_in"))
    return None, False


def _proposal_ids(path: str, approved_hash: str, named: set[str]) -> set[str]:
    """The case ids of the proposal at ``path`` when its bytes still match ``approved_hash`` and the
    approval names every security or ``not in`` row of it; otherwise none."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError:
        return set()
    if hashlib.sha256(raw).hexdigest() != approved_hash:
        return set()
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return set()
    security_tags = _security_tags()
    ids: set[str] = set()
    protected: set[str] = set()
    records = document.get("records") if isinstance(document, dict) else None
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict) or record.get("disposition") != _CASE_DISPOSITION:
            continue
        row_id, is_protected = _row_id_and_protection(record, security_tags)
        if row_id is None:
            continue
        ids.add(row_id)
        if is_protected:
            protected.add(row_id)
    return ids if protected <= named else set()


def approved_case_ids(gate_dir: str) -> set[str]:
    """Every case id an approved, unchanged case-migration proposal holds."""
    proposals_dir = os.environ.get("DATRIX_CASE_PROPOSALS_DIR") or PROPOSALS_DIR
    ids: set[str] = set()
    try:
        names = os.listdir(gate_dir)
    except OSError:
        return ids
    for name in names:
        if not name.endswith(CASES_APPROVAL_SUFFIX):
            continue
        fields = _approval_fields(os.path.join(gate_dir, name))
        if fields is None:
            continue
        proposal, approved_hash, named = fields
        ids |= _proposal_ids(os.path.join(proposals_dir, os.path.basename(proposal)), approved_hash, named)
    return ids


def _parsed_case_ids(text: str) -> set[str]:
    """The ``id`` of every row *text* parses to as YAML (every scalar a string); none when PyYAML is
    not importable or the text is not a YAML list."""
    try:
        import yaml
    except ImportError:
        return set()
    try:
        rows = yaml.load(text, Loader=yaml.BaseLoader)  # noqa: S506 - BaseLoader builds no object
    except yaml.YAMLError:
        return set()
    if not isinstance(rows, list):
        return set()
    return {row["id"] for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str)}


def case_ids(text: str) -> set[str]:
    """Every case id a case file's *text* holds: its parsed rows' ids and every ``id:`` key the
    case-id grammar matches (a block-scalar or otherwise unusual spelling cannot hide an id)."""
    return set(CASE_ID_RE.findall(text)) | _parsed_case_ids(text)


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def _after_text(tool_name: str, tool_input: dict[str, object], before: str) -> str | None:
    """The file's text after the Write or Edit, or None when the Edit cannot be applied."""
    if tool_name == "Write":
        content = tool_input.get("content")
        return content if isinstance(content, str) else ""
    old = tool_input.get("old_string")
    new = tool_input.get("new_string")
    if not isinstance(old, str) or not isinstance(new, str) or not old or old not in before:
        return None
    return before.replace(old, new) if tool_input.get("replace_all") else before.replace(old, new, 1)


def check_case_file(
    tool_name: str, tool_input: dict[str, object], raw_path: str, path: str, gate_dir: str, session_id: str
) -> None:
    """Refuse adding, while armed, a case id that no approved proposal holds."""
    armed = read_armed(gate_dir)
    if armed is None or armed["session_id"] != session_id:
        return
    if not path.startswith(armed["tests_root"] + "/") or not path.endswith(CASE_FILE_SUFFIX):
        return
    before = _read(raw_path)
    after = _after_text(tool_name, tool_input, before)
    if after is None:
        return
    added = case_ids(after) - case_ids(before)
    unapproved = sorted(added - approved_case_ids(gate_dir))
    if unapproved:
        block(
            f"this edit adds case id(s) {unapproved} to `{raw_path}` while the test rebuild is armed, and no "
            f"approved proposal holds them. A case id reaches a case file only through `cases.ps1 accept` of a "
            f"proposal Jon approved (`<name>{CASES_APPROVAL_SUFFIX}` in {GATE_DIR}). Run `cases.ps1 migrate`, "
            "stop, and ask Jon to approve the proposal."
        )


def annotation_lines(text: str) -> Counter[str]:
    """Every line of a ``.dtrx`` *text* that carries an annotation or a directive (``// @word``),
    stripped, with its count; a code line with a trailing annotation counts whole."""
    return Counter(line.strip() for line in text.splitlines() if ANNOTATION_LINE_RE.search(line))


def _annotate_lines(record: dict[str, object]) -> list[tuple[str, str]]:
    """``(tests-root-relative path, annotation line)`` for every annotation an ``annotate`` record writes."""
    edits = record.get("edits")
    found: list[tuple[str, str]] = []
    for edit in edits if isinstance(edits, list) else []:
        if not isinstance(edit, dict) or not isinstance(edit.get("path"), str):
            continue
        lines = edit.get("lines")
        if edit.get("edit") == "fixture" and isinstance(edit.get("text"), str):
            lines = edit["text"].splitlines()
        found.extend(
            (normalize(edit["path"]), line.strip())
            for line in (lines if isinstance(lines, list) else [])
            if isinstance(line, str) and ANNOTATION_LINE_RE.search(line)
        )
    return found


def _approved_annotation_lines(path: str, approved_hash: str, named: set[str]) -> Counter[tuple[str, str]]:
    """The annotation lines of the annotation proposal at ``path`` when its bytes still match
    ``approved_hash`` and the approval names every security record of it; otherwise none."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        document = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return Counter()
    if hashlib.sha256(raw).hexdigest() != approved_hash or not isinstance(document, dict):
        return Counter()
    records = [r for r in document.get("records") or [] if isinstance(r, dict) and r.get("disposition") == _ANNOTATE]
    if any(record.get("security") and record.get("id") not in named for record in records):
        return Counter()
    return Counter(entry for record in records for entry in _annotate_lines(record))


def approved_annotations(gate_dir: str) -> Counter[tuple[str, str]]:
    """Every ``(path, annotation line)`` an approved, unchanged annotation proposal writes."""
    proposals_dir = os.environ.get("DATRIX_CASE_PROPOSALS_DIR") or PROPOSALS_DIR
    approved: Counter[tuple[str, str]] = Counter()
    try:
        names = os.listdir(gate_dir)
    except OSError:
        return approved
    for name in names:
        fields = _approval_fields(os.path.join(gate_dir, name)) if name.endswith(CASES_APPROVAL_SUFFIX) else None
        if fields is not None:
            proposal, approved_hash, named = fields
            approved |= _approved_annotation_lines(
                os.path.join(proposals_dir, os.path.basename(proposal)), approved_hash, named
            )
    return approved


def check_annotated_fixture(
    tool_name: str, tool_input: dict[str, object], raw_path: str, path: str, gate_dir: str, session_id: str
) -> None:
    """Refuse adding, while armed, an annotation (or a per-code fixture) no approved proposal writes."""
    armed = read_armed(gate_dir)
    if armed is None or armed["session_id"] != session_id:
        return
    tests_root = armed["tests_root"]
    if not path.startswith(tests_root + "/") or not path.endswith(DTRX_SUFFIX):
        return
    before = _read(raw_path)
    after = _after_text(tool_name, tool_input, before)
    if after is None:
        return
    relative = path[len(tests_root) + 1:]
    allowed = Counter({line: count for (where, line), count in approved_annotations(gate_dir).items() if where == relative})
    unapproved = sorted((annotation_lines(after) - annotation_lines(before)) - allowed)
    if unapproved:
        block(
            f"this edit adds annotation line(s) {unapproved[:5]} to `{raw_path}` while the test rebuild is armed, "
            f"and no approved proposal writes them. A fixture annotation (or a per-code fixture) reaches the armed "
            f"tests root only through `cases.ps1 accept` of an annotation proposal Jon approved "
            f"(`cases.ps1 migrate <package> <module> -Annotations`, then `<name>{CASES_APPROVAL_SUFFIX}` in {GATE_DIR})."
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
    if tool_name in ("Write", "Edit") and isinstance(session_id, str):
        check_case_file(tool_name, tool_input, raw_path, path, gate_dir, session_id)
        check_annotated_fixture(tool_name, tool_input, raw_path, path, gate_dir, session_id)
    sys.exit(EXIT_ALLOW)


if __name__ == "__main__":
    main()
