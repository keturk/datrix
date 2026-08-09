r"""Stop hook: a config-driven checklist that costs nothing when it passes.

WHY A HOOK AND NOT A PARAGRAPH
------------------------------
A checklist written into CLAUDE.md or a skill body is paid for on EVERY turn, in
tokens, forever — and it competes for attention with everything else in context,
which is precisely how the existing rules got long enough to stop working.

A checklist evaluated here is paid for only when it FAILS. On the happy path this
hook exits 0 silently: zero tokens, no context consumed, nothing for the model to
weigh. On a failure it emits only the items that actually failed, so cost is
proportional to violations rather than to turns. That inverts the usual economics
of a rule: adding a check no longer makes every future turn more expensive.

The corollary is a hard constraint on what may go in one: every item must be
MECHANICALLY decidable from disk or the transcript. "Think carefully about X" is
not a checklist item — it cannot be evaluated, so it would have to be injected,
so it belongs in a doc the agent reads when it needs it. If an item cannot be
written as a predicate, this is the wrong home for it.

DEFINING ONE
------------
Drop a JSON file in `.claude/checklists/`. No code changes:

    {
      "name": "azure-deploy",
      "applies_to": {"skill_matches": "task-orchestrator"},
      "items": [
        {"id": "seam-census",
         "type": "glob_fresh",
         "glob": ".tmp/predeploy/*.json",
         "max_age_s": 7200,
         "fix": "Write the seam census before claiming the deploy is ready."},
        {"id": "no-unverified-claims",
         "type": "reply_lacks",
         "pattern": "(?i)\\b(should work|assuming|not verified)\\b",
         "fix": "Replace the claim with what you actually ran and what it printed."}
      ]
    }

`applies_to` is one of `{"always": true}`, `{"skill_matches": "<regex>"}` (against
the skill recorded by `record-active-skill.py`), or `{"tool_used": "<regex>"}`
(against commands run this session). Absent `applies_to` means never — a config
must opt in, so a half-written file cannot start blocking every session.

ITEM TYPES (all mechanical)
---------------------------
  file_exists / file_missing      {path}
  file_fresh                      {path, max_age_s}
  file_contains / file_lacks      {path, pattern}
  glob_exists / glob_fresh        {glob, max_age_s?}
  reply_has / reply_lacks         {pattern}          - the final assistant message
  command_ran / command_not_ran   {pattern}          - Bash/PowerShell this session

NOT A WEDGE
-----------
Per-session block cap, `stop_hook_active` short-circuit, and every error fails
OPEN. A malformed config is reported once and skipped, never enforced.

Exit codes:
  0 - allow the turn to end (and the silent, zero-cost default)
  2 - block; stderr lists ONLY the failed items
"""

from __future__ import annotations

import glob as globlib
import json
import os
import re
import sys
import time
from typing import Any, Final

from _report_language import last_assistant_text

_REPO_ROOT: Final = "d:/datrix"
_STATE_DIR: Final = os.path.join(_REPO_ROOT, ".claude", "hooks", ".state")

# The override exists so the test suite can point at a fixture directory instead of
# writing live configs into `.claude/checklists/` — a test that crashed midway would
# otherwise leave a stray config blocking every session in the workspace. It is not
# an escape hatch: hook subprocesses inherit Claude Code's environment, not a shell
# the agent can export into, so nothing the model runs can set it.
_CONFIG_DIR: Final = os.environ.get(
    "DATRIX_CHECKLIST_DIR", os.path.join(_REPO_ROOT, ".claude", "checklists")
)

# A checklist that has refused the same turn this many times is not teaching
# anything — it is stuck. Let the turn end rather than hold the session hostage.
_MAX_BLOCKS: Final = 6

# Transcripts grow without bound; a Stop hook must stay fast. Only the tail is
# scanned, and only when an item actually needs it.
_TRANSCRIPT_TAIL_BYTES: Final = 4 * 1024 * 1024

_TRANSCRIPT_TYPES: Final = frozenset(
    {"reply_has", "reply_lacks", "command_ran", "command_not_ran"}
)


def _safe(session_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "unknown")


def _state_path(session_id: str) -> str:
    return os.path.join(_STATE_DIR, f"checklist-{_safe(session_id)}.json")


def _skill_state_path(session_id: str) -> str:
    """Written by record-active-skill.py, which arms nothing and blocks nothing."""
    return os.path.join(_STATE_DIR, f"skill-{_safe(session_id)}.json")


