"""PreToolUse hook: enforce CLAUDE.md's Temporary File Policy on Write/Edit.

Stray scratch files, test logs, and result dumps written into the repo tree get
committed and pushed. CLAUDE.md bans this, the rule was ignored, so it is now
enforced by the harness.

Temp/scratch files must live in exactly one of:
    D:\\datrix\\.scripts\\       — one-off scripts, runners, helpers
    D:\\datrix\\.test-output\\   — test output, result logs
    D:\\datrix\\.tmp\\           — everything else temporary
(or the session scratchpad under %TEMP%\\claude\\...)

This hook is deliberately NARROW: it blocks only paths that carry an unambiguous
scratch signature (by name or extension). Real source, tests, docs, and config are
never touched. A false negative is fine — the docs and review still cover those.
A false positive would be infuriating, so the bar is high.

Exit codes:
  0 — allow
  2 — block (stderr becomes feedback to Claude)
"""

import json
import re
import sys

_REPO_ROOT = "d:/datrix"

# The only places a temp/scratch file may live.
_ALLOWED_DIRS = (
    "d:/datrix/.scripts/",
    "d:/datrix/.test-output/",
    "d:/datrix/.tmp/",
    "d:/datrix/.agent_output/",
    "d:/datrix/reports/",
)

# Any path containing one of these segments is a legitimate, non-temp location
# even if the filename looks scratch-ish (e.g. a fixture named `sample_output.json`).
_EXEMPT_SEGMENTS = (
    "/tests/fixtures/",
    "/test_data/",
    "/.test_results/",  # written by test.ps1 itself, by design
    "/node_modules/",
    "/.git/",
    "/scratchpad/",  # the session scratchpad
    "/appdata/local/temp/",
)

# Unambiguous scratch signatures — extension-based.
_SCRATCH_EXT_RE = re.compile(r"\.(log|tmp|bak|orig|out|dump|swp)$")

# Unambiguous scratch signatures — filename-based (basename only).
_SCRATCH_NAME_RE = re.compile(
    r"^("
    r"(tmp|temp|scratch|debug|dbg|junk|foo|bar|baz|test123|asdf)[-_.\w]*"
    r"|[-_\w]*(_|-)(scratch|tmpfile|debug_output|dump)[-_.\w]*"
    r"|(check|verify|repro|run|try|quick|oneoff|one_off)[-_]?\d*\.(py|ps1|sh|js|ts)"
    r"|(results?|output|findings|summary|notes|analysis)[-_]?\d*\.(json|txt|md|csv)"
    r")$",
    re.IGNORECASE,
)


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lower()


def _block(path: str, reason: str) -> None:
    sys.stderr.write(
        f"BLOCKED: refusing to write `{path}` — {reason}\n\n"
        "CLAUDE.md § Temporary File Policy: temp files, scratch scripts, test logs, "
        "and result dumps must NEVER be written into the repo tree. They get "
        "committed and pushed.\n\n"
        "Write it to one of these instead:\n"
        "  D:\\datrix\\.scripts\\        temporary scripts / runners / helpers\n"
        "  D:\\datrix\\.test-output\\    test output, result logs\n"
        "  D:\\datrix\\.tmp\\            all other temp / scratch files\n\n"
        "PREFER A TEST OVER A SCRATCH SCRIPT: if this check is worth proving, land it "
        "as a real test in the owning package — a scratch script proves it once and "
        "evaporates; a test proves it forever.\n\n"
        "If this is NOT a temp file (it is real source, a real test, or real docs), "
        "give it a proper name and a proper home in the owning package — the name you "
        "chose is what triggered this."
    )
    sys.exit(2)


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if tool_name not in ("Write", "Edit", "NotebookEdit"):
        sys.exit(0)

    raw_path = data.get("tool_input", {}).get("file_path", "")
    if not raw_path:
        sys.exit(0)

    path = _normalize(raw_path)

    # Only police the repo tree.
    if not path.startswith(_REPO_ROOT):
        sys.exit(0)

    # Already in a sanctioned temp location, or an exempt subtree.
    if path.startswith(_ALLOWED_DIRS) or any(seg in path for seg in _EXEMPT_SEGMENTS):
        sys.exit(0)

    basename = path.rsplit("/", 1)[-1]

    if _SCRATCH_EXT_RE.search(basename):
        _block(raw_path, "that extension marks it as a log/temp/dump artifact.")

    if _SCRATCH_NAME_RE.match(basename):
        _block(raw_path, "that filename has an unambiguous scratch/temp signature.")

    sys.exit(0)


if __name__ == "__main__":
    main()
