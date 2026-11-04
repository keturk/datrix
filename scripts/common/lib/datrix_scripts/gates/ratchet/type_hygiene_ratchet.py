#!/usr/bin/env python3
"""Per-package type-hygiene ratchet: the escape hatches a type checker cannot see past may only fall.

For every ``datrix-*`` directory with a ``src/`` tree (discovered on disk), one pass over each ``.py``
file under ``src/`` counts:

  - ``type_ignores``: comment tokens matching ``type:\\s*ignore``, with or without a code list.
  - ``any_signatures``: function definitions whose parameter or return annotation mentions ``Any``
    (an ``ast.Name`` ``Any`` or an ``ast.Attribute`` ending in ``.Any``, anywhere in the annotation).
    A string annotation is parsed first; ``Literal`` arguments and ``Annotated`` metadata are data,
    not types. A function counts once however many mentions it holds.
  - ``casts``: calls whose callee is ``cast`` or ends in ``.cast``.

Each count is compared tighten-only with ``scripts/config/type-hygiene-ratchet.json``,
``{package: {type_ignores, any_signatures, casts}}``; a package the baseline does not name has a
baseline of 0 for each count. The type checker itself is never run: this gate only reads source.

Exit codes:
    0: Every count is at or below its baseline (or a successful --update-baseline, or --warn).
    1: A count exceeds its baseline, or --self-test reports a failing check.
    2: Usage error: a missing or malformed baseline, a file that cannot be read or parsed, a rise
       under --update-baseline, or a failed self-test step on a normal run.

Run through ``gates/ratchet/type-hygiene-ratchet.ps1`` (or its ``.sh`` twin) in gate mode
(``datrix_scripts.gate_log.run_as_gate``): the last line is
``[GATE] type-hygiene-ratchet PASSED|FAILED exit=<n> log=<path>``.

Usage:
    type-hygiene-ratchet.ps1
    type-hygiene-ratchet.ps1 -Warn
    type-hygiene-ratchet.ps1 -ShowFiles
    type-hygiene-ratchet.ps1 -UpdateBaseline
    type-hygiene-ratchet.ps1 -SelfTest
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
import re
import sys
import tempfile
import tokenize
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.count_ratchet import RatchetMode, compare, read_counts
from datrix_scripts.framework_repos import PackageMarker, workspace_package_dirs
from datrix_scripts.function_sources import terminal_name
from datrix_scripts.gate_harness import (
    EXIT_PASS,
    EXIT_USAGE,
    EXIT_VIOLATION,
    WRAPPER_DEBUG_FLAG,
    NamedCheck,
    UsageError,
    expect_usage_error,
    harness_self_test,
    named_checks,
    print_command,
    report_step,
    run_checks,
    write_files,
)
from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.paths import CONFIG_DIR, WORKSPACE_DIR
from datrix_scripts.test import wrappers

GATE: Final = "type-hygiene-ratchet"
MODULE: Final = "datrix_scripts.gates.ratchet.type_hygiene_ratchet"
WRAPPER: Final = "type-hygiene-ratchet"

BASELINE_RELATIVE: Final = CONFIG_DIR.relative_to(WORKSPACE_DIR) / "type-hygiene-ratchet.json"

TYPE_IGNORES: Final = "type_ignores"
ANY_SIGNATURES: Final = "any_signatures"
CASTS: Final = "casts"
COUNT_NAMES: Final = (TYPE_IGNORES, ANY_SIGNATURES, CASTS)

_FIXES: Final[Mapping[str, str]] = {
    TYPE_IGNORES: "type the expression so the ignore comment can go",
    ANY_SIGNATURES: "annotate the function with the concrete type",
    CASTS: "narrow the value with a check or a precise type instead of the cast",
}

TYPE_IGNORE_PATTERN: Final = re.compile(r"type:\s*ignore")
ANY_NAME: Final = "Any"
CAST_NAME: Final = "cast"
LITERAL_NAME: Final = "Literal"
ANNOTATED_NAME: Final = "Annotated"
PYTHON_GLOB: Final = "*.py"
KEY_SEPARATOR: Final = ":"

PackageCounts = dict[str, dict[str, int]]


def _forward_reference(node: ast.Constant) -> ast.expr:
    """The type expression a string annotation holds.

    Raises:
        ValueError: the string is not a type expression, so what it mentions cannot be known.
    """
    try:
        return ast.parse(str(node.value), mode="eval").body
    except SyntaxError as exc:
        raise ValueError(
            f"line {node.lineno}: annotation string {node.value!r} is not a type expression ({exc.msg})"
        ) from exc


def _subscript_type_parts(node: ast.Subscript) -> list[ast.expr]:
    """The parts of a subscript that name types: never ``Literal`` arguments or ``Annotated`` metadata."""
    name = terminal_name(node.value)
    if name == LITERAL_NAME:
        return [node.value]
    if name == ANNOTATED_NAME and isinstance(node.slice, ast.Tuple):
        return [node.value, node.slice.elts[0]]
    return [node.value, node.slice]


def mentions_any(annotation: ast.expr) -> bool:
    """Whether *annotation* mentions ``Any`` at any depth, string annotations parsed first.

    Raises:
        ValueError: from ``_forward_reference``.
    """
    if terminal_name(annotation) == ANY_NAME:
        return True
    if isinstance(annotation, ast.Constant):
        return isinstance(annotation.value, str) and mentions_any(_forward_reference(annotation))
    if isinstance(annotation, ast.Subscript):
        return any(mentions_any(part) for part in _subscript_type_parts(annotation))
    return any(mentions_any(child) for child in ast.iter_child_nodes(annotation) if isinstance(child, ast.expr))


def _signature_annotations(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.expr]:
    """Every parameter annotation of *function*, of every parameter kind, and its return annotation."""
    arguments = function.args
    parameters = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
    parameters.extend(parameter for parameter in (arguments.vararg, arguments.kwarg) if parameter is not None)
    annotations = [parameter.annotation for parameter in parameters if parameter.annotation is not None]
    if function.returns is not None:
        annotations.append(function.returns)
    return annotations


def count_source(source: bytes) -> dict[str, int]:
    """The three counts of one module's *source*, each read in the same pass over the file.

    Raises:
        SyntaxError: the source does not parse.
        ValueError: the source cannot be decoded, or a string annotation is not a type expression.
        tokenize.TokenError: the source does not tokenize.
    """
    tree = ast.parse(source)
    tokens = tokenize.tokenize(io.BytesIO(source).readline)
    counts = dict.fromkeys(COUNT_NAMES, 0)
    counts[TYPE_IGNORES] = sum(
        1 for token in tokens if token.type == tokenize.COMMENT and TYPE_IGNORE_PATTERN.search(token.string)
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and terminal_name(node.func) == CAST_NAME:
            counts[CASTS] += 1
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            counts[ANY_SIGNATURES] += any(mentions_any(item) for item in _signature_annotations(node))
    return counts


def count_file(path: Path) -> dict[str, int]:
    """The three counts of the module at *path*.

    Raises:
        UsageError: the file cannot be read, decoded, tokenized or parsed. It would otherwise escape
            the census.
    """
    try:
        return count_source(path.read_bytes())
    except (OSError, SyntaxError, ValueError, tokenize.TokenError) as exc:
        raise UsageError(
            f"cannot census {path}: {exc}. A source file the census cannot read would escape every "
            "count. Fix: correct the file's syntax, encoding or annotation."
        ) from exc


def take_census(base_dir: Path, *, show_files: bool) -> PackageCounts:
    """The three counts of every discovered package's ``src/`` tree, by package directory name.

    Raises:
        UsageError: no package was found, or a file cannot be counted (``count_file``).
    """
    package_dirs = workspace_package_dirs(base_dir, any_of=frozenset({PackageMarker.SRC}))
    if not package_dirs:
        raise UsageError(f"no datrix-* directory with a src/ tree under {base_dir}. Expected the workspace root.")
    census: PackageCounts = {}
    for package_dir in package_dirs:
        totals = dict.fromkeys(COUNT_NAMES, 0)
        for path in sorted((package_dir / PackageMarker.SRC.value).rglob(PYTHON_GLOB)):
            if show_files:
                print(f"Scanning: {path.relative_to(base_dir).as_posix()}")
            for name, value in count_file(path).items():
                totals[name] += value
        census[package_dir.name] = totals
    return census


def load_baseline(baseline_path: Path) -> PackageCounts:
    """Read ``{package: {type_ignores, any_signatures, casts}}`` from *baseline_path*.

    Raises:
        UsageError: the file is missing or malformed, or a package does not hold exactly the three
            counts. A missing baseline is not an empty one, which would pass nothing and prove nothing.
    """
    if not baseline_path.is_file():
        raise UsageError(
            f"type hygiene baseline {baseline_path} does not exist. A missing baseline is not an empty "
            "one. Fix: restore it, or freeze it from the live tree with -UpdateBaseline."
        )
    try:
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{baseline_path}: expected a JSON object of packages, got {type(data).__name__}")
        baseline = {
            package: read_counts(table, source=baseline_path, table_name=package)
            for package, table in data.items()
        }
    except (OSError, ValueError) as exc:
        raise UsageError(f"unusable type hygiene baseline: {exc}. Fix: restore the file.") from exc
    for package, counts in baseline.items():
        if set(counts) != set(COUNT_NAMES):
            raise UsageError(
                f"{baseline_path}: package {package!r} holds {sorted(counts)}; expected exactly "
                f"{sorted(COUNT_NAMES)}. Fix: restore the package's three counts."
            )
    return baseline


def write_baseline(baseline_path: Path, census: PackageCounts) -> None:
    """Write *census* to the baseline JSON, sorted by package name."""
    payload = {package: census[package] for package in sorted(census)}
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _flattened(table: PackageCounts) -> dict[str, int]:
    """*table* as the flat ``<package>:<count>`` map ``count_ratchet.compare`` reads."""
    return {
        f"{package}{KEY_SEPARATOR}{name}": value
        for package, counts in table.items()
        for name, value in counts.items()
    }


def ratchet_failures(census: PackageCounts, baseline: PackageCounts) -> list[str]:
    """One message per count above its baseline, naming the package, the count and both values."""
    messages: list[str] = []
    for delta in compare(_flattened(census), _flattened(baseline), RatchetMode.TIGHTEN_ONLY):
        package, _, name = delta.key.rpartition(KEY_SEPARATOR)
        messages.append(
            f"{package} {name} rose from baseline {delta.frozen} to {delta.current}. Fix: {_FIXES[name]}. "
            "A fall is banked with -UpdateBaseline; a rise is never accepted."
        )
    return messages


def _print_census(census: PackageCounts) -> None:
    """One line per package and the workspace totals."""
    for package, counts in census.items():
        print(f"{package}: " + " ".join(f"{name}={counts[name]}" for name in COUNT_NAMES))
    totals = {name: sum(counts[name] for counts in census.values()) for name in COUNT_NAMES}
    print("total: " + " ".join(f"{name}={totals[name]}" for name in COUNT_NAMES))


def _print_failures(failures: Sequence[str]) -> None:
    print()
    for message in failures:
        print(f"FAIL {message}")


def _update_baseline(census: PackageCounts, baseline_path: Path) -> int:
    """Freeze the first baseline, or tighten an existing one; a rise is refused and nothing is written.

    Raises:
        UsageError: the existing baseline is unusable (``load_baseline``); it is never overwritten.
    """
    froze = not baseline_path.exists()
    if not froze:
        rises = ratchet_failures(census, load_baseline(baseline_path))
        if rises:
            _print_failures(rises)
            print("\n-UpdateBaseline only writes when no count rises; the baseline is unchanged.")
            return EXIT_USAGE
    write_baseline(baseline_path, census)
    action = "Froze the first" if froze else "Tightened the"
    print(f"\n{action} type hygiene baseline: {len(census)} package(s) at {baseline_path}")
    return EXIT_PASS


def run_ratchet(base_dir: Path, *, update_baseline: bool, warn: bool, show_files: bool) -> int:
    """Count the packages under *base_dir* and compare them with its baseline (or write it).

    Raises:
        UsageError: from ``take_census`` or ``load_baseline``.
    """
    census = take_census(base_dir, show_files=show_files)
    _print_census(census)
    baseline_path = base_dir / BASELINE_RELATIVE
    if update_baseline:
        return _update_baseline(census, baseline_path)
    failures = ratchet_failures(census, load_baseline(baseline_path))
    if not failures:
        return EXIT_PASS
    _print_failures(failures)
    return EXIT_PASS if warn else EXIT_VIOLATION


# --------------------------------------------------------------------------- self-test
# Each check plants a workspace in a temporary directory and runs the real census on it: no real tree is read.

_ALPHA: Final = "datrix-alpha"
_BETA: Final = "datrix-beta"
_ALPHA_MODULE: Final = "datrix-alpha/src/alpha/hygiene.py"

_PLANTED: Final[Mapping[str, str]] = {
    _ALPHA_MODULE: (
        "import typing\n"
        "from typing import Any\n"
        "\n"
        "\n"
        'def f(x: "dict[str, Any]") -> None:\n'
        "    y = x.missing  # type: ignore[attr-defined]\n"
        "    typing.cast(int, y)\n"
    ),
    "datrix-alpha/tests/test_hygiene.py": "VALUE = 1  # type: ignore\n",
    "datrix-beta/src/beta/clean.py": 'NOTE = "# type: ignore"\n\n\ndef g(x: int) -> int:\n    return x\n',
    "datrix-no-src/README.md": "no source tree\n",
    "other/src/other.py": "VALUE = 1  # type: ignore\n",
}

_PLANTED_ONE_EACH: Final[Mapping[str, int]] = {TYPE_IGNORES: 1, ANY_SIGNATURES: 1, CASTS: 1}
_PLANTED_NONE: Final[Mapping[str, int]] = {TYPE_IGNORES: 0, ANY_SIGNATURES: 0, CASTS: 0}

_SIGNATURE_FORMS: Final = (
    "import typing\n"
    "\n"
    "\n"
    "def a(*args: typing.Any) -> None: ...\n"
    'async def b(*, key: list["Any"]) -> Any: ...\n'
    'def c(x: int, /, **rest: "typing.Any") -> int: ...\n'
    'def d(x: "Callable[[\'Any\'], None]") -> None: ...\n'
    "def e(x: int) -> str: ...\n"
)
_DATA_FORMS: Final = (
    'def a(x: Literal["Any"]) -> None: ...\n'
    'def b(x: typing.Literal["not a type!"]) -> None: ...\n'
    'def c(x: Annotated[int, "free text: Any"]) -> None: ...\n'
)
_ANNOTATED_TYPE_FORM: Final = 'def a(x: Annotated["Any", "free text"]) -> None: ...\n'
_CAST_FORMS: Final = "cast(int, 1)\ntyping.cast(int, 1)\nvalue.cast(int)\ncaster(1)\nvalue.casting()\n"
_IGNORE_FORMS: Final = (
    "a = 1  # type: ignore\n"
    "b = 2  #type:ignore[arg-type]\n"
    "c = 3  # type:   ignore[arg-type, attr-defined]\n"
    "d = 4  # noqa\n"
    'e = "# type: ignore"\n'
)


@contextlib.contextmanager
def _planted_workspace() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="type-hygiene-selftest-") as tmp:
        root = Path(tmp)
        write_files(root, _PLANTED)
        yield root


def _quiet_ratchet(root: Path, *, update_baseline: bool = False, warn: bool = False) -> tuple[int, str]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = run_ratchet(root, update_baseline=update_baseline, warn=warn, show_files=False)
    return code, output.getvalue()


def _check_planted_tree_gives_the_planted_counts() -> None:
    with _planted_workspace() as root:
        census = take_census(root, show_files=False)
    expected = {_ALPHA: dict(_PLANTED_ONE_EACH), _BETA: dict(_PLANTED_NONE)}
    assert census == expected, f"the planted tree must count {expected}, got {census}"


def _check_signature_forms_counted_once_each() -> None:
    counted = count_source(_SIGNATURE_FORMS.encode())[ANY_SIGNATURES]
    assert counted == 4, f"four functions mention Any, one of them twice; counted {counted}"


def _check_literal_and_annotated_metadata_are_data() -> None:
    counted = count_source(_DATA_FORMS.encode())[ANY_SIGNATURES]
    assert counted == 0, f"Literal arguments and Annotated metadata are not annotations; counted {counted}"
    typed = count_source(_ANNOTATED_TYPE_FORM.encode())[ANY_SIGNATURES]
    assert typed == 1, f"the type argument of Annotated is an annotation; counted {typed}"


def _check_casts_bare_and_qualified() -> None:
    counted = count_source(_CAST_FORMS.encode())[CASTS]
    assert counted == 3, f"a bare and two qualified casts were planted; counted {counted}"


def _check_ignore_comments_only() -> None:
    counted = count_source(_IGNORE_FORMS.encode())[TYPE_IGNORES]
    assert counted == 3, f"three ignore comments and one string were planted; counted {counted}"


def _check_rise_is_reported() -> None:
    with _planted_workspace() as root:
        frozen, _ = _quiet_ratchet(root, update_baseline=True)
        write_files(root, {"datrix-beta/src/beta/added.py": "VALUE = 1  # type: ignore\n"})
        code, output = _quiet_ratchet(root)
        warned, warned_output = _quiet_ratchet(root, warn=True)
    assert frozen == EXIT_PASS, f"the first freeze must exit {EXIT_PASS}, got {frozen}"
    assert code == EXIT_VIOLATION, f"a count above its baseline must exit {EXIT_VIOLATION}, got {code}"
    message = f"{_BETA} {TYPE_IGNORES} rose from baseline 0 to 1"
    assert message in output, f"the failure must name the package, the count and both values: {output}"
    assert warned == EXIT_PASS, f"-Warn must exit {EXIT_PASS}, got {warned}"
    assert message in warned_output, f"-Warn must still report the rise: {warned_output}"


def _check_equal_count_passes() -> None:
    with _planted_workspace() as root:
        _quiet_ratchet(root, update_baseline=True)
        code, output = _quiet_ratchet(root)
    assert code == EXIT_PASS, f"counts equal to the baseline must exit {EXIT_PASS}, got {code}: {output}"


def _check_update_baseline_refuses_a_rise() -> None:
    with _planted_workspace() as root:
        _quiet_ratchet(root, update_baseline=True)
        baseline_path = root / BASELINE_RELATIVE
        frozen = baseline_path.read_bytes()
        write_files(root, {"datrix-alpha/src/alpha/added.py": "VALUE = cast(int, 1)\n"})
        code, output = _quiet_ratchet(root, update_baseline=True)
        after = baseline_path.read_bytes()
    assert code == EXIT_USAGE, f"-UpdateBaseline over a rise must exit {EXIT_USAGE}, got {code}"
    assert f"{_ALPHA} {CASTS} rose from baseline 1 to 2" in output, f"the refusal must name it: {output}"
    assert after == frozen, "a refused -UpdateBaseline rewrote the baseline"


def _check_fall_is_banked() -> None:
    with _planted_workspace() as root:
        _quiet_ratchet(root, update_baseline=True)
        (root / _ALPHA_MODULE).unlink()
        passed, _ = _quiet_ratchet(root)
        code, _ = _quiet_ratchet(root, update_baseline=True)
        baseline = load_baseline(root / BASELINE_RELATIVE)
    assert passed == EXIT_PASS, f"a fall must pass the gate, got {passed}"
    assert code == EXIT_PASS, f"-UpdateBaseline over a fall must exit {EXIT_PASS}, got {code}"
    assert baseline[_ALPHA] == dict(_PLANTED_NONE), f"the fall was not banked: {baseline}"


def _check_package_missing_from_baseline_is_zero() -> None:
    failures = ratchet_failures({_ALPHA: dict(_PLANTED_ONE_EACH)}, {})
    assert len(failures) == len(COUNT_NAMES), f"each count of an unnamed package is pinned at 0: {failures}"
    assert not ratchet_failures({_BETA: dict(_PLANTED_NONE)}, {}), "a zero count over a missing package failed"


def _check_missing_baseline_refused() -> None:
    with _planted_workspace() as root:
        expect_usage_error(lambda: _quiet_ratchet(root), "does not exist")


def _check_malformed_baseline_refused() -> None:
    malformed = {
        "{not json": "unusable type hygiene baseline",
        "[1, 2]": "expected a JSON object",
        '{"datrix-alpha": 3}': "datrix-alpha",
        '{"datrix-alpha": {"type_ignores": -1, "any_signatures": 0, "casts": 0}}': "non-negative",
        '{"datrix-alpha": {"type_ignores": 1}}': "expected exactly",
        '{"datrix-alpha": {"type_ignores": 1, "any_signatures": 1, "casts": 1, "extra": 0}}': "expected exactly",
    }
    with _planted_workspace() as root:
        for text, fragment in malformed.items():
            write_files(root, {BASELINE_RELATIVE.as_posix(): text})
            expect_usage_error(lambda: _quiet_ratchet(root), fragment)


def _check_update_baseline_never_overwrites_a_malformed_baseline() -> None:
    with _planted_workspace() as root:
        baseline_path = write_files(root, {BASELINE_RELATIVE.as_posix(): "{not json"})[0]
        expect_usage_error(lambda: _quiet_ratchet(root, update_baseline=True), "unusable")
        kept = baseline_path.read_text(encoding="utf-8")
    assert kept == "{not json", f"a malformed baseline was overwritten: {kept}"


def _check_unparsable_source_refused() -> None:
    with _planted_workspace() as root:
        write_files(root, {"datrix-beta/src/beta/broken.py": "def broken(:\n"})
        expect_usage_error(lambda: take_census(root, show_files=False), "broken.py")


def _check_undecodable_source_refused() -> None:
    with _planted_workspace() as root:
        (root / "datrix-beta/src/beta/latin.py").write_bytes(b"NAME = '\xff'\n")
        expect_usage_error(lambda: take_census(root, show_files=False), "latin.py")


def _check_unparsable_annotation_string_refused() -> None:
    with _planted_workspace() as root:
        write_files(root, {"datrix-beta/src/beta/odd.py": 'def odd(x: "not a type!") -> None: ...\n'})
        expect_usage_error(lambda: take_census(root, show_files=False), "odd.py")


def _check_no_package_refused() -> None:
    with tempfile.TemporaryDirectory(prefix="type-hygiene-selftest-") as tmp:
        expect_usage_error(lambda: take_census(Path(tmp), show_files=False), "no datrix-* directory")


_SELF_TEST_CHECKS: Final[list[NamedCheck]] = named_checks(
    [
        _check_planted_tree_gives_the_planted_counts,
        _check_signature_forms_counted_once_each,
        _check_literal_and_annotated_metadata_are_data,
        _check_casts_bare_and_qualified,
        _check_ignore_comments_only,
        _check_rise_is_reported,
        _check_equal_count_passes,
        _check_update_baseline_refuses_a_rise,
        _check_fall_is_banked,
        _check_package_missing_from_baseline_is_zero,
        _check_missing_baseline_refused,
        _check_malformed_baseline_refused,
        _check_update_baseline_never_overwrites_a_malformed_baseline,
        _check_unparsable_source_refused,
        _check_undecodable_source_refused,
        _check_unparsable_annotation_string_refused,
        _check_no_package_refused,
    ]
)


def build_parser() -> argparse.ArgumentParser:
    """The gate's options: exactly the wrapper's parameters, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description="Type-hygiene ratchet: per-package escape-hatch counts may only fall",
        allow_abbrev=False,
    )
    parser.add_argument("--warn", action="store_true", help="Report a rise but exit 0.")
    parser.add_argument("--show-files", action="store_true", help="Print each file scanned.")
    parser.add_argument("--base-dir", default="", help="Workspace root (default: the workspace)")
    parser.add_argument(
        "--update-baseline", action="store_true",
        help="Freeze the first baseline, or tighten it; refused when any count rises.",
    )
    parser.add_argument(
        "--self-test", action="store_true",
        help="Run only the harness self-test, the census checks over a planted workspace and the wrapper seam check.",
    )
    parser.add_argument(
        WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Print the interpreter and the arguments."
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    """Run the self-test, or the census once the census checks have passed."""
    if args.debug:
        print_command()
    if args.self_test:
        return wrappers.run_self_test(
            [wrappers.self_test_check("harness_self_test", harness_self_test), *_SELF_TEST_CHECKS],
            wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=wrappers.RATCHET_GATES_DIR,
        )
    base_dir = Path(args.base_dir).resolve() if args.base_dir else WORKSPACE_DIR
    if not base_dir.is_dir():
        raise UsageError(f"-BaseDir {base_dir} is not a directory. Expected the workspace root holding datrix-*.")
    report_step("Self-test: type hygiene census checks")
    if not run_checks(_SELF_TEST_CHECKS):
        print("\nERROR: self-test failed; the census is not trusted for a real scan. Fix the gate first.")
        return EXIT_USAGE
    return run_ratchet(
        base_dir, update_baseline=args.update_baseline, warn=args.warn, show_files=args.show_files
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
