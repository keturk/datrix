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
* **Design-doc shape.** The design-side pattern required the literal word
  ``doc`` (``design doc 046``), so the shape people actually write --
  ``design 048``, ``design-019``, ``design 021 Section 5`` -- passed straight
  through, and fifteen of them accumulated across five packages while this
  gate reported clean. The word ``doc`` is optional now.
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

# A reference looks like `task-07-42`, `task 50-22`, `tasks 09-21 and 09-22`,
# `design/044-foo`, `design 048`, `design-019`, `design doc 046`, or a
# `.tasks/phase-07` path.
# Matching the *shape* is deliberate: a number alone is far too common to flag.
#
# Both the noun and the separator run are permissive, and both had to be. Each
# pattern here was once written with a SINGULAR noun and exactly ONE separator,
# and each was blind to a whole family of the thing it exists to catch while
# reporting clean:
#
#   * the singular-only task pattern missed the plural entirely -- `tasks 09-21
#     and 09-22` is the natural way to cite more than one, and five real
#     references (including every one in `datrix-codegen-docker`, a package that
#     therefore looked clean because the pattern was blind, not the repo) were
#     invisible until `tasks?` and a `*`-quantified separator class landed;
#   * the one-separator task pattern missed `task  43-01`, `Task_43-01` and
#     `task43-01`;
#   * requiring the literal word `doc` missed `design 048` and `design-019`
#     for fifteen references across five packages.
#
# Hence `s?` on both nouns, `[-_\s]*` (zero or more) for every separator run,
# and a plural-tolerant `doc` group. `\b` on both ends keeps this from firing
# on `subtask43-01` or on an identifier like `DESIGN2024`.
_SEP = r"[-_\s]*"
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("task-file id", re.compile(rf"\btasks?{_SEP}\d{{2}}-\d{{2,3}}\b", re.IGNORECASE)),
    ("design path", re.compile(r"designs?[/\\]\d{3}-[a-z0-9-]+", re.IGNORECASE)),
    (
        "design doc number",
        re.compile(
            rf"\bdesigns?{_SEP}(?:(?:doc|docs|document|documents){_SEP})?\d{{3}}\b",
            re.IGNORECASE,
        ),
    ),
    ("phase dir", re.compile(r"\.tasks[/\\]phase-\d{2}")),
)

# Deliberately NOT a pattern: a bare ``phase 88``. The committed architecture
# docs use "Phase NN capabilities" as product vocabulary for delivery waves,
# with their own headings and anchors -- self-contained text, not a pointer into
# a gitignored ``.tasks/phase-NN/`` tree, which the "phase dir" pattern above
# already catches. Flagging the bare form conflates the two and would force an
# anchor-churning docs rename for no gain in pointer safety.

SCAN_EXTENSIONS = (
    ".py", ".ps1", ".json", ".md", ".j2", ".ts", ".mts", ".cts",
    ".js", ".mjs", ".cjs", ".cs", ".java",
    ".toml", ".yaml", ".yml", ".dtrx",
)

# Never scanned: the gitignored orchestration trees themselves, plus build noise.
SKIP_DIRS = frozenset({".git", "__pycache__", "node_modules", ".venv", ".tasks", ".bugs", "design",
                       ".tmp", ".scripts", ".test-output", ".test_results", "generated"})

WORKSPACE_ROOT = "D:/datrix"

#: Committed subtrees of a ``datrix-*`` package. ``scripts`` is here because a
#: package's build tooling is committed like any other source: datrix-vscode
#: keeps its grammar generation and packaging checks under ``scripts/``, and a
#: subtree no gate scans is a subtree where a dangling design/task reference
#: survives review.
PACKAGE_SUBTREES = ("src", "tests", "docs", "scripts")

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

        # One planted line per shape. NON-VACUITY MEANS ENUMERATING THE SHAPES
        # A PATTERN MUST CATCH, not proving it fires once: every entry below
        # from `plural` onward is a form this gate reported clean on while real
        # references sat in the tree. Add a shape here before widening a
        # pattern, never after.
        shapes = {
            "hyphenated.py": "# Implements task-07-42 per design/044-language-parity.\n",
            "prose.py": "# Realized for task 50-22, the enum-value surface.\n",
            "three_digit.py": "# Mirrors task-06-103's own coercion cascade.\n",
            "phase_dir.md": "See .tasks/phase-31 for the ordering that produced this.\n",
            "fixture.dtrx": "// documentation realization (task 50-22): one documented member\n",
            "bare_design.py": "# Covers design 048 Section 5's host/port hole.\n",
            "hyphen_design.py": "# Unit tests for design-019 D1's native-only validator.\n",
            "design_doc.md": "The split is settled in design doc 046.\n",
            # The plural is the natural way to cite more than one, and it hid
            # five real references -- every one in datrix-codegen-docker.
            "plural.py": "# After tasks 09-21 and 09-22, the target emits no .env file.\n",
            "plural_slashed.py": "# Build the plan first (see tasks 08-07/08-09).\n",
            "plural_design.md": "Both splits are settled in design docs 046.\n",
            # Separator runs other than exactly one hyphen or one space.
            "wide_sep.py": "# Implements task  43-01 across the two emitters.\n",
            "underscore_sep.py": "# Mirrors Task_31-07's own base-image skip.\n",
            "no_sep.py": "# See task43-01 for the universe widening.\n",
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
        "INFO: Non-vacuity self-test passed: the detector flags all 14 planted "
        "reference shapes (hyphenated, prose, three-digit, phase dir, .dtrx, "
        "bare 'design NNN', hyphenated 'design-NNN', 'design doc NNN', plural "
        "'tasks NN-NN', slashed plural, plural 'design docs NNN', "
        "multi-space, underscore and zero separators), reports zero for a "
        "clean file, and leaves a bare delivery-wave heading alone."
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
