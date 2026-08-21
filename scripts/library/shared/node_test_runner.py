"""Run a Datrix package's Node test suite and produce the standard artifacts.

Datrix is a multi-language toolchain, and its repo tooling has to be one too.
A package whose suite runs under Node (``datrix-vscode``, the VS Code client)
must land in ``.test_results/test-results-<stamp>/`` looking exactly like a
pytest package's run: a ``full.log``, a JUnit ``.xml``, and the structured
``index.json`` that ``status-tests.ps1``, ``test.ps1 -Rerun``, ``compare-tests``
and the affected-set gate all read. Everything downstream then works on a Node
package without knowing one exists.

Two facts about Node's ``--test-reporter=junit`` output shape this module:

* Test cases are emitted **directly under** ``<testsuites>`` with no
  ``<testsuite>`` wrapper, and every ``classname`` is the literal string
  ``test``. The shared :class:`~shared.structured_log_writer.StructuredLogWriter`
  reads ``<testsuite>`` elements and treats ``classname`` as the owning file, so
  raw Node output would parse to zero results. This module therefore runs one
  invocation per test file — which is also what ``--specific`` selection needs —
  and rewrites the merged XML with the real owning file on each case.
* Counts are emitted as XML *comments*, which every conforming parser discards.
  They are never read here; the ``<testcase>`` elements are the only source.

The file a case is attributed to is the **source** file, recovered from the
compiled file's source map, and stack frames are resolved the same way via
``--enable-source-maps``. Attribution and failure location therefore name the
same file, and its line numbers are the ones an author can act on.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from shared.logging_utils import ColorCodes, LogConfig, TeeLogger, colorize
from shared.package_suites import (
    NODE_DATRIX_BLOCK_KEY,
    NODE_MANIFEST_NAME,
    read_json_object,
)
from shared.structured_log_writer import (
    PHASE_STATUS_FAILED,
    PHASE_STATUS_PASSED,
    StructuredLogWriter,
)

logger = logging.getLogger(__name__)

#: Key naming the glob that selects a package's compiled test files, relative to
#: the package root, e.g. ``"out/test/*.test.js"``.
TEST_FILES_KEY = "testFiles"

#: Key naming the npm script that must run before the suite (the compile step).
#: Optional: a package that needs no build simply omits it.
BUILD_SCRIPT_KEY = "build"

#: Suite name written into the merged JUnit XML. Deliberately constant and
#: neutral: StructuredLogWriter infers a run phase from the suite name, so a
#: per-file name like ``src/test/serialization.test.ts`` would be misread as the
#: "serial" phase.
_MERGED_SUITE_NAME = "node"

_MERGED_XML_NAME = "junit-node.xml"


class NodeSuiteError(RuntimeError):
    """A Node suite cannot be run as declared."""


@dataclass(frozen=True)
class NodeSuiteDeclaration:
    """What a Node package's ``datrix`` manifest block declares."""

    test_files_glob: str
    build_script: str | None


