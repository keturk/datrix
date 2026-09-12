#!/usr/bin/env python
"""Ignored-source gate: a `.gitignore` rule may never shadow a publishable file.

WHY THIS EXISTS
---------------
A `.gitignore` pattern once deleted a package's source from every clone, and
nothing caught it. A frontend generator package carried the stock Python
`.gitignore`'s UNANCHORED ``MANIFEST`` line -- meant for setuptools' root
``MANIFEST`` file. Git matches an unanchored pattern at ANY depth, and
``core.ignorecase=true`` on this platform makes the match case-insensitive, so
it also matched a ``templates/manifest/`` directory and swallowed both Jinja2
templates inside it.

That failure mode is the dangerous kind: completely invisible locally. The
files are on disk, every test passes, the emitted output compiles, and the
package looks healthy. The loss appears only after a clone or a wheel install,
as a package that cannot generate -- and by then the templates are gone from
history. It was found by hand, by comparing a `find` count against a
`git add -A --dry-run` count. Nothing in the repo computed that comparison.

WHAT THIS COMPUTES
------------------
The seam is *files on disk* (producer) versus *files git will publish*
(consumer), and this is its set comparison, living in code: for every framework
repo, every path present in the working tree that ``git add -A`` would NOT
stage must be a reviewed, counted exemption. Anything else is a publishable
file a `.gitignore` rule is silently deleting.

GIT IS THE ORACLE, NOT A RE-IMPLEMENTATION
------------------------------------------
Ignore matching is never re-implemented here. ``git ls-files -o -i
--exclude-standard`` produces the on-disk-minus-staged set and
``git check-ignore -v`` names the `.gitignore` file, line number and pattern
responsible for each element. Glob semantics, anchoring, negation (``!``),
nested `.gitignore` files, `.git/info/exclude`, global excludes and
``core.ignorecase`` interact in ways a hand-rolled matcher gets wrong -- and a
wrong matcher returns a confident "clean" that will be believed, which is
exactly how the original defect survived.

WHY THE FINDING NAMES THE RULE
------------------------------
Reporting only the shadowed file leaves the fix a hunt through several hundred
`.gitignore` lines. Every finding carries `<gitignore>:<line>: <pattern>` taken
verbatim from git, so the fix is to that line.

EXEMPTIONS ARE SCOPED, NOT BLANKET
----------------------------------
Deliberate build output (bytecode caches, coverage reports, editable-install
metadata, generated parser sources) is legitimately ignored and must stay
ignored. Each such rule is a reviewed entry in
``scripts/config/ignored-source-exemptions.json`` carrying a written reason,
and each entry is scoped to the paths it may cover. The scope is load-bearing:
an entry for the root ``build/`` directory must not also excuse an unanchored
``build/`` rule swallowing a ``templates/build/`` directory full of source --
that is the same defect wearing a different name.

A STRAY TEMP DIRECTORY IS A DIFFERENT FINDING, WITH A DIFFERENT FIX
--------------------------------------------------------------------
Temp, scratch and test-output directories never belong inside a package repo
(the workspace-level ``D:\\datrix\\.tmp``, ``.scripts``, ``.test-output`` are
where they go), and the ``guard-repo-temp-dirs.py`` hook refuses to create one
there. One that exists anyway -- left by a run before the hook, or by a tool
that defaulted its output path -- is full of ``.py``/``.java``/``.sql`` files a
``.gitignore`` backstop rule hides, and to a scan that only knows "ignored,
unexempted" it looks like hundreds of shadowed source files whose fix is to
edit the ignore line or add an exemption. Both are wrong: the files are not
source, and the directory should not exist. So the gate classifies such a path
by the SAME name list the hook enforces (``_repo_temp_dir_names.py`` beside the
hook -- one definition, two enforcement points) and reports it once, as a
stray directory with the delete command, never as a shadowed-source finding
and never as a reason to exempt the directory. It does not fail the gate: the
contents are already unpublishable, and this gate's verdict is about what a
clone would lose.

Repo-level validation script, per the datrix showcase boundary: the showcase
repo hosts no pytest suite, so cross-repo checks live here as scripts and the
gate's own self-test is its coverage.

Exit codes:
  0 = every unstaged path is a reviewed exemption
  1 = at least one publishable file is shadowed, or the self-test failed
  2 = usage error, or the exemption file is missing/malformed/miscounted
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LIBRARY_DIR = SCRIPT_DIR.parent
DATRIX_ROOT = SCRIPT_DIR.parents[2]
sys.path.insert(0, str(LIBRARY_DIR))

from dev.customer_domain_isolation import framework_repos  # noqa: E402

logger = logging.getLogger(__name__)

EXEMPTION_RELPATH = ("scripts", "config", "ignored-source-exemptions.json")

# The one definition of a temp/scratch directory name, kept beside the hook that
# refuses to create one (see the module docstring). Loaded by path because the
# hooks directory is not a package: the hook must import it with nothing but its
# own directory on sys.path, and this gate must read the same file, not a copy.
TEMP_DIR_NAMES_RELPATH = ("claude-config", ".claude", "hooks", "_repo_temp_dir_names.py")

# Wildcard accepted in an entry's `repos` list, meaning "every framework repo".
# Present so a rule that is uniform across packages (a bytecode cache, an
# editable-install metadata directory) needs no edit here when a new
# datrix-* package is cloned.
ALL_REPOS = "*"

# How many shadowed paths a single violating rule prints before it is summarized.
MAX_REPORTED_PATHS = 20

# Placeholders used when git attributes no rule to a path it nonetheless
# refuses to stage. That is unexplained, so it is reported and fails the gate
# rather than being dropped.
UNATTRIBUTED_SOURCE = "(no .gitignore attributed by git check-ignore)"
UNATTRIBUTED_PATTERN = "(unattributed)"

# Number of NUL-terminated fields per `git check-ignore -v -z` record:
# source, line number, pattern, pathname.
CHECK_IGNORE_FIELDS = 4


class IgnoredSourceGateError(RuntimeError):
    """The gate cannot run: git failed, or the exemption file is unusable."""


@dataclass(frozen=True)
class IgnoreRule:
    """The `.gitignore` line git itself blames for shadowing a path."""

    gitignore: str
    line: int
    pattern: str

    def render(self) -> str:
        return f"{self.gitignore}:{self.line}: {self.pattern}"


@dataclass(frozen=True)
class ShadowedPath:
    """One working-tree path in one repo that `git add -A` would not stage."""

    repo: str
    path: str
    rule: IgnoreRule

    def render(self) -> str:
        """One line naming the file AND the rule -- never the file alone.

        Without the rule the fix is a hunt through several hundred `.gitignore`
        lines, so the two travel together everywhere a finding is reported.
        """
        return f"{self.repo}/{self.path}  <- shadowed by {self.rule.render()}"


@dataclass(frozen=True)
class Exemption:
    """One reviewed, scoped permission for a rule to hide non-publishable output."""

    repos: frozenset[str]
    gitignore: str
    pattern: str
    path_glob: str
    reason: str
    matcher: re.Pattern[str]

    @property
    def applies_to_every_repo(self) -> bool:
        return ALL_REPOS in self.repos

    def covers(self, shadowed: ShadowedPath) -> bool:
        """True when this entry authorizes hiding `shadowed`."""
        if not self.applies_to_every_repo and shadowed.repo not in self.repos:
            return False
        if self.gitignore != shadowed.rule.gitignore:
            return False
        if self.pattern != shadowed.rule.pattern:
            return False
        return self.matcher.fullmatch(shadowed.path) is not None

    def render(self) -> str:
        scope = "every repo" if self.applies_to_every_repo else ", ".join(sorted(self.repos))
        return f"{self.gitignore}: {self.pattern} -> {self.path_glob} [{scope}]"


@dataclass(frozen=True)
class ExemptionSet:
    """Every reviewed entry, indexed by the rule identity it excuses."""

    entries: tuple[Exemption, ...]
    index: dict[tuple[str, str], tuple[Exemption, ...]]

    def covering(self, shadowed: ShadowedPath) -> Exemption | None:
        """Return the entry authorizing `shadowed`, or None when it is a violation."""
        candidates = self.index.get((shadowed.rule.gitignore, shadowed.rule.pattern), ())
        for entry in candidates:
            if entry.covers(shadowed):
                return entry
        return None


@dataclass(frozen=True)
class StrayTempDir:
    """A temp/scratch directory sitting inside a package repo, with what it holds.

    Not a shadowed-source finding: its contents are unpublishable by
    construction, and the fix is to delete the directory, never to edit the
    ignore rule that hides it or to exempt it.
    """

    repo: str
    relpath: str
    file_count: int

    def render(self, repo_path: Path) -> str:
        """One line per directory, carrying the delete command."""
        absolute = repo_path / Path(self.relpath)
        return (
            f"{self.repo}/{self.relpath}/  -- stray temp directory inside a package repo, "
            f"{self.file_count} ignored file(s). Delete it: "
            f"Remove-Item -Recurse -Force \"{absolute}\""
        )


@dataclass(frozen=True)
class RepoResult:
    """One repo's census: what git hides, what is excused, what is not."""

    repo: str
    shadowed_total: int
    exempt_total: int
    violations: tuple[ShadowedPath, ...]
    stray_temp_dirs: tuple[StrayTempDir, ...]


