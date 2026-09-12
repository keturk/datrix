"""The one definition of "a temp/scratch/output directory name" inside a package repo.

Two enforcement points consume it and must agree:

* ``guard-repo-temp-dirs.py`` (PreToolUse hook) refuses to CREATE such a directory
  inside a repo.
* ``datrix/scripts/library/test/ignored_source.py`` (the ignored-source gate, also
  the pre-stage check in ``git/commit-and-push.py``) recognizes one that already
  EXISTS, so its contents are reported as a stray temp tree to delete rather
  than as publishable source a ``.gitignore`` rule is silently dropping.

Detection is by directory NAME, not by guesswork: the names below appear nowhere
in any repo's tracked files, so a match is unambiguous. Kept beside the hook
(rather than under ``scripts/library``) because the hook must stay importable
with nothing but its own directory on ``sys.path`` -- a hook whose import fails
fails OPEN, and a guard that silently stops guarding is worse than none.
"""

from __future__ import annotations

# Directory names that mark a temp/scratch/output location. Exact segment match,
# case-insensitive.
TEMP_DIR_SEGMENTS: frozenset[str] = frozenset(
    {
        ".tmp",
        "tmp",
        ".temp",
        "temp",
        ".scratch",
        "scratch",
        "scratchpad",
        ".scripts",
        ".agent_output",
        "agent_output",
        ".test_output",
        "test_output",
        ".test-output",
        "test-output",
    }
)

# `.test-output-foundation-check`, `test-output-2`, ... -- same thing with a suffix.
TEMP_DIR_PREFIXES: tuple[str, ...] = (".test-output", "test-output", ".test_output", "test_output")

# Third-party / tooling trees that legitimately carry a `tmp` of their own. Their
# contents are not ours to police and are already ignored by every repo.
# `.hypothesis` is Hypothesis's example database, which keeps a `tmp/` for its
# own scratch files beside `constants/` and `unicode_data/`.
THIRD_PARTY_SEGMENTS: frozenset[str] = frozenset(
    {"node_modules", ".venv", ".git", "site-packages", ".hypothesis"}
)

# Written inside each package by design (test.ps1, pytest-benchmark) and ignored there.
SANCTIONED_SEGMENTS: frozenset[str] = frozenset({".test_results", ".benchmarks"})


def temp_dir_segment(segments: list[str]) -> str | None:
    """Return the first segment naming a temp/scratch directory, or None.

    Walks *segments* in path order. Reaching a third-party or sanctioned
    segment first answers None for the whole path: whatever sits under
    ``node_modules/`` or ``.test_results/`` is that tree's business, not a
    stray temp directory of ours.
    """
    for segment in segments:
        name = segment.strip().lower()
        if not name or name in (".", ".."):
            continue
        if name in THIRD_PARTY_SEGMENTS or name in SANCTIONED_SEGMENTS:
            return None
        if name in TEMP_DIR_SEGMENTS or name.startswith(TEMP_DIR_PREFIXES):
            return segment
    return None
