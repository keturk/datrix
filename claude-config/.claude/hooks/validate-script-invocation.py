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
  datrix/scripts/review/quick-reference.md
  datrix/scripts/skill/quick-reference.md

Exit codes:
  0 — allow (outputs JSON with permissionDecision)
  2 — block (stderr becomes feedback to Claude)
"""

import json
import re
import sys

from _command_shape import executable_text, invoked_scripts, segments

# Map script subfolder to its category quick-reference file
_CATEGORY_MAP = {
    "test": "test/quick-reference.md",
    "dev": "dev/quick-reference.md",
    "git": "git/quick-reference.md",
    "metrics": "metrics/quick-reference.md",
    "visualize": "visualize/quick-reference.md",
    "tasks": "tasks/quick-reference.md",
    "review": "review/quick-reference.md",
    "skill": "skill/quick-reference.md",
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

# Group-generation flags on generate.ps1. CLAUDE.md ("Generation granularity"):
# regenerate only the affected project; never run group generation to verify a
# change. One sweep costs minutes per example and proves nothing a unit test in
# the owning package would not prove permanently. Scoped to generate.ps1 alone —
# `-All` is legitimate on test.ps1 / compile.ps1 / libcst.ps1 / semgrep.ps1.
_GROUP_GENERATION_FLAGS = ("-all", "-domains", "-testset")
# The same refusals spelled as the generate module's own flags: what its POSIX
# twin `generate.sh` and a direct `python -m datrix_scripts.dev.generate` take.
_GROUP_GENERATION_MODULE_FLAGS = ("--all", "--domains", "--test-set")

# `generate.ps1` / `generate.sh` by file name, so `generate-doc-fragments.ps1`
# and `generate-test-rules.ps1` (which legitimately take -All) never match.
_GENERATE_SCRIPT = "generate.ps1"
_GENERATE_TWIN = "generate.sh"
# The module behind both wrappers, run directly: `-m` alone or closing a group of
# the interpreter's argument-free flags (`-Im`, lowercased here), with or without
# a space before the module name, as the interpreter accepts each.
_GENERATE_MODULE_RE = re.compile(
    r"(?:^|[\s;|&(])-[bdeiopqrsuvx]*m\s*datrix_scripts\.dev\.generate(?![\w.])"
)
_SCRIPTS_MARKER = "datrix/scripts/"


def _block(msg: str) -> None:
    """Write feedback to stderr and exit with the block code."""
    sys.stderr.write(msg)
    sys.exit(2)


def _generate_runs(segment: str) -> tuple[bool, bool]:
    """Whether this statement executes `generate.ps1`, and whether it executes
    its module-flag forms (`generate.sh`, `-m datrix_scripts.dev.generate`) --
    run, not merely named."""
    names = {script.path.rsplit("/", 1)[-1].lower() for script in invoked_scripts(segment)}
    module_form = _GENERATE_TWIN in names or bool(_GENERATE_MODULE_RE.search(segment))
    return _GENERATE_SCRIPT in names, module_form


def _used_flags(text: str, flags: tuple[str, ...]) -> list[str]:
    """The *flags* written as whole arguments in *text* (`--test-set=x` counts)."""
    return [flag for flag in flags if re.search(rf"(?:^|\s){re.escape(flag)}(?![\w-])", text)]


def _scripts_paths_run(command: str) -> list[str]:
    """Lowercased paths of the scripts under `datrix/scripts/` the command executes."""
    return [
        script.path.lower()
        for script in invoked_scripts(command)
        if _SCRIPTS_MARKER in script.path.lower()
    ]


def _detect_category(script_path: str) -> str:
    """Extract the script category from an invoked script's path."""
    # Match datrix/scripts/<category>/
    match = re.search(r"datrix/scripts/(\w+)/", script_path)
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

    # Every check below asks "does this command invoke script X", and answered it
    # by testing whether X's name appeared ANYWHERE in the text. That confuses
    # naming a script with running one: `grep -n "Unit" datrix/scripts/test/test.ps1`
    # was refused for lacking a quick-reference marker, blocking an agent from
    # reading the source of the very script this hook guards. Read-only segments
    # are dropped first, so only text that could actually execute is analysed. A
    # real invocation chained alongside a read still survives and still blocks.
    normalized = executable_text(command).replace("\\", "/").lower()

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

    # 3. generate.ps1 must never run group generation. Verification regenerates
    #    the ONE affected project; a corpus sweep is wasted minutes per example
    #    and belongs in a unit test in the owning package instead. The flags are
    #    read from the statements that execute generate.ps1, its twin
    #    generate.sh or its module, each in that form's own spelling.
    used: list[str] = []
    for part in segments(normalized):
        runs_wrapper, runs_module_form = _generate_runs(part)
        if runs_wrapper:
            used += _used_flags(part, _GROUP_GENERATION_FLAGS)
        if runs_module_form:
            used += _used_flags(part, _GROUP_GENERATION_MODULE_FLAGS)
    if used:
        _block(
            f"BLOCKED: generate.ps1 (generate.sh, datrix_scripts.dev.generate) must not be run with "
            f"{' or '.join(dict.fromkeys(used))}.\n"
            "CLAUDE.md (Generation granularity): regenerate only the AFFECTED "
            "project's system.dtrx. Never run group/-All/-TestSet/-Domains "
            "generation.\n"
            "Each example costs minutes to generate, and which example is worked "
            "next is Jon's call, not an agent's.\n"
            "To verify one project:\n"
            '  powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" '
            '"d:/datrix/datrix/examples/{group}/{example}/system.dtrx" -L {language}\n'
            "To prove a fix generalizes beyond one example, write a test in the "
            "owning datrix-codegen-* package — it proves the invariant forever, "
            "whereas a sweep proves it once and evaporates."
        )

    # Only a command that RUNS a script under datrix/scripts/ needs the marker. A
    # path held in a variable, listed in a `for`, or written in a heredoc body is
    # named, not run (`_command_shape.invoked_scripts`).
    run_paths = _scripts_paths_run(command)
    if not run_paths:
        sys.exit(0)

    # If description contains the verification marker, allow
    if "VERIFIED_AGAINST_QUICK_REFERENCE" in description:
        sys.exit(0)

    # Determine which category quick-reference to point to
    ref_file = _detect_category(run_paths[0])
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
