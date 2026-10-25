"""Analyze a fixture project in seconds and show what the production front half makes of it.

The module behind ``dev/probe-fixture.ps1`` (and its ``.sh`` twin). A fixture project is a ``.dtrx``
whose ``system`` and ``service`` declarations name committed ``.dcfg`` files. A wrong ``.dcfg`` key,
flavor or DSL shape surfaces as an analysis or config-resolution error; this script runs the same
front half the tests run (``datrix_testing.project.analyzed_project``) for each requested profile
and prints either the error text or what each service holds (its datasource blocks, queues,
serverless blocks and integrations), so the project is known to analyze before a test run depends
on it.

It writes a stamp, ``<workspace>/.tmp/fixture-probes/<sha1 of the project directory>.json``, once
it has shown the result, failed or not. ``.claude/hooks/guard-test-run-discipline.py`` refuses a
test run that follows an edit of a ``tests/fixtures/[projects/]<name>/`` project with no stamp newer
than the edit; the stamp key and the project-directory rule below are the hook's
(``_fixture_probe.py``), and the hook's self-test compares the two.

Usage:
    python -m datrix_scripts.dev.probe_fixture --path <system.dtrx|dir> [--config-profile test[,other]] [--dbg]

Exit codes: 0 every profile analyzed, 1 a profile failed, 2 usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.dev.arguments import comma_values
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, UsageError, expect_usage_error, write_files
from datrix_scripts.paths import TMP_DIR
from datrix_scripts.test.wrappers import DEV_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.dev.probe_fixture"
WRAPPER: Final = "probe-fixture"
EXIT_OK: Final[int] = 0
EXIT_FAILED: Final[int] = 1
DEFAULT_PROFILE: Final = "test"
MAIN_DTRX: Final = "system.dtrx"
STAMP_DIR: Final[Path] = TMP_DIR / "fixture-probes"
MAX_ERROR_CHARS: Final = 3000

#: The directory of a fixture project: the first directory below ``tests/fixtures/`` (below
#: ``tests/fixtures/projects/`` when that exists) holding the probed file.
_PROJECT_RE: Final = re.compile(r"^(.*?/tests/fixtures/(?:projects/)?[^/]+)/.+$", re.IGNORECASE)

#: The model attributes that hold a service's named blocks, in the order they are printed.
_BLOCK_ATTRIBUTES: Final = (
    "rdbms_blocks",
    "nosql_blocks",
    "cache_blocks",
    "pubsub_blocks",
    "storage_blocks",
    "search_blocks",
    "cdn_blocks",
    "serverless_blocks",
)

_MINIMAL_PROJECT: Final = {
    "system.dtrx": (
        "system shop.Mini('config/system.dcfg') : version('1.0.0') {\n}\n\n"
        "service shop.Svc('config/svc.dcfg') : version('1.0.0') {\n"
        "    rest_api Api : basePath('/api') {\n    }\n}\n"
    ),
    "config/system.dcfg": (
        "config system shop.Mini {\n  base {\n    deployment {\n"
        '      runtime = "docker-compose";\n      provider = "local";\n    }\n  }\n\n'
        '  profile test as "test" extends base {\n'
        '    alias env = "TEST";\n    alias resource = "test";\n  }\n}\n'
    ),
    "config/svc.dcfg": (
        "config service shop.Svc {\n  base {\n    port = 8080;\n"
        '    flavor = "compose";\n  }\n\n'
        '  profile test as "test" extends base {\n'
        '    alias env = "TEST";\n    alias resource = "test";\n  }\n}\n'
    ),
}


def build_parser() -> argparse.ArgumentParser:
    """The options of ``dev/probe-fixture.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--path", default="", help="The fixture project's .dtrx file, or its directory (system.dtrx).")
    parser.add_argument(
        "--config-profile",
        action="append",
        default=[],
        help=f"Config profile to analyze (default {DEFAULT_PROFILE}). Repeatable or comma-separated.",
    )
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Debug logging.")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the self-test: a planted project analyzes, a broken one reports its error, the stamp is keyed.",
    )
    parser.set_defaults(debug=False)
    return parser


def resolve_dtrx(raw: str) -> Path:
    """The ``.dtrx`` to probe: the file named, or ``system.dtrx`` of the directory named."""
    if not raw:
        raise UsageError("-Path is required: the fixture project's .dtrx file or its directory.")
    path = Path(raw).resolve()
    candidate = path / MAIN_DTRX if path.is_dir() else path
    if candidate.suffix.lower() != ".dtrx" or not candidate.is_file():
        raise UsageError(f"-Path {raw} is not a .dtrx file and holds no {MAIN_DTRX}. Name the project's .dtrx.")
    return candidate


