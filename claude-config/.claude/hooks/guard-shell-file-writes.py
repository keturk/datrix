r"""PreToolUse hook: file CONTENT is authored with Write/Edit, never through a shell.

THE DEFECT CLASS
----------------
An agent that knows the rule still drifts to the shell, because a heredoc feels
like one action where `Edit` feels like several. It happened in a single session
on this repo: bulk edits across eight conformance baselines went through
`python - <<PY ... p.write_text(...)`, and once that pattern was established the
agent used `cat >> tests/...py <<'APPEND'` to append 160 lines to ONE file, where
`Edit` was plainly correct.

Shell-authored file content is worse than the dedicated tools on every axis that
matters here:

  * It prompts. Bash/PowerShell go through the permission layer; Write/Edit are
    auto-accepted in Auto mode. Every heredoc is an interruption Jon did not need.
  * It writes blind. No diff is surfaced, so a bad edit lands unreviewed.
  * It has no clobber guard. `Write` refuses to overwrite a file the agent has
    not read; `cat >` overwrites anything.
  * It is fragile in exactly the ways that waste a turn. In that same session one
    heredoc died on `unexpected EOF` because the content held an apostrophe, and
    another was refused by a different hook because the CONTENT contained the
    word "pytest". Both were self-inflicted and both cost a round trip.

WHAT IS BLOCKED
---------------
Commands that author file content: heredoc redirection, `>`/`>>` into a file,
`echo`/`printf` into a file, PowerShell `Set-Content`/`Add-Content`/`Out-File`,
and inline interpreters (`python -c`, `python - <<`, `node -e`, `perl -e`) whose
body calls a write API.

WHAT IS NOT BLOCKED -- deliberately, because these are not authoring
------------------------------------------------------------------
  * Redirection into the workspace scratch areas (`.tmp`, `.test-output`,
    `.scripts`, `.generated`, the session scratchpad, `/dev/null`, `$null`, `NUL`):
    that is transient measurement output, not source under review.
  * `2>&1`, `2>$null` and friends -- stream plumbing, no file authored.
  * Reading: `<` redirection, and any command whose leading token is a read-only
    inspection tool.
  * Real tools that happen to write files as their JOB -- a compiler, a formatter,
    a generator, `git`, `pip`, a test runner. Only the shell's own
    content-authoring constructs and inline interpreters are in scope.

FAILING OPEN
------------
Unparseable input, an unreadable command, or any unexpected error allows the
call. This hook can annoy; it must never wedge a session.

Exit codes:
  0 -- allow
  2 -- block (stderr becomes feedback to Claude)
"""

from __future__ import annotations

import json
import re
import sys
from typing import Final

from _command_shape import segments

#: Paths whose contents are transient by construction. A redirect landing in one
#: of these authors no reviewable artifact, so it is never this hook's business.
#: Matched anywhere in the redirect target, case-insensitively.
_TRANSIENT_TARGETS: Final = (
    "/dev/null",
    "$null",
    r"\.tmp[/\\]",
    r"\.tmp$",
    r"\.test-output[/\\]",
    r"\.test_results[/\\]",
    r"\.scripts[/\\]",
    r"\.generated[/\\]",
    r"scratchpad[/\\]",
    r"[/\\]temp[/\\]claude[/\\]",
)
_TRANSIENT_RE: Final = re.compile("|".join(_TRANSIENT_TARGETS), re.IGNORECASE)

#: `NUL` only as a whole target, so a file named `nul-report.txt` is not exempt.
_NUL_RE: Final = re.compile(r"^nul$", re.IGNORECASE)

#: Heredoc introducing content: `<<EOF`, `<<'PY'`, `<<-"X"`. Any of these in a
#: segment that also redirects to a file means the shell is authoring content.
_HEREDOC_RE: Final = re.compile(r"<<-?\s*[\"']?[A-Za-z_][A-Za-z0-9_]*[\"']?")

#: Output redirection to a target that is not a file descriptor. `2>&1` and
#: `>&2` are stream plumbing and must not match.
_REDIRECT_RE: Final = re.compile(r"(?<![0-9&])>{1,2}\s*(?![&|])([^\s;|&]+)")

#: PowerShell cmdlets whose whole purpose is writing file content.
_PS_WRITE_CMDLETS: Final = frozenset(
    {"set-content", "add-content", "out-file", "new-item"}
)

#: Inline interpreters: a body passed on the command line or via heredoc.
_INLINE_INTERPRETER_RE: Final = re.compile(
    r"\b(python|python3|py|node|perl|ruby|pwsh|powershell)(\.exe)?\b"
    r"[^;|&\n]*?(\s-c\b|\s-e\b|\s-\s*<<|\s--%\s*-c\b)",
    re.IGNORECASE,
)

