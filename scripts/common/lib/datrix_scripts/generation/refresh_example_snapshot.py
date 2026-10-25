"""Refresh one committed example snapshot with one command.

Generates a single example in a single registered language into a scratch
directory, then replaces ``<example>/generated/<language>-<platform>/`` with
exactly the files a commit would keep:

  1. ``datrix_scripts.dev.generate --source=<source> --output=<scratch>
     --language=<language>`` (generate.ps1's module, single-project mode; never
     ``--all``, ``--domains`` or ``--test-set``).
  2. The scratch tree is copied into place, then every path git would ignore
     there is deleted again. The ignore set is asked of git itself
     (``git ls-files --others --ignored --exclude-standard``) against the
     showcase repository, so it is the union of the repository's own rules
     (``.datrix/`` state) and the generated project's own ``.gitignore``
     (build output, per-service ``secrets/``) with their real anchoring --
     derived, never restated here.
  3. A language that is not a registered ``datrix.languages`` entry is
     refused (exit 2), naming the installed set.

``<platform>`` is a registered ``datrix.platforms`` name taken from the
example's resolved deployment (default profile ``test``): the provider-owned
platform generator when the provider owns one (``aws``), otherwise the
platform that emits the runtime's container scaffolding (``docker`` for
docker-compose). When the deployment names none or several, ``--platform``
chooses and the run is refused without it.

The module behind ``generation/refresh-example-snapshot.ps1`` (and its ``.sh`` twin).

Usage:
    python -m datrix_scripts.generation.refresh_example_snapshot --source=<system.dtrx> --language=<name>
    python -m datrix_scripts.generation.refresh_example_snapshot --self-test
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, UsageError
from datrix_scripts.paths import WORKSPACE_DIR, script_env
from datrix_scripts.registered_targets import (
    registered_language_names,
    registered_platform_names,
)
from datrix_scripts.test.wrappers import GENERATION_SCRIPTS_DIR, module_main, run_self_test

logger = logging.getLogger(__name__)

MODULE: Final = "datrix_scripts.generation.refresh_example_snapshot"
WRAPPER: Final = "refresh-example-snapshot"
WORKSPACE_ROOT: Path = WORKSPACE_DIR
SCRATCH_ROOT: Path = WORKSPACE_ROOT / ".tmp"
SNAPSHOT_SCRATCH_ROOT: Path = SCRATCH_ROOT / "example-snapshots"
GENERATE_MODULE: Final = "datrix_scripts.dev.generate"
SNAPSHOT_CONTAINER_NAME: Final = "generated"
DEFAULT_PROFILE: Final = "test"

EXIT_OK: Final = 0
EXIT_FAIL: Final = 1
EXIT_USAGE: Final = 2


class RefreshError(Exception):
    """A refresh could not proceed; the message names the cause and the fix.

    ``exit_code`` is ``EXIT_USAGE`` for a refused request (unregistered target,
    bad source, ambiguous platform) and ``EXIT_FAIL`` for a failed run.
    """

    def __init__(self, message: str, exit_code: int = EXIT_FAIL) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def derive_platform(
    source_dir: Path, profile: str, platforms: frozenset[str]
) -> str:
    """The registered platform a snapshot of *source_dir* under *profile* is named for.

    The resolved deployment decides: a provider that owns a platform generator
    names the snapshot (``aws``); otherwise the platform that declares the
    runtime's container scaffolding does (``docker`` for docker-compose).

    Raises:
        RefreshError: The deployment resolves to no registered platform or to several.
    """
    from datrix_common.config.unified_loader import load_system_config
    from datrix_common.plugin._capability_declarations import declaration_for_provider
    from datrix_common.plugin._capability_scaffold_ports import (
        container_scaffold_generator_names_for,
    )
    from datrix_language.parser.dcfg_documents import disk_config_documents

    unified = load_system_config(
        config_path=source_dir / "config" / "system.dcfg",
        project_root=source_dir,
        profile=profile,
        documents=disk_config_documents(),
    )
    deployment = unified.system.deployment
    provider = deployment.provider.value
    if declaration_for_provider(provider).owns_provider_platform_generator:
        candidates = [provider]
    else:
        candidates = list(container_scaffold_generator_names_for(deployment.runtime))
    candidates = [name for name in candidates if name in platforms]
    if len(candidates) != 1:
        raise RefreshError(
            f"profile '{profile}' of {source_dir} (runtime {deployment.runtime.value}, "
            f"provider {provider}) resolves to platform candidates {candidates}; exactly "
            f"one is required. Registered platforms: {sorted(platforms)}. Fix: pass "
            f"--platform <name>.",
            EXIT_USAGE,
        )
    return candidates[0]


def extended(path: Path) -> Path:
    """*path* in the form the OS accepts past ``MAX_PATH`` (a generated tree nests deeper).

    On Windows an absolute path is prefixed ``\\\\?\\``; elsewhere it is returned unchanged.
    """
    if os.name != "nt":
        return path
    resolved = str(path.resolve())
    return Path(resolved if resolved.startswith("\\\\?\\") else "\\\\?\\" + resolved)


def _git(repo: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-c", "core.quotepath=off", "-C", str(repo), *args],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise RefreshError(
            f"git {' '.join(args)} failed in {repo} (exit {completed.returncode}): "
            f"{completed.stderr.decode('utf-8', errors='replace').strip()}. "
            f"Fix: the snapshot must sit inside a git repository."
        )
    return completed.stdout


def repository_root(path: Path) -> Path:
    """The git work-tree root containing *path*."""
    return Path(_git(path, "rev-parse", "--show-toplevel").decode("utf-8").strip())


def prune_ignored(repo: Path, tree: Path) -> list[Path]:
    """Delete every path under *tree* that git would ignore; return what was deleted.

    Args:
        repo: The git work-tree root *tree* sits in.
        tree: The directory to prune (absolute, inside *repo*).
    """
    relative = tree.relative_to(repo).as_posix()
    listing = _git(
        repo,
        "ls-files",
        "-z",
        "--others",
        "--ignored",
        "--exclude-standard",
        "--directory",
        "--",
        relative,
    )
    removed: list[Path] = []
    for raw in listing.split(b"\0"):
        if not raw:
            continue
        target = repo / raw.decode("utf-8").rstrip("/")
        if any(parent in removed for parent in target.parents):
            continue
        if extended(target).is_dir():
            shutil.rmtree(extended(target))
        else:
            extended(target).unlink()
        removed.append(target)
    return removed


def _generate(source: Path, scratch: Path, language: str) -> None:
    command = [
        sys.executable,
        "-m",
        GENERATE_MODULE,
        f"--source={source}",
        f"--output={scratch}",
        f"--language={language}",
    ]
    print(f"Generating {source} for {language} into {scratch}", flush=True)
    completed = subprocess.run(command, env=script_env(), check=False)
    if completed.returncode != 0:
        raise RefreshError(
            f"generate.ps1 exited {completed.returncode} for {source} (-Language {language}). "
            f"A generation failure is a generator defect: fix it for {language}; the "
            f"stale snapshot is left untouched."
        )
    if not scratch.is_dir() or not any(scratch.iterdir()):
        raise RefreshError(
            f"generate.ps1 exited 0 but wrote nothing under {scratch}. Fix: run it "
            f"directly and read its output."
        )


def refresh(source: Path, language: str, platform: str | None, profile: str) -> Path:
    """Regenerate ``<example>/generated/<language>-<platform>/``; return that directory."""
    languages = registered_language_names()
    if language not in languages:
        raise RefreshError(
            f"'{language}' is not a registered datrix.languages entry; installed: "
            f"{sorted(languages)}. Fix: pass one of those, or install the "
            f"datrix-codegen package that registers it.",
            EXIT_USAGE,
        )
    if not source.is_file():
        raise RefreshError(
            f"source {source} is not a file. Fix: pass the example's system.dtrx.", EXIT_USAGE
        )
    example_dir = source.parent
    chosen = platform or derive_platform(example_dir, profile, registered_platform_names())
    if chosen not in registered_platform_names():
        raise RefreshError(
            f"'{chosen}' is not a registered datrix.platforms entry; installed: "
            f"{sorted(registered_platform_names())}.",
            EXIT_USAGE,
        )
    name = f"{language}-{chosen}"
    scratch = SNAPSHOT_SCRATCH_ROOT / example_dir.name / name
    if extended(scratch).exists():
        shutil.rmtree(extended(scratch))
    scratch.parent.mkdir(parents=True, exist_ok=True)
    _generate(source, scratch, language)

    destination = example_dir / SNAPSHOT_CONTAINER_NAME / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if extended(destination).exists():
        shutil.rmtree(extended(destination))
    shutil.copytree(extended(scratch), extended(destination))
    removed = prune_ignored(repository_root(destination), destination)
    kept = sum(1 for p in extended(destination).rglob("*") if p.is_file())
    print(f"Refreshed {destination}: {kept} file(s) kept, {len(removed)} ignored path(s) dropped")
    return destination


def fixture_failures() -> list[str]:
    """A fixture project with ``secrets/`` and ``.datrix/`` copies neither."""
    failures: list[str] = []
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=SCRATCH_ROOT) as scratch:
        repo = Path(scratch) / "repo"
        project = repo / "examples" / "x" / SNAPSHOT_CONTAINER_NAME / "lang-platform"
        files = {
            repo / ".gitignore": ".datrix/\n",
            project / ".gitignore": "secrets/\nbuild/\n",
            project / "src" / "a.txt": "kept\n",
            project / "secrets" / "db-password": "ignored by the project's own rule\n",
            project / "build" / "out.bin": "ignored by the project's own rule\n",
            project / ".datrix" / "state.json": "ignored by the repository rule\n",
        }
        for path, content in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        _git(repo, "init", "--quiet")
        removed = prune_ignored(repo, project)
        survivors = sorted(
            p.relative_to(project).as_posix() for p in project.rglob("*") if p.is_file()
        )
        if survivors != [".gitignore", "src/a.txt"]:
            failures.append(f"fixture survivors {survivors}, expected ['.gitignore', 'src/a.txt']")
        removed_names = sorted(p.relative_to(project).as_posix() for p in removed)
        if removed_names != [".datrix", "build", "secrets"]:
            failures.append(
                f"fixture removed {removed_names}, expected ['.datrix', 'build', 'secrets']"
            )
    return failures


def build_parser() -> argparse.ArgumentParser:
    """The options of ``generation/refresh-example-snapshot.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--source", type=Path, help="The example's system.dtrx.")
    parser.add_argument("--language", type=str.lower, help="A registered datrix.languages name.")
    parser.add_argument("--platform", help="Override the platform derived from the deployment.")
    parser.add_argument("--config-profile", dest="profile", default=DEFAULT_PROFILE,
                        help=f"Config profile that selects the deployment (default: {DEFAULT_PROFILE}).")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the fixture self-test (a project with secrets/ and .datrix/ copies neither).")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Enable DEBUG logging.")
    return parser


def _check_ignored_paths_are_not_copied() -> None:
    failures = fixture_failures()
    assert not failures, "; ".join(failures)


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test([_check_ignored_paths_are_not_copied], wrapper=WRAPPER, module=MODULE,
                             parser=build_parser(), folder=GENERATION_SCRIPTS_DIR)
    if args.source is None or args.language is None:
        raise UsageError("-Source and -Language are required unless -SelfTest is given.")
    failures = fixture_failures()
    if failures:
        for failure in failures:
            print(f"SELF-TEST FAILURE: {failure}")
        return EXIT_USAGE
    print("Self-test passed")
    try:
        refresh(args.source.resolve(), args.language, args.platform, args.profile)
    except RefreshError as exc:
        print(f"ERROR: {exc}")
        return exc.exit_code
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
