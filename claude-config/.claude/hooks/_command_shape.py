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

WHICH SCRIPTS A COMMAND RUNS, AND WHETHER IT DEPLOYS
----------------------------------------------------
`invoked_scripts` answers "which script files does this command execute" from the
command's shape: a PowerShell host given `-File`, `-Command` or `-EncodedCommand`,
a call/dot-source operator or a first token naming a `.ps1`, and a Python
interpreter given a `.py`. A path that only appears as an argument of another
program (a `for` list, a `sed` operand, a variable assignment, a heredoc body)
is named, not run, and yields nothing. Wrappers that run their argument as a
command (`bash -c`, `cmd /c`, `env`, `nohup`, `Invoke-Expression`, `$( … )`) are
unwrapped and read the same way, so no command that ran a script or deployed
before stops being seen as doing so. `is_deploy` is the one definition of "this
command deploys" for the pre-deploy guard and the deploy checklist.
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
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
    previous = ""
    for char in command:
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
            previous = char
            continue
        if char in _QUOTES:
            quote = char
            current.append(char)
            previous = char
            continue
        is_call_operator = char == "&" and previous != "&" and not "".join(current).strip()
        previous = char
        if is_call_operator:
            # PowerShell's `& <script>` at the start of a statement runs the script;
            # it is the statement's first token, not a separator.
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


# ---------------------------------------------------------------- invoked scripts

#: How an invoked script was reached; the `via` of an `InvokedScript`.
VIA_POWERSHELL_FILE: Final = "powershell-file"
VIA_POWERSHELL_COMMAND: Final = "powershell-command"
VIA_CALL: Final = "call"
VIA_DIRECT: Final = "direct"
VIA_PYTHON: Final = "python"

_POWERSHELL_HOSTS: Final = frozenset({"powershell", "pwsh"})
_PYTHON_HOST_RE: Final = re.compile(r"^(?:python[\d.]*|py|.*python[\d.]*)$")
_SHELL_HOSTS: Final = frozenset({"bash", "sh", "zsh", "dash"})
_CMD_HOSTS: Final = frozenset({"cmd"})
_EVAL_COMMANDS: Final = frozenset({"invoke-expression", "iex", "eval"})
_PREFIX_COMMANDS: Final = frozenset({"env", "nohup", "time", "exec", "command", "xargs", "start"})
_START_PROCESS: Final = "start-process"
_START_PROCESS_FILE: Final = "filepath"
_START_PROCESS_ARGS: Final = "argumentlist"
_CALL_OPERATORS: Final = frozenset({"&", "."})
_ENV_ASSIGNMENT_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SUBSTITUTION_RE: Final = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
_HEREDOC_RE: Final = re.compile(r"(?<!<)<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")

#: PowerShell host parameters that take a value. Any unambiguous prefix of a
#: parameter name is accepted by the host, so matching is by prefix.
_PS_VALUE_PARAMETERS: Final = (
    "executionpolicy", "windowstyle", "outputformat", "inputformat",
    "configurationname", "workingdirectory", "psconsolefile", "version",
    "settingsfile", "custompipename",
)
_PS_VALUE_ALIASES: Final = frozenset({"ep", "ex", "wd"})
_PS_FILE: Final = "file"
_PS_COMMAND: Final = "command"
_PS_COMMAND_FULL: Final = "commandwithargs"
_PS_COMMAND_ALIASES: Final = frozenset({"cwa"})
_PS_ENCODED: Final = "encoded"
_PS_ENCODED_FULL: Final = "encodedcommand"
_PS_ENCODED_ALIASES: Final = frozenset({"e", "ec"})
_PS_VALUE: Final = "value"
_PS_SWITCH: Final = "switch"
_PY_VALUE_OPTIONS: Final = frozenset({"-w", "-x"})
_PY_STOP_OPTIONS: Final = frozenset({"-c", "-m"})
_MAX_DEPTH: Final = 6

_DEPLOY_SCRIPT_RE: Final = re.compile(r"^(?:deploy[\w-]*|sync-staging)\.ps1$", re.IGNORECASE)

