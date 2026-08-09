r"""Shell-command shape helpers shared by the command guards.

THE DEFECT CLASS THIS EXISTS TO CLOSE
-------------------------------------
Several guards decided what a command DOES by testing whether a script name or a
path appeared anywhere in its text. That confuses naming a script with running
one, and it produced live over-blocks in two hooks on the same afternoon:

    grep -nE "Unit|marker|-m " datrix/scripts/test/test.ps1

`guard-full-suite-runs.py` refused it as a whole-suite run (reporting its package
list as `<unnamed>, <unnamed>` — the parse announcing it had matched nothing), and
`validate-script-invocation.py` then refused the same command for lacking a
quick-reference marker. Both were blocking an agent from READING the source of the
very script they guard, which is the one thing a guard must never do.

Fixing one instance would have left the other; the shape is shared, so the fix is.

QUOTE AWARENESS IS NOT OPTIONAL
-------------------------------
The first fix split segments with a regex on `[;|\n]` and still failed, because
the pipe inside `"Unit|marker"` is part of an argument, not a separator. Splitting
there left a fragment whose leading token was `marker` rather than `grep`, so the
read-tool test could not fire. Every command this exemption exists for — search
commands — is liable to carry a quoted pipe or semicolon, so the split walks the
string tracking quote state instead.

FAILING TOWARD THE BLOCK
------------------------
An unparseable command yields itself as a single segment with an unrecognised
leading token, which reads as "not a read" and leaves the caller's block intact.
The exemption only ever fires on a command that positively looks like an
inspection.
"""

from __future__ import annotations

from typing import Final

#: Commands that read a file's bytes and print them. Running one of these against
#: a script inspects it; it never executes it.
READ_ONLY_TOOLS: Final = frozenset(
    {
        "grep", "rg", "egrep", "fgrep", "ack", "ag", "cat", "bat", "head", "tail",
        "less", "more", "sed", "awk", "wc", "diff", "cmp", "file", "stat", "ls",
        "dir", "find", "nl", "strings", "md5sum", "sha256sum", "type", "code",
        "select-string", "get-content", "get-item", "get-childitem", "test-path",
        "resolve-path", "format-list", "format-table",
    }
)

_SEPARATORS: Final = frozenset({";", "|", "\n", "&"})
_QUOTES: Final = frozenset({'"', "'"})
_LEADING_STRIP: Final = "(&$= \t\"'"


def segments(command: str) -> list[str]:
    """Split on shell statement separators (`;` `|` `&&` `||` newline) outside quotes."""
    parts: list[str] = []
    current: list[str] = []
    quote = ""
    for char in command:
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
            continue
        if char in _QUOTES:
            quote = char
            current.append(char)
            continue
        if char in _SEPARATORS:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


def leading_token(segment: str) -> str:
    """Bare, lowercased name of the executable a segment starts with."""
    stripped = segment.lstrip(_LEADING_STRIP)
    token: list[str] = []
    for char in stripped:
        if char.isalnum() or char in "._-/\\:":
            token.append(char)
            continue
        break
    name = "".join(token).rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def is_read_only(segment: str) -> bool:
    """True when this segment merely inspects files rather than running them."""
    return leading_token(segment) in READ_ONLY_TOOLS


def executable_text(command: str) -> str:
    """The command with read-only inspection segments removed.

    Callers that decide "does this command invoke X" should search THIS rather
    than the raw command, so that reading X is never mistaken for running it. A
    real invocation chained alongside a read survives, because only the
    inspecting segments are dropped.
    """
    return "\n".join(part for part in segments(command) if not is_read_only(part))
