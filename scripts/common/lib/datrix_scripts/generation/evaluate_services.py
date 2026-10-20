"""Run /evaluate-generated-service prompts in parallel through the Claude Code CLI.

The module behind ``generation/evaluate-services.ps1`` (and its ``.sh`` twin). Finds every
``service-*.prompt.md`` in the evaluation folder (the current directory unless ``--eval-dir``
names one; ``evaluated/`` when the folder holds none), asks to proceed, and runs each prompt
through ``claude -p`` in batches of ``--parallel``.

Without ``--full``, each service is first triaged by the local model servers
(``python -m datrix_scripts.generation.service_triage``, one child process per service): a
service whose Phase 3.5 categories are all clean gets its report from the triage and no Claude
Code run (triage exit 0); a service that needs review (exit 3) goes to Claude Code with its
``service-<name>.local-triage.json`` appended to the prompt; any other triage exit sends it
untriaged.

Each Claude Code run is an argument vector, never a shell string: the prompt is written to the
child's stdin, and the working directory is the evaluation folder, with read access to the
source and generated trees through ``--add-dir``. Where the CLI on ``PATH`` is a batch shim
(``claude.cmd`` on Windows, which ``cmd.exe`` runs), an argument holding a ``cmd.exe``
metacharacter is refused rather than handed to ``cmd.exe`` to parse.

Exit codes: 0 = every run succeeded (or the run was declined), 1 = a run failed or an input
directory is missing, 2 = usage error.

Usage:
    python -m datrix_scripts.generation.evaluate_services --source-dir=<dir> --generated-dir=<dir> [--eval-dir=<dir>]
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from datrix_scripts.claude_cli import CLAUDE, require_batch_safe
from datrix_scripts.gate_harness import UsageError, expect_usage_error
from datrix_scripts.generation import service_triage
from datrix_scripts.logging_utils import ColorCodes, colorize
from datrix_scripts.paths import script_env
from datrix_scripts.test.wrappers import GENERATION_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.generation.evaluate_services"
WRAPPER: Final = "evaluate-services"
TRIAGE_MODULE: Final = "datrix_scripts.generation.service_triage"
DEFAULT_PARALLEL: Final = 5
DEFAULT_MODEL: Final = "opus"
ALLOWED_TOOLS: Final = ("Read", "Glob", "Grep", "Write", "Task", "WebSearch", "TodoWrite")
SKILL: Final = "/evaluate-generated-service"
PROMPT_GLOB: Final = "service-*.prompt.md"
PROMPT_PREFIX: Final = "service-"
PROMPT_SUFFIX: Final = ".prompt.md"
RUN_LOG: Final = "evaluation-run.log"
PROCEED_PROMPT: Final = "Proceed? (y/N) "
PROCEED_ANSWERS: Final = frozenset({"y", "Y"})
TRIAGE_CLEAN: Final = 0
STATUS_OK: Final = "OK"
STATUS_FAILED: Final = "FAILED"
RULE: Final = "=" * 60
EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
SECONDS_PER_MINUTE: Final = 60
_UTF8: Final = "utf-8"
_REPLACE: Final = "replace"


@dataclass(frozen=True)
class Evaluation:
    """One service's Claude Code run."""

    service: str
    status: str
    minutes: float
    output: str