def project_directory(dtrx: Path) -> str:
    """The directory a stamp is keyed by: the fixture project directory, else the file's own."""
    posix = dtrx.resolve().as_posix()
    match = _PROJECT_RE.match(posix)
    return match.group(1) if match else dtrx.resolve().parent.as_posix()


def stamp_path(directory: str) -> Path:
    """The stamp file of a project directory (the hook computes the same name)."""
    digest = hashlib.sha1(directory.replace("\\", "/").lower().encode("utf-8"), usedforsecurity=False).hexdigest()
    return STAMP_DIR / f"{digest}.json"


def write_stamp(directory: str, profiles: Sequence[str], failed: Sequence[str], stamp_dir: Path = STAMP_DIR) -> Path:
    """Record that the probe showed *directory*'s result just now."""
    target = stamp_dir / stamp_path(directory).name
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"dir": directory, "ts": time.time(), "profiles": list(profiles), "failed": list(failed)}
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def _block_summary(service: object) -> list[str]:
    parts: list[str] = []
    for attribute in _BLOCK_ATTRIBUTES:
        blocks = getattr(service, attribute, None)
        if blocks:
            parts.append(f"{attribute.removesuffix('_blocks')}[{', '.join(str(name) for name in blocks)}]")
    if getattr(service, "queues_block", None) is not None:
        parts.append("queues")
    if getattr(service, "integrations", None) is not None:
        parts.append("integrations")
    return parts


def probe_profile(dtrx: Path, profile: str) -> bool:
    """Analyze the project under *profile* and print the outcome; False when it failed."""
    from datrix_testing.parsing import register_installed_parsers
    from datrix_testing.project import analyzed_project

    register_installed_parsers()
    try:
        app = analyzed_project(dtrx, profile=profile)
    except Exception as exc:  # noqa: BLE001 - every analysis failure is the answer this script exists to show
        print(f"[FAIL] profile {profile}: {type(exc).__name__}")
        print(str(exc)[:MAX_ERROR_CHARS])
        return False
    print(f"[ OK ] profile {profile}: {len(app.services)} service(s)")
    for name, service in app.services.items():
        print(f"         {name}: {', '.join(_block_summary(service)) or 'no blocks'}")
    return True


def probe(dtrx: Path, profiles: Sequence[str]) -> int:
    """Probe every profile, stamp the project, and return the exit code."""
    failed = [profile for profile in profiles if not probe_profile(dtrx, profile)]
    stamp = write_stamp(project_directory(dtrx), profiles, failed)
    print(f"stamp: {stamp.as_posix()}")
    return EXIT_FAILED if failed else EXIT_OK


def _check_a_planted_project_analyzes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_files(root, _MINIMAL_PROJECT)
        assert probe_profile(resolve_dtrx(str(root)), DEFAULT_PROFILE), "the planted minimal project must analyze"


def _check_a_broken_project_reports_its_error() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_files(
            root,
            {**_MINIMAL_PROJECT, "config/svc.dcfg": "config service shop.Svc {\n  base {\n    nonsense = 1;\n  }\n}\n"},
        )
        assert not probe_profile(resolve_dtrx(str(root)), DEFAULT_PROFILE), "a project with an unknown key must fail"


def _check_the_stamp_is_keyed_by_the_project_directory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "pkg" / "tests" / "fixtures" / "projects" / "demo"
        write_files(project, _MINIMAL_PROJECT)
        dtrx = resolve_dtrx(str(project / MAIN_DTRX))
        directory = project_directory(dtrx)
        assert directory == project.resolve().as_posix(), f"the project directory is {directory}"
        nested = project_directory(project / "config" / "svc.dcfg")
        assert nested == directory, "a file below the project resolves to the same project directory"
        written = write_stamp(directory, ["test"], [], stamp_dir=Path(tmp) / "stamps")
        assert written.name == stamp_path(directory).name, "the stamp name is the hash of the directory"
        assert json.loads(written.read_text(encoding="utf-8"))["dir"] == directory


def _check_a_missing_path_is_refused() -> None:
    expect_usage_error(lambda: resolve_dtrx(""), "-Path is required")
    expect_usage_error(lambda: resolve_dtrx(str(Path(tempfile.gettempdir()))), "holds no system.dtrx")


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [
            _check_a_planted_project_analyzes,
            _check_a_broken_project_reports_its_error,
            _check_the_stamp_is_keyed_by_the_project_directory,
            _check_a_missing_path_is_refused,
        ]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=DEV_SCRIPTS_DIR)
    profiles = comma_values(args.config_profile) or [DEFAULT_PROFILE]
    return probe(resolve_dtrx(args.path), profiles)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
