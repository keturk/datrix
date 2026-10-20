"""Snapshot the SHA-256 of every file under one or more trees, and diff two snapshots.

The module behind ``generation/tree-hash.ps1`` (and its ``.sh`` twin). The check behind "this
refactor changes no output": snapshot the generated tree, make the change, regenerate, snapshot
again, diff. Keys are ``<root name>/<path relative to the root>``, so two checkouts (or two runs
into different directories) compare file by file.

Exit codes: ``--snapshot`` 0; ``--diff`` 0 = identical, 1 = files added, removed or changed
(each listed), 2 = bad input.

Usage:
    python -m datrix_scripts.generation.tree_hash --snapshot --manifest=M.json --root=ROOT [--root=ROOT ...]
    python -m datrix_scripts.generation.tree_hash --diff --before=B.json --after=A.json [--limit=N]
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.dev.arguments import comma_values
from datrix_scripts.gate_harness import UsageError, expect_usage_error
from datrix_scripts.test.wrappers import GENERATION_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.generation.tree_hash"
WRAPPER: Final = "tree-hash"
DEFAULT_LIMIT: Final = 50
EXIT_SAME: Final[int] = 0
EXIT_DIFFERENT: Final[int] = 1
EXIT_USAGE: Final[int] = 2
SKIPPED_DIR_NAMES: Final[frozenset[str]] = frozenset(
    {".git", "node_modules", "__pycache__", ".ruff_cache", ".mypy_cache", ".pytest_cache", ".venv"}
)
MANIFEST_ROOTS_KEY: Final[str] = "roots"
MANIFEST_FILES_KEY: Final[str] = "files"
HASH_CHUNK_BYTES: Final[int] = 1 << 20


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_tree(root: Path) -> dict[str, str]:
    """``<root name>/<relative path>`` -> SHA-256 for every file under *root*."""
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_file() and not SKIPPED_DIR_NAMES & set(relative.parts):
            hashes[f"{root.name}/{relative.as_posix()}"] = file_digest(path)
    return hashes


def snapshot(manifest: Path, roots: Sequence[Path]) -> int:
    missing = [str(root) for root in roots if not root.is_dir()]
    if missing:
        print(f"Not a directory: {missing}. Pass the generated tree(s) to snapshot.")
        return EXIT_USAGE
    names = [root.name for root in roots]
    if len(set(names)) != len(names):
        print(f"Root directory names must be distinct (they prefix every key); got {names}.")
        return EXIT_USAGE
    files: dict[str, str] = {}
    for root in roots:
        files.update(hash_tree(root))
    manifest.parent.mkdir(parents=True, exist_ok=True)
    payload = {MANIFEST_ROOTS_KEY: [str(root.resolve()) for root in roots], MANIFEST_FILES_KEY: files}
    manifest.write_text(json.dumps(payload, indent=0, sort_keys=True), encoding="utf-8")
    print(f"{len(files)} file(s) hashed under {len(roots)} root(s) -> {manifest}")
    return EXIT_SAME


def _load(manifest: Path) -> Mapping[str, str]:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get(MANIFEST_FILES_KEY), dict):
        raise ValueError(f"{manifest} is not a tree-hash manifest (no '{MANIFEST_FILES_KEY}' table). Re-run snapshot.")
    return data[MANIFEST_FILES_KEY]


def diff(before_path: Path, after_path: Path, limit: int) -> int:
    try:
        before, after = _load(before_path), _load(after_path)
    except (OSError, ValueError) as exc:
        print(str(exc))
        return EXIT_USAGE
    sections = (
        ("added", sorted(set(after) - set(before))),
        ("removed", sorted(set(before) - set(after))),
        ("changed", sorted(name for name in set(before) & set(after) if before[name] != after[name])),
    )
    for label, names in sections:
        print(f"{label}: {len(names)}")
        shown = names if limit == 0 else names[:limit]
        for name in shown:
            print(f"  {name}")
        if len(shown) < len(names):
            print(f"  ... {len(names) - len(shown)} more; pass --limit 0 to list all")
    return EXIT_DIFFERENT if any(names for _, names in sections) else EXIT_SAME


def build_parser() -> argparse.ArgumentParser:
    """The options of ``generation/tree-hash.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--snapshot", action="store_true", help="Write a manifest of --root to --manifest.")
    parser.add_argument("--manifest", type=Path, help="Manifest file to write (keep it outside the package repos).")
    parser.add_argument("--root", action="append", default=[],
                        help="A tree to hash (repeatable or comma-separated; directory names must differ).")
    parser.add_argument("--diff", action="store_true", help="Compare --before with --after.")
    parser.add_argument("--before", type=Path, help="Earlier manifest.")
    parser.add_argument("--after", type=Path, help="Later manifest.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"Paths listed per diff section (0 = all). Default: {DEFAULT_LIMIT}.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: a planted tree is snapshotted and a changed file is diffed.")
    parser.set_defaults(debug=False)
    return parser


def _request(args: argparse.Namespace) -> tuple[str, list[Path]]:
    """The mode (``snapshot`` or ``diff``) and its paths; a ``UsageError`` for an incomplete request."""
    if args.snapshot == args.diff:
        raise UsageError("Pass exactly one of -Snapshot (with -Manifest and -Root) or -Diff (with -Before and -After).")
    if args.snapshot:
        roots = [Path(root) for root in comma_values(args.root)]
        if args.manifest is None or not roots:
            raise UsageError("-Snapshot needs -Manifest <file> and -Root <dir>[,<dir>...].")
        return "snapshot", [args.manifest, *roots]
    if args.before is None or args.after is None:
        raise UsageError("-Diff needs -Before <manifest> and -After <manifest>.")
    if args.limit < 0:
        raise UsageError(f"-Limit must be 0 (all) or positive; got {args.limit}.")
    return "diff", [args.before, args.after]


def _check_a_changed_file_is_diffed() -> None:
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()) as printed:
        root = Path(tmp) / "tree"
        (root / "node_modules").mkdir(parents=True)
        (root / "node_modules" / "skipped.js").write_text("skipped", encoding="utf-8")
        (root / "a.txt").write_text("one", encoding="utf-8")
        before, after = Path(tmp) / "before.json", Path(tmp) / "after.json"
        assert snapshot(before, [root]) == EXIT_SAME, "the snapshot of a planted tree failed"
        assert diff(before, before, DEFAULT_LIMIT) == EXIT_SAME, "a manifest differs from itself"
        (root / "a.txt").write_text("two", encoding="utf-8")
        snapshot(after, [root])
        assert diff(before, after, DEFAULT_LIMIT) == EXIT_DIFFERENT, "a changed file was not reported"
    assert "  tree/a.txt" in printed.getvalue(), f"the changed file was not listed: {printed.getvalue()!r}"
    assert "skipped.js" not in printed.getvalue(), "a file under node_modules was hashed"


def _check_incomplete_requests_are_refused() -> None:
    parser = build_parser()
    expect_usage_error(lambda: _request(parser.parse_args([])), "exactly one of")
    expect_usage_error(lambda: _request(parser.parse_args(["--snapshot", "--manifest=m.json"])), "-Root")
    expect_usage_error(lambda: _request(parser.parse_args(["--diff", "--before=b", "--after=a", "--limit=-1"])),
                       "-Limit")
    mode, paths = _request(parser.parse_args(["--snapshot", "--manifest=m.json", "--root=a,b"]))
    assert (mode, [path.name for path in paths]) == ("snapshot", ["m.json", "a", "b"]), (mode, paths)


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_a_changed_file_is_diffed, _check_incomplete_requests_are_refused]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(),
                             folder=GENERATION_SCRIPTS_DIR)
    mode, paths = _request(args)
    if mode == "snapshot":
        return snapshot(paths[0], paths[1:])
    return diff(paths[0], paths[1], args.limit)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
