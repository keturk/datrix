"""Count the files ending with each given extension in every Datrix repository, one column per extension.

``scripts/workspace/file-count.ps1`` (and its ``.sh`` twin) runs this module. The repositories are the
workspace's ``datrix`` showcase repository and every ``datrix-*`` directory, discovered from disk
(``framework_repos.workspace_package_dirs``), never listed. A file counts under an extension only when its
name ends with it, case-insensitively (``x.dtrx.false`` counts as ``dtrx.false``, never as ``dtrx``). The walk
leaves out hidden files and folders, as PowerShell's ``Get-ChildItem`` does, and never enters a symbolic link
or junction (its target can lie anywhere). Extensions are given without or with the leading dot, one per
``--extension`` or comma-separated (``powershell -File`` passes ``dtrx,dtrx.false`` as one string); the default
is ``j2``.

Exit codes: 0 = counted; 1 = a self-test check failed; 2 = a usage error.

Usage (PYTHONPATH=scripts/common/lib; the wrapper sets it):
    python -m datrix_scripts.workspace.file_count
    python -m datrix_scripts.workspace.file_count py
    python -m datrix_scripts.workspace.file_count --extension=dtrx,dtrx.false
    python -m datrix_scripts.workspace.file_count --self-test
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from datrix_scripts.cleanup_utils import children, is_link, plant_directory_link
from datrix_scripts.dev.arguments import comma_values
from datrix_scripts.framework_repos import workspace_package_dirs
from datrix_scripts.gate_harness import EXIT_PASS, write_files
from datrix_scripts.logging_utils import ColorCodes, colorize
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import WORKSPACE_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.workspace.file_count"
WRAPPER: Final = "file-count"

DEFAULT_EXTENSION: Final = "j2"
DIRECTORY_HEADING: Final = "Directory"
_DOT: Final = "."
_COLUMN_GAP: Final = " "
_RULE_CHAR: Final = "-"


@dataclass(frozen=True)
class RepositoryCount:
    """One repository's name and its file count per extension, in the requested order."""

    name: str
    counts: tuple[int, ...]


def normalized_extensions(values: Sequence[str]) -> list[str]:
    """Each requested extension, comma lists split, as ``.<extension>`` (a leading dot kept, never doubled)."""
    return [value if value.startswith(_DOT) else _DOT + value for value in comma_values(values)]


def _file_names(directory: Path) -> Iterator[str]:
    """The names of every visible file below *directory*; hidden entries and links are not entered."""
    for entry in children(directory, include_hidden=False):
        if is_link(entry):
            continue
        if entry.is_dir():
            yield from _file_names(entry)
        elif entry.is_file():
            yield entry.name


def count_repository(repository: Path, extensions: Sequence[str]) -> RepositoryCount:
    """How many files below *repository* end with each of *extensions*, case-insensitively."""
    names = [name.casefold() for name in _file_names(repository)]
    counts = tuple(sum(1 for name in names if name.endswith(extension.casefold())) for extension in extensions)
    return RepositoryCount(repository.name, counts)


def table_lines(rows: Sequence[RepositoryCount], extensions: Sequence[str]) -> list[str]:
    """The table ``Format-Table -AutoSize`` prints: the name column left-aligned, each count right-aligned under
    its extension, every column as wide as its widest cell, a dashed rule under each heading."""
    name_width = max([len(DIRECTORY_HEADING), *(len(row.name) for row in rows)])
    widths = [
        max([len(extension), *(len(str(row.counts[index])) for row in rows)])
        for index, extension in enumerate(extensions)
    ]

    def line(name: str, cells: Sequence[str]) -> str:
        return _COLUMN_GAP.join([name.ljust(name_width), *(cell.rjust(width) for cell, width in zip(cells, widths))])

    rule = _COLUMN_GAP.join([(_RULE_CHAR * len(DIRECTORY_HEADING)).ljust(name_width),
                             *((_RULE_CHAR * len(extension)).rjust(width) for extension, width in zip(extensions, widths))])
    return [
        line(DIRECTORY_HEADING, extensions),
        rule,
        *(line(row.name, [str(count) for count in row.counts]) for row in rows),
    ]


