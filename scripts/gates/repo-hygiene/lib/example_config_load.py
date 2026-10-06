"""Example config load gate: every declared profile of every example ``.dcfg`` loads.

Every model a ConfigDSL document validates into rejects unknown keys, so a
key the model does not declare is an error at load time instead of a value
silently dropped. This gate loads every declared profile of every ``.dcfg``
under ``datrix/examples`` through the real loaders and reports every error,
so a misspelled or retired key in the corpus is found here and not by whoever
generates that example next.

Each config kind is loaded by its own loader (``service``, ``shared``,
``system``, ``identity``, ``app``, ``strings``, ``extern``); the kind is read
from the parsed declaration, never from a file name. A kind with no loader
here is a failure of the gate itself, so a new kind cannot be skipped
silently.

Built-in non-vacuity self-test, every invocation: a planted ``.dcfg`` carrying
an unknown nested key must be reported with the key named and the valid keys
listed, and the same document without the key must load clean.

Usage:
    python example_config_load.py
    python example_config_load.py --debug
    python example_config_load.py --self-test
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from datrix_common.config.dcfg.ast_nodes import ConfigDecl
from datrix_common.config.dcfg.parser import ConfigDSLParseError, parse_dcfg
from datrix_common.config.dcfg.resolver import ConfigDSLResolutionError
from datrix_common.config.extern_service.loader import load_extern_service_config
from datrix_common.config.unified_loader import (
    load_app_config,
    load_identity_config,
    load_service_config,
    load_shared_config,
    load_strings_config,
    load_system_config,
)
from datrix_common.errors.configuration import ConfigValidationError

from datrix_scripts.paths import SHOWCASE_DIR

logger = logging.getLogger(__name__)

DATRIX_DIR: Path = SHOWCASE_DIR
EXAMPLES_ROOT: Path = DATRIX_DIR / "examples"

#: The file name that marks an example's project root.
_PROJECT_MARKER: str = "system.dtrx"

#: A strings file has no deployment-profile axis: it is loaded once.
_STRINGS_KIND: str = "strings"

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

_LOAD_ERRORS = (ConfigValidationError, ConfigDSLResolutionError, ConfigDSLParseError)

_PLANTED_UNKNOWN_KEY: str = "timeout"

_PLANTED_TEMPLATE = """config service probe.ProbeService {{
  base {{
    port = 8000;
    resilience {{
      dependencyPolicy {{
        defaults {{
          service {{
            availability = "required";
            health = "ready";
{extra}          }}
        }}
      }}
    }}
  }}
  profile test extends base {{
  }}
}}
"""


def project_root_of(config_path: Path) -> Path:
    """The nearest ancestor holding ``system.dtrx``, else the file's directory."""
    for ancestor in config_path.parents:
        if (ancestor / _PROJECT_MARKER).is_file():
            return ancestor
    return config_path.parent


def _loader_for(kind: str) -> Callable[[Path, Path, str], object]:
    """The loader of one config kind, with the uniform (path, root, profile) shape."""
    loaders: dict[str, Callable[[Path, Path, str], object]] = {
        "service": load_service_config,
        "shared": load_shared_config,
        "system": load_system_config,
        "identity": load_identity_config,
        "app": load_app_config,
        "extern": lambda path, root, profile: load_extern_service_config(
            path, profile, project_root=root
        ),
    }
    if kind not in loaders:
        raise ConfigValidationError(
            Path("<gate>"),
            [
                f"example-config-load gate has no loader for config kind '{kind}'. "
                f"Known kinds: {sorted([*loaders, _STRINGS_KIND])}. Fix: add the kind's "
                f"loader to this gate."
            ],
        )
    return loaders[kind]


def _declaration_of(config_path: Path) -> ConfigDecl:
    return parse_dcfg(config_path.read_text(encoding="utf-8"), str(config_path))


