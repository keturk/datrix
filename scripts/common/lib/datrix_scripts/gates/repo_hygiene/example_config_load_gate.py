"""Example config load gate: every declared profile of every example ``.dcfg`` loads,
and every example analyzes under every leaf profile of its system config.

Every model a config document validates into rejects unknown keys, so a
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

A config that loads can still contradict a semantic rule only analysis checks
(a pooled block sizing itself, a group its members disagree on), and a
profile nobody generates by default is otherwise first analyzed by whoever
generates it. So every example whose configs all load is then analyzed --
parse, config resolution and semantic analysis, the front half a generation
run executes (``datrix_testing.project.analysis_of``) -- under every leaf
profile of its system config: a profile no other profile ``extends``. An
intermediate profile only other profiles build on is not a deployment
profile, and service configs need not declare it.

Built-in non-vacuity self-test, every invocation: a planted ``.dcfg`` carrying
an unknown nested key must be reported with the key named and the valid keys
listed, and the same document without the key must load clean; a planted
project whose pooled messaging block sizes itself must be reported with
``POOL002`` under its leaf profile, and its clean twin -- whose system config
also declares an intermediate profile the service config does not -- must
analyze clean.

Run it through ``gates/repo-hygiene/example-config-load-gate.ps1`` or its ``.sh`` twin; it runs in gate
mode (``datrix_scripts.gate_log.run_as_gate``) and prints the
``[GATE] example-config-load PASSED|FAILED exit=<n> log=<path>`` verdict last.
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Final

from datrix_common.config.dcfg.ast_nodes import ConfigDecl
from datrix_common.config.dcfg.errors import DcfgResolutionError, DcfgSyntaxError
from datrix_common.config.extern_service.loader import load_extern_service_config
from datrix_common.config.unified_loader import (
    load_app_config,
    load_identity_config,
    load_service_config,
    load_shared_config,
    load_strings_config,
    load_system_config,
)
from datrix_common.config_resolution import ConfigResolutionError
from datrix_common.errors.base import DatrixError
from datrix_common.errors.codegen import PipelineError
from datrix_common.errors.configuration import ConfigValidationError
from datrix_common.protocols.config_documents import ConfigDocumentSourceProtocol
from datrix_common.source_syntax import SourceParseError
from datrix_language.parser.dcfg_documents import disk_config_documents
from datrix_testing.parsing import register_installed_parsers
from datrix_testing.project import analysis_of

from datrix_scripts.gate_harness import write_files
from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.gates.repo_hygiene.gate_options import packages_current, self_test_gate_parser
from datrix_scripts.paths import SHOWCASE_DIR
from datrix_scripts.test import wrappers

logger = logging.getLogger(__name__)

GATE: Final = "example-config-load"
MODULE: Final = "datrix_scripts.gates.repo_hygiene.example_config_load_gate"
WRAPPER: Final = "example-config-load-gate"

DATRIX_DIR: Path = SHOWCASE_DIR
EXAMPLES_ROOT: Path = DATRIX_DIR / "examples"

#: The file name that marks an example's project root.
_PROJECT_MARKER: str = "system.dtrx"

#: A strings file has no deployment-profile axis: it is loaded once.
_STRINGS_KIND: str = "strings"

#: The config kind whose leaf profiles an example is analyzed under.
_SYSTEM_KIND: str = "system"

#: Packages whose INFO narration (builtins, config resolution, analysis) is not
#: this gate's report.
_QUIET_PACKAGES: tuple[str, ...] = (
    "datrix_common",
    "datrix_language",
    "datrix_semantic",
    "datrix_codegen_kernel",
    "datrix_testing",
)

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

_LOAD_ERRORS = (ConfigValidationError, DcfgResolutionError, DcfgSyntaxError)

#: What the front half raises instead of returning diagnostics: a source or
#: config that does not parse, resolve or validate, or a seed document that
#: cannot be read.
_ANALYSIS_ERRORS = (
    DatrixError,
    PipelineError,
    ConfigResolutionError,
    DcfgResolutionError,
    SourceParseError,
)

_PLANTED_UNKNOWN_KEY: str = "timeout"

_PLANTED_TEMPLATE = """config service probe.ProbeService {{
  base {{
    port = 8000;
    resilience {{
      dependencyPolicy {{
        defaults {{
          rdbms {{
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

#: Where the planted pooled project's service config takes its planted sizing line.
_SIZING_SLOT: str = "<sizing>"

#: The diagnostic a pooled block that sizes itself must raise.
_PLANTED_SIZING_CODE: str = "POOL002"

#: A project whose messaging block pools into a namespace group. Its system
#: config declares an intermediate profile (``cloud``) the service config does
#: not, so analyzing that profile would fail: only the leaf ``test`` is analyzed.
_PLANTED_POOLED_PROJECT: dict[str, str] = {
    "system.dtrx": (
        "system probe.Store('config/system.dcfg') : version('1.0.0') {}\n\n"
        "service probe.OrderService('config/order-service.dcfg') : version('1.0.0') {\n"
        "    pubsub events {\n"
        "        topic OrderTopic {\n"
        "            publish OrderPlaced(UUID orderId);\n"
        "        }\n"
        "    }\n\n"
        "    subscribe OrderTopic {\n"
        "        on OrderPlaced(UUID orderId) {\n"
        '            Log.info("placed");\n'
        "        }\n"
        "    }\n"
        "}\n"
    ),
    "config/system.dcfg": (
        "config system probe.Store {\n"
        "  base {\n"
        "    deployment {\n"
        '      runtime = "azure-app-service-container";\n'
        '      provider = "azure";\n'
        "    }\n"
        "  }\n\n"
        "  profile cloud extends base {\n"
        "    namespaceGroups {\n"
        "      core {\n"
        '        sku = "Standard";\n'
        "        capacity = 1;\n"
        "      }\n"
        "    }\n"
        "  }\n\n"
        '  profile test as "test" extends cloud {\n'
        '    alias env = "TEST";\n'
        '    alias resource = "test";\n'
        "  }\n"
        "}\n"
    ),
    "config/order-service.dcfg": (
        "config service probe.OrderService {\n"
        "  base {\n"
        "    port = 8000;\n"
        "    pubsub events {\n"
        '      engine = "kafka";\n'
        '      flavor = "event-hubs";\n'
        f"{_SIZING_SLOT}"
        "      partitions = 3;\n"
        "      replicationFactor = 1;\n"
        '      namespaceGroup = "core";\n'
        "    }\n"
        "  }\n\n"
        '  profile test as "test" extends base {\n'
        '    alias env = "TEST";\n'
        '    alias resource = "test";\n'
        "  }\n"
        "}\n"
    ),
}


def project_root_of(config_path: Path) -> Path:
    """The nearest ancestor holding ``system.dtrx``, else the file's directory."""
    for ancestor in config_path.parents:
        if (ancestor / _PROJECT_MARKER).is_file():
            return ancestor
    return config_path.parent


def _loader_for(
    kind: str, documents: ConfigDocumentSourceProtocol
) -> Callable[[Path, Path, str], object]:
    """The loader of one config kind, with the uniform (path, root, profile) shape,
    reading every ``.dcfg`` through *documents*."""
    loaders: dict[str, Callable[[Path, Path, str], object]] = {
        "service": lambda path, root, profile: load_service_config(
            path, root, profile, documents=documents
        ),
        "shared": lambda path, root, profile: load_shared_config(
            path, root, profile, documents=documents
        ),
        "system": lambda path, root, profile: load_system_config(
            path, root, profile, documents=documents
        ),
        "identity": lambda path, root, profile: load_identity_config(
            path, root, profile, documents=documents
        ),
        "app": lambda path, root, profile: load_app_config(
            path, root, profile, documents=documents
        ),
        "extern": lambda path, root, profile: load_extern_service_config(
            path, profile, documents=documents, project_root=root
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


def load_errors(
    config_path: Path, project_root: Path, documents: ConfigDocumentSourceProtocol
) -> list[str]:
    """One line per profile of ``config_path`` that fails to load.

    The declaration and every load read through *documents*, so a file (or an
    import several files share) is parsed once per gate run.

    Raises:
        DcfgSyntaxError: If the file does not parse.
    """
    config_path = config_path.resolve()
    declaration = documents.config_document(config_path)
    if declaration.kind == _STRINGS_KIND:
        profiles = [""]
    else:
        profiles = [profile.name for profile in declaration.profiles]
    errors: list[str] = []
    for profile in profiles:
        try:
            if declaration.kind == _STRINGS_KIND:
                load_strings_config(config_path, project_root, documents=documents)
            else:
                _loader_for(declaration.kind, documents)(config_path, project_root, profile)
        except _LOAD_ERRORS as exc:
            label = profile or declaration.kind
            errors.append(f"{config_path.name} [{declaration.kind} {label}]: {exc}")
    return errors


def leaf_profiles(declaration: ConfigDecl) -> list[str]:
    """The profiles of *declaration* no other profile of it ``extends``, in declaration order."""
    extended = {profile.extends for profile in declaration.profiles}
    return [profile.name for profile in declaration.profiles if profile.name not in extended]


def analysis_errors(dtrx: Path, profiles: Iterable[str], label: str) -> list[str]:
    """One line per error the front half reports for *dtrx* under each of *profiles*.

    A profile whose source or config raises instead of reporting diagnostics is
    one line naming the exception.
    """
    errors: list[str] = []
    for profile in profiles:
        try:
            result = analysis_of(dtrx, profile=profile)
        except _ANALYSIS_ERRORS as exc:
            errors.append(f"{label} [{profile}]: {type(exc).__name__}: {exc}")
            continue
        errors.extend(
            f"{label} [{profile}]: {diagnostic.code}: {diagnostic.location}: {diagnostic.message}"
            if diagnostic.location
            else f"{label} [{profile}]: {diagnostic.code}: {diagnostic.message}"
            for diagnostic in result.errors
        )
    return errors


def discover_configs() -> list[Path]:
    """Every ``.dcfg`` under the examples tree."""
    return sorted(EXAMPLES_ROOT.rglob("*.dcfg"))


def discover_projects() -> list[Path]:
    """Every example project root (a directory holding ``system.dtrx``)."""
    return sorted(marker.parent for marker in EXAMPLES_ROOT.rglob(_PROJECT_MARKER))


def _self_test_load() -> list[str]:
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

        documents = disk_config_documents()
        planted_errors = load_errors(planted, root, documents)
        if not any(f"Unknown key '{_PLANTED_UNKNOWN_KEY}'" in line for line in planted_errors):
            problems.append(
                "the planted unknown key was not reported as an unknown key; got "
                f"{planted_errors!r}"
            )
        if any("5000" in line for line in planted_errors):
            problems.append("the load error echoed the offending value")
        clean_errors = load_errors(clean, root, documents)
        if clean_errors:
            problems.append(f"the clean twin of the planted document failed to load: {clean_errors!r}")
    return problems


def _planted_project_errors(sizing: str) -> tuple[list[str], list[str]]:
    """The leaf profiles and analysis errors of the planted pooled project with *sizing*."""
    with tempfile.TemporaryDirectory(prefix="example-config-analyze-") as raw_dir:
        root = Path(raw_dir)
        files = {
            name: content.replace(_SIZING_SLOT, sizing) for name, content in _PLANTED_POOLED_PROJECT.items()
        }
        write_files(root, files)
        declaration = disk_config_documents().config_document((root / "config" / "system.dcfg").resolve())
        profiles = leaf_profiles(declaration)
        return profiles, analysis_errors(root / _PROJECT_MARKER, profiles, "planted")


def _self_test_analysis() -> list[str]:
    """Prove a pooled block that sizes itself is reported under the leaf profile only,
    and its clean twin analyzes clean."""
    problems: list[str] = []
    planted_profiles, planted_errors = _planted_project_errors('      sku = "Standard";\n')
    if planted_profiles != ["test"]:
        problems.append(
            f"the planted project's leaf profiles are {planted_profiles!r}; expected ['test'] "
            "(the intermediate 'cloud' profile is extended, so it is not a leaf)"
        )
    if not any(f": {_PLANTED_SIZING_CODE}:" in line for line in planted_errors):
        problems.append(
            f"the planted self-sizing pooled block was not reported as {_PLANTED_SIZING_CODE}; "
            f"got {planted_errors!r}"
        )
    _, clean_errors = _planted_project_errors("")
    if clean_errors:
        problems.append(f"the clean twin of the planted pooled project failed analysis: {clean_errors!r}")
    return problems


def run_self_test() -> list[str]:
    """Prove both checks report a planted defect and pass its clean twin."""
    return [*_self_test_load(), *_self_test_analysis()]


def _system_declarations(
    configs: Iterable[Path], documents: ConfigDocumentSourceProtocol
) -> dict[Path, list[ConfigDecl]]:
    """The system config declarations under each project root."""
    by_root: dict[Path, list[ConfigDecl]] = {}
    for config_path in configs:
        declaration = documents.config_document(config_path.resolve())
        if declaration.kind == _SYSTEM_KIND:
            by_root.setdefault(project_root_of(config_path), []).append(declaration)
    return by_root


def example_analysis_errors(
    projects: Iterable[Path], declarations: dict[Path, list[ConfigDecl]]
) -> tuple[list[str], int]:
    """The analysis errors of every project under every leaf profile of its one
    system config, and the number of (project, profile) analyses run."""
    errors: list[str] = []
    analyzed = 0
    for root in projects:
        label = root.relative_to(EXAMPLES_ROOT).as_posix()
        found = declarations.get(root, [])
        if len(found) != 1:
            errors.append(
                f"{label}: holds {len(found)} system config declaration(s) below it; exactly one "
                f"names the profiles the example is analyzed under. Fix: keep one `config system`."
            )
            continue
        profiles = leaf_profiles(found[0])
        analyzed += len(profiles)
        errors.extend(analysis_errors(root / _PROJECT_MARKER, profiles, label))
    return errors, analyzed


def check_example_configs() -> int:
    """Run the gate against the real examples tree."""
    configs = discover_configs()
    projects = discover_projects()
    if not configs or not projects:
        logger.error(
            "EXAMPLE-CONFIG-LOAD GATE CANNOT RUN: %d .dcfg and %d %s found under %s -- an empty "
            "corpus would make this check vacuously pass.",
            len(configs),
            len(projects),
            _PROJECT_MARKER,
            EXAMPLES_ROOT,
        )
        return EXIT_USAGE
    documents = disk_config_documents()
    load_failures: list[str] = []
    unloadable_roots: set[Path] = set()
    for config_path in configs:
        root = project_root_of(config_path)
        errors = load_errors(config_path, root, documents)
        if errors:
            unloadable_roots.add(root)
        load_failures.extend(errors)
    analyzable = [root for root in projects if root not in unloadable_roots]
    analysis_failures, analyzed = example_analysis_errors(
        analyzable, _system_declarations(configs, documents)
    )
    for failure in [*load_failures, *analysis_failures]:
        logger.error("  %s", failure)
    if load_failures or analysis_failures:
        logger.error(
            "EXAMPLE-CONFIG-LOAD GATE FAILED: %d profile load(s) failed across %d config file(s); "
            "%d analysis error(s) across %d leaf profile(s) of %d example(s) (%d example(s) not "
            "analyzed because a config failed to load).",
            len(load_failures),
            len(configs),
            len(analysis_failures),
            analyzed,
            len(analyzable),
            len(projects) - len(analyzable),
        )
        return EXIT_FAIL
    logger.info(
        "EXAMPLE-CONFIG-LOAD GATE PASSED: %d config file(s), every declared profile loads; "
        "%d example(s) analyze clean under %d leaf profile(s).",
        len(configs),
        len(projects),
        analyzed,
    )
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/repo-hygiene/example-config-load-gate.ps1``: one per wrapper parameter,
    spelled exactly."""
    return self_test_gate_parser(
        WRAPPER,
        "Example config load gate: every declared profile of every example .dcfg "
        "loads through the real loaders, and every example analyzes under every leaf "
        "profile of its system config.",
    )


def _run(args: argparse.Namespace) -> int:
    """Run the gate.

    Returns:
        0 = every profile loads and every example analyzes clean (or a successful
        ``--self-test``), 1 = at least one profile failed to load or one leaf profile
        failed analysis, a failed wrapper seam check, or package installs that are not
        current, 2 = self-test failure, empty corpus, or an unparsable file.
    """
    if not packages_current():
        return EXIT_FAIL
    if not args.debug:
        # The config loader, the builtins loader and analysis narrate every step
        # at INFO; only this gate's verdict lines are the report.
        for package in _QUIET_PACKAGES:
            logging.getLogger(package).setLevel(logging.WARNING)
    register_installed_parsers()

    problems = run_self_test()
    if problems:
        logger.error("NON-VACUITY SELF-TEST FAILED -- aborting before any real check:")
        for problem in problems:
            logger.error("  %s", problem)
        return EXIT_USAGE
    logger.info("non-vacuity self-test: PASS")

    if args.self_test:
        return wrappers.run_self_test(
            [], wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=wrappers.REPO_HYGIENE_GATES_DIR
        )

    try:
        return check_example_configs()
    except (DcfgSyntaxError, OSError, ConfigValidationError) as exc:
        logger.error("ERROR: %s", exc)
        return EXIT_USAGE


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