#: Write APIs that make an inline interpreter body a file-authoring act.
#: Two alternations, not one: the `open(..., "w")` arm ends on a quote, and a
#: trailing `\b` after a quote can never match (the next character is `)`), which
#: silently let `python -c "open('x.py','w').write(...)"` through until the
#: hook's own test caught it.
_WRITE_API_RE: Final = re.compile(
    r"\b(?:write_text|write_bytes|writelines|writeFileSync|writeFile"
    r"|appendFileSync|Set-Content|Add-Content|Out-File)\b"
    r"|open\s*\([^)]*[\"'][arwx]\+?b?[\"']",
    re.IGNORECASE,
)

_GUIDANCE: Final = (
    "Author file content with the dedicated tools:\n"
    "  * new file, or full replacement of one you have read  -> Write\n"
    "  * change part of a file                               -> Edit\n"
    "  * same change in many places in one file              -> Edit(replace_all=True)\n"
    "  * the same edit across N files                        -> N Edit calls\n"
    "\n"
    "N separate Edit calls IS the correct shape for a bulk change. It is not "
    "worth one shell script: Edit is auto-accepted so it never interrupts Jon, "
    "each call surfaces a reviewable diff, and Write refuses to clobber a file "
    "you have not read. A heredoc has none of that and breaks on an apostrophe "
    "in the content."
)


def _block(reason: str) -> None:
    sys.stderr.write(f"BLOCKED: {reason}\n\n{_GUIDANCE}\n")
    sys.exit(2)


def _is_transient(target: str) -> bool:
    """True when a redirect target is scratch space rather than a reviewable file."""
    cleaned = target.strip().strip("\"'")
    if not cleaned or _NUL_RE.match(cleaned):
        return True
    return bool(_TRANSIENT_RE.search(cleaned.replace("\\", "/")))


def _authored_redirect_target(segment: str) -> str | None:
    """Return the redirect target this segment authors, or None."""
    for match in _REDIRECT_RE.finditer(segment):
        target = match.group(1)
        if not _is_transient(target):
            return target
    return None


def _check_segment(segment: str) -> None:
    """Block one segment that authors file content through the shell.

    Three independent ways in, each tested on its own: a redirect (with or
    without a heredoc body), a PowerShell content cmdlet, and an inline
    interpreter whose body calls a write API. A segment that does none of these
    is left alone.
    """
    target = _authored_redirect_target(segment)
    has_heredoc = bool(_HEREDOC_RE.search(segment))

    # Note on the read-only exemption used elsewhere in these hooks: it answers
    # "is this merely inspecting files" from the LEADING TOKEN, so `cat` reads
    # as an inspection even in `cat > src/x.py <<'EOF'` -- the single most
    # common way to author a file from a shell. It is therefore deliberately
    # NOT consulted here; the presence of a write is what decides.
    if target is not None:
        if has_heredoc:
            _block(f"this heredoc writes file content to `{target}` through the shell.")
        leading = segment.strip().split()[:1]
        name = (
            leading[0].rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower() if leading else ""
        )
        if name.startswith(("echo", "printf", "cat", "type")):
            _block(f"this command writes file content to `{target}` through the shell.")

    lowered = segment.lower()
    for cmdlet in _PS_WRITE_CMDLETS:
        if not re.search(rf"\b{re.escape(cmdlet)}\b", lowered):
            continue
        if cmdlet == "new-item":
            if "-itemtype directory" in lowered:
                continue  # a directory carries no content
            if "-value" not in lowered:
                continue  # touch-equivalent; no content authored
        _block(f"`{cmdlet}` writes file content through the shell.")

    if _INLINE_INTERPRETER_RE.search(segment) and _WRITE_API_RE.search(segment):
        _block(
            "this inline interpreter body writes files. Running an ad-hoc "
            "script to edit source is the same act as a heredoc, at one more "
            "level of indirection."
        )


def _check_command(command: str) -> None:
    # A heredoc body can span statement separators, so an inline interpreter
    # with a `<<` body is tested against the whole command before splitting.
    if _INLINE_INTERPRETER_RE.search(command) and _WRITE_API_RE.search(command):
        _block(
            "this inline interpreter body writes files. Running an ad-hoc "
            "script to edit source is the same act as a heredoc, at one more "
            "level of indirection."
        )
    for segment in segments(command):
        _check_segment(segment)


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if data.get("tool_name", "") not in ("Bash", "PowerShell"):
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if not command:
        sys.exit(0)

    try:
        _check_command(command)
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 -- a guard must never wedge a session
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
