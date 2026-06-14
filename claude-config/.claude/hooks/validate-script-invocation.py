"""PreToolUse hook: block datrix script invocations that haven't been verified.

When Claude attempts to run a powershell script from datrix/scripts/,
this hook blocks the call and reminds Claude to read the category-specific
quick-reference.md first. Claude must include the marker
VERIFIED_AGAINST_QUICK_REFERENCE in the command description to proceed.

It also hard-blocks two test-invocation anti-patterns globally (these cannot
be overridden by the VERIFIED marker):
  1. test.ps1 with -NoSave or -VerboseOutput. -VerboseOutput burns tokens for
     no benefit; -NoSave hides the saved test progress/results. Agents must run
     test.ps1 with neither flag.
  2. Running pytest directly. All tests go through test.ps1 / test-single.ps1,
     which activate the shared venv and save timestamped results.

Category quick-reference files:
  datrix/scripts/test/quick-reference.md
  datrix/scripts/dev/quick-reference.md
  datrix/scripts/git/quick-reference.md
  datrix/scripts/metrics/quick-reference.md
  datrix/scripts/visualize/quick-reference.md
  datrix/scripts/tasks/quick-reference.md

Exit codes:
  0 — allow (outputs JSON with permissionDecision)
  2 — block (stderr becomes feedback to Claude)
"""

import json
import re
import sys

# Map script subfolder to its category quick-reference file
_CATEGORY_MAP = {
    "test": "test/quick-reference.md",
    "dev": "dev/quick-reference.md",
    "git": "git/quick-reference.md",
    "metrics": "metrics/quick-reference.md",
    "visualize": "visualize/quick-reference.md",
    "tasks": "tasks/quick-reference.md",
}

_SCRIPTS_BASE = "d:/datrix/datrix/scripts/"

# Banned test.ps1 flags (lowercased). -VerboseOutput burns tokens; -NoSave
# hides saved test progress. Neither is ever allowed, even with the
# VERIFIED_AGAINST_QUICK_REFERENCE marker.
_BANNED_TEST_FLAGS = ("-nosave", "-verboseoutput")

# Direct pytest invocation (not wrapped in a .ps1 test script). Matches
# `pytest ...`, `python -m pytest`, `py.test`, `python -m py.test` as a
# command token, so substrings inside paths/keywords do not false-positive.
_DIRECT_PYTEST_RE = re.compile(
    r"(?:^|[\s;|&(])(?:py\.?test\b|python[\w.]*\s+(?:-\S+\s+)*-m\s+py\.?test\b)"
)


def _block(msg: str) -> None:
    """Write feedback to stderr and exit with the block code."""
    sys.stderr.write(msg)
    sys.exit(2)


def _detect_category(command: str) -> str:
    """Extract the script category from the command path."""
    normalized = command.replace("\\", "/").lower()
    # Match datrix/scripts/<category>/
    match = re.search(r"datrix/scripts/(\w+)/", normalized)
    if match:
        category = match.group(1)
        if category in _CATEGORY_MAP:
            return _CATEGORY_MAP[category]
    # Fallback to root index
    return "quick-reference.md"


def main() -> None:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Can't parse input — allow by default
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    command = tool_input.get("command", "")
    description = tool_input.get("description", "")

    normalized = command.replace("\\", "/").lower()

    # ── Hard bans (cannot be overridden by VERIFIED_AGAINST_QUICK_REFERENCE) ──

    # 1. test.ps1 must never carry -NoSave or -VerboseOutput.
    if "test.ps1" in normalized:
        banned = [flag for flag in _BANNED_TEST_FLAGS if flag in normalized]
        if banned:
            _block(
                "BLOCKED: test.ps1 must not be run with "
                f"{' or '.join(banned)}.\n"
                "-VerboseOutput burns tokens for no benefit, and -NoSave hides "
                "the saved test progress/results.\n"
                "Re-run test.ps1 with NEITHER flag — the default minimal output "
                "plus the saved timestamped .test_results/ folder is what you "
                "must use. Read index.json for the canonical result."
            )

    # 2. Never run pytest directly — all tests go through test.ps1 /
    #    test-single.ps1 (which activate the shared venv and save results).
    if ".ps1" not in normalized and _DIRECT_PYTEST_RE.search(normalized):
        _block(
            "BLOCKED: do not invoke pytest directly.\n"
            "Run tests through the PowerShell wrappers, which activate the "
            "shared venv and save timestamped results:\n"
            '  powershell -File "d:/datrix/datrix/scripts/test/test.ps1" '
            "{package-name} -Specific \"{test-path}\"\n"
            "  (or test-single.ps1 for a single node id). "
            "Then read the run's index.json for the canonical result."
        )

    # Only intercept powershell script calls under datrix/scripts/
    if "datrix/scripts/" not in normalized:
        sys.exit(0)

    # If description contains the verification marker, allow
    if "VERIFIED_AGAINST_QUICK_REFERENCE" in description:
        sys.exit(0)

    # Determine which category quick-reference to point to
    ref_file = _detect_category(command)
    ref_path = f"{_SCRIPTS_BASE}{ref_file}"

    # Block: Claude hasn't verified the parameters
    msg = (
        "BLOCKED: You are about to run a datrix script. "
        "Before executing, you MUST:\n"
        f"1. Read {ref_path}\n"
        "2. Verify that EVERY parameter you are passing is documented there\n"
        "3. Re-issue the command with description containing "
        "VERIFIED_AGAINST_QUICK_REFERENCE\n\n"
        "Do NOT guess parameters. Do NOT invent script names. "
        "Look them up first."
    )
    sys.stderr.write(msg)
    sys.exit(2)


if __name__ == "__main__":
    main()
