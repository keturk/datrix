"""Run prompts one after another as headless Claude Code steps, each slash command on its own skill's model.

The module behind ``scripts/skill/skill-chain.ps1`` (and its ``.sh`` twin). The wrapper's prompts arrive
as one ``--step=<prompt>`` each (a caller of the ``.sh`` twin may write them positionally); each runs as
its own step of ``datrix_scripts.skill.chain``, in order, and the chain stops at the first step that ends
in error. Every step's stream, result and stderr are kept under ``<workspace>/.tmp/skill-chain/<timestamp>/``.

Exit codes: 0 every step finished (or a passing self-test); 1 no prompt was given, the claude CLI is not on
PATH, a step ended in error, or a self-test check failed; 2 a command line this module cannot read.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final, NoReturn

from datrix_scripts.claude_cli import CLAUDE
from datrix_scripts.logging_utils import ColorCodes, say
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.skill.chain import (
    CHAIN_CHECKS,
    EXIT_DONE,
    EXIT_FAILED,
    Chain,
    ChainOptions,
    add_chain_arguments,
    chain_exit_code,
    chain_options,
)
from datrix_scripts.test.wrappers import SKILL_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.skill.skill_chain"
WRAPPER: Final = "skill-chain"
NO_STEPS: Final = 'Pass the prompts to run ("/a" "/b" ...). For a design: implement-design.ps1.'


def run_steps(chain: Chain, prompts: Sequence[str]) -> NoReturn:
    """Run each prompt as step ``step<n>``; stop with 1 at the first step that ends in error."""
    for index, prompt in enumerate(prompts, start=1):
        row = chain.step(f"step{index}", prompt)
        if not row.dry_run and row.is_error:
            chain.stop(EXIT_FAILED, f"Step {index} ended in error ({row.subtype}).", row)
    chain.complete()


def build_parser() -> argparse.ArgumentParser:
    """The options of ``skill/skill-chain.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description="Run prompts one after another as headless Claude Code steps, each on its skill's model.",
        allow_abbrev=False,
    )
    parser.add_argument("positional_steps", nargs="*", metavar="PROMPT", help="as --step, for a caller of the .sh twin")
    parser.add_argument("--step", action="append", default=[], metavar="PROMPT",
                        help="One prompt to run (repeat for each, in order).")
    add_chain_arguments(parser, resume=True)
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the chain checks, the dry-run check and the wrapper seam checks.")
    parser.set_defaults(debug=False)
    return parser


def _check_the_steps_are_the_prompts_in_order() -> None:
    parser = build_parser()
    for argv in (["--step=/fix-codegen-python x", "--step=/commit-and-push"], ["/fix-codegen-python x", "/commit-and-push"]):
        args = parser.parse_args(argv)
        assert [*args.step, *args.positional_steps] == ["/fix-codegen-python x", "/commit-and-push"], (argv, args)
    with TemporaryDirectory() as raw:
        chain = Chain(ChainOptions(workspace=Path(raw), dry_run=True), CLAUDE)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = chain_exit_code(lambda: run_steps(chain, ["/a", "/b\nTASKS: none"]))
    assert code == EXIT_DONE, code
    assert printed.getvalue().splitlines() == [
        "", "=== step 01-step1 [compacts at 300000 tokens] ===", "/a",
        "", "=== step 02-step2 [compacts at 300000 tokens] ===", "/b", "TASKS: none",
    ], printed.getvalue()


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [*CHAIN_CHECKS, _check_the_steps_are_the_prompts_in_order]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=SKILL_SCRIPTS_DIR)
    prompts = [*args.step, *args.positional_steps]
    if not prompts:
        say(NO_STEPS, ColorCodes.RED)
        return EXIT_FAILED
    options = chain_options(args, WORKSPACE_DIR, resume=args.resume)
    return chain_exit_code(lambda: run_steps(Chain.start(options), prompts))


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
