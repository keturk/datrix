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

Two holes this gate had, both of which let whole phases' worth of references
through while it reported clean:

* **Reference shape.** Matching only the hyphenated ``task-07-42`` form missed
  the far more common prose form an agent actually writes -- ``task 50-22`` --
  and any task number that reached three digits (``task-06-103``). Both are
  covered now, case-insensitively.
* **Coverage.** A hand-authored list of five trees silently excluded ten
  packages and every ``tests/`` tree in the workspace. Roots are derived from
  what is on disk, so a new package is scanned the day it appears.

The terminal state is zero: there is no baseline and no count to ratchet down,
because every reference found when those holes were closed was removed rather
than pinned. Adding an ``ALLOWLIST`` entry is the only escape hatch, and it is
for files that document the ID *format* -- never for a file that merely happens
to carry a reference.

Run with ``--self-test`` to verify the detector is non-vacuous.
"""

from __future__ import annotations

import argparse
import os
import re
import tempfile

# A reference looks like `task-07-42`, `task 50-22`, `design/044-foo`,
# `design doc 046`, or a `.tasks/phase-07` path. Matching the *shape* is
# deliberate: a number alone is far too common to flag.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("task-file id", re.compile(r"\btask[-\s]\d{2}-\d{2,3}\b", re.IGNORECASE)),
    ("design path", re.compile(r"design[/\\]\d{3}-[a-z0-9-]+")),
    ("design doc number", re.compile(r"\bdesign\s+doc(?:ument)?\s+\d{3}\b", re.IGNORECASE)),
    ("phase dir", re.compile(r"\.tasks[/\\]phase-\d{2}")),
)

# Deliberately NOT a pattern: a bare ``phase 88``. The committed architecture
# docs use "Phase NN capabilities" as product vocabulary for delivery waves,
# with their own headings and anchors -- self-contained text, not a pointer into
# a gitignored ``.tasks/phase-NN/`` tree, which the "phase dir" pattern above
# already catches. Flagging the bare form conflates the two and would force an
# anchor-churning docs rename for no gain in pointer safety.

SCAN_EXTENSIONS = (
    ".py", ".ps1", ".json", ".md", ".j2", ".ts", ".cs", ".java",
    ".toml", ".yaml", ".yml", ".dtrx",
)

# Never scanned: the gitignored orchestration trees themselves, plus build noise.
SKIP_DIRS = frozenset({".git", "__pycache__", "node_modules", ".venv", ".tasks", ".bugs", "design",
                       ".tmp", ".scripts", ".test-output", ".test_results", "generated"})

WORKSPACE_ROOT = "D:/datrix"

#: Committed subtrees of an installable ``datrix-*`` package.
PACKAGE_SUBTREES = ("src", "tests", "docs")

#: Committed subtrees of the ``datrix`` showcase repo, which has no ``src``.
SHOWCASE_SUBTREES = ("scripts", "docs", "examples")

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


def default_roots(workspace: str = WORKSPACE_ROOT) -> list[str]:
    """Every committed tree in the workspace, derived from disk.

    Never a hand-authored package list: a new ``datrix-*`` package is scanned as
    soon as it exists, which is exactly what the previous five-entry literal
    could not do.
    """
    roots: list[str] = []
    for name in sorted(os.listdir(workspace)):
        package_dir = os.path.join(workspace, name)
        if not name.startswith("datrix") or not os.path.isdir(package_dir):
            continue
        subtrees = SHOWCASE_SUBTREES if name == "datrix" else PACKAGE_SUBTREES
        for subtree in subtrees:
            candidate = os.path.join(package_dir, subtree)
            if os.path.isdir(candidate):
                roots.append(candidate.replace("\\", "/"))
    return roots


def scan(roots: list[str]) -> list[tuple[str, int, str, str]]:
    """Return (relative_path, lineno, label, line) for every reference found."""
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


def _write(path: str, body: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)


def self_test() -> int:
    """Prove the detector fires on every reference shape and stays quiet without one."""
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, "clean.py"),
               "# Emits the response DTO mapping for custom endpoints.\n")
        if scan([tmp]):
            print("SELF-TEST FAILED: detector reported a hit on a clean file")
            return 1

        # One planted line per shape, including the three the gate used to miss:
        # the prose form, a three-digit task number, and a non-.py extension.
        shapes = {
            "hyphenated.py": "# Implements task-07-42 per design/044-language-parity.\n",
            "prose.py": "# Realized for task 50-22, the enum-value surface.\n",
            "three_digit.py": "# Mirrors task-06-103's own coercion cascade.\n",
            "phase_dir.md": "See .tasks/phase-31 for the ordering that produced this.\n",
            "fixture.dtrx": "// documentation realization (task 50-22): one documented member\n",
        }
        for filename, body in shapes.items():
            _write(os.path.join(tmp, filename), body)
        found = scan([tmp])
        if len(found) != len(shapes):
            missed = sorted(set(shapes) - {os.path.basename(rel) for rel, _, _, _ in found})
            print(f"SELF-TEST FAILED: expected {len(shapes)} hits, got {len(found)}; missed {missed}")
            return 1

        # A bare delivery-wave mention is product vocabulary, not a pointer.
        _write(os.path.join(tmp, "vocab.md"), "### Phase 01 capabilities (Stable)\n")
        if len(scan([tmp])) != len(shapes):
            print("SELF-TEST FAILED: a bare 'Phase NN' heading must not be flagged")
            return 1

    print(
        "INFO: Non-vacuity self-test passed: the detector flags every planted "
        "reference shape (hyphenated, prose, three-digit, phase dir, .dtrx), "
        "reports zero for a clean file, and leaves a bare delivery-wave "
        "heading alone."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", help="directories to scan (default: every committed tree)")
    parser.add_argument("--self-test", action="store_true", help="run only the non-vacuity self-test")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if self_test() != 0:
        return 1

    roots = args.roots or default_roots()
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
