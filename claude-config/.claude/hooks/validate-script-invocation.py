"""PreToolUse hook: block datrix script invocations that haven't been verified.

When Claude attempts to run a powershell script from datrix/scripts/,
this hook blocks the call and reminds Claude to read the category-specific
quick-reference.md first. Claude must include the marker
VERIFIED_AGAINST_QUICK_REFERENCE in the command description to proceed.

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

    # Only intercept powershell script calls under datrix/scripts/
    if "datrix/scripts/" not in command.replace("\\", "/").lower():
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