def read_suite_declaration(package_root: Path) -> NodeSuiteDeclaration:
    """Read the ``datrix`` declaration block from a package's ``package.json``.

    Args:
        package_root: Root directory of the Node package.

    Returns:
        The parsed declaration.

    Raises:
        NodeSuiteError: If the manifest is unreadable, the block is missing or
            malformed, or it names a build script the manifest does not declare.
            Failing loud is required: a Node package that declares a ``test``
            script is already reported as testable, so a silently-skipped suite
            would show up as a passing run of zero tests.
    """
    manifest_path = package_root / NODE_MANIFEST_NAME
    manifest = read_json_object(manifest_path)
    if manifest is None:
        raise NodeSuiteError(
            f"Could not read a JSON object from {manifest_path}. Expected the "
            f"Node manifest of package '{package_root.name}'. Fix the file so "
            f"it parses as JSON."
        )

    block = manifest.get(NODE_DATRIX_BLOCK_KEY)
    if not isinstance(block, dict):
        raise NodeSuiteError(
            f"{manifest_path} declares a 'scripts.test' entry but no "
            f"'{NODE_DATRIX_BLOCK_KEY}' block, so the repo test runner cannot "
            f"tell which files hold its tests. Expected an object such as "
            f'{{"{NODE_DATRIX_BLOCK_KEY}": {{"{TEST_FILES_KEY}": '
            f'"out/test/*.test.js", "{BUILD_SCRIPT_KEY}": "compile"}}}}. '
            f"Add that block to {manifest_path}."
        )

    test_files_glob = block.get(TEST_FILES_KEY)
    if not isinstance(test_files_glob, str) or not test_files_glob:
        raise NodeSuiteError(
            f"{manifest_path} has a '{NODE_DATRIX_BLOCK_KEY}' block with no "
            f"usable '{TEST_FILES_KEY}' entry (got {test_files_glob!r}). "
            f"Expected a non-empty glob relative to the package root, e.g. "
            f'"out/test/*.test.js".'
        )

    build_script = block.get(BUILD_SCRIPT_KEY)
    if build_script is not None and (not isinstance(build_script, str) or not build_script):
        raise NodeSuiteError(
            f"{manifest_path} has a '{NODE_DATRIX_BLOCK_KEY}.{BUILD_SCRIPT_KEY}' "
            f"entry that is not a non-empty string (got {build_script!r}). "
            f"Expected the name of an npm script to run before the suite, e.g. "
            f'"compile", or omit the key entirely.'
        )

    if build_script is not None:
        scripts = manifest.get("scripts")
        declared_scripts = scripts if isinstance(scripts, dict) else {}
        if build_script not in declared_scripts:
            raise NodeSuiteError(
                f"{manifest_path} names '{build_script}' as the "
                f"'{NODE_DATRIX_BLOCK_KEY}.{BUILD_SCRIPT_KEY}' script, but "
                f"'scripts' declares no such entry. Declared scripts: "
                f"{sorted(declared_scripts)}. Fix the name or add the script."
            )

    return NodeSuiteDeclaration(
        test_files_glob=test_files_glob,
        build_script=build_script,
    )


def _require_executable(name: str) -> str:
    """Resolve an executable on PATH, or raise naming what is missing.

    Args:
        name: Executable to look up (e.g. ``"node"``).

    Returns:
        Absolute path to the resolved executable.

    Raises:
        NodeSuiteError: If PATH holds no such executable.
    """
    resolved = shutil.which(name)
    if resolved is None:
        raise NodeSuiteError(
            f"'{name}' was not found on PATH, and a Node package's test suite "
            f"cannot run without it. Expected a Node.js installation whose "
            f"binary directory is on PATH. Fix: install Node.js (>= 22, for "
            f"the built-in test runner's junit reporter) and re-open the shell."
        )
    return resolved


def discover_test_files(package_root: Path, declaration: NodeSuiteDeclaration) -> list[Path]:
    """Resolve the declared test-file glob against the package tree.

    Args:
        package_root: Root directory of the Node package.
        declaration: The package's parsed ``datrix`` declaration.

    Returns:
        Sorted list of existing test files, as absolute paths.
    """
    matches = sorted(
        path for path in package_root.glob(declaration.test_files_glob) if path.is_file()
    )
    return matches


def select_test_files(candidates: list[Path], specific: str | None) -> list[Path]:
    """Narrow the discovered test files to a ``--specific`` selection.

    A selection entry matches a candidate when it equals the candidate's path,
    its name, or its name with the extension chain removed. That last form is
    what makes a source-side name work: a caller naturally names
    ``serverResolution.test.ts`` while the runner executes the compiled
    ``serverResolution.test.js``.

    Args:
        candidates: All discovered test files.
        specific: Comma-separated selection, or ``None`` for "all".

    Returns:
        The selected subset, in discovery order.

    Raises:
        NodeSuiteError: If any selection entry matches no candidate. An entry
            that silently matched nothing would shrink the run without saying
            so, and a run of the remaining files would report a pass that never
            covered what the caller asked for.
    """
    if specific is None:
        return candidates

    entries = [entry.strip() for entry in specific.split(",")]
    entries = [entry for entry in entries if entry]
    if not entries:
        return candidates

    selected: list[Path] = []
    unmatched: list[str] = []
    for entry in entries:
        normalized = entry.replace("\\", "/")
        stem = normalized.rsplit("/", 1)[-1].split(".", 1)[0]
        matches = [
            candidate
            for candidate in candidates
            if str(candidate).replace("\\", "/").endswith(normalized)
            or candidate.name == normalized
            or candidate.name.split(".", 1)[0] == stem
        ]
        if not matches:
            unmatched.append(entry)
            continue
        for match in matches:
            if match not in selected:
                selected.append(match)

    if unmatched:
        available = sorted(candidate.name for candidate in candidates)
        raise NodeSuiteError(
            f"No test file matches {unmatched}. Expected each --specific entry "
            f"to name one of the package's test files. Available: {available}. "
            f"Fix: use one of those names (the source-side '.ts' name is "
            f"accepted for a compiled '.js' file)."
        )

    return [candidate for candidate in candidates if candidate in selected]


