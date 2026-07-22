"""Reference-example parity gate: the repo's proof that generated output is stable.

WHAT THIS GATE PROTECTS
-----------------------
For every reference example under ``datrix/examples/`` this gate runs the REAL
generation pipeline (``datrix_cli.pipeline.generation.GenerationPipeline`` -- the
exact code path ``generate.ps1`` runs, with the same ``PipelineConfig`` defaults)
and compares a per-file sha256 manifest of the whole generated tree against a
stored baseline.  Any byte that changes in any generated file, and any file that
appears or disappears, fails the gate.

It is the only automated proof behind the "generated output is byte-identical"
acceptance property that refactors in this repo routinely claim.

WHY THE PIPELINE, NOT A FIXTURE PATH
------------------------------------
The previous incarnation of this gate lived as a pytest module in
``datrix-codegen-common`` and synthesized an ``Application`` + ``CodegenContext``
by hand (``parse_fixture_with_semantics`` + ``attach_default_configs`` +
``make_test_context``).  That path is NOT the generator: it skips ConfigDSL
resolution, ``DeploymentPlan.resolve()``, ``build_runtime_bootstrap()``, the
secret-backend policy, the connection surfaces, the companion generators
(sql/component/platform) and the post-generation language hooks (ruff import-fix
and formatting).  It drifted from the pipeline and eventually could not generate
at all (``CodegenContext.runtime_bootstrap is not populated``), which is why the
gate was disabled rather than re-blessed.  A hand-rolled replica of the pipeline
will drift again; calling the pipeline cannot.

``datrix_codegen_common`` may not import ``datrix_cli`` (an import-boundary rule
that applies to its tests too), so the gate lives here, as a repo-level
validation script -- the same shape as ``typescript-whole-system-gate.ps1`` and
``check-generated-file-ratchet.ps1``.

ONE LANGUAGE PER EXAMPLE -- NOT A LANGUAGE MATRIX
-------------------------------------------------
The real generator reads the target language from each project's
``config/system.dcfg``; ``generate.ps1``'s ``-L`` flag only labels the output
path (see ``scripts/library/dev/generate.py``).  There is therefore exactly one
generated output per example, in one language.  The old gate forced every example
through every installed language generator; that synthetic matrix is unreachable
from any supported user flow, and it is what produced its 28-entry TypeScript
"known non-generating" allowlist.  This gate generates each example exactly once,
the way the generator does.

FAILURE OUTPUT
--------------
A failure lists EVERY changed / added / removed path (not "the first divergent
file"), and -- when a local baseline cache from the last bless is present and
still matches the committed baseline -- a real unified diff of each changed file.
The freshly generated tree is left on disk and its path is printed.

RE-BLESSING
-----------
``regen-parity-baselines.ps1 [-Example <relpath>]`` is the ONLY writer.  Baselines
are per-example, so an intentional change to one example re-blesses one example.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import logging
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# --- Roots -----------------------------------------------------------------
# This file: datrix/scripts/library/test/reference_example_parity.py
# parents[3] -> datrix/ ; parents[4] -> the monorepo root.
_HERE = Path(__file__).resolve()
DATRIX_DIR: Path = _HERE.parents[3]
WORKSPACE_ROOT: Path = _HERE.parents[4]

EXAMPLES_ROOT: Path = DATRIX_DIR / "examples"
BASELINES_ROOT: Path = DATRIX_DIR / "scripts" / "config" / "parity-baselines"
KNOWN_NON_GENERATING_PATH: Path = (
    DATRIX_DIR / "scripts" / "config" / "parity-known-nongenerating.json"
)

#: Full generated trees kept from the last bless, so a failing gate can show a
#: real unified diff. Scratch output (CLAUDE.md temp-output policy).
CACHE_ROOT: Path = WORKSPACE_ROOT / ".test-output" / "parity-baseline-cache"

#: Where the gate generates the current output. Left on disk after a failure so
#: the changed files can be read directly.
SCRATCH_ROOT: Path = WORKSPACE_ROOT / ".test-output" / "parity-current"

#: Config profile the gate generates under -- ``datrix generate``'s own default
#: (see scripts/library/dev/generate.py::_active_profile).
PROFILE: str = "test"

#: Directories excluded from the manifest: post-generation build/install
#: artifacts, not generated source. Same exclusion set as
#: typescript-whole-system-gate.ps1.
EXCLUDED_DIRS: frozenset[str] = frozenset(
    {".datrix", ".ruff_cache", ".tsc_cache", "node_modules", "__pycache__"}
)

#: sha256sum convention: "<path><2 spaces><hex>".
_SEP = "  "

#: Caps so one huge change cannot bury the report.
_MAX_DIFFED_FILES = 10
_MAX_DIFF_LINES_PER_FILE = 60
_MAX_LISTED_PATHS = 40

#: Example used by the always-on non-vacuity self-test (the smallest real one).
SELF_TEST_EXAMPLE: str = "01-foundation"

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


# ---------------------------------------------------------------------------
# Examples
# ---------------------------------------------------------------------------


def example_id(system_dtrx: Path) -> str:
    """Return the deterministic id of an example from its ``system.dtrx`` path.

    Args:
        system_dtrx: Absolute path to a ``system.dtrx`` under ``EXAMPLES_ROOT``.

    Returns:
        The example directory's path relative to ``EXAMPLES_ROOT`` with separators
        replaced by ``-`` (e.g. ``02-features-03-infrastructure-blocks-jobs``).
    """
    return "-".join(system_dtrx.parent.relative_to(EXAMPLES_ROOT).parts)


def example_relpath(system_dtrx: Path) -> str:
    """Return the example's posix path relative to ``EXAMPLES_ROOT``.

    This is the value ``regen-parity-baselines.ps1 -Example`` takes.

    Args:
        system_dtrx: Absolute path to a ``system.dtrx`` under ``EXAMPLES_ROOT``.

    Returns:
        Posix relative path of the example directory (e.g. ``01-foundation``).
    """
    return system_dtrx.parent.relative_to(EXAMPLES_ROOT).as_posix()


def discover_examples() -> list[Path]:
    """Return every example ``system.dtrx``, sorted.

    Discovery is a glob -- the example count is never hard-coded, so the gate
    stays current as examples are added or removed.

    Returns:
        Sorted absolute paths to every ``system.dtrx`` under ``EXAMPLES_ROOT``.
    """
    return sorted(EXAMPLES_ROOT.rglob("system.dtrx"))


def resolve_language(system_dtrx: Path) -> str:
    """Return the target language the real generator uses for this example.

    Reads the example's ``config/system.dcfg`` for the active profile, exactly as
    the pipeline's ``_build_codegen_context`` does.

    Args:
        system_dtrx: Absolute path to the example's ``system.dtrx``.

    Returns:
        The declared language name (e.g. ``"python"``, ``"typescript"``).

    Raises:
        FileNotFoundError: If the example has no ``config/system.dcfg``.
    """
    from datrix_common.config.unified_loader import load_system_config

    project_dir = system_dtrx.parent
    config_path = project_dir / "config" / "system.dcfg"
    if not config_path.exists():
        raise FileNotFoundError(
            f"Example {example_relpath(system_dtrx)!r} has no config/system.dcfg "
            f"(expected at {config_path}). Every example the generator can build "
            f"declares its language there; add the file or remove the example."
        )
    unified = load_system_config(
        config_path=config_path,
        project_root=project_dir,
        profile=PROFILE,
    )
    return str(unified.system.language.value)


# ---------------------------------------------------------------------------
# Allowlist of examples the real generator cannot build today
# ---------------------------------------------------------------------------


def load_known_non_generating() -> dict[str, str]:
    """Load and validate the known-non-generating allowlist.

    The allowlist converts a genuine, pre-existing generation FAILURE into a
    loudly-reported skip. It never hides a manifest mismatch: a listed example
    that does generate is still hash-compared, and a listed example that has a
    baseline is still expected to match it.

    Returns:
        Mapping of ``example_id`` -> reason string.

    Raises:
        ValueError: If the file is missing, malformed, has an empty reason, or its
            entry count does not match the pinned ``expected_count``.
    """
    if not KNOWN_NON_GENERATING_PATH.exists():
        raise ValueError(
            f"Missing allowlist {KNOWN_NON_GENERATING_PATH}. It pins the examples the "
            f"real generator cannot build today. Restore it from git; the gate never "
            f"creates it."
        )
    data = json.loads(KNOWN_NON_GENERATING_PATH.read_text(encoding="utf-8"))
    examples = data.get("examples")
    expected = data.get("expected_count")
    if not isinstance(examples, dict) or not isinstance(expected, int):
        raise ValueError(
            f"Malformed allowlist {KNOWN_NON_GENERATING_PATH}: expected an object with "
            f"'expected_count' (int) and 'examples' (object of example_id -> reason)."
        )
    for ex_id, reason in examples.items():
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(
                f"Allowlist entry {ex_id!r} has an empty reason. Every entry must state "
                f"the defect and a tracking identifier."
            )
    if len(examples) != expected:
        raise ValueError(
            f"Allowlist {KNOWN_NON_GENERATING_PATH} has {len(examples)} entries but "
            f"'expected_count' is pinned at {expected}. The count is a deliberate, "
            f"reviewed value: update it in the same change that adds or removes an entry."
        )
    return {str(k): str(v) for k, v in examples.items()}


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def build_manifest(tree_root: Path) -> dict[str, str]:
    """Hash every generated file under ``tree_root``.

    Args:
        tree_root: Root of a generated output tree.

    Returns:
        Mapping of posix relative path -> sha256 hex digest, for every file not
        under an :data:`EXCLUDED_DIRS` directory.
    """
    manifest: dict[str, str] = {}
    for path in tree_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(tree_root)
        if EXCLUDED_DIRS.intersection(rel.parts):
            continue
        manifest[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return manifest


def manifest_to_text(manifest: dict[str, str]) -> str:
    """Render a manifest as sorted, newline-terminated ``path<2sp>sha256`` lines.

    Args:
        manifest: Mapping of relative path -> sha256 hex digest.

    Returns:
        Deterministic manifest text.
    """
    lines = [f"{rel}{_SEP}{digest}" for rel, digest in sorted(manifest.items())]
    return "\n".join(lines) + "\n"


def parse_manifest_text(text: str) -> dict[str, str]:
    """Parse manifest text back into a mapping.

    Args:
        text: Contents of a ``.sha256`` baseline file.

    Returns:
        Mapping of relative path -> sha256 hex digest.

    Raises:
        ValueError: On a line that is not ``path<2sp>sha256``.
    """
    manifest: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(_SEP, 1)
        if len(parts) != 2:
            raise ValueError(
                f"Malformed manifest line (expected 'path  sha256hex'): {line!r}"
            )
        manifest[parts[0]] = parts[1]
    return manifest


def baseline_path(ex_id: str, language: str) -> Path:
    """Return the stored baseline path for one example.

    Args:
        ex_id: Example id from :func:`example_id`.
        language: The example's declared language.

    Returns:
        Absolute path of the ``.sha256`` baseline file.
    """
    return BASELINES_ROOT / ex_id / f"{language}.sha256"


@dataclass(frozen=True)
class ManifestDiff:
    """The delta between a stored baseline manifest and a computed one."""

    changed: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Whether the two manifests are identical."""
        return not (self.changed or self.added or self.removed)


