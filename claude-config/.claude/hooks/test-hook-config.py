"""settings.json's hook registrations must match CLAUDE.md's enforcement table.

THE FAILURE MODE: a hook registered in settings.json whose .py file is absent is still
valid JSON. Claude Code reports nothing, the guard simply never runs, and the surface it
policed is silently unguarded from then on. The inverse is just as quiet -- a guard added
to settings.json but never written into CLAUDE.md's table blocks work that agents were
never told was blocked, and they burn a turn discovering it by being refused.

This is a producer/consumer seam like any other: settings.json decides which hooks fire on
which event, CLAUDE.md's "Enforced by the Harness" table tells every agent what fires. The
two sets were never compared, and they had already drifted -- guard-repo-temp-dirs.py runs
on Bash|PowerShell as well as on edits, and the table listed only the edit registration.

Three set comparisons, each in both directions:
  1. referenced-in-settings.json  vs  present-on-disk
  2. present-on-disk              vs  registered-anywhere
  3. (event, blocking hook) pairs vs  the CLAUDE.md table's pairs

"Blocking" is derived from each hook's own source -- a hook blocks iff it can exit 2 --
so a new guard is classified by what it does, never by a list somebody has to remember to
update. The state hooks (session-context, track-mandatory-reads, arm-orchestration-run,
record-active-skill) refuse nothing and are correctly absent from a table of refusals.

Fails closed: an unreadable settings.json, an unparseable table, or an empty set on either
side is a FAILURE, never a skip. A check that cannot evaluate its input does not pass.

Run: python .claude/hooks/test-hook-config.py
"""
import json
import os
import re
import sys

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
CLAUDE_DIR = os.path.dirname(HOOKS_DIR)
SETTINGS_JSON = os.path.join(CLAUDE_DIR, "settings.json")
CLAUDE_MD = os.path.join(CLAUDE_DIR, "CLAUDE.md")

TABLE_HEADING = "## Enforced by the Harness"
BLOCK_EXIT_RE = re.compile(r"sys\.exit\(2\)")
HOOK_FILE_RE = re.compile(r"([\w.-]+\.py)")
TABLE_ROW_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(.+?)\s*\|", re.MULTILINE)

fails: list[str] = []


def check(label: str, got: object, want: object) -> None:
    """Record and print one comparison; sets are printed sorted for a readable diff."""
    ok = got == want
    if not ok:
        fails.append(
            f"{label}\n      got:  {sorted(got) if isinstance(got, set) else got!r}"
            f"\n      want: {sorted(want) if isinstance(want, set) else want!r}"
        )
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")


def die(message: str) -> None:
    """Fail closed: the check could not evaluate its input, so it denies."""
    print(f"  FAIL  {message}")
    print(f"\n1 FAILURE(S):\n  - {message}")
    sys.exit(1)


def read_text(path: str) -> str:
    """Read a required input; an unreadable one is a failure, not a skip."""
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        die(f"cannot read {path}: {exc}")
    return ""


def owned_hook_files() -> set[str]:
    """Every hook this repo ships, excluding `_` helpers and these `test-` self-tests."""
    return {
        name
        for name in os.listdir(HOOKS_DIR)
        if name.endswith(".py") and not name.startswith(("_", "test-"))
    }


def registered_pairs(settings: dict) -> set[tuple[str, str]]:
    """{(event-with-matcher, hook filename)} exactly as settings.json registers them.

    `PreToolUse` + matcher `Bash|PowerShell` -> `PreToolUse(Bash|PowerShell)`; an event
    with no matcher (Stop, SessionStart) keeps its bare name, matching how CLAUDE.md's
    table spells it.
    """
    pairs: set[tuple[str, str]] = set()
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict) or not hooks:
        die("settings.json declares no hooks -- the comparison would be vacuous")
    for event, blocks in hooks.items():
        for block in blocks:
            matcher = block.get("matcher")
            label = f"{event}({matcher})" if matcher else event
            for hook in block.get("hooks", []):
                found = HOOK_FILE_RE.search(hook.get("command", ""))
                if not found:
                    die(f"{label} registers a command with no .py file: {hook!r}")
                pairs.add((label, found.group(1)))
    return pairs


def documented_pairs(claude_md: str) -> set[tuple[str, str]]:
    """{(event, hook filename)} claimed by CLAUDE.md's enforcement table.

    The table escapes the matcher's pipe for markdown (`Bash\\|PowerShell`); unescape it
    so both sides of the comparison spell the event the same way. One cell may name
    several hooks.
    """
    start = claude_md.find(TABLE_HEADING)
    if start < 0:
        die(f"CLAUDE.md has no '{TABLE_HEADING}' section to compare against")
    end = claude_md.find("\n## ", start + len(TABLE_HEADING))
    section = claude_md[start : end if end > 0 else len(claude_md)]

    pairs: set[tuple[str, str]] = set()
    for event, hook_cell in TABLE_ROW_RE.findall(section):
        if event == "Event":  # the header row
            continue
        for hook in HOOK_FILE_RE.findall(hook_cell):
            pairs.add((event.replace("\\|", "|"), hook))
    return pairs


def blocking_hooks(names: set[str]) -> set[str]:
    """Hooks that can refuse -- derived from source, so a new guard classifies itself."""
    return {
        name
        for name in names
        if BLOCK_EXIT_RE.search(read_text(os.path.join(HOOKS_DIR, name)))
    }


raw_settings = read_text(SETTINGS_JSON)
try:
    parsed_settings = json.loads(raw_settings)
except json.JSONDecodeError as exc:
    die(f"settings.json is not valid JSON: {exc}")

on_disk = owned_hook_files()
registered = registered_pairs(parsed_settings)
documented = documented_pairs(read_text(CLAUDE_MD))

referenced = {hook for _, hook in registered}
blocking = blocking_hooks(on_disk)
non_blocking = on_disk - blocking

print("== the inputs are non-vacuous (this check is able to fail) ==")
check("settings.json registers at least one hook", bool(registered), True)
check("CLAUDE.md's table declares at least one hook", bool(documented), True)
check("some hook on disk can refuse", bool(blocking), True)
check("some hook on disk cannot refuse (the classifier discriminates)",
      bool(non_blocking), True)

print("== every registered hook exists, and every hook is registered ==")
check("no hook is registered but missing from disk", referenced - on_disk, set())
check("no hook sits on disk unregistered (it would never run)", on_disk - referenced, set())

print("== THE DRIFT: the table and settings.json agree on what blocks what ==")
blocking_registered = {pair for pair in registered if pair[1] in blocking}
check("no blocking hook is registered but undocumented", blocking_registered - documented,
      set())
check("no documented hook is absent from settings.json", documented - registered, set())

print("== the table only claims hooks that actually refuse ==")
check("every documented hook can refuse", {h for _, h in documented} - blocking, set())

print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for failure in fails:
        print("  - " + failure)
    sys.exit(1)
print("all checks passed")