def resolve_source_file(compiled_file: Path, package_root: Path) -> str:
    """Map a compiled test file back to the source file that produced it.

    Reads the sibling ``.map`` emitted alongside the compiled file. Falls back
    to the compiled file itself when no usable map exists — reporting the file
    that actually ran is always truthful, where guessing a source path from a
    directory-name convention would not be.

    Args:
        compiled_file: The test file the runner executes.
        package_root: Package root, used to produce a relative path.

    Returns:
        Forward-slash path relative to *package_root*.
    """
    map_path = compiled_file.with_name(compiled_file.name + ".map")
    if map_path.is_file():
        try:
            source_map = json.loads(map_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("source_map_unreadable path=%s error=%s", map_path, exc)
        else:
            sources = source_map.get("sources")
            if isinstance(sources, list) and sources and isinstance(sources[0], str):
                source_root = source_map.get("sourceRoot")
                relative = sources[0]
                if isinstance(source_root, str) and source_root:
                    relative = f"{source_root.rstrip('/')}/{relative}"
                resolved = (map_path.parent / relative).resolve()
                return _relative_to_package(resolved, package_root)

    return _relative_to_package(compiled_file.resolve(), package_root)


def _relative_to_package(path: Path, package_root: Path) -> str:
    """Render *path* relative to *package_root* with forward slashes."""
    try:
        relative = path.relative_to(package_root.resolve())
    except ValueError:
        return str(path).replace("\\", "/")
    return str(relative).replace("\\", "/")


def _run_build(
    package_root: Path, script_name: str, tee: TeeLogger
) -> int:
    """Run the package's declared build script via npm.

    Args:
        package_root: Package root, used as the working directory.
        script_name: npm script to run.
        tee: Logger receiving the build output.

    Returns:
        The build's exit code.
    """
    npm = _require_executable("npm")
    tee.write(f"Building {package_root.name} (npm run {script_name})...")
    completed = subprocess.run(  # noqa: S603 -- resolved executable, fixed argv
        [npm, "run", script_name],
        cwd=package_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.stdout:
        tee.write(completed.stdout.rstrip("\n"))
    if completed.stderr:
        tee.write(completed.stderr.rstrip("\n"))
    return completed.returncode


def _run_one_file(
    node_exe: str,
    package_root: Path,
    test_file: Path,
    xml_path: Path,
    tee: TeeLogger,
    name_pattern: str | None,
) -> int:
    """Run one test file under Node's built-in runner with the junit reporter.

    Args:
        node_exe: Resolved ``node`` executable.
        package_root: Working directory for the run.
        test_file: The compiled test file to execute.
        xml_path: Destination for this file's JUnit XML.
        tee: Logger receiving the run's console output.
        name_pattern: Regular expression narrowing the run to matching test
            names, or ``None`` to run every test in the file.

    Returns:
        Node's exit code for this file.
    """
    argv = [
        node_exe,
        "--enable-source-maps",
        "--test",
        "--test-reporter=junit",
        f"--test-reporter-destination={xml_path}",
    ]
    if name_pattern is not None:
        argv.append(f"--test-name-pattern={name_pattern}")
    argv.append(str(test_file))

    completed = subprocess.run(  # noqa: S603 -- resolved executable, fixed argv
        argv,
        cwd=package_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.stdout:
        tee.write(completed.stdout.rstrip("\n"))
    if completed.stderr:
        tee.write(completed.stderr.rstrip("\n"))
    return completed.returncode


def merge_junit_xml(
    per_file_xml: list[tuple[str, Path]], destination: Path, duration_seconds: float
) -> dict[str, int]:
    """Merge per-file Node JUnit XML into one file the shared writer can read.

    Node emits ``<testcase>`` elements directly under ``<testsuites>`` and sets
    every ``classname`` to ``test``. This rebuilds the document with a single
    ``<testsuite>`` wrapper carrying the run's wall time, and re-stamps each case
    with the source file it came from.

    Args:
        per_file_xml: ``(source_file, xml_path)`` pairs in execution order.
        destination: Path to write the merged document to.
        duration_seconds: Wall-clock seconds the whole suite took.

    Returns:
        Outcome counts with keys ``passed``, ``failed``, ``error``, ``skipped``.
    """
    suite = ET.Element(
        "testsuite",
        {"name": _MERGED_SUITE_NAME, "time": f"{duration_seconds:.6f}"},
    )
    counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}

    for source_file, xml_path in per_file_xml:
        if not xml_path.is_file() or xml_path.stat().st_size == 0:
            logger.warning(
                "node_junit_xml_missing source=%s path=%s", source_file, xml_path
            )
            continue
        try:
            tree = ET.parse(xml_path)  # noqa: S314 -- runner-produced, local file
        except ET.ParseError as exc:
            logger.warning(
                "node_junit_xml_corrupt source=%s path=%s error=%s",
                source_file,
                xml_path,
                exc,
            )
            continue

        for testcase in tree.getroot().iter("testcase"):
            testcase.set("classname", source_file)
            # JUnit's optional `file` attribute: the owning file stated outright
            # rather than left to be inferred from the classname's shape.
            testcase.set("file", source_file)
            # Node duplicates the failure text into a `failure` attribute on the
            # element itself. It carries no information the child <failure>
            # lacks, and it makes the merged XML far larger than it needs to be.
            testcase.attrib.pop("failure", None)
            suite.append(testcase)
            counts[_outcome_of(testcase)] += 1

    suite.set("tests", str(sum(counts.values())))
    suite.set("failures", str(counts["failed"]))
    suite.set("errors", str(counts["error"]))
    suite.set("skipped", str(counts["skipped"]))

    root = ET.Element("testsuites")
    root.append(suite)
    ET.ElementTree(root).write(destination, encoding="utf-8", xml_declaration=True)
    return counts


def _outcome_of(testcase: ET.Element) -> str:
    """Classify a ``<testcase>`` element into a counts key."""
    if testcase.find("failure") is not None:
        return "failed"
    if testcase.find("error") is not None:
        return "error"
    if testcase.find("skipped") is not None:
        return "skipped"
    return "passed"


def _format_summary(counts: dict[str, int], duration_seconds: float) -> str:
    """Render the one pytest-shaped summary line ``test.ps1`` parses.

    ``test.ps1``'s Parse-TestCounts scans the runner's output backwards for
    lines carrying both outcome counts and an ``in <n>.<n>s`` timing, treating
    the last two it finds as two phases and summing them. Exactly one such line
    must therefore be emitted per run.

    Args:
        counts: Outcome counts.
        duration_seconds: Wall-clock seconds the suite took.

    Returns:
        A line such as ``33 passed, 1 skipped in 6.51s``.
    """
    parts = [
        f"{counts[key]} {label}"
        for key, label in (
            ("failed", "failed"),
            ("error", "error"),
            ("passed", "passed"),
            ("skipped", "skipped"),
        )
        if counts[key] > 0
    ]
    if not parts:
        parts = ["0 passed"]
    return f"{', '.join(parts)} in {duration_seconds:.2f}s"


def run_node_suite(
    package_root: Path,
    project_name: str,
    *,
    verbose: bool = False,
    save_log: bool = True,
    specific: str | None = None,
    name_pattern: str | None = None,
) -> int:
    """Run a package's Node test suite and write the standard run artifacts.

    Args:
        package_root: Root directory of the Node package.
        project_name: Package name, as it appears in reports.
        verbose: Stream the suite's output instead of only the summary.
        save_log: Write ``.test_results/`` artifacts. When false the suite still
            runs and its exit code is still authoritative.
        specific: Comma-separated test-file selection, or ``None`` for all.
        name_pattern: Regular expression narrowing the run to matching test
            names. This is Node's ``--test-name-pattern``: a regex, where
            pytest's ``-k`` takes a boolean name expression. A caller passing a
            pytest expression gets a loud result either way -- an invalid regex
            fails the run, and a valid one that matches nothing selects zero
            tests, which is reported as a non-pass rather than a green run.

    Returns:
        Process exit code: 0 when every selected test passed, 1 on any failure,
        error, build failure, or declaration problem, and 5 when the selection
        matched no test file at all.
    """
    try:
        declaration = read_suite_declaration(package_root)
        node_exe = _require_executable("node")
        candidates = discover_test_files(package_root, declaration)
    except NodeSuiteError as exc:
        print(f"ERROR: {exc}")
        return 1

    log_config = LogConfig(
        log_dir=".test_results",
        prefix="test-results",
        project_name=project_name,
        save_to_file=save_log,
        quiet_mode=not verbose,
    )

    with TeeLogger(log_config, package_root) as tee:
        run_dir = tee.get_run_dir()
        start = time.monotonic()

        if declaration.build_script is not None:
            build_rc = _run_build(package_root, declaration.build_script, tee)
            if build_rc != 0:
                tee.write_error(
                    f"Build step 'npm run {declaration.build_script}' failed with "
                    f"exit code {build_rc} for {project_name}. The suite was not "
                    f"run, because testing a stale build proves nothing about the "
                    f"current sources."
                )
                return 1
            # The build may have created or removed compiled test files, so the
            # selection is resolved against the tree the suite will actually run.
            candidates = discover_test_files(package_root, declaration)

        try:
            selected = select_test_files(candidates, specific)
        except NodeSuiteError as exc:
            tee.write_error(f"ERROR: {exc}")
            return 1

        if not selected:
            tee.write_error(
                f"No test files were selected for {project_name} (glob: "
                f"{declaration.test_files_glob}"
                + (f", selection: {specific}" if specific else "")
                + "). Expected at least one test file to run; zero ran, so this "
                "result proves nothing and is NOT a pass. Fix: check the glob "
                "resolves against the built tree, and that the build step ran."
            )
            return 5

        # With --no-save there is no run directory, and the JUnit XML is a
        # transient means to counting outcomes rather than an artifact. It goes
        # to a scratch directory that is removed on the way out, so a
        # non-saving run leaves nothing behind inside the package.
        with ExitStack() as stack:
            if run_dir is not None:
                xml_dir = run_dir
            else:
                xml_dir = Path(stack.enter_context(TemporaryDirectory(prefix="datrix-node-junit-")))

            per_file_xml: list[tuple[str, Path]] = []
            worst_rc = 0

            for index, test_file in enumerate(selected, start=1):
                source_file = resolve_source_file(test_file, package_root)
                tee.write(f"[{index}/{len(selected)}] {source_file}")
                file_xml = xml_dir / f"junit-node-{index:03d}.xml"
                rc = _run_one_file(
                    node_exe, package_root, test_file, file_xml, tee, name_pattern
                )
                if rc != 0 and worst_rc == 0:
                    worst_rc = rc
                per_file_xml.append((source_file, file_xml))

            duration = time.monotonic() - start
            merged_xml = xml_dir / _MERGED_XML_NAME
            counts = merge_junit_xml(per_file_xml, merged_xml, duration)

            total_cases = sum(counts.values())
            if total_cases == 0:
                tee.write_error(
                    f"{project_name}: {len(selected)} test file(s) ran but produced "
                    f"zero test cases"
                    + (f" for name pattern {name_pattern!r}" if name_pattern else "")
                    + ". Expected at least one; a run that executes no test case "
                    "is NOT a pass. Fix: "
                    + (
                        "widen or correct the name pattern"
                        if name_pattern
                        else f"check the compiled files under "
                        f"{declaration.test_files_glob} actually register tests"
                    )
                    + "."
                )
                return 5

            failed = counts["failed"] + counts["error"] > 0
            returncode = 1 if (failed or worst_rc != 0) else 0

            if run_dir is not None and save_log:
                phase_status = (
                    PHASE_STATUS_FAILED if returncode != 0 else PHASE_STATUS_PASSED
                )
                writer = StructuredLogWriter(project_name=project_name, run_dir=run_dir)
                writer.write(
                    xml_paths=[merged_xml],
                    timestamp=datetime.now(),
                    phase_results={
                        "Tests": {"status": phase_status, "items": total_cases}
                    },
                )

        summary = _format_summary(counts, duration)
        tee.write("")
        tee.write(summary)

        if tee.quiet_mode:
            status = "PASSED" if returncode == 0 else "FAILED"
            color = ColorCodes.GREEN if returncode == 0 else ColorCodes.RED
            tee.write_console("")
            tee.write_console(colorize(f"[{status}] {project_name}", color))
            tee.write_console(f"  {summary}")
            if run_dir is not None and save_log:
                tee.write_console(f"  Details: {run_dir / 'index.json'}")
            elif tee.get_log_path():
                tee.write_console(f"  Log: {tee.get_log_path()}")

        return returncode
