"""The skill assists' wrapper: one assist command of ``datrix_scripts.skill.assist_cli`` per run.

The module behind ``scripts/skill/skill-assist.ps1`` (and its ``.sh`` twin). The wrapper's
``-Command <command> [<argument> ...]`` arrives as ``--command=<command>`` and one ``--arguments=<argument>``
per argument (a caller of the ``.sh`` twin may write the command and its arguments positionally); the
assist command line is ``<command> <argument> ...``, and for a command that may ask a local model, the
local-model flags built from ``--local-machines``, ``--llm-model`` and ``--llm-timeout`` (seconds) follow.
The assists run in this process.

Exit codes: those of the assist (0 done; 1 the request could not be carried out; 2 the check found
something to act on; 3 no local model answered); 2 also for a command line this wrapper cannot read; and
for ``--self-test`` 0 passed, 1 a check failed.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Final

from datrix_scripts.local_llm import MILLISECONDS_PER_SECOND, QUALITY_MODEL_PREFERENCE, add_wrapper_llm_arguments
from datrix_scripts.skill.assist_cli import build_parser as assist_cli_parser
from datrix_scripts.test.wrappers import SKILL_SCRIPTS_DIR, add_command_arguments, run_command_wrapper

MODULE: Final = "datrix_scripts.skill.skill_assist"
WRAPPER: Final = "skill-assist"
CLI_MODULE: Final = "datrix_scripts.skill.assist_cli"
# A request to the most capable model reads a prompt at about half the speed of the fast one.
LLM_TIMEOUT_SECONDS: Final = 600
COMMANDS: Final = (
    "context-digest", "readiness", "findings-index", "findings-check", "findings-redundant",
    "findings-redundant-delete", "finding-select", "finding-close", "checklist", "absorb-transfer", "absorb-references", "absorb-delete",
    "bug-resolution", "design-inventory", "design-verify", "design-plan", "design-check", "design-xref",
    "design-close", "rule-names",
)
# The commands that may ask a local model; the others are exact and take no model flags.
MODEL_COMMANDS: Final = frozenset(
    {"readiness", "findings-index", "findings-redundant", "checklist", "absorb-transfer",
     "bug-resolution", "design-verify", "design-plan", "rule-names"}
)
# The model commands whose answer decides something or is written into the docs: with no -LlmModel they use
# QUALITY_MODEL_PREFERENCE, the most capable model first, and wait for it. The others (an index entry, a
# name proposal a person reviews) take whichever model is resident.
QUALITY_COMMANDS: Final = frozenset(
    {"readiness", "findings-redundant", "absorb-transfer", "bug-resolution", "design-plan"}
)
# The assist command line's local-model flags (``local_llm.add_local_llm_arguments``).
_CLI_TIMEOUT_FLAG: Final = "--local-timeout-ms"
_CLI_MACHINE_FLAG: Final = "--local-machine"
_CLI_MODEL_FLAG: Final = "--local-model"


def assist_argv(args: argparse.Namespace, command: str, arguments: list[str]) -> list[str]:
    """``<command> <argument> ...``, and for a model command the local-model flags of the wrapper's options."""
    line = [command, *arguments]
    if command not in MODEL_COMMANDS:
        return line
    line += [_CLI_TIMEOUT_FLAG, str(args.llm_timeout * MILLISECONDS_PER_SECOND)]
    for machine in args.local_machine_specs or ():
        line += [_CLI_MACHINE_FLAG, machine]
    models = args.local_models or (QUALITY_MODEL_PREFERENCE if command in QUALITY_COMMANDS else ())
    for model in models:
        line += [_CLI_MODEL_FLAG, model]
    return line


