#!/usr/bin/env python3
"""Snapshot the SHA-256 of every file under one or more trees, and diff two snapshots.

The check behind "this refactor changes no output": snapshot the generated tree, make the
change, regenerate, snapshot again, diff. Keys are ``<root name>/<path relative to the root>``,
so two checkouts (or two runs into different directories) compare file by file.

Exit codes: ``snapshot`` 0; ``diff`` 0 = identical, 1 = files added, removed or changed
(each listed), 2 = bad input.

Usage:
    python tree_hash.py snapshot MANIFEST.json ROOT [ROOT ...]
    python tree_hash.py diff BEFORE.json AFTER.json [--limit N]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

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


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    snap = commands.add_parser("snapshot", help="Hash every file under the roots.")
    snap.add_argument("manifest", type=Path)
    snap.add_argument("roots", type=Path, nargs="+")
    compare = commands.add_parser("diff", help="Compare two manifests.")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    compare.add_argument("--limit", type=int, default=50, help="Paths listed per section (0 = all). Default: 50.")
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    if args.command == "snapshot":
        return snapshot(args.manifest, args.roots)
    if args.limit < 0:
        print(f"--limit must be 0 (all) or positive; got {args.limit}.")
        return EXIT_USAGE
    return diff(args.before, args.after, args.limit)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
