"""PreToolUse hook: no temp/scratch/output DIRECTORIES inside the package repos.

Each `datrix-*` package (and `datrix` itself) is its own git repository. A temp
directory created inside one of them is not merely untidy -- unless someone
notices and adds an ignore rule, its contents get committed and pushed. That has
already happened once: 5076 files of generated test output were committed into
the `datrix` repo before anyone caught it.

So the rule is not "ignore them", it is "never create them there". Temp output
belongs OUTSIDE every repo tree, in the workspace-level directories:

    D:\\datrix\\.scripts\\       one-off scripts, runners, helpers
    D:\\datrix\\.test-output\\   test output, result logs
    D:\\datrix\\.tmp\\           everything else temporary

This hook blocks two ways in:
  * Write/Edit/NotebookEdit whose target path lands in such a directory.
  * Bash/PowerShell commands that CREATE or WRITE one (mkdir, New-Item, a
    redirect, a copy/move, an -Output/-OutDir argument). Read-only inspection of
    an existing stray directory stays allowed -- cleaning one up must not be
    blocked by the hook that objects to it.

Detection is by directory NAME, not by guesswork: the banned names below appear
nowhere in any of the 15 repos' tracked files, so a match is unambiguous.

Exit codes:
  0 -- allow
  2 -- block (stderr becomes feedback to Claude)
"""

import json
import re
import sys

# The 15 git repositories under the workspace root. Longest-first so the
# alternation cannot match `datrix` where `datrix-codegen-aws` was meant.
_REPOS = (
    "datrix-codegen-typescript",
    "datrix-codegen-component",
    "datrix-codegen-common",
    "datrix-codegen-docker",
    "datrix-codegen-dotnet",
    "datrix-codegen-azure",
    "datrix-codegen-python",
    "datrix-extensions",
    "datrix-codegen-java",
    "datrix-codegen-aws",
    "datrix-codegen-sql",
    "datrix-language",
    "datrix-common",
    "datrix-cli",
    "datrix",
)

# Directory names that mark a temp/scratch/output location. Exact segment match,
# case-insensitive. Verified absent from every repo's tracked file list, so none
# of these can collide with real source, tests, docs, or fixtures.
_BANNED_SEGMENTS = frozenset(
    {
        ".tmp",
        "tmp",
        ".temp",
        "temp",
        ".scratch",
        "scratch",
        "scratchpad",
        ".scripts",
        ".agent_output",
        "agent_output",
        ".test_output",
        "test_output",
        ".test-output",
        "test-output",
    }
)

# `.test-output-foundation-check`, `test-output-2`, ... -- same thing with a suffix.
_BANNED_PREFIXES = (".test-output", "test-output", ".test_output", "test_output")

# Third-party / tooling trees that legitimately carry a `tmp` of their own. Their
# contents are not ours to police and are already ignored by every repo.
_EXEMPT_SEGMENTS = frozenset({"node_modules", ".venv", ".git", "site-packages"})

# Written by test.ps1 inside each package by design, and ignored there.
_EXEMPT_EXACT = frozenset({".test_results", ".benchmarks"})

# A repo-rooted path is either absolute under the workspace (`d:/datrix/<repo>/`)
# or workspace-relative (`<repo>/...`, the shell's default cwd). The workspace
# directory and the showcase repo are BOTH named `datrix`, so the relative form
# must not match after a separator -- otherwise `d:/datrix/.tmp/x` (the sanctioned
# workspace temp dir) would read as repo `datrix` plus a banned `.tmp`.
_REPO_PATH_RE = re.compile(
    r"(?:[a-z]:/datrix/|(?<![\w./-]))(" + "|".join(_REPOS) + r")/([^\s\"'|;,)]*)",
    re.IGNORECASE,
)

# A command is blocked only when the banned path is the TARGET of a write --
# inspecting or deleting an existing stray directory must stay possible. Every
# alternative is anchored at a token start (`(?<![\w.-])`), because otherwise
# `.test-output` reads as the `-output` flag and `Remove-Item` as `Move-Item`.
_WRITE_INTENT_RE = re.compile(
    r"(?:>|(?<![\w.-])(?:"
    r"mkdir|makedirs|mkdirs|new-item|touch"
    r"|out-file|set-content|add-content|tee-object|tee"
    r"|cp|copy|copy-item|mv|move|move-item"
    r"|-{1,2}out(?:put)?(?:dir|path|-dir)?"
    r")\b)",
    re.IGNORECASE,
)

# How far back to look for that write verb. Long enough to span an argument list
# like `New-Item -ItemType Directory -Path "<path>"`.
_WRITE_INTENT_WINDOW = 60

_GUIDANCE = (
    "\n\nEach `datrix-*` package -- and `datrix` itself -- is its own GIT REPOSITORY. "
    "A temp directory created inside one gets committed and pushed (5076 files of "
    "test output already were, once). CLAUDE.md forbids it outright.\n\n"
    "Put it outside every repo tree instead:\n"
    "  D:\\datrix\\.scripts\\        temporary scripts / runners / helpers\n"
    "  D:\\datrix\\.test-output\\    test output, result logs\n"
    "  D:\\datrix\\.tmp\\            all other temp / scratch files\n\n"
    "If a script or tool defaults to writing inside the package, pass it an output "
    "path under one of those directories -- do not let it create its own.\n\n"
    "If this is NOT temp output but a real part of the package, it needs a real "
    "directory name: the name you chose is what triggered this."
)


def _normalize(text: str) -> str:
    """Windows and POSIX separators, single or doubled, all read the same."""
    return re.sub(r"[\\/]+", "/", text)


def _block(what: str) -> None:
    sys.stderr.write("BLOCKED: " + what + _GUIDANCE)
    sys.exit(2)


def _banned_segment(segments: list[str]) -> str | None:
    """Return the first segment that names a temp/scratch directory, if any."""
    for segment in segments:
        name = segment.strip().lower()
        if not name or name in (".", ".."):
            continue
        if name in _EXEMPT_SEGMENTS or name in _EXEMPT_EXACT:
            return None
        if name in _BANNED_SEGMENTS or name.startswith(_BANNED_PREFIXES):
            return segment
    return None


def _check_path(raw_path: str) -> None:
    """Block a Write/Edit target that lands in a temp directory inside a repo."""
    match = _REPO_PATH_RE.search(_normalize(raw_path))
    if not match:
        return

    repo, tail = match.group(1), match.group(2)
    hit = _banned_segment(tail.split("/"))
    if hit:
        _block(
            f"refusing to write `{raw_path}` -- `{hit}` is a temp/scratch "
            f"directory inside the `{repo}` repository."
        )


def _check_command(command: str) -> None:
    """Block a command that creates or writes a temp directory inside a repo."""
    text = _normalize(command)

    for match in _REPO_PATH_RE.finditer(text):
        repo, tail = match.group(1), match.group(2)
        hit = _banned_segment(tail.split("/"))
        preceding = text[max(0, match.start() - _WRITE_INTENT_WINDOW) : match.start()]
        if hit and _WRITE_INTENT_RE.search(preceding):
            _block(
                f"this command writes to `{match.group(0)}` -- `{hit}` is a "
                f"temp/scratch directory inside the `{repo}` repository."
            )


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool_name in ("Write", "Edit", "NotebookEdit"):
        file_path = tool_input.get("file_path", "")
        if file_path:
            _check_path(file_path)
    elif tool_name in ("Bash", "PowerShell"):
        command = tool_input.get("command", "")
        if command:
            _check_command(command)

    sys.exit(0)


if __name__ == "__main__":
    main()