def diff_manifests(stored: dict[str, str], computed: dict[str, str]) -> ManifestDiff:
    """Compare a stored baseline manifest against a freshly computed one.

    Args:
        stored: The committed baseline manifest.
        computed: The manifest of the current generated tree.

    Returns:
        A :class:`ManifestDiff` naming every changed, added, and removed path.
    """
    stored_paths = set(stored)
    computed_paths = set(computed)
    return ManifestDiff(
        changed=sorted(
            p for p in stored_paths & computed_paths if stored[p] != computed[p]
        ),
        added=sorted(computed_paths - stored_paths),
        removed=sorted(stored_paths - computed_paths),
    )


# ---------------------------------------------------------------------------
# Failure rendering
# ---------------------------------------------------------------------------


def _read_lines_for_diff(path: Path) -> list[str] | None:
    """Return a file's lines for diffing, or ``None`` when it is not UTF-8 text.

    Args:
        path: File to read.

    Returns:
        Line list (keeping line endings), or ``None`` for binary content.
    """
    try:
        return path.read_text(encoding="utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return None


def render_unified_diff(rel: str, old_tree: Path, new_tree: Path) -> list[str]:
    """Render a capped unified diff of one file between two generated trees.

    Args:
        rel: Posix relative path of the file.
        old_tree: Root of the baseline-era tree (the local bless cache).
        new_tree: Root of the freshly generated tree.

    Returns:
        Indented lines of the rendered diff.
    """
    old_lines = _read_lines_for_diff(old_tree / rel)
    new_lines = _read_lines_for_diff(new_tree / rel)
    if old_lines is None or new_lines is None:
        return ["      (binary file -- content diff not shown)"]
    diff = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"baseline/{rel}",
            tofile=f"current/{rel}",
            lineterm="",
            n=2,
        )
    )
    rendered = [f"      {line.rstrip()}" for line in diff[:_MAX_DIFF_LINES_PER_FILE]]
    if len(diff) > _MAX_DIFF_LINES_PER_FILE:
        rendered.append(
            f"      ... ({len(diff) - _MAX_DIFF_LINES_PER_FILE} more diff lines)"
        )
    return rendered