def build_parser() -> argparse.ArgumentParser:
    """The options of ``skill/skill-assist.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description="Skill assists: the mechanical phases of agent skills, done by scripts and local models.",
        allow_abbrev=False,
    )
    add_command_arguments(parser, COMMANDS)
    add_wrapper_llm_arguments(parser, timeout_seconds=LLM_TIMEOUT_SECONDS)
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the command-line and assist-command checks and the wrapper seam checks.")
    # The wrapper has no -Dbg; the shared command-wrapper main reads the flag.
    parser.set_defaults(dbg=False)
    return parser


def _check_the_commands_are_the_assist_commands() -> None:
    cli = assist_cli_parser()
    subcommands = next(action for action in cli._actions if isinstance(action, argparse._SubParsersAction))
    assist_commands = set(subcommands.choices)
    assert set(COMMANDS) == assist_commands, (
        f"wrapper commands {sorted(set(COMMANDS) - assist_commands)} have no assist; assists "
        f"{sorted(assist_commands - set(COMMANDS))} have no wrapper command. Expected the same set in COMMANDS."
    )
    takes_model = {name for name, sub in subcommands.choices.items()
                   if any(_CLI_TIMEOUT_FLAG in action.option_strings for action in sub._actions)}
    assert takes_model == MODEL_COMMANDS, (
        f"MODEL_COMMANDS {sorted(MODEL_COMMANDS)} differ from the assists that take the local-model flags "
        f"{sorted(takes_model)}"
    )


def _check_model_commands_get_the_local_model_flags() -> None:
    parser = build_parser()
    model = parser.parse_intermixed_args(["--command=readiness", "--arguments=--phase", "--arguments=12",
                                          "--local-machines=alpha", "--llm-model=m1", "--llm-model=m2",
                                          "--llm-timeout=7"])
    assert assist_argv(model, "readiness", ["--phase", "12"]) == [
        "readiness", "--phase", "12", "--local-timeout-ms", "7000", "--local-machine", "alpha",
        "--local-model", "m1", "--local-model", "m2"], assist_argv(model, "readiness", ["--phase", "12"])
    exact = parser.parse_intermixed_args(["--command=absorb-delete", "--arguments=--design", "--arguments=d.md"])
    assert assist_argv(exact, "absorb-delete", ["--design", "d.md"]) == ["absorb-delete", "--design", "d.md"]
    default = parser.parse_intermixed_args(["design-plan"])
    quality = ["design-plan", "--local-timeout-ms", "600000"]
    for name in QUALITY_MODEL_PREFERENCE:
        quality += [_CLI_MODEL_FLAG, name]
    assert assist_argv(default, "design-plan", []) == quality, assist_argv(default, "design-plan", [])
    for fast in ("findings-index", "checklist"):
        assert assist_argv(default, fast, []) == [fast, "--local-timeout-ms", "600000"], assist_argv(default, fast, [])
    assert QUALITY_COMMANDS <= MODEL_COMMANDS, sorted(QUALITY_COMMANDS - MODEL_COMMANDS)
    for command in COMMANDS:
        assist_cli_parser().parse_args(assist_argv(model, command, []) + _REQUIRED[command])


#: The smallest arguments each assist accepts, so every line ``assist_argv`` builds is proven to parse.
_REQUIRED: Final[dict[str, list[str]]] = {
    "context-digest": ["--phase", "1"], "readiness": ["--phase", "1"], "findings-index": [],
    "findings-check": ["--delete", "f.md"], "findings-redundant": [], "findings-redundant-delete": [],
    "finding-select": [], "finding-close": ["--finding", "f.md"],
    "checklist": ["--design", "d.md"], "absorb-transfer": ["--design", "d.md", "--target", "t.md"],
    "absorb-references": ["--design", "d.md"], "absorb-delete": ["--design", "d.md"],
    "bug-resolution": ["--report", "r.md"], "design-inventory": [], "design-verify": [], "design-plan": [],
    "design-check": [], "design-xref": [], "design-close": ["--finding", "f.md"],
    "rule-names": ["--site", "s.dtrx:1"],
}


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return run_command_wrapper(
        build_parser(),
        argv,
        commands=COMMANDS,
        wrapper=WRAPPER,
        module=MODULE,
        cli_module=CLI_MODULE,
        cli_argv=assist_argv,
        checks=(_check_the_commands_are_the_assist_commands, _check_model_commands_get_the_local_model_flags),
        folder=SKILL_SCRIPTS_DIR,
    )


if __name__ == "__main__":
    sys.exit(main())