TempDirSegmentFn = Callable[[list[str]], "str | None"]


def temp_dir_names_path(datrix_root: Path) -> Path:
    """Canonical location of the shared temp-directory name definition."""
    return datrix_root.joinpath(*TEMP_DIR_NAMES_RELPATH)


def load_temp_dir_segment(datrix_root: Path) -> TempDirSegmentFn:
    """Load ``temp_dir_segment`` from the definition the temp-dir hook enforces.

    Raises:
        IgnoredSourceGateError: the module is missing or does not export the
            function. The gate refuses to run rather than fall back to a private
            name list -- a second list is how the two enforcement points drift.
    """
    path = temp_dir_names_path(datrix_root)
    if not path.is_file():
        raise IgnoredSourceGateError(
            f"Temp-directory name definition not found at {path}. The ignored-source gate "
            f"classifies stray temp directories by the same list guard-repo-temp-dirs.py "
            f"enforces; restore that module rather than giving the gate a copy."
        )
    spec = importlib.util.spec_from_file_location("_repo_temp_dir_names", path)
    if spec is None or spec.loader is None:
        raise IgnoredSourceGateError(f"Could not build an import spec for {path}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    function = getattr(module, "temp_dir_segment", None)
    if not callable(function):
        raise IgnoredSourceGateError(
            f"{path} exports no callable 'temp_dir_segment'. The hook and this gate share "
            f"that one function; it must be defined there."
        )
    return function


def exemption_path(datrix_root: Path) -> Path:
    """Canonical location of the reviewed exemption file inside the showcase repo."""
    return datrix_root.joinpath(*EXEMPTION_RELPATH)


def glob_to_regex(path_glob: str) -> re.Pattern[str]:
    """Compile an exemption scope glob into an anchored regex.

    ``**/`` spans zero or more whole path segments, ``**`` spans any remainder,
    ``*`` and ``?`` stay inside one segment. Segment-aware on purpose: an
    exemption for the root ``build/`` must not silently also cover
    ``src/pkg/templates/build/``, which is the very shape this gate exists to
    catch.
    """
    parts: list[str] = []
    index = 0
    while index < len(path_glob):
        if path_glob.startswith("**/", index):
            parts.append("(?:[^/]+/)*")
            index += 3
        elif path_glob.startswith("**", index):
            parts.append(".*")
            index += 2
        elif path_glob[index] == "*":
            parts.append("[^/]*")
            index += 1
        elif path_glob[index] == "?":
            parts.append("[^/]")
            index += 1
        else:
            parts.append(re.escape(path_glob[index]))
            index += 1
    return re.compile("".join(parts))


def _require_str(entry: dict[str, object], field: str, path: Path, position: int) -> str:
    """Return a required non-empty string field, or raise naming the fix."""
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise IgnoredSourceGateError(
            f"Exemption entry {position} in {path} has no non-empty string '{field}'. "
            f"Every entry is {{'repos': [...], 'gitignore': ..., 'pattern': ..., "
            f"'path_glob': ..., 'reason': ...}}; add the missing field."
        )
    return value


def _parse_repos(entry: dict[str, object], path: Path, position: int) -> frozenset[str]:
    """Return an entry's repo scope, or raise naming the fix."""
    raw = entry.get("repos")
    if not isinstance(raw, list) or not raw:
        raise IgnoredSourceGateError(
            f"Exemption entry {position} in {path} has no non-empty 'repos' list. "
            f"Use [\"{ALL_REPOS}\"] for every framework repo, or name the repos explicitly."
        )
    names: set[str] = set()
    for name in raw:
        if not isinstance(name, str) or not name.strip():
            raise IgnoredSourceGateError(
                f"Exemption entry {position} in {path} has a non-string repo name {name!r}."
            )
        names.add(name.strip())
    return frozenset(names)


def _parse_entry(entry: object, path: Path, position: int) -> Exemption:
    """Build one Exemption from raw JSON, raising on anything underspecified."""
    if not isinstance(entry, dict):
        raise IgnoredSourceGateError(
            f"Exemption entry {position} in {path} is {type(entry).__name__}, not an object."
        )
    path_glob = _require_str(entry, "path_glob", path, position)
    return Exemption(
        repos=_parse_repos(entry, path, position),
        gitignore=_require_str(entry, "gitignore", path, position),
        pattern=_require_str(entry, "pattern", path, position),
        path_glob=path_glob,
        reason=_require_str(entry, "reason", path, position),
        matcher=glob_to_regex(path_glob),
    )


def load_exemptions(path: Path) -> ExemptionSet:
    """Load and validate the reviewed exemption file.

    A missing or malformed file is an error, never an empty exemption set:
    silently scanning with zero entries would report every build artifact as a
    violation and train the next reader to ignore the gate.
    """
    if not path.is_file():
        raise IgnoredSourceGateError(
            f"Ignored-source exemption file not found at {path}. Expected a JSON object "
            f'{{"exemptions": [...]}}. Restore it from version '
            f"control; the gate cannot distinguish deliberate build output without it."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IgnoredSourceGateError(f"Exemption file at {path} is unreadable: {exc}") from exc

    raw_entries = data.get("exemptions")
    if not isinstance(raw_entries, list):
        raise IgnoredSourceGateError(
            f"Exemption file at {path} has no 'exemptions' list. Expected a JSON array of "
            f"entry objects (an empty array is legal and means nothing is excused)."
        )
    entries = tuple(
        _parse_entry(entry, path, position) for position, entry in enumerate(raw_entries, start=1)
    )
    index: dict[tuple[str, str], list[Exemption]] = {}
    for entry in entries:
        index.setdefault((entry.gitignore, entry.pattern), []).append(entry)
    return ExemptionSet(
        entries=entries, index={key: tuple(value) for key, value in index.items()}
    )


def run_git(repo_path: Path, args: list[str], stdin_data: bytes | None = None) -> bytes:
    """Run a read-only git command in `repo_path` and return raw stdout.

    Bytes, not text: paths are NUL-separated and may hold any byte a filesystem
    accepts, and decoding early would corrupt exactly the unusual filename most
    likely to be silently dropped.
    """
    result = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        capture_output=True,
        input=stdin_data,
        check=False,
    )
    if result.returncode not in (0, 1):
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise IgnoredSourceGateError(
            f"git {' '.join(args)} failed in {repo_path.name} ({result.returncode}): {detail}"
        )
    return result.stdout


def _split_nul(raw: bytes) -> list[str]:
    """Split NUL-terminated git output into fields, dropping the trailing empty."""
    fields = raw.decode("utf-8", errors="surrogateescape").split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    return fields


def ignored_paths(repo_path: Path) -> list[str]:
    """Every working-tree path in `repo_path` that `git add -A` would NOT stage.

    This is the set difference itself, computed by git: tracked files are always
    staged, untracked-but-not-ignored files are staged by `-A`, and what remains
    is exactly the ignored remainder. Directories are NOT collapsed -- the
    comparison is at file granularity, so a source file inside a shadowed
    directory is an element of the result rather than a detail hidden behind a
    directory entry.
    """
    return _split_nul(run_git(repo_path, ["ls-files", "-o", "-i", "--exclude-standard", "-z"]))


def attribute_rules(repo_path: Path, paths: list[str]) -> list[ShadowedPath]:
    """Ask git which `.gitignore` line is responsible for each path.

    `--non-matching` makes every input produce a record, so a path git refuses
    to stage but attributes to no rule is visible rather than absent; it is
    reported with a placeholder rule and can never match an exemption.
    """
    if not paths:
        return []
    stdin_data = ("\0".join(paths) + "\0").encode("utf-8", errors="surrogateescape")
    fields = _split_nul(
        run_git(repo_path, ["check-ignore", "-v", "--non-matching", "-z", "--stdin"], stdin_data)
    )
    if len(fields) % CHECK_IGNORE_FIELDS != 0:
        raise IgnoredSourceGateError(
            f"git check-ignore returned {len(fields)} field(s) in {repo_path.name}, which is "
            f"not a multiple of {CHECK_IGNORE_FIELDS}. The gate cannot attribute rules to "
            f"paths from a truncated response and refuses to report a partial result."
        )
    records = [
        fields[start : start + CHECK_IGNORE_FIELDS]
        for start in range(0, len(fields), CHECK_IGNORE_FIELDS)
    ]
    if len(records) != len(paths):
        raise IgnoredSourceGateError(
            f"git check-ignore attributed {len(records)} of {len(paths)} path(s) in "
            f"{repo_path.name}. Every unstaged path must be attributed; a partial "
            f"attribution would hide the unattributed remainder."
        )
    return [_to_shadowed(repo_path.name, record) for record in records]


def _to_shadowed(repo_name: str, record: list[str]) -> ShadowedPath:
    """Turn one `git check-ignore -v -z` record into a ShadowedPath."""
    source, line_text, pattern, path = record
    if not source or not line_text.isdigit():
        rule = IgnoreRule(gitignore=UNATTRIBUTED_SOURCE, line=0, pattern=UNATTRIBUTED_PATTERN)
    else:
        rule = IgnoreRule(gitignore=source, line=int(line_text), pattern=pattern)
    return ShadowedPath(repo=repo_name, path=path, rule=rule)


def stray_temp_dir_of(path: str, temp_dir_segment: TempDirSegmentFn) -> str | None:
    """The repo-relative temp directory containing *path*, or None.

    Only DIRECTORY segments are consulted: a file whose own name happens to be
    ``tmp`` is a file, and this classification is about where a path lives.
    The result is the prefix up to and including the temp segment, so every
    file under one stray directory folds into one finding.
    """
    segments = path.split("/")
    directories = segments[:-1]
    hit = temp_dir_segment(directories)
    if hit is None:
        return None
    return "/".join(directories[: directories.index(hit) + 1])


def scan_repo(
    repo_path: Path,
    exemptions: ExemptionSet,
    used: set[str],
    temp_dir_segment: TempDirSegmentFn,
) -> RepoResult:
    """Compute one repo's shadowed set and split it three ways.

    A path inside a temp directory is folded into a stray-directory finding
    BEFORE the exemption lookup: it is neither a violation (its contents are
    not source) nor something an exemption may excuse (the directory should
    not exist). Everything else is exempt or violating, as before.
    """
    shadowed = attribute_rules(repo_path, ignored_paths(repo_path))
    violations: list[ShadowedPath] = []
    stray_counts: dict[str, int] = {}
    exempt_total = 0
    for candidate in shadowed:
        stray = stray_temp_dir_of(candidate.path, temp_dir_segment)
        if stray is not None:
            stray_counts[stray] = stray_counts.get(stray, 0) + 1
            continue
        entry = exemptions.covering(candidate)
        if entry is None:
            violations.append(candidate)
            continue
        exempt_total += 1
        used.add(entry.render())
    return RepoResult(
        repo=repo_path.name,
        shadowed_total=len(shadowed),
        exempt_total=exempt_total,
        violations=tuple(violations),
        stray_temp_dirs=tuple(
            StrayTempDir(repo=repo_path.name, relpath=relpath, file_count=count)
            for relpath, count in sorted(stray_counts.items())
        ),
    )


def scan_for_commit(
    repo_path: Path, exemptions: ExemptionSet, temp_dir_segment: TempDirSegmentFn
) -> RepoResult:
    """One repo's census for a caller outside this gate.

    The entry point for the commit seam in ``git/commit-and-push.py``, which
    asks the question per dirty repo rather than across the whole workspace.
    Exemption-usage bookkeeping is a reporting concern of the standalone gate,
    so it is discarded here rather than pushed onto every caller; the stray
    temp directories travel with the violations because the caller reports
    them differently (a warning with a delete command versus a refusal).
    """
    return scan_repo(repo_path, exemptions, set(), temp_dir_segment)


def group_by_rule(violations: tuple[ShadowedPath, ...]) -> dict[IgnoreRule, list[str]]:
    """Group a repo's violations by the `.gitignore` line responsible."""
    grouped: dict[IgnoreRule, list[str]] = {}
    for violation in violations:
        grouped.setdefault(violation.rule, []).append(violation.path)
    return grouped


def report_repo(result: RepoResult) -> None:
    """Print one repo's violations, rule by rule, with the paths each one hides."""
    print(f"\n  {result.repo}:")
    for rule, paths in group_by_rule(result.violations).items():
        print(f"    {rule.render()}  -- shadows {len(paths)} publishable file(s):")
        for path in sorted(paths)[:MAX_REPORTED_PATHS]:
            print(f"      {path}")
        if len(paths) > MAX_REPORTED_PATHS:
            print(f"      ... and {len(paths) - MAX_REPORTED_PATHS} more")


def report_stray_temp_dirs(results: list[RepoResult], repo_paths: dict[str, Path]) -> None:
    """Warn once per stray temp directory, with the command that removes it.

    Reported, never failed: the contents are already unpublishable, so a clone
    loses nothing. What is wrong is that the directory exists inside a repo at
    all, and the fix for that is deletion -- not an ignore-rule edit and not an
    exemption entry, which is why these never reach the violation report.
    """
    strays = [stray for result in results for stray in result.stray_temp_dirs]
    if not strays:
        return
    print(
        f"\n  WARNING: {len(strays)} stray temp director(ies) inside package repos. Temp "
        f"output belongs under D:\\datrix\\.tmp, .scripts or .test-output -- never inside "
        f"a repo. Not shadowed source and not exemptable; delete them:"
    )
    for stray in strays:
        print(f"    {stray.render(repo_paths[stray.repo])}")


def report_unused(exemptions: ExemptionSet, used: set[str]) -> None:
    """Name entries that matched nothing on this machine.

    Reported, never failed: an entry covers output a tool writes only when it
    has run (a coverage report, an npm install), so its absence is normal on a
    clean checkout and is not evidence the entry is stale.
    """
    unused = [entry for entry in exemptions.entries if entry.render() not in used]
    if not unused:
        return
    print(f"\n  {len(unused)} exemption entr(ies) matched nothing in this working tree:")
    for entry in unused:
        print(f"    {entry.render()}")


def resolve_repos(workspace_root: Path, wanted: list[str] | None) -> list[Path]:
    """Return the repos to scan, raising when a requested name does not exist."""
    repos = framework_repos(workspace_root)
    if not repos:
        raise IgnoredSourceGateError(
            f"No framework repo found under {workspace_root}. Expected the datrix showcase "
            f"repo and its datrix-* siblings, each a git checkout."
        )
    if wanted is None:
        return repos
    selected = [repo for repo in repos if repo.name in set(wanted)]
    missing = sorted(set(wanted) - {repo.name for repo in selected})
    if missing:
        raise IgnoredSourceGateError(
            f"No framework repo named {', '.join(missing)} under {workspace_root}. "
            f"Known: {', '.join(repo.name for repo in repos)}"
        )
    return selected


# --------------------------------------------------------------------------
# Self-test: the gate proves it can still see a shadowed file before it is
# believed about anything. A scan that can only return zero is not evidence --
# that is precisely how the defect this gate exists to prevent survived.
# --------------------------------------------------------------------------

SELF_TEST_IGNORE_LINES = ("__pycache__/", "build/", "MANIFEST", ".test-output/")

# Planted tree for the main self-test repo. Each entry is a repo-relative path
# and what the gate must conclude about it.
SELF_TEST_SHADOWED_BY_MANIFEST = "src/pkg/templates/MANIFEST/entry.j2"
SELF_TEST_SHADOWED_BY_NESTED_BUILD = "src/pkg/templates/build/template.j2"
SELF_TEST_EXEMPT_PYCACHE = "src/pkg/__pycache__/module.pyc"
SELF_TEST_EXEMPT_ROOT_BUILD = "build/lib/artifact.txt"
SELF_TEST_PUBLISHED = "src/pkg/keep.py"
# A stray temp directory: source-shaped files an ignore backstop hides. Two files
# in two different subtrees, so the finding provably folds the whole tree into
# the one temp directory (not its children) with a count.
SELF_TEST_STRAY_TEMP_DIR = ".test-output"
SELF_TEST_STRAY_TEMP_FILES = (
    f"{SELF_TEST_STRAY_TEMP_DIR}/leftover-run/svc/src/main.py",
    f"{SELF_TEST_STRAY_TEMP_DIR}/second-run/svc/sql/schema.sql",
)

SELF_TEST_PLANTED = (
    SELF_TEST_SHADOWED_BY_MANIFEST,
    SELF_TEST_SHADOWED_BY_NESTED_BUILD,
    SELF_TEST_EXEMPT_PYCACHE,
    SELF_TEST_EXEMPT_ROOT_BUILD,
    SELF_TEST_PUBLISHED,
    *SELF_TEST_STRAY_TEMP_FILES,
)


def _make_repo(root: Path, ignore_lines: tuple[str, ...], relpaths: tuple[str, ...]) -> None:
    """Create a real git repo with a real `.gitignore` and real planted files."""
    subprocess.run(["git", "init", "-q", str(root)], capture_output=True, check=True)
    (root / ".gitignore").write_text("\n".join(ignore_lines) + "\n", encoding="utf-8")
    for relpath in relpaths:
        target = root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("planted by the ignored-source gate self-test\n", encoding="utf-8")


def _by_path(shadowed: list[ShadowedPath]) -> dict[str, ShadowedPath]:
    return {entry.path: entry for entry in shadowed}


def _check_glob_semantics() -> list[str]:
    """The scope matcher must be segment-aware, or every exemption is a blanket."""
    cases: tuple[tuple[str, str, bool], ...] = (
        ("**/__pycache__/**", "src/pkg/__pycache__/m.pyc", True),
        ("**/__pycache__/**", "__pycache__/m.pyc", True),
        ("**/__pycache__/**", "src/pkg/__pycache__x/m.pyc", False),
        ("build/**", "build/lib/x.txt", True),
        ("build/**", "src/pkg/templates/build/x.j2", False),
        ("*.log", "crash.log", True),
        ("*.log", "logs/crash.log", False),
        ("tests/**/.datrix/**", "tests/fixtures/.datrix/schema.json", True),
        ("tests/**/.datrix/**", "src/.datrix/schema.json", False),
    )
    failures: list[str] = []
    for path_glob, candidate, expected in cases:
        actual = glob_to_regex(path_glob).fullmatch(candidate) is not None
        if actual is not expected:
            failures.append(
                f"self-test: scope glob {path_glob!r} vs {candidate!r} returned "
                f"{actual}, expected {expected}"
            )
    return failures


def _check_planted_detection(repo: Path, exemptions: ExemptionSet) -> list[str]:
    """The load-bearing half: a planted shadowed source file must be caught."""
    failures: list[str] = []
    found = _by_path(attribute_rules(repo, ignored_paths(repo)))

    if SELF_TEST_PUBLISHED in found:
        failures.append("self-test: a publishable file was reported as shadowed")

    planted = found.get(SELF_TEST_SHADOWED_BY_MANIFEST)
    if planted is None:
        failures.append(
            "self-test: an unanchored MANIFEST rule shadowing a template file was NOT detected"
        )
        return failures
    if planted.rule.pattern != "MANIFEST" or planted.rule.gitignore != ".gitignore":
        failures.append(
            f"self-test: the planted file was blamed on {planted.rule.render()}, "
            f"expected .gitignore:{SELF_TEST_IGNORE_LINES.index('MANIFEST') + 1}: MANIFEST"
        )
    if planted.rule.line != SELF_TEST_IGNORE_LINES.index("MANIFEST") + 1:
        failures.append(
            f"self-test: the planted file was blamed on line {planted.rule.line}, expected "
            f"{SELF_TEST_IGNORE_LINES.index('MANIFEST') + 1}"
        )
    if exemptions.covering(planted) is not None:
        failures.append("self-test: a shadowed source file was excused by an exemption entry")
    return failures


def _check_exemption_scope(repo: Path, exemptions: ExemptionSet) -> list[str]:
    """Deliberate build output is excused; the same rule out of scope is not."""
    failures: list[str] = []
    found = _by_path(attribute_rules(repo, ignored_paths(repo)))
    expectations: tuple[tuple[str, bool, str], ...] = (
        (SELF_TEST_EXEMPT_PYCACHE, True, "a bytecode cache was not excused by its entry"),
        (SELF_TEST_EXEMPT_ROOT_BUILD, True, "the root build tree was not excused by its entry"),
        (
            SELF_TEST_SHADOWED_BY_NESTED_BUILD,
            False,
            "a root-scoped build/ entry excused a nested templates/build/ directory",
        ),
    )
    for relpath, should_be_exempt, message in expectations:
        candidate = found.get(relpath)
        if candidate is None:
            failures.append(f"self-test: planted path {relpath} never reached the scanner")
            continue
        is_exempt = exemptions.covering(candidate) is not None
        if is_exempt is not should_be_exempt:
            failures.append(f"self-test: {message}")
    empty = ExemptionSet(entries=(), index={})
    cached = found.get(SELF_TEST_EXEMPT_PYCACHE)
    if cached is not None and empty.covering(cached) is not None:
        failures.append("self-test: an empty exemption set excused a shadowed path")
    return failures


def _check_stray_temp_classification(
    repo: Path, exemptions: ExemptionSet, temp_dir_segment: TempDirSegmentFn
) -> list[str]:
    """A temp directory is one stray finding, never a violation, never exempt.

    Also the non-vacuity half for the shared name list: if the hook's module
    stopped naming ``.test-output``, the planted tree would surface as two
    violations and this check would say so.
    """
    failures: list[str] = []
    result = scan_repo(repo, exemptions, set(), temp_dir_segment)
    violating_paths = {violation.path for violation in result.violations}
    for relpath in SELF_TEST_STRAY_TEMP_FILES:
        if relpath in violating_paths:
            failures.append(
                f"self-test: {relpath} inside a planted temp directory was reported as "
                f"shadowed source instead of a stray temp directory"
            )
    strays = {stray.relpath: stray for stray in result.stray_temp_dirs}
    stray = strays.get(SELF_TEST_STRAY_TEMP_DIR)
    if stray is None:
        failures.append(
            f"self-test: planted temp directory {SELF_TEST_STRAY_TEMP_DIR} was NOT reported "
            f"as stray (found: {sorted(strays) or 'none'})"
        )
        return failures
    if stray.file_count != len(SELF_TEST_STRAY_TEMP_FILES):
        failures.append(
            f"self-test: stray directory {SELF_TEST_STRAY_TEMP_DIR} counted "
            f"{stray.file_count} file(s), expected {len(SELF_TEST_STRAY_TEMP_FILES)}"
        )
    if SELF_TEST_SHADOWED_BY_MANIFEST not in violating_paths:
        failures.append(
            "self-test: stray-directory folding swallowed a shadowed source finding "
            f"({SELF_TEST_SHADOWED_BY_MANIFEST})"
        )
    delete_hint = stray.render(repo)
    if "Remove-Item" not in delete_hint or SELF_TEST_STRAY_TEMP_DIR.split("/")[0] not in delete_hint:
        failures.append(f"self-test: the stray-directory report carries no delete command: {delete_hint}")
    return failures


def _check_git_semantics(root: Path) -> list[str]:
    """Negation and case-folding are git's to decide, and must be honoured."""
    failures: list[str] = []
    repo = root / "negation"
    _make_repo(repo, ("*.j2", "!src/keep.j2"), ("src/keep.j2", "src/drop.j2"))
    found = _by_path(attribute_rules(repo, ignored_paths(repo)))
    if "src/keep.j2" in found:
        failures.append("self-test: a re-included (!) path was reported as shadowed")
    if "src/drop.j2" not in found:
        failures.append("self-test: an ignored path was missed in a repo using negation")

    folded = root / "casefold"
    _make_repo(folded, ("MANIFEST",), ("src/pkg/templates/manifest/lower.j2",))
    ignorecase = (
        run_git(folded, ["config", "--get", "core.ignorecase"]).decode("utf-8").strip() == "true"
    )
    detected = "src/pkg/templates/manifest/lower.j2" in _by_path(
        attribute_rules(folded, ignored_paths(folded))
    )
    if detected is not ignorecase:
        failures.append(
            f"self-test: with core.ignorecase={ignorecase}, a lowercase 'manifest' directory "
            f"under an uppercase MANIFEST rule reported detected={detected}"
        )
    return failures


def self_test(exemptions: ExemptionSet, temp_dir_segment: TempDirSegmentFn) -> list[str]:
    """Prove the gate is non-vacuous. Returns a list of failure descriptions.

    Runs before every real scan. A scanner that silently stopped scanning
    reports a clean tree, which is indistinguishable from a clean tree.
    """
    failures = _check_glob_semantics()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        main_repo = root / "package"
        _make_repo(main_repo, SELF_TEST_IGNORE_LINES, SELF_TEST_PLANTED)
        failures.extend(_check_planted_detection(main_repo, exemptions))
        failures.extend(_check_exemption_scope(main_repo, exemptions))
        failures.extend(_check_stray_temp_classification(main_repo, exemptions, temp_dir_segment))
        failures.extend(_check_git_semantics(root))
    return failures


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        action="append",
        default=None,
        help="Limit the scan to this repo name (repeatable). Default: every framework repo.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip the real scan.",
    )
    parser.add_argument(
        "--show-exempt",
        action="store_true",
        help="Also print every reviewed exemption entry and its written reason.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    return parser.parse_args(argv)


def print_exemptions(exemptions: ExemptionSet) -> None:
    """Print the reviewed entry list with each entry's written reason."""
    print(f"\nReviewed exemption entries ({len(exemptions.entries)}):")
    for entry in exemptions.entries:
        print(f"  {entry.render()}")
        print(f"      {entry.reason}")


def run_scan(
    repos: list[Path], exemptions: ExemptionSet, temp_dir_segment: TempDirSegmentFn
) -> int:
    """Scan every repo, print the census, and return the process exit code."""
    print(
        f"Comparing working tree against what 'git add -A' would stage in "
        f"{len(repos)} repo(s), with {len(exemptions.entries)} reviewed exemption entr(ies)"
    )
    used: set[str] = set()
    results = [scan_repo(repo, exemptions, used, temp_dir_segment) for repo in repos]
    for result in results:
        stray_files = sum(stray.file_count for stray in result.stray_temp_dirs)
        print(
            f"  {result.repo}: {result.shadowed_total} unstaged path(s), "
            f"{result.exempt_total} exempt, {stray_files} in stray temp dir(s), "
            f"{len(result.violations)} shadowed"
        )
    report_stray_temp_dirs(results, {repo.name: repo for repo in repos})
    report_unused(exemptions, used)

    violating = [result for result in results if result.violations]
    if not violating:
        print(
            "\nIGNORED-SOURCE GATE PASSED: every working-tree path git refuses to stage is a "
            "reviewed exemption."
        )
        return 0

    total = sum(len(result.violations) for result in violating)
    print(
        f"\nIGNORED-SOURCE GATE FAILED: {total} publishable file(s) in "
        f"{len(violating)} repo(s) would not survive a clone. Fix the named .gitignore line "
        f"-- anchor the pattern to the repo root ('/PATTERN') or narrow it -- or, if the "
        f"output is deliberately unpublished, add a scoped entry with a written reason to "
        f"{exemption_path(DATRIX_ROOT)}."
    )
    for result in violating:
        report_repo(result)
    return 1


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    workspace_root = DATRIX_ROOT.parent

    try:
        exemptions = load_exemptions(exemption_path(DATRIX_ROOT))
        temp_dir_segment = load_temp_dir_segment(DATRIX_ROOT)
    except IgnoredSourceGateError as exc:
        print(f"IGNORED-SOURCE GATE CANNOT RUN: {exc}", file=sys.stderr)
        return 2

    logger.debug("loaded %d exemption entrie(s)", len(exemptions.entries))
    if args.show_exempt:
        print_exemptions(exemptions)

    try:
        failures = self_test(exemptions, temp_dir_segment)
    except IgnoredSourceGateError as exc:
        print(f"IGNORED-SOURCE GATE CANNOT RUN: self-test could not execute: {exc}", file=sys.stderr)
        return 2
    if failures:
        print("IGNORED-SOURCE GATE CANNOT BE TRUSTED: non-vacuity self-test failed.")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("Self-test passed: the scanner still detects a planted shadowed source file.")

    if args.self_test:
        return 0

    try:
        repos = resolve_repos(workspace_root, args.repo)
        return run_scan(repos, exemptions, temp_dir_segment)
    except IgnoredSourceGateError as exc:
        print(f"IGNORED-SOURCE GATE CANNOT RUN: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