def build_parser() -> argparse.ArgumentParser:
    """The options of ``generation/evaluate-services.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--source-dir", help="The project source directory (containing .dtrx files).")
    parser.add_argument("--generated-dir", help="The generated output directory.")
    parser.add_argument("--eval-dir", help="The evaluation directory holding the prompt files (default: current).")
    parser.add_argument("--parallel", type=int, default=DEFAULT_PARALLEL,
                        help=f"Claude Code processes run at once (default: {DEFAULT_PARALLEL}).")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model to use (default: {DEFAULT_MODEL}).")
    parser.add_argument("--full", action="store_true", help="Skip the local triage: every service goes to Claude Code.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: the local triage's checks and this runner's own.")
    parser.set_defaults(debug=False)
    return parser


def service_name(prompt: Path) -> str:
    """``service-<name>.prompt.md`` -> ``<name>``."""
    return prompt.name.removeprefix(PROMPT_PREFIX).removesuffix(PROMPT_SUFFIX)


def find_prompts(eval_dir: Path) -> list[Path]:
    """The prompt files in *eval_dir*, else in its ``evaluated/``; empty when neither holds one."""
    prompts = sorted(path for path in eval_dir.glob(PROMPT_GLOB) if path.is_file())
    if prompts:
        return prompts
    print(colorize(f"No service prompt files found in current directory: {eval_dir}", ColorCodes.YELLOW))
    print(colorize(f"Looking in {service_triage.EVALUATED_DIR}/ subfolder...", ColorCodes.YELLOW))
    evaluated = eval_dir / service_triage.EVALUATED_DIR
    return sorted(path for path in evaluated.glob(PROMPT_GLOB) if path.is_file())


def claude_prompt(prompt_path: Path, triage_file: Path | None) -> str:
    """The prompt that invokes the skill on *prompt_path*, with the local triage appended when there is one."""
    text = f"{SKILL}\n\nPROMPT_FILE: {prompt_path}"
    if triage_file is not None:
        text += (f"\nLOCAL_TRIAGE: {triage_file} (a local model's Phase 3.5 verdicts with cited lines: "
                 "a lead to confirm, not a result)\n")
    return text


def claude_command(executable: str, model: str, source_dir: Path, generated_dir: Path) -> list[str]:
    """The Claude Code argument vector; the prompt goes to its stdin."""
    command = [executable, "-p", "--model", model, "--allowedTools", *ALLOWED_TOOLS,
               "--add-dir", str(source_dir), "--add-dir", str(generated_dir)]
    require_batch_safe(command, "pass -SourceDir, -GeneratedDir and -Model without those characters (rename or link "
                                "the directory).")
    return command


def batches(items: Sequence[Path], size: int) -> list[list[Path]]:
    """*items* in consecutive batches of at most *size*."""
    return [list(items[start:start + size]) for start in range(0, len(items), size)]


def triage_all(prompts: Sequence[Path], source_dir: Path, generated_dir: Path) -> tuple[list[Path], dict[Path, Path], int]:
    """Triage each prompt locally: the prompts for Claude Code, their triage files, and the clean count."""
    print()
    print(colorize("Local triage (pass -Full to skip)...", ColorCodes.GREEN))
    to_claude: list[Path] = []
    triage_files: dict[Path, Path] = {}
    clean = 0
    for prompt in prompts:
        command = [sys.executable, "-m", TRIAGE_MODULE, f"--prompt={prompt}", f"--source-dir={source_dir}",
                   f"--generated-dir={generated_dir}"]
        code = subprocess.run(command, env=script_env(), check=False).returncode
        if code == TRIAGE_CLEAN:
            clean += 1
            continue
        if code == service_triage.EXIT_NEEDS_REVIEW:
            triage_files[prompt] = prompt.parent / service_triage.TRIAGE_FILENAME_TEMPLATE.format(name=service_name(prompt))
        else:
            print(colorize(f"  Triage failed (exit {code}): {prompt.name}; it goes to Claude Code untriaged.",
                           ColorCodes.YELLOW))
        to_claude.append(prompt)
    print(colorize(f"Local triage: {clean} service(s) clean, {len(to_claude)} to Claude Code.", ColorCodes.CYAN))
    return to_claude, triage_files, clean


def evaluate_one(command: Sequence[str], prompt_text: str, eval_dir: Path, service: str) -> Evaluation:
    """One Claude Code run in *eval_dir*, its output captured."""
    started = time.monotonic()
    completed = subprocess.run(
        list(command), input=prompt_text, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=eval_dir,
        env={**os.environ, "NO_COLOR": "1"}, text=True, encoding=_UTF8, errors=_REPLACE, check=False,
    )
    minutes = (time.monotonic() - started) / SECONDS_PER_MINUTE
    status = STATUS_OK if completed.returncode == 0 else STATUS_FAILED
    return Evaluation(service, status, minutes, completed.stdout)


def run_batches(
    prompts: Sequence[Path], triage_files: dict[Path, Path], command: Sequence[str], eval_dir: Path, parallel: int
) -> list[Evaluation]:
    """Every prompt through Claude Code, *parallel* at a time, a batch finishing before the next starts."""
    groups = batches(prompts, parallel)
    print(colorize(f"Processing {len(prompts)} services in {len(groups)} batch(es) of up to {parallel}...",
                   ColorCodes.CYAN))
    print()
    results: list[Evaluation] = []
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for number, group in enumerate(groups, start=1):
            print(f"--- Batch {number}/{len(groups)} ({len(group)} services) ---")
            for prompt in group:
                print(f"  Starting: {service_name(prompt)}")
            print()
            print(colorize(f"  Waiting for batch {number} to complete...", ColorCodes.GRAY))
            runs = [pool.submit(evaluate_one, command, claude_prompt(prompt, triage_files.get(prompt)), eval_dir,
                                service_name(prompt)) for prompt in group]
            for run in runs:
                result = run.result()
                color = ColorCodes.GREEN if result.status == STATUS_OK else ColorCodes.RED
                label = "DONE:  " if result.status == STATUS_OK else "FAILED:"
                print(colorize(f"  {label} {result.service} ({result.minutes:.1f} min)", color))
                results.append(result)
            print()
    return results


def run_log(eval_dir: Path, model: str, parallel: int, results: Sequence[Evaluation], triaged: int, minutes: float) -> str:
    """The ``evaluation-run.log`` text."""
    failed = [result for result in results if result.status == STATUS_FAILED]
    lines = [
        "Evaluation Run Summary",
        "======================",
        f"Date:       {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Directory:  {eval_dir}",
        f"Model:      {model}",
        f"Parallel:   {parallel}",
        f"Total:      {len(results) + triaged}",
        f"Triaged:    {triaged} (local triage only)",
        f"Completed:  {len(results) - len(failed)}",
        f"Failed:     {len(failed)}",
        f"Duration:   {minutes:.1f} minutes",
        "",
        "Results:",
        *(f"  [{result.status}] {result.service} - {result.minutes:.1f} min" for result in results),
    ]
    if failed:
        lines += ["", "Failed Services Output:", ""]
        lines += [f"--- {result.service} ---\n{result.output}\n" for result in failed]
    return "\n".join(lines) + "\n"


def print_summary(results: Sequence[Evaluation], triaged: int, minutes: float) -> None:
    failed = sum(1 for result in results if result.status == STATUS_FAILED)
    print(RULE)
    print(colorize("EVALUATION COMPLETE", ColorCodes.GREEN))
    print(RULE)
    print()
    print(f"Total services: {len(results) + triaged}")
    print(colorize(f"Local triage:   {triaged} (clean, no Claude Code run)", ColorCodes.GREEN))
    print(colorize(f"Completed:      {len(results) - failed}", ColorCodes.GREEN))
    print(colorize(f"Failed:         {failed}", ColorCodes.RED if failed else ColorCodes.GRAY))
    print(colorize(f"Total time:     {minutes:.1f} minutes", ColorCodes.CYAN))
    print()


def confirmed(read_answer: Callable[[str], str] = input) -> bool:
    """``Proceed? (y/N)``: True only for a typed y; an end of input is a no."""
    try:
        return read_answer(PROCEED_PROMPT).strip() in PROCEED_ANSWERS
    except EOFError:
        print()
        return False


class MissingDirectoryError(Exception):
    """An input directory the run names does not exist (exit 1, as the PowerShell script did)."""


def _existing_dir(value: str, label: str, parameter: str) -> Path:
    """*value* resolved.

    Raises:
        MissingDirectoryError: *value* is not a directory.
    """
    path = Path(value)
    if not path.is_dir():
        raise MissingDirectoryError(
            f"{label} directory not found: {value}. Pass an existing directory as {parameter}."
        )
    return path.resolve()


def _announce(prompts: Sequence[Path], args: argparse.Namespace, source: Path, generated: Path, eval_dir: Path) -> None:
    print()
    print(colorize(f"Found {len(prompts)} service prompt files to evaluate:", ColorCodes.GREEN))
    for prompt in prompts:
        print(colorize(f"  - {prompt.name}", ColorCodes.GRAY))
    print()
    print(colorize(f"Parallelism: {args.parallel} | Model: {args.model}", ColorCodes.CYAN))
    print(colorize(f"Source:    {source}", ColorCodes.CYAN))
    print(colorize(f"Generated: {generated}", ColorCodes.CYAN))
    print(colorize(f"Eval dir:  {eval_dir}", ColorCodes.CYAN))
    print()


def _resolve_inputs(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    """The source, generated and evaluation directories.

    Raises:
        UsageError: A required option is missing, or ``--parallel`` is below 1.
        MissingDirectoryError: A named directory does not exist.
    """
    if not args.source_dir or not args.generated_dir:
        raise UsageError("-SourceDir and -GeneratedDir are required: the project source and its generated output.")
    if args.parallel < 1:
        raise UsageError(f"-Parallel must be 1 or more; got {args.parallel}.")
    source = _existing_dir(args.source_dir, "Source", "-SourceDir")
    generated = _existing_dir(args.generated_dir, "Generated", "-GeneratedDir")
    eval_dir = _existing_dir(args.eval_dir, "Evaluation", "-EvalDir") if args.eval_dir else Path.cwd()
    return source, generated, eval_dir


def evaluate(args: argparse.Namespace) -> int:
    try:
        source, generated, eval_dir = _resolve_inputs(args)
    except MissingDirectoryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_FAILED
    prompts = find_prompts(eval_dir)
    if not prompts:
        print("ERROR: No service-*.prompt.md files found. Run /evaluate-generated first, then cd into the evaluation "
              "folder.", file=sys.stderr)
        return EXIT_FAILED
    _announce(prompts, args, source, generated, eval_dir)
    if not confirmed():
        print(colorize("Aborted.", ColorCodes.YELLOW))
        return EXIT_OK
    executable = shutil.which(CLAUDE)
    if executable is None:
        print(f"ERROR: '{CLAUDE}' was not found on PATH. Expected the Claude Code CLI; install it and re-open the "
              "shell.", file=sys.stderr)
        return EXIT_FAILED
    command = claude_command(executable, args.model, source, generated)
    started = time.monotonic()
    triage_files: dict[Path, Path] = {}
    triaged = 0
    if not args.full:
        prompts, triage_files, triaged = triage_all(prompts, source, generated)
    print()
    print(colorize("Starting evaluations...", ColorCodes.GREEN))
    print(RULE)
    results = run_batches(prompts, triage_files, command, eval_dir, args.parallel)
    minutes = (time.monotonic() - started) / SECONDS_PER_MINUTE
    print_summary(results, triaged, minutes)
    log_path = eval_dir / RUN_LOG
    log_path.write_text(run_log(eval_dir, args.model, args.parallel, results, triaged, minutes), encoding=_UTF8)
    print(colorize(f"Log written to: {log_path}", ColorCodes.GRAY))
    failed = [result.service for result in results if result.status == STATUS_FAILED]
    if not failed:
        return EXIT_OK
    print()
    print(colorize("Failed services:", ColorCodes.RED))
    for service in failed:
        print(colorize(f"  - {service}", ColorCodes.RED))
    return EXIT_FAILED


def _check_prompts_are_found_and_named() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        eval_dir = Path(tmp)
        evaluated = eval_dir / service_triage.EVALUATED_DIR
        evaluated.mkdir()
        (evaluated / "service-catalog.prompt.md").write_text("", encoding=_UTF8)
        found = find_prompts(eval_dir)
        assert [path.name for path in found] == ["service-catalog.prompt.md"], found
        assert service_name(found[0]) == "catalog", service_name(found[0])
        (eval_dir / "service-orders.prompt.md").write_text("", encoding=_UTF8)
        assert [path.name for path in find_prompts(eval_dir)] == ["service-orders.prompt.md"]


def _check_the_prompt_goes_to_stdin_and_the_command_is_a_vector() -> None:
    prompt = claude_prompt(Path("e") / "service-a.prompt.md", Path("e") / "service-a.local-triage.json")
    assert prompt.startswith(f"{SKILL}\n\nPROMPT_FILE: "), prompt
    assert "\nLOCAL_TRIAGE: " in prompt, prompt
    assert "LOCAL_TRIAGE" not in claude_prompt(Path("service-a.prompt.md"), None)
    command = claude_command("claude", "sonnet", Path("src"), Path("gen"))
    assert command[:4] == ["claude", "-p", "--model", "sonnet"], command
    assert command.count("--add-dir") == 2 and all(tool in command for tool in ALLOWED_TOOLS), command
    claude_command("claude.cmd", "opus", Path("D:/src/shop"), Path("D:/gen/shop"))
    expect_usage_error(lambda: claude_command("claude.cmd", "opus", Path("D:/a&b"), Path("gen")), "cmd.exe")
    claude_command("claude", "opus", Path("D:/a&b"), Path("gen"))


def _check_batches_hold_at_most_parallel() -> None:
    items = [Path(str(index)) for index in range(7)]
    assert [len(group) for group in batches(items, 3)] == [3, 3, 1], batches(items, 3)
    args = build_parser().parse_args(["--source-dir=.", "--generated-dir=.", "--parallel=0"])
    expect_usage_error(lambda: _resolve_inputs(args), "-Parallel")


def _check_a_missing_directory_exits_1() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "no-such"
        args = build_parser().parse_args([f"--source-dir={missing}", f"--generated-dir={tmp}"])
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            code = evaluate(args)
    assert code == EXIT_FAILED, code
    assert f"Source directory not found: {missing}" in errors.getvalue() and "-SourceDir" in errors.getvalue(), (
        errors.getvalue()
    )


def _check_only_a_typed_y_proceeds() -> None:
    def ended(_prompt: str) -> str:
        raise EOFError

    assert confirmed(lambda _prompt: "y") and confirmed(lambda _prompt: "Y ")
    assert not confirmed(lambda _prompt: "") and not confirmed(lambda _prompt: "yes")
    assert not confirmed(ended)


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [
            *(check.run for check in service_triage.self_test_checks()),
            _check_prompts_are_found_and_named,
            _check_the_prompt_goes_to_stdin_and_the_command_is_a_vector,
            _check_batches_hold_at_most_parallel,
            _check_a_missing_directory_exits_1,
            _check_only_a_typed_y_proceeds,
        ]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(),
                             folder=GENERATION_SCRIPTS_DIR)
    return evaluate(args)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
