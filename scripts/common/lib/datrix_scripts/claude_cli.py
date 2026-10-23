"""What every script that runs the Claude Code CLI shares: its name on ``PATH``, the batch-shim refusal
and the headless agent run (``AgentRequest`` / ``run_agent``).

On Windows ``claude`` on ``PATH`` is ``claude.cmd``, a batch shim that ``cmd.exe`` runs and parses: a
line break in an argument ends the command there (the rest of the argument and every argument after it
never reach the CLI), and ``&``, ``|``, ``<``, ``>``, ``^``, ``%``, ``!``, ``"`` and parentheses are
read as ``cmd.exe`` syntax. So a script hands the CLI its prompt on stdin, never as an argument, and
``require_batch_safe`` refuses any remaining argument holding one of those characters before the launch,
rather than letting ``cmd.exe`` run something else.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import UsageError

CLAUDE: Final = "claude"
BATCH_SHIM_SUFFIXES: Final = frozenset({".bat", ".cmd"})
CMD_METACHARACTERS: Final = frozenset('&|<>^%!"()\r\n')
AGENT_EFFORTS: Final = ("low", "medium", "high", "xhigh", "max")


def batch_unsafe_arguments(command: Sequence[str]) -> list[str]:
    """The arguments of *command* that ``cmd.exe`` would parse, when its executable is a batch shim; else none."""
    if Path(command[0]).suffix.lower() not in BATCH_SHIM_SUFFIXES:
        return []
    return [argument for argument in command[1:] if CMD_METACHARACTERS & set(argument)]


def require_batch_safe(command: Sequence[str], fix: str) -> None:
    """Refuse *command* when it runs a batch shim (``claude.cmd``) with an argument ``cmd.exe`` would parse.

    Raises:
        UsageError: naming the arguments, the characters and *fix* (what the caller should pass instead).
    """
    unsafe = batch_unsafe_arguments(command)
    if unsafe:
        raise UsageError(
            f"{command[0]} is a batch shim that cmd.exe runs, and these arguments hold a cmd.exe metacharacter "
            f"({''.join(sorted(CMD_METACHARACTERS - {chr(13), chr(10)}))} or a line break): {unsafe}. Fix: {fix}"
        )


class AgentRunError(RuntimeError):
    """A headless agent run could not start, timed out, exited non-zero or reported an error."""


@dataclass(frozen=True)
class AgentRequest:
    """One headless Claude Code agent run: who runs it, with which tools, where, and for how long.

    ``tools`` is the built-in tool set (``--tools``); ``allowed_tools`` are tool names let through
    without a prompt (``--allowedTools``), which is how MCP tools are named. The ``prompt`` goes to
    stdin, never to an argument. The run uses the workspace's own CLAUDE.md, hooks and skills from
    ``cwd``, so a skill named by a leading ``/name`` in the prompt runs as if typed.
    """

    prompt: str
    model: str
    effort: str
    permission_mode: str
    tools: str
    allowed_tools: tuple[str, ...]
    cwd: Path
    timeout_ms: int
    label: str
    persist_session: bool = False
    """Save the session transcript. A hook that must see the typed ``/skill`` reads it from there."""


def agent_command(claude: str, request: AgentRequest) -> list[str]:
    """The ``claude`` argument vector of *request* (its prompt goes to stdin).

    Raises:
        UsageError: for an effort the CLI does not take, an empty model, or an argument ``cmd.exe``
            would parse when *claude* is a batch shim.
    """
    if request.effort not in AGENT_EFFORTS:
        raise UsageError(f"Agent effort '{request.effort}' is not one of {list(AGENT_EFFORTS)}. Pass one of them.")
    if not request.model:
        raise UsageError("The agent model is empty. Pass a model alias or id such as claude-sonnet-5-5.")
    command = [
        claude, "-p", "--output-format", "json", "--permission-mode", request.permission_mode,
        "--tools", request.tools, "--model", request.model, "--effort", request.effort,
    ]
    if not request.persist_session:
        command.append("--no-session-persistence")
    if request.allowed_tools:
        command += ["--allowedTools", ",".join(request.allowed_tools)]
    require_batch_safe(command, "pass a model alias or id without those characters")
    return command


def agent_summary(stdout: str, label: str) -> str:
    """The final reply in the CLI's ``--output-format json`` output.

    Raises:
        AgentRunError: when the output is not a JSON object or the run reports an error.
    """
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise AgentRunError(f"The {label} agent returned non-JSON output: {exc}") from exc
    if not isinstance(data, dict):
        raise AgentRunError(f"The {label} agent returned {type(data).__name__}, not an object.")
    result = data.get("result")
    summary = result if isinstance(result, str) else ""
    if data.get("is_error"):
        raise AgentRunError(f"The {label} agent ended in error: {summary or data}")
    return summary.strip()


def run_agent(request: AgentRequest) -> str:
    """Run *request* to the end and return the agent's final reply.

    Raises:
        AgentRunError: the CLI is not on ``PATH``, the run timed out, exited non-zero or reported an error.
        UsageError: see ``agent_command``.
    """
    claude = shutil.which(CLAUDE)
    if claude is None:
        raise AgentRunError(
            f"The {request.label} agent cannot start: the claude CLI is not on PATH. "
            "Install it: npm install -g @anthropic-ai/claude-code"
        )
    command = agent_command(claude, request)
    try:
        result = subprocess.run(
            command, input=request.prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=request.cwd, env={**os.environ, "NO_COLOR": "1"}, timeout=max(1, request.timeout_ms / 1000.0),
        )
    except subprocess.TimeoutExpired as exc:
        raise AgentRunError(f"The {request.label} agent timed out after {request.timeout_ms} ms.") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise AgentRunError(f"The {request.label} agent exited {result.returncode}: {detail}")
    return agent_summary(result.stdout, request.label)