def run(extension_values: Sequence[str], workspace: Path = WORKSPACE_DIR) -> int:
    """Count and print the table and the per-extension totals; returns the exit code."""
    extensions = normalized_extensions(extension_values or [DEFAULT_EXTENSION])
    print(colorize(f"Counting {', '.join(extensions)} files in subfolders...", ColorCodes.CYAN))
    print()
    rows = [count_repository(repository, extensions) for repository in workspace_package_dirs(workspace, include_showcase=True)]
    print()
    for text in table_lines(rows, extensions):
        print(text.rstrip())
    print()
    print()
    for index, extension in enumerate(extensions):
        total = sum(row.counts[index] for row in rows)
        print(colorize(f"Total {extension} files: {total}", ColorCodes.GREEN))
    return EXIT_PASS


def build_parser() -> argparse.ArgumentParser:
    """The options of ``file-count.ps1``: its parameters as ``--kebab-name`` flags."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER,
        description="Count files by extension in every Datrix repository, one column per extension.",
        allow_abbrev=False,
    )
    parser.add_argument("positional_extensions", nargs="*", metavar="EXTENSION",
                        help="as --extension, for a caller of the .sh twin")
    parser.add_argument("--extension", action="append", default=[],
                        help=f"an extension to count, without the dot; repeatable or comma-separated "
                             f"(default: {DEFAULT_EXTENSION})")
    parser.add_argument("--self-test", action="store_true", help="run the self-test and exit")
    parser.set_defaults(debug=False)
    return parser


# ---------------------------------------------------------------------------
# Self-test: a planted workspace in a temporary directory.
# ---------------------------------------------------------------------------

_PLANTED: Final = {
    "datrix/examples/a.dtrx": "\n",
    "datrix/examples/b.DTRX": "\n",
    "datrix/examples/c.dtrx.false": "\n",
    "datrix-a/src/t.j2": "\n",
    "datrix-a/.dotted/counted.dtrx": "\n",
    "datrix-b/README.md": "\n",
    "other/x.dtrx": "\n",
}


def _check_extensions_are_normalized_and_split() -> None:
    got = normalized_extensions(["dtrx,dtrx.false", ".py", " ", "j2"])
    assert got == [".dtrx", ".dtrx.false", ".py", ".j2"], got


def _check_counts_by_suffix_only() -> None:
    with TemporaryDirectory() as raw:
        root = Path(raw)
        write_files(root, _PLANTED)
        extensions = normalized_extensions(["dtrx,dtrx.false"])
        rows = [count_repository(path, extensions) for path in workspace_package_dirs(root, include_showcase=True)]
    # A dot-named folder is not hidden (Windows hides by attribute), so its files count, as Get-ChildItem's do.
    expected = [RepositoryCount("datrix", (2, 1)), RepositoryCount("datrix-a", (1, 0)), RepositoryCount("datrix-b", (0, 0))]
    assert rows == expected, rows


def _check_links_are_not_entered() -> None:
    with TemporaryDirectory() as raw:
        root = Path(raw)
        write_files(root, {"datrix-a/src/t.j2": "\n", "outside/u.j2": "\n"})
        plant_directory_link(root / "datrix-a" / "linked", root / "outside")
        row = count_repository(root / "datrix-a", [".j2"])
    assert row.counts == (1,), f"a link was entered: {row}"


def _check_table_is_aligned() -> None:
    rows = [RepositoryCount("datrix", (210, 0)), RepositoryCount("datrix-language", (171, 28))]
    lines = [text.rstrip() for text in table_lines(rows, [".dtrx", ".dtrx.false"])]
    assert lines == [
        "Directory       .dtrx .dtrx.false",
        "---------       ----- -----------",
        "datrix            210           0",
        "datrix-language   171          28",
    ], lines


_SELF_TEST_CHECKS: Final = (
    _check_extensions_are_normalized_and_split,
    _check_counts_by_suffix_only,
    _check_links_are_not_entered,
    _check_table_is_aligned,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the self-test, or count the files."""
    parser = build_parser()

    def dispatch(args: argparse.Namespace) -> int:
        if args.self_test:
            return run_self_test(
                _SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=parser, folder=WORKSPACE_SCRIPTS_DIR
            )
        return run([*args.extension, *args.positional_extensions])

    return module_main(parser, dispatch, argv)


if __name__ == "__main__":
    sys.exit(main())