def load_errors(config_path: Path, project_root: Path) -> list[str]:
    """One line per profile of ``config_path`` that fails to load.

    Raises:
        ConfigDSLParseError: If the file does not parse.
    """
    declaration = _declaration_of(config_path)
    if declaration.kind == _STRINGS_KIND:
        profiles = [""]
    else:
        profiles = [profile.name for profile in declaration.profiles]
    errors: list[str] = []
    for profile in profiles:
        try:
            if declaration.kind == _STRINGS_KIND:
                load_strings_config(config_path, project_root)
            else:
                _loader_for(declaration.kind)(config_path, project_root, profile)
        except _LOAD_ERRORS as exc:
            label = profile or declaration.kind
            errors.append(f"{config_path.name} [{declaration.kind} {label}]: {exc}")
    return errors


def discover_configs() -> list[Path]:
    """Every ``.dcfg`` under the examples tree."""
    return sorted(EXAMPLES_ROOT.rglob("*.dcfg"))


def run_self_test() -> list[str]:
    """Prove a planted unknown key is reported and its clean twin loads."""
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="example-config-load-") as raw_dir:
        root = Path(raw_dir)
        planted = root / "planted.dcfg"
        planted.write_text(
            _PLANTED_TEMPLATE.format(extra=f"            {_PLANTED_UNKNOWN_KEY} = 5000;\n"),
            encoding="utf-8",
        )
        clean = root / "clean.dcfg"
        clean.write_text(_PLANTED_TEMPLATE.format(extra=""), encoding="utf-8")

        planted_errors = load_errors(planted, root)
        if not any(f"Unknown key '{_PLANTED_UNKNOWN_KEY}'" in line for line in planted_errors):
            problems.append(
                "the planted unknown key was not reported as an unknown key; got "
                f"{planted_errors!r}"
            )
        if any("5000" in line for line in planted_errors):
            problems.append("the load error echoed the offending value")
        clean_errors = load_errors(clean, root)
        if clean_errors:
            problems.append(f"the clean twin of the planted document failed to load: {clean_errors!r}")
    return problems


def check_example_configs() -> int:
    """Run the gate against the real examples tree."""
    configs = discover_configs()
    if not configs:
        logger.error(
            "EXAMPLE-CONFIG-LOAD GATE CANNOT RUN: zero .dcfg found under %s -- an empty "
            "corpus would make this check vacuously pass.",
            EXAMPLES_ROOT,
        )
        return EXIT_USAGE
    failures: list[str] = []
    for config_path in configs:
        failures.extend(load_errors(config_path, project_root_of(config_path)))
    for failure in failures:
        logger.error("  %s", failure)
    if failures:
        logger.error(
            "EXAMPLE-CONFIG-LOAD GATE FAILED: %d profile load(s) failed across %d config file(s).",
            len(failures),
            len(configs),
        )
        return EXIT_FAIL
    logger.info(
        "EXAMPLE-CONFIG-LOAD GATE PASSED: %d config file(s), every declared profile loads.",
        len(configs),
    )
    return EXIT_OK


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Example config load gate: every declared profile of every example .dcfg "
            "loads through the real loaders."
        ),
    )
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip the real check",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Returns:
        0 = every profile loads (or a successful ``--self-test``), 1 = at least one
        profile failed to load, 2 = self-test failure, empty corpus, or an unparsable
        file.
    """
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    if not args.debug:
        # The config loader narrates every profile resolution at INFO; only
        # this gate's verdict lines are the report.
        logging.getLogger("datrix_common").setLevel(logging.WARNING)

    problems = run_self_test()
    if problems:
        logger.error("NON-VACUITY SELF-TEST FAILED -- aborting before any real check:")
        for problem in problems:
            logger.error("  %s", problem)
        return EXIT_USAGE
    logger.info("non-vacuity self-test: PASS")

    if args.self_test:
        return EXIT_OK

    try:
        return check_example_configs()
    except (ConfigDSLParseError, OSError, ConfigValidationError) as exc:
        logger.error("ERROR: %s", exc)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