def _read_json(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _write_json(path: str, payload: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
    except OSError:
        pass


def _abs(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(_REPO_ROOT, path)


def _age_s(path: str) -> float | None:
    try:
        return time.time() - os.path.getmtime(path)
    except OSError:
        return None


def _file_text(path: str) -> str:
    try:
        with open(_abs(path), encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _session_commands(transcript_path: str) -> str:
    """Concatenated Bash/PowerShell commands in the transcript tail."""
    try:
        size = os.path.getsize(transcript_path)
        with open(transcript_path, encoding="utf-8", errors="replace") as handle:
            if size > _TRANSCRIPT_TAIL_BYTES:
                handle.seek(size - _TRANSCRIPT_TAIL_BYTES)
                handle.readline()  # discard the partial line
            lines = handle.readlines()
    except OSError:
        return ""

    commands: list[str] = []
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        content = entry.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") not in ("Bash", "PowerShell"):
                continue
            command = block.get("input", {}).get("command", "")
            if isinstance(command, str):
                commands.append(command)
    return "\n".join(commands)


def _newest_glob_age(pattern: str) -> float | None:
    matches = globlib.glob(_abs(pattern))
    ages = [age for age in (_age_s(m) for m in matches) if age is not None]
    return min(ages) if ages else None


def _evaluate(item: dict[str, Any], reply: str, commands: str) -> bool:
    """True when the item is satisfied. An unknown type is satisfied (fail open)."""
    # `only_if_reply` is what makes a checklist able to catch the highest-value
    # defect available to a mechanical checker: a CLAIM with no corresponding ACT.
    # "The suite is green" is unfalsifiable prose on its own; "the suite is green"
    # in a session where no test command ever ran is a provable fabrication.
    gate = item.get("only_if_reply")
    if isinstance(gate, str) and not re.search(gate, reply):
        return True

    kind = item.get("type")
    pattern = item.get("pattern")
    path = item.get("path")
    pat = item.get("glob")

    if kind == "file_exists":
        return isinstance(path, str) and os.path.exists(_abs(path))
    if kind == "file_missing":
        return isinstance(path, str) and not os.path.exists(_abs(path))
    if kind == "file_fresh":
        if not isinstance(path, str):
            return True
        age = _age_s(_abs(path))
        return age is not None and age <= float(item.get("max_age_s", 7200))
    if kind == "file_contains":
        return bool(isinstance(pattern, str) and re.search(pattern, _file_text(str(path))))
    if kind == "file_lacks":
        return not (isinstance(pattern, str) and re.search(pattern, _file_text(str(path))))
    if kind == "glob_exists":
        return bool(isinstance(pat, str) and globlib.glob(_abs(pat)))
    if kind == "glob_fresh":
        if not isinstance(pat, str):
            return True
        age = _newest_glob_age(pat)
        return age is not None and age <= float(item.get("max_age_s", 7200))
    if kind == "reply_has":
        return bool(isinstance(pattern, str) and re.search(pattern, reply))
    if kind == "reply_lacks":
        return not (isinstance(pattern, str) and re.search(pattern, reply))
    if kind == "command_ran":
        return bool(isinstance(pattern, str) and re.search(pattern, commands))
    if kind == "command_not_ran":
        return not (isinstance(pattern, str) and re.search(pattern, commands))
    return True


def _applies(config: dict[str, Any], skill: str, commands_needed: bool) -> bool | None:
    """True/False, or None when the answer needs the transcript we have not read."""
    rule = config.get("applies_to")
    if not isinstance(rule, dict):
        return False
    if rule.get("always") is True:
        return True
    matcher = rule.get("skill_matches")
    if isinstance(matcher, str) and matcher:
        return bool(re.search(matcher, skill, re.IGNORECASE))
    if isinstance(rule.get("tool_used"), str):
        return None if not commands_needed else True
    return False


def _configs() -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for path in sorted(globlib.glob(os.path.join(_CONFIG_DIR, "*.json"))):
        config = _read_json(path)
        if config.get("items"):
            config["_path"] = path
            found.append(config)
    return found


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    if data.get("stop_hook_active"):
        sys.exit(0)

    configs = _configs()
    if not configs:
        sys.exit(0)  # the common case: nothing configured, nothing spent

    session_id = data.get("session_id") or ""
    skill = str(_read_json(_skill_state_path(session_id)).get("skill", ""))

    active = [c for c in configs if _applies(c, skill, False) is not False]
    if not active:
        sys.exit(0)

    # Only now is reading the transcript justified.
    needs_transcript = any(
        item.get("type") in _TRANSCRIPT_TYPES or "only_if_reply" in item
        for config in active
        for item in config.get("items", [])
        if isinstance(item, dict)
    )
    transcript_path = data.get("transcript_path", "")
    reply = last_assistant_text(transcript_path) if needs_transcript else ""
    commands = _session_commands(transcript_path) if needs_transcript else ""

    failures: list[str] = []
    for config in active:
        rule = config.get("applies_to", {})
        matcher = rule.get("tool_used") if isinstance(rule, dict) else None
        if isinstance(matcher, str) and not re.search(matcher, commands):
            continue
        for item in config.get("items", []):
            if not isinstance(item, dict) or _evaluate(item, reply, commands):
                continue
            label = item.get("id") or item.get("type") or "?"
            fix = str(item.get("fix", "")).strip()
            failures.append(f"  [{config.get('name', '?')}/{label}] {fix or 'unsatisfied'}")

    if not failures:
        sys.exit(0)

    state_path = _state_path(session_id)
    state = _read_json(state_path)
    blocks = int(state.get("blocks", 0) or 0)
    if blocks >= _MAX_BLOCKS:
        sys.exit(0)
    state["blocks"] = blocks + 1
    _write_json(state_path, state)

    sys.stderr.write(
        "STOP REJECTED — checklist items are unsatisfied:\n\n"
        + "\n".join(failures)
        + "\n\nEach line is a mechanical check evaluated against disk or this "
        "session's transcript, not an opinion about your summary. Satisfy them and "
        "finish, or — if one is genuinely wrong for this situation — say so "
        "explicitly to Jon rather than rephrasing around it."
    )
    sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - a checklist must never wedge a session
        sys.exit(0)