def usable_cache_tree(ex_id: str, stored: dict[str, str]) -> Path | None:
    """Return the local bless-cache tree when it still matches the baseline.

    A cache written by an older bless would render a misleading diff, so it is
    used only when its own manifest equals the committed baseline exactly.

    Args:
        ex_id: Example id.
        stored: The committed baseline manifest.

    Returns:
        The cached tree root, or ``None`` when absent or stale.
    """
    cached_tree = CACHE_ROOT / ex_id
    if not cached_tree.is_dir():
        return None
    if build_manifest(cached_tree) != stored:
        logger.debug("parity_cache_stale example=%s", ex_id)
        return None
    return cached_tree


def _render_path_list(title: str, paths: list[str]) -> list[str]:
    """Render a capped, titled list of relative paths.

    Args:
        title: Section heading.
        paths: Relative paths to list.

    Returns:
        Report lines (empty when ``paths`` is empty).
    """
    if not paths:
        return []
    lines = [f"    {title} ({len(paths)}):"]
    lines.extend(f"      {p}" for p in paths[:_MAX_LISTED_PATHS])
    if len(paths) > _MAX_LISTED_PATHS:
        lines.append(f"      ... ({len(paths) - _MAX_LISTED_PATHS} more)")
    return lines


def render_failure(
    ex_id: str,
    rel_example: str,
    delta: ManifestDiff,
    stored: dict[str, str],
    new_tree: Path,
) -> str:
    """Build the human-readable failure report for one drifted example.

    Args:
        ex_id: Example id.
        rel_example: The example's path relative to ``datrix/examples/``.
        delta: The manifest delta.
        stored: The committed baseline manifest (used to validate the diff cache).
        new_tree: Root of the freshly generated tree (left on disk).

    Returns:
        A multi-line report naming every drifted path, with unified diffs when a
        valid local bless cache is available.
    """
    lines: list[str] = [
        f"  PARITY DRIFT  example={rel_example}",
        f"    changed={len(delta.changed)} added={len(delta.added)} "
        f"removed={len(delta.removed)}",
    ]
    lines.extend(_render_path_list("CHANGED", delta.changed))
    lines.extend(_render_path_list("ADDED (new in output, not in baseline)", delta.added))
    lines.extend(
        _render_path_list("REMOVED (in baseline, no longer generated)", delta.removed)
    )

    cache_tree = usable_cache_tree(ex_id, stored)
    if cache_tree is None:
        lines.append(
            "    Content diff unavailable: no local baseline cache for this example "
            "(it is written by regen-parity-baselines.ps1, and is discarded when "
            ".test-output is cleaned). The freshly generated tree is on disk -- open "
            "the CHANGED paths below it to read the new content."
        )
    elif delta.changed:
        shown = delta.changed[:_MAX_DIFFED_FILES]
        lines.append(f"    CONTENT DIFF (baseline -> current), first {len(shown)}:")
        for rel in shown:
            lines.extend(render_unified_diff(rel, cache_tree, new_tree))
        if len(delta.changed) > _MAX_DIFFED_FILES:
            lines.append(
                f"    ... ({len(delta.changed) - _MAX_DIFFED_FILES} more changed files "
                f"not diffed; see the full CHANGED list above)"
            )

    lines.append(f"    Current output: {new_tree}")
    lines.append(
        "    If this change is intentional and reviewed, re-bless THIS example only:"
    )
    lines.append(
        f'      powershell -File "d:/datrix/datrix/scripts/test/regen-parity-baselines.ps1" '
        f'-Example "{rel_example}"'
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


#: A language's post-generation hooks shell out to formatters/import-fixers
#: (resolved with ``shutil.which``). When such a tool is absent the hook does not
#: fail -- it records a warning and leaves the files unprocessed, which SILENTLY
#: CHANGES THE GENERATED BYTES. A baseline blessed in that environment would be
#: wrong, and the gate would be flaky against a complete environment. Any warning
#: carrying this marker is therefore a hard error here. This keys off the hooks'
#: warning contract, not off any particular language or tool name.
_TOOL_MISSING_MARKER = "not found on PATH"


def _assert_generation_environment_complete(warnings: list[str]) -> None:
    """Fail loud when a post-generation tool was missing from the environment.

    Args:
        warnings: The pipeline's warnings for one generation run.

    Raises:
        RuntimeError: If any warning reports a post-processing tool that could not
            be resolved on PATH.
    """
    missing = [w for w in warnings if _TOOL_MISSING_MARKER in w]
    if not missing:
        return
    raise RuntimeError(
        "Incomplete generation environment -- a post-generation tool was not on PATH, "
        "so the generated files were left unformatted / with unfixed imports. Their "
        "bytes do not match what the real generator produces, so they must never be "
        "compared or blessed.\n  "
        + "\n  ".join(missing)
        + "\n  Fix: run this gate through its .ps1 wrapper (it activates D:/datrix/.venv, "
        "which puts the tools on PATH), or activate the venv before invoking the engine "
        "directly."
    )


def generate_example(system_dtrx: Path, output_dir: Path) -> None:
    """Generate one example into ``output_dir`` via the REAL pipeline.

    Uses ``GenerationPipeline`` with ``PipelineConfig``'s defaults, which are the
    defaults ``datrix generate`` itself passes (profile=test, format_output=True,
    validation_level=STANDARD, no incremental, no migrations). The output dir is
    cleared first so generation always starts from a clean tree.

    Args:
        system_dtrx: Absolute path to the example's ``system.dtrx``.
        output_dir: Directory to generate into (created/cleared).

    Raises:
        RuntimeError: If the pipeline reports failure, or if a post-generation tool
            was missing from the environment (which would change the output bytes).
    """
    from datrix_cli.pipeline.generation import GenerationPipeline, PipelineConfig

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    result = GenerationPipeline().run(
        system_dtrx,
        output_dir,
        PipelineConfig(profile=PROFILE),
    )
    if not result.success:
        raise RuntimeError("; ".join(result.errors) or "pipeline reported success=False")
    _assert_generation_environment_complete(result.warnings)


def _register_language_plugins() -> None:
    """Register the parser + stdlib parser, exactly as ``datrix_cli.main`` does.

    ``datrix-common`` declares parser protocols; ``datrix-language`` implements
    them and the CLI wires them at startup. A script that drives the pipeline
    directly must do the same wiring or every parse raises ``StdlibLoadError``.
    """
    from datrix_language.registration import register_all

    register_all()


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def run_self_test(generated_tree: Path) -> list[str]:
    """Prove the comparator detects a real change in real generated output.

    A gate that cannot fail is worse than no gate. This runs on every CHECK: it
    copies a genuinely generated tree, mutates ONE byte of ONE file, and requires
    that the manifest comparison reports exactly that path as CHANGED and that a
    unified diff is rendered for it. If the comparator does not bite, the gate
    exits non-zero regardless of how the examples compare.

    Args:
        generated_tree: A real generated output tree (from the gate's own run).

    Returns:
        A list of failure descriptions -- empty means the comparator is sound.
    """
    problems: list[str] = []
    mutant_tree = SCRATCH_ROOT / "_self_test_mutant"
    if mutant_tree.exists():
        shutil.rmtree(mutant_tree)
    shutil.copytree(generated_tree, mutant_tree)

    original = build_manifest(generated_tree)
    if not original:
        return [
            f"self-test: {generated_tree} contains no generated files -- the gate would "
            f"compare nothing."
        ]

    target_rel = sorted(
        rel for rel in original if rel.endswith((".py", ".ts", ".yml", ".json", ".sql"))
    )[0]
    target = mutant_tree / target_rel
    target.write_bytes(target.read_bytes() + b"\n# parity self-test mutation\n")

    mutated = build_manifest(mutant_tree)
    delta = diff_manifests(original, mutated)

    if delta.changed != [target_rel]:
        problems.append(
            f"self-test: mutating {target_rel!r} should report exactly that path as "
            f"CHANGED, but the comparator reported changed={delta.changed!r} "
            f"added={delta.added!r} removed={delta.removed!r}."
        )
    if delta.added or delta.removed:
        problems.append(
            f"self-test: a content-only mutation must not report added/removed paths, "
            f"got added={delta.added!r} removed={delta.removed!r}."
        )
    diff_lines = render_unified_diff(target_rel, generated_tree, mutant_tree)
    if not any("parity self-test mutation" in line for line in diff_lines):
        problems.append(
            f"self-test: the unified diff for {target_rel!r} did not show the mutated "
            f"content. Rendered:\n" + "\n".join(diff_lines)
        )

    shutil.rmtree(mutant_tree)
    return problems


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@dataclass
class ExampleOutcome:
    """The gate's verdict for one example."""

    ex_id: str
    rel_example: str
    status: str
    detail: str = ""
    #: Root of the tree this example generated, when generation succeeded. Present
    #: even when the manifest drifted -- a drifted example still produced real
    #: output, and the non-vacuity self-test can run against it.
    tree: Path | None = None


def _select_examples(example_filter: str | None) -> list[Path]:
    """Return the examples to operate on.

    Args:
        example_filter: A path relative to ``datrix/examples/``, or ``None`` for all.

    Returns:
        The matching ``system.dtrx`` paths.

    Raises:
        ValueError: If the filter matches no example.
    """
    all_examples = discover_examples()
    if example_filter is None:
        return all_examples
    target_dir = (EXAMPLES_ROOT / example_filter).resolve()
    selected = [p for p in all_examples if p.parent.resolve() == target_dir]
    if not selected:
        available = "\n  ".join(example_relpath(p) for p in all_examples)
        raise ValueError(
            f"No system.dtrx found for example {example_filter!r} (looked in {target_dir}). "
            f"Pass a path relative to datrix/examples/. Available:\n  {available}"
        )
    return selected


def cmd_bless(example_filter: str | None) -> int:
    """Regenerate stored baselines. The ONLY sanctioned baseline writer.

    Generates into the local bless cache and keeps the tree there, so that a later
    failing CHECK can render a real unified diff against it.

    Args:
        example_filter: A path relative to ``datrix/examples/``, or ``None`` for all.

    Returns:
        Process exit code.
    """
    examples = _select_examples(example_filter)
    known = load_known_non_generating()
    print(f"Blessing parity baselines for {len(examples)} example(s).")

    failures = 0
    blessed = 0
    for dtrx in examples:
        ex_id = example_id(dtrx)
        rel = example_relpath(dtrx)
        language = resolve_language(dtrx)
        tree = CACHE_ROOT / ex_id
        try:
            generate_example(dtrx, tree)
        except Exception as exc:  # noqa: BLE001 -- reported per example, never swallowed
            if ex_id in known:
                print(f"  SKIP  {rel} [{language}] -- known non-generating: {known[ex_id]}")
                continue
            failures += 1
            print(f"  FAIL  {rel} [{language}] -- generation failed: {exc}")
            continue
        manifest = build_manifest(tree)
        dest = baseline_path(ex_id, language)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(manifest_to_text(manifest), encoding="utf-8")
        blessed += 1
        print(f"  OK    {rel} [{language}] -- {len(manifest)} files -> {dest.name}")

    print()
    if failures:
        print(
            f"Baseline bless FAILED: {failures} example(s) could not generate. "
            f"No baseline was written for them. Fix the generation failure, or add the "
            f"example to {KNOWN_NON_GENERATING_PATH.name} with a reason (and bump its "
            f"expected_count) if the defect is pre-existing and tracked."
        )
        return EXIT_FAIL
    print(f"Blessed {blessed} baseline(s) under {BASELINES_ROOT}.")
    print("REVIEW THE BASELINE DIFF BEFORE COMMITTING -- an unexpected change is a bug.")
    return EXIT_OK


def _check_one(
    dtrx: Path,
    known: dict[str, str],
) -> ExampleOutcome:
    """Generate one example and compare it against its stored baseline.

    Args:
        dtrx: The example's ``system.dtrx``.
        known: The known-non-generating allowlist.

    Returns:
        The outcome for this example.
    """
    ex_id = example_id(dtrx)
    rel = example_relpath(dtrx)
    language = resolve_language(dtrx)
    bsl = baseline_path(ex_id, language)

    if not bsl.exists():
        if ex_id in known:
            return ExampleOutcome(ex_id, rel, "skip", known[ex_id])
        return ExampleOutcome(
            ex_id,
            rel,
            "fail",
            f"  NO BASELINE  example={rel} language={language}\n"
            f"    Expected {bsl}\n"
            f"    The gate never creates baselines. Bless it deliberately:\n"
            f'      powershell -File "d:/datrix/datrix/scripts/test/regen-parity-baselines.ps1" '
            f'-Example "{rel}"',
        )

    tree = SCRATCH_ROOT / ex_id
    try:
        generate_example(dtrx, tree)
    except Exception as exc:  # noqa: BLE001 -- reported per example, never swallowed
        if ex_id in known:
            return ExampleOutcome(ex_id, rel, "skip", f"{known[ex_id]} (raised: {exc})")
        return ExampleOutcome(
            ex_id,
            rel,
            "fail",
            f"  GENERATION FAILED  example={rel} language={language}\n    {exc}",
        )

    stored = parse_manifest_text(bsl.read_text(encoding="utf-8"))
    computed = build_manifest(tree)
    delta = diff_manifests(stored, computed)
    if delta.is_empty:
        return ExampleOutcome(ex_id, rel, "ok", f"{len(computed)} files", tree)
    return ExampleOutcome(
        ex_id, rel, "fail", render_failure(ex_id, rel, delta, stored, tree), tree
    )


def cmd_check(example_filter: str | None) -> int:
    """Run the gate: every example must match its stored baseline byte for byte.

    Args:
        example_filter: A path relative to ``datrix/examples/``, or ``None`` for all.

    Returns:
        Process exit code.
    """
    examples = _select_examples(example_filter)
    known = load_known_non_generating()
    print(f"Reference-example parity gate: {len(examples)} example(s).")
    print()

    outcomes: list[ExampleOutcome] = []
    self_test_problems: list[str] | None = None

    for dtrx in examples:
        outcome = _check_one(dtrx, known)
        outcomes.append(outcome)
        if outcome.status == "ok":
            print(f"  OK    {outcome.rel_example} ({outcome.detail})")
        elif outcome.status == "skip":
            print(f"  SKIP  {outcome.rel_example} -- known non-generating: {outcome.detail}")
        else:
            print(f"  FAIL  {outcome.rel_example}")

        # Non-vacuity self-test, against the first REAL generated tree this run
        # produced -- including a drifted one, which is still real output.
        if self_test_problems is None and outcome.tree is not None:
            self_test_problems = run_self_test(outcome.tree)

    failed = [o for o in outcomes if o.status == "fail"]
    skipped = [o for o in outcomes if o.status == "skip"]
    passed = [o for o in outcomes if o.status == "ok"]

    if failed:
        print()
        for o in failed:
            print(o.detail)
            print()

    print("=" * 78)
    print(f"passed={len(passed)}  failed={len(failed)}  known-non-generating={len(skipped)}")

    if skipped:
        print()
        print("Known non-generating examples (real, pre-existing defects -- NOT hidden):")
        for o in skipped:
            print(f"  {o.rel_example}: {o.detail}")
        print()

    if self_test_problems is None:
        print(
            "NON-VACUITY SELF-TEST DID NOT RUN: no example generated a tree, so the gate "
            "proved nothing about output stability. Treating as failure."
        )
        return EXIT_FAIL
    if self_test_problems:
        print("NON-VACUITY SELF-TEST FAILED -- the comparator cannot detect a real change:")
        for p in self_test_problems:
            print(f"  {p}")
        return EXIT_FAIL
    print(
        "non-vacuity self-test: PASS "
        "(a one-byte mutation of real generated output is detected and diffed)"
    )

    if failed:
        print(f"PARITY GATE FAILED: {len(failed)} example(s) drifted from their baseline.")
        print("Any diff you cannot explain is a bug, not a baseline update.")
        return EXIT_FAIL

    print("PARITY GATE PASSED: every example's generated output matches its baseline.")
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments.

    Args:
        argv: Argument list (without the program name).

    Returns:
        Parsed namespace.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Reference-example parity gate. 'check' compares every example's real "
            "generated output against its stored baseline; 'bless' rewrites the "
            "baselines (the only sanctioned writer)."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("check", "bless"),
        default="check",
        help="check (default) compares against baselines; bless rewrites them.",
    )
    parser.add_argument(
        "--example",
        metavar="RELPATH",
        default=None,
        help=(
            "Path relative to datrix/examples/ for a single example "
            "(e.g. '01-foundation'). Omit for all examples."
        ),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable DEBUG-level logging (very verbose: the pipeline logs every stage).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code: 0 pass, 1 drift/failure, 2 usage error.
    """
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    # The pipeline logs a stage line per generator at INFO; that noise would bury
    # the report (and, under PowerShell 5.1, every stderr line becomes a
    # NativeCommandError). Keep it at WARNING unless --debug is requested.
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    _register_language_plugins()

    try:
        if args.mode == "bless":
            return cmd_bless(args.example)
        return cmd_check(args.example)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
