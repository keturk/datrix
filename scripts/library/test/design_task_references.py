"""Fail if a committed artifact cites a design document or a task file.

Design documents (``design/``) and task files (``.tasks/``) are gitignored and are
developed on more than one machine, so their numbering collides: two different
``044-*`` documents can exist, and neither is present after a clone. A reference
to one from anything that *is* committed is therefore a dangling pointer -- it
resolves to nothing, or worse, to a different artifact elsewhere.

So no design-doc or task-file number, filename, ID, or path may appear in code
comments, docstrings, committed documentation, or committed configuration.
Describe *what* the code does and *why*, never which ticket tracked it.

Design and task files referencing **each other** are exempt: that is gitignored
orchestration machinery, not a committed artifact. Those trees are skipped.

Run with ``--self-test`` to verify the detector is non-vacuous.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile

# A reference looks like `task-07-42`, `design/044-foo`, `design doc 046`, or a
# `.tasks/phase-07` path. Matching the *shape* is deliberate: a number alone is
# far too common to flag.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("task-file id", re.compile(r"\btask-\d{2}-\d{2}\b")),
    ("design path", re.compile(r"design[/\\]\d{3}-[a-z0-9-]+")),
    ("design doc number", re.compile(r"\bdesign\s+doc(?:ument)?\s+\d{3}\b", re.IGNORECASE)),
    ("phase dir", re.compile(r"\.tasks[/\\]phase-\d{2}")),
)

SCAN_EXTENSIONS = (".py", ".ps1", ".json", ".md", ".j2", ".ts", ".cs", ".java", ".toml", ".yaml", ".yml")

# Never scanned: the gitignored orchestration trees themselves, plus build noise.
SKIP_DIRS = frozenset({".git", "__pycache__", "node_modules", ".venv", ".tasks", ".bugs", "design",
                       ".tmp", ".scripts", ".test-output", ".test_results", "generated"})

# Files allowed to contain the *shape* of a reference because they document the
# ID FORMAT itself or synthesize fixtures. Each entry needs a reason: this list
# is an escape hatch and must not become a dumping ground.
ALLOWLIST: dict[str, str] = {
    "datrix/scripts/library/tasks/task_metadata.py":
        "documents and parses the task-ID grammar; the IDs in its docstrings are format examples",
    "datrix/scripts/library/review/review_schema.py":
        "field docstring showing the shape of a task-relative location string",
    "datrix/scripts/tasks/quick-reference.md":
        "usage examples for the task scripts; the IDs are illustrative arguments",
    "datrix/scripts/review/quick-reference.md":
        "usage example for the review runner",
    "datrix/scripts/review/README.md":
        "usage example for the review runner",
    "datrix/scripts/test/review-library-gate.py":
        "self-test fixtures that synthesize task files in a temp dir",
    "datrix/scripts/library/test/design_task_references.py":
        "this gate's own patterns and self-test fixtures",
    "datrix-common/docs/contributing/agent_skills/execute_tasks.md":
        "documents the phase-directory input format of a skill",
}


def _norm(path: str) -> str:
    return path.replace("\\", "/").removeprefix("D:/datrix/").removeprefix("d:/datrix/")


def scan(roots: list[str]) -> list[tuple[str, int, str, str]]:
    """Return (relative_path, lineno, label, line) for every violation found."""
    hits: list[tuple[str, int, str, str]] = []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for filename in filenames:
                if not filename.endswith(SCAN_EXTENSIONS):
                    continue
                path = os.path.join(dirpath, filename)
                rel = _norm(path)
                if rel in ALLOWLIST:
                    continue
                try:
                    text = open(path, encoding="utf-8", errors="replace").read()
                except OSError:
                    continue
                for lineno, line in enumerate(text.splitlines(), 1):
                    for label, pattern in PATTERNS:
                        if pattern.search(line):
                            hits.append((rel, lineno, label, line.strip()[:160]))
                            break
    return hits


def self_test() -> int:
    """Prove the detector fires on a planted reference and stays quiet without one."""
    with tempfile.TemporaryDirectory() as tmp:
        clean = os.path.join(tmp, "clean.py")
        with open(clean, "w", encoding="utf-8") as handle:
            handle.write("# Emits the response DTO mapping for custom endpoints.\n")
        if scan([tmp]):
            print("SELF-TEST FAILED: detector reported a hit on a clean file")
            return 1

        dirty = os.path.join(tmp, "dirty.py")
        with open(dirty, "w", encoding="utf-8") as handle:
            handle.write("# Implements task-07-42 per design/044-language-parity.\n")
        found = scan([tmp])
        if len(found) != 1:
            print(f"SELF-TEST FAILED: expected exactly 1 hit on a planted reference, got {len(found)}")
            return 1

    print(
        "INFO: Non-vacuity self-test passed: the detector flags a planted "
        "task-file/design reference and reports zero for a clean file."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", help="directories to scan (default: the committed trees)")
    parser.add_argument("--self-test", action="store_true", help="run only the non-vacuity self-test")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    roots = args.roots or [
        "D:/datrix/datrix/scripts",
        "D:/datrix/datrix/docs",
        "D:/datrix/datrix-common/src",
        "D:/datrix/datrix-common/docs",
        "D:/datrix/datrix-codegen-common/src",
    ]
    if self_test() != 0:
        return 1

    hits = scan(roots)
    if not hits:
        print(f"INFO: No design-doc or task-file references in {len(roots)} committed tree(s).")
        print("Design/task reference check passed")
        return 0

    print(f"ERROR: {len(hits)} design-doc/task-file reference(s) in committed artifacts:")
    for rel, lineno, label, line in hits:
        print(f"  [{label}] {rel}:{lineno}: {line}")
    print(
        "\nDesign docs and task files are gitignored and numbered per-machine, so these are "
        "dangling pointers. Describe the WORK, not the ticket."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