#: Deploy verbs, matched at the start of a segment (after environment
#: assignments and command wrappers).
_DEPLOY_VERB_RE: Final = re.compile(
    r"^(?:az\s+deployment\s+(?:group|sub|mg|tenant)\s+create\b"
    r"|az\s+group\s+deployment\s+create\b"
    r"|az\s+(?:webapp|functionapp|containerapp|staticwebapp)\s+"
    r"(?:deploy(?:ment)?|create|update|up)\b"
    r"|az\s+acr\s+build\b"
    r"|terraform\s+apply\b"
    r"|kubectl\s+apply\b"
    r"|helm\s+(?:install|upgrade)\b"
    r"|docker\s+stack\s+deploy\b"
    r"|docker(?:\s+|-)compose\s+(?:-\S+(?:\s+[^-\s]\S*)?\s+)*up\b"
    r"|docker\s+push\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class InvokedScript:
    """A script file a command executes, and the form that executes it."""

    path: str
    via: str


#: One shell word: a run of quoted spans (an unclosed quote runs to the end) and bare characters.
_WORD: Final = re.compile(r"""(?:"[^"]*"?|'[^']*'?|[^\s"'])+""")
#: One part of a word: the inside of a double- or single-quoted span, or a bare run.
_WORD_PART: Final = re.compile(r""""([^"]*)"?|'([^']*)'?|([^\s"']+)""")


def _tokens(segment: str) -> list[str]:
    """Whitespace-split outside quotes, quotes removed (``""`` is one empty token)."""
    return [
        "".join(
            next(text for text in part.groups() if text is not None)
            for part in _WORD_PART.finditer(word.group())
        )
        for word in _WORD.finditer(segment)
    ]


def _program(token: str) -> str:
    """Bare lowercased program name of a token (`C:/x/pwsh.exe` -> `pwsh`)."""
    name = token.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def _normalise_path(token: str) -> str:
    return token.strip("\"'").replace("\\", "/")


def _strip_prefixes(tokens: list[str]) -> list[str]:
    """Drop leading `VAR=value` assignments and argument-running wrappers."""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if _ENV_ASSIGNMENT_RE.match(token):
            index += 1
            continue
        if _program(token) in _PREFIX_COMMANDS:
            index += 1
            while index < len(tokens) and tokens[index].startswith("-"):
                index += 1
            continue
        break
    return tokens[index:]


def _ps_parameter(token: str) -> str:
    """Lowercased PowerShell host parameter name, or "" when the token is not one."""
    if len(token) < 2 or token[0] != "-" or any(char.isspace() for char in token):
        return ""
    return token.lstrip("-").lower()


def _ps_role(name: str) -> str:
    """What a PowerShell host parameter does; the host accepts any unambiguous prefix.

    An ambiguous prefix resolves toward the role that runs something, so a
    shortened flag can never hide an invocation.
    """
    if _PS_FILE.startswith(name):
        return _PS_FILE
    if name in _PS_COMMAND_ALIASES or _PS_COMMAND_FULL.startswith(name):
        return _PS_COMMAND
    if name in _PS_ENCODED_ALIASES or (len(name) >= 2 and _PS_ENCODED_FULL.startswith(name)):
        return _PS_ENCODED
    if name in _PS_VALUE_ALIASES or any(full.startswith(name) for full in _PS_VALUE_PARAMETERS):
        return _PS_VALUE
    return _PS_SWITCH


def _decode_encoded_command(value: str) -> str:
    try:
        return base64.b64decode(value, validate=True).decode("utf-16-le")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return ""


def _powershell_runs(args: list[str]) -> tuple[str, str]:
    """(script file, command text) a `powershell`/`pwsh` host runs; one of them is ""."""
    index = 0
    while index < len(args):
        name = _ps_parameter(args[index])
        if not name:
            return "", " ".join(args[index:])
        role = _ps_role(name)
        value = args[index + 1] if index + 1 < len(args) else ""
        if role == _PS_FILE:
            return _normalise_path(value), ""
        if role == _PS_COMMAND:
            return "", " ".join(args[index + 1 :])
        if role == _PS_ENCODED:
            return "", _decode_encoded_command(value)
        index += 2 if role == _PS_VALUE else 1
    return "", ""


def _powershell_host(args: list[str], depth: int) -> list[InvokedScript]:
    """A `powershell`/`pwsh` invocation: what its -File / -Command / bare arguments run."""
    script, text = _powershell_runs(args)
    if script:
        return [InvokedScript(script, VIA_POWERSHELL_FILE)]
    return _scripts_in(text, depth + 1, VIA_POWERSHELL_COMMAND)


def _python_host(args: list[str]) -> list[InvokedScript]:
    index = 0
    while index < len(args):
        token = args[index]
        lowered = token.lower()
        if lowered in _PY_STOP_OPTIONS:
            return []
        if lowered in _PY_VALUE_OPTIONS:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        path = _normalise_path(token)
        return [InvokedScript(path, VIA_PYTHON)] if path.lower().endswith(".py") else []
    return []


def _wrapped_command(program: str, args: list[str]) -> str | None:
    """The command text a shell/eval wrapper runs, or None when `program` is not one."""
    if program in _SHELL_HOSTS:
        for index, arg in enumerate(args):
            if arg.startswith("-") and "c" in arg.lstrip("-"):
                return " ".join(args[index + 1 : index + 2])
        return None
    if program in _CMD_HOSTS:
        for index, arg in enumerate(args):
            if arg.lower() in ("/c", "/k"):
                return " ".join(args[index + 1 :])
        return None
    if program in _EVAL_COMMANDS:
        return " ".join(args)
    return None


def _start_process_tokens(args: list[str]) -> list[str]:
    """`Start-Process <file> -ArgumentList '<args>'` as the token list it launches."""
    file_path = ""
    launched: list[str] = []
    index = 0
    while index < len(args):
        name = _ps_parameter(args[index])
        value = args[index + 1] if index + 1 < len(args) else ""
        if name and _START_PROCESS_FILE.startswith(name):
            file_path = value
            index += 2
            continue
        if name and _START_PROCESS_ARGS.startswith(name):
            launched.extend(_tokens(value.replace(",", " ")))
            index += 2
            continue
        if not name and not file_path:
            file_path = args[index]
        index += 1
    return [file_path, *launched] if file_path else []


def _segment_scripts(tokens: list[str], depth: int, via_command: str) -> list[InvokedScript]:
    """Scripts one segment's tokens (wrappers already stripped) execute."""
    if not tokens:
        return []
    first = tokens[0]
    program = _program(first)
    if program == _START_PROCESS:
        return _segment_scripts(_start_process_tokens(tokens[1:]), depth + 1, via_command)
    if first in _CALL_OPERATORS:
        rest = tokens[1:]
        return [InvokedScript(_normalise_path(rest[0]), VIA_CALL)] if rest else []
    if program in _POWERSHELL_HOSTS:
        return _powershell_host(tokens[1:], depth)
    if _PYTHON_HOST_RE.match(program) and not program.endswith(".py"):
        return _python_host(tokens[1:])
    if program.endswith(".ps1"):
        return [InvokedScript(_normalise_path(first), via_command)]
    wrapped = _wrapped_command(program, tokens[1:])
    if wrapped is not None:
        return _scripts_in(wrapped, depth + 1, via_command)
    return []


def _executable_segments(command: str) -> list[list[str]]:
    """Token lists of each segment, with leading wrappers and assignments removed."""
    found: list[list[str]] = []
    for segment in segments(command):
        tokens = _strip_prefixes(_tokens(segment))
        if tokens:
            found.append(tokens)
    return found


def _substitutions(command: str) -> list[str]:
    """Bodies of `$( … )` and backtick command substitutions."""
    return [match.group(1) or match.group(2) or "" for match in _SUBSTITUTION_RE.finditer(command)]


def _heredoc_feeds_interpreter(line: str) -> bool:
    """True when the segment holding a line's `<<` operator is a shell or interpreter."""
    holder = next((part for part in reversed(segments(line)) if "<<" in part), "")
    tokens = _strip_prefixes(_tokens(holder.split("<<", 1)[0]))
    if not tokens:
        return False
    program = _program(tokens[0])
    return program in _POWERSHELL_HOSTS | _SHELL_HOSTS | _CMD_HOSTS


def _without_heredoc_data(command: str) -> str:
    """The command with the bodies of heredocs that feed a non-shell program removed.

    `cat <<EOF … EOF` writes its body as data; a line in it naming a script runs
    nothing. A heredoc fed to a shell host is code and is kept.
    """
    kept: list[str] = []
    terminator = ""
    for line in command.split("\n"):
        if terminator:
            if line.strip() == terminator:
                terminator = ""
            continue
        kept.append(line)
        match = _HEREDOC_RE.search(line)
        if match and not _heredoc_feeds_interpreter(line):
            terminator = match.group(1)
    return "\n".join(kept)


def _scripts_in(command: str, depth: int, via_command: str) -> list[InvokedScript]:
    if depth > _MAX_DEPTH or not command.strip():
        return []
    command = _without_heredoc_data(command)
    found: list[InvokedScript] = []
    for tokens in _executable_segments(command):
        found.extend(_segment_scripts(tokens, depth, via_command))
    for body in _substitutions(command):
        found.extend(_scripts_in(body, depth + 1, via_command))
    return found


def invoked_scripts(command: str) -> list[InvokedScript]:
    """Every script file the command executes (paths unquoted, `\\` as `/`).

    Only an execution form yields a path; a path named as another program's
    argument never does.
    """
    return _scripts_in(command, 0, VIA_DIRECT)


def _deploy_verb_segments(command: str, depth: int) -> bool:
    if depth > _MAX_DEPTH or not command.strip():
        return False
    for tokens in _executable_segments(_without_heredoc_data(command)):
        if _program(tokens[0]) == _START_PROCESS:
            tokens = _start_process_tokens(tokens[1:])
        if tokens and _segment_deploys(tokens, depth):
            return True
    return any(_deploy_verb_segments(body, depth + 1) for body in _substitutions(command))


def _segment_deploys(tokens: list[str], depth: int) -> bool:
    program = _program(tokens[0])
    if _DEPLOY_VERB_RE.match(" ".join([program, *tokens[1:]])):
        return True
    if program in _POWERSHELL_HOSTS:
        return _deploy_verb_segments(_powershell_runs(tokens[1:])[1], depth + 1)
    wrapped = _wrapped_command(program, tokens[1:])
    return wrapped is not None and _deploy_verb_segments(wrapped, depth + 1)


def is_deploy(command: str) -> bool:
    """True when the command runs a deploy script or begins a deploy verb."""
    for script in invoked_scripts(command):
        if _DEPLOY_SCRIPT_RE.match(script.path.rsplit("/", 1)[-1]):
            return True
    return _deploy_verb_segments(command, 0)
