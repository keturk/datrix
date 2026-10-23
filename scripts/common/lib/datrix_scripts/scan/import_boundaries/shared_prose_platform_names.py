"""Shared-prose platform-name scanner and its ratchet.

The identifier ratchets (target literals, provider conditionals, shared target
names) read the AST and deliberately skip docstrings, comments and message
text. A shared layer that names a provider in that prose still teaches the
reader that the shared layer knows its targets (Principle 10), and a new
provider name there passes every identifier ratchet. This ratchet reads the
token stream instead: every comment, string literal (docstrings included) and
f-string text segment in the DERIVED shared-package set, matched against the
registered platform names.
"""

from __future__ import annotations

import io
import re
import shutil
import subprocess
import sys
import tokenize
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from datrix_scripts.gate_harness import NamedCheck, report_step
from datrix_scripts.registered_targets import registered_platform_names
from datrix_scripts.scan.import_boundaries._ast_common import (
    _SELF_TEST_SCRATCH_ROOT,
    CLI_COMMAND,
    PackageInfo,
    _check,
    _self_test_write_manifest,
    self_test_check,
    tighten_only_messages,
    write_count_baseline,
)
from datrix_scripts.scan.import_boundaries.target_literals import _platform_token_vocabulary

#: The entry key of this ratchet's baseline: ``<root-relative file>::<platform name>``.
SHARED_PROSE_PLATFORM_NAME_BASELINE_KEY = "entry"
_ENTRY_SEPARATOR = "::"

#: Token kinds that carry prose rather than code: comments, string literals
#: (docstrings are string tokens) and the literal text of an f-string or
#: t-string, which Python 3.12+ tokenizes as separate ``*_MIDDLE`` tokens.
_PROSE_TOKEN_TYPES: frozenset[int] = frozenset(
    {tokenize.COMMENT, tokenize.STRING}
    | {getattr(tokenize, kind) for kind in ("FSTRING_MIDDLE", "TSTRING_MIDDLE") if hasattr(tokenize, kind)}
)


@dataclass(frozen=True)
class SharedProsePlatformNameHit:
    """One registered platform name spelled in shared-layer prose."""

    file_path: Path
    line_number: int
    platform_name: str


def shared_prose_platform_name_vocabulary() -> frozenset[str]:
    """Registered platform names, minus the English-word collisions the
    platform-token identifier match already excludes (one exclusion set)."""
    return _platform_token_vocabulary()


def _name_patterns(platform_names: frozenset[str]) -> dict[str, re.Pattern[str]]:
    """One case-insensitive whole-name pattern per platform name.

    A hyphen is part of a name, never a boundary: ``acme`` does not match inside
    ``acme-vm`` or ``acme-app-service``, and ``acme-vm`` matches whole. An
    underscore or a letter on either side is a different word (``acme_blob``).
    """
    return {
        name: re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])", re.IGNORECASE)
        for name in sorted(platform_names)
    }


def scan_source_for_shared_prose_platform_names(
    file_path: Path, source_code: str, platform_names: frozenset[str]
) -> list[SharedProsePlatformNameHit]:
    """Every platform-name mention in *source_code*'s prose tokens, in token order.

    A token spanning several lines (a docstring) reports each mention on the
    line it sits on.

    Raises:
        tokenize.TokenError, SyntaxError: The source cannot be tokenized
            (caller decides how to report).
    """
    patterns = _name_patterns(platform_names)
    hits: list[SharedProsePlatformNameHit] = []
    for token in tokenize.generate_tokens(io.StringIO(source_code).readline):
        if token.type not in _PROSE_TOKEN_TYPES:
            continue
        for offset, line in enumerate(token.string.splitlines()):
            for name, pattern in patterns.items():
                hits.extend(
                    SharedProsePlatformNameHit(file_path, token.start[0] + offset, name)
                    for _ in pattern.finditer(line)
                )
    return hits


def _fail_scan(message: str) -> NoReturn:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(2)


def scan_shared_prose_platform_names(
    packages: dict[str, PackageInfo],
    monorepo_root: Path,
    shared_packages: tuple[str, ...],
) -> dict[Path, list[SharedProsePlatformNameHit]]:
    """Scan every ``.py`` file under each of *shared_packages*' ``src/`` tree.

    Args:
        packages: Package name -> PackageInfo, as returned by discover_packages().
        monorepo_root: Monorepo root for relative path reporting.
        shared_packages: The DERIVED shared-package set (``discover_shared_packages``).

    Returns:
        Mapping of file path -> hits in that file (files with zero hits omitted).
    """
    platform_names = shared_prose_platform_name_vocabulary()
    results: dict[Path, list[SharedProsePlatformNameHit]] = {}
    for package_name in shared_packages:
        package_info = packages.get(package_name)
        if package_info is None:
            continue
        for py_file in sorted(package_info.src_dir.rglob("*.py")):
            rel_path = py_file.relative_to(monorepo_root)
            try:
                source_code = py_file.read_text(encoding="utf-8-sig")
                hits = scan_source_for_shared_prose_platform_names(py_file, source_code, platform_names)
            except (tokenize.TokenError, SyntaxError) as e:
                _fail_scan(
                    f"Failed to tokenize {rel_path} - {e}. A policed file that cannot be "
                    f"tokenized would escape this scan (a silent blind spot); fix its syntax."
                )
            except (OSError, UnicodeDecodeError) as e:
                _fail_scan(
                    f"Failed to read {rel_path} - {e}. A policed file that cannot be read "
                    f"would escape this scan; resolve the read error."
                )
            if hits:
                results[py_file] = hits
    return results


def shared_prose_platform_name_counts(
    hits_by_file: dict[Path, list[SharedProsePlatformNameHit]], monorepo_root: Path
) -> dict[str, int]:
    """``{"<root-relative file, forward slashes>::<platform name>": mention count}``."""
    counts: dict[str, int] = {}
    for file_path, hits in hits_by_file.items():
        rel_path = file_path.relative_to(monorepo_root).as_posix()
        for hit in hits:
            entry = f"{rel_path}{_ENTRY_SEPARATOR}{hit.platform_name}"
            counts[entry] = counts.get(entry, 0) + 1
    return counts


_SHARED_PROSE_PLATFORM_NAME_BASELINE_HEADER = (
    "# Shared-Prose Platform-Name Ratchet Baseline (Principle 10)\n"
    "#\n"
    "# Frozen counts of registered platform names (datrix.platforms entry points,\n"
    "# minus the English-word collisions the platform-token match excludes)\n"
    "# spelled in comments, docstrings, string literals and f-string text of\n"
    "# the derived shared-package set, one entry per (file, platform name).\n"
    "# A (file, name) pair with no entry is held at zero, so a platform name\n"
    "# entering shared prose anywhere new fails\n"
    "# datrix/scripts/scan/check-import-boundaries.ps1 -CheckSharedProsePlatformNames.\n"
    "# Any INCREASE fails; decreases are always allowed and are captured by\n"
    "# re-running with -UpdateBaseline once a change rewords a mention.\n"
    "# The target is an empty file: reword each mention provider-neutrally, or\n"
    "# move the fact into the platform's own declaration.\n"
    "#\n"
    "# Format:\n"
    "#   [[baseline]]\n"
    '#   entry = "path/relative/to/monorepo-root, forward slashes::platform-name"\n'
    "#   count = <int>\n"
)


def write_shared_prose_platform_name_baseline(baseline_path: Path, counts: dict[str, int]) -> None:
    """Write ``counts`` as ``[[baseline]] entry=... count=...`` entries, sorted by entry."""
    write_count_baseline(
        baseline_path,
        counts,
        header=_SHARED_PROSE_PLATFORM_NAME_BASELINE_HEADER,
        key_field=SHARED_PROSE_PLATFORM_NAME_BASELINE_KEY,
    )


def check_shared_prose_platform_name_ratchet(
    current_counts: dict[str, int], baseline: dict[str, int]
) -> list[str]:
    """One message per (file, platform name) whose mention count rose above its
    baseline (an absent entry is 0), sorted by entry."""
    return tighten_only_messages(current_counts, baseline, "shared-prose platform-name")


# ---------------------------------------------------------------------------
# Self-tests
# ---------------------------------------------------------------------------


def _self_test_shared_prose_platform_name_scanner() -> bool:
    """The token scanner matches whole platform names in every prose token kind,
    treats a hyphen as part of a name, and never reads code identifiers."""
    report_step("Self-test: shared-prose platform-name scanner (prose token kinds, whole-name matching)")
    ok = True
    # Synthetic names: a short name and a hyphenated name that contains it.
    names = frozenset({"acme", "acme-vm"})
    path = Path("sample.py")

    def found(source: str) -> list[tuple[int, str]]:
        return [(hit.line_number, hit.platform_name) for hit in scan_source_for_shared_prose_platform_names(path, source, names)]

    ok &= _check(
        "a docstring naming the hyphenated platform reports it once, not its short prefix",
        found('def f() -> None:\n    """Runs behind\n    an acme-vm edge."""\n') == [(3, "acme-vm")],
    )
    ok &= _check("a comment naming a platform reports it", found("x = 1  # the ACME backend\n") == [(1, "acme")])
    ok &= _check(
        "an error-message string naming a platform reports it",
        found("raise ValueError('acme only')\n") == [(1, "acme")],
    )
    ok &= _check(
        "the literal text of an f-string naming a platform reports it",
        found('label = f"on acme-vm: {name}"\n') == [(1, "acme-vm")],
    )
    ok &= _check(
        "a code identifier carrying the name is not prose (the identifier ratchets own it)",
        found("acme = AcmeConfig()\nacme_vm = 1\n") == [],
    )
    ok &= _check(
        "an underscore or hyphen continuation is a different word (acme_blob, acme-app-service)",
        found("KINDS = ('acme_blob', 'acme-app-service', 'acmeish')\n") == [],
    )
    ok &= _check(
        "two mentions in one string count twice",
        found("# acme here, acme there\n") == [(1, "acme"), (1, "acme")],
    )

    live = shared_prose_platform_name_vocabulary()
    registered = frozenset(registered_platform_names())
    ok &= _check("the live vocabulary is non-empty", bool(live))
    ok &= _check("the live vocabulary is drawn from the registered platform names", live <= registered)
    ok &= _check(
        "the live vocabulary drops the platform-token English-word exclusions",
        live == _platform_token_vocabulary(),
    )
    ok &= _check(
        "the ratchet fails a count above its baseline and an entry with no baseline",
        check_shared_prose_platform_name_ratchet({"a.py::acme": 2, "b.py::acme-vm": 1}, {"a.py::acme": 1})
        == [
            "a.py::acme: shared-prose platform-name count increased from baseline 1 to 2",
            "b.py::acme-vm: shared-prose platform-name count increased from baseline 0 to 1",
        ],
    )
    ok &= _check(
        "the ratchet passes a decrease and an equal count",
        check_shared_prose_platform_name_ratchet({"a.py::acme": 1}, {"a.py::acme": 1, "c.py::acme": 3}) == [],
    )
    return ok


def _self_test_live_platform_names() -> tuple[str, str] | None:
    """Two distinct live vocabulary names (the baselined one, the planted one), or None."""
    live = sorted(shared_prose_platform_name_vocabulary(), key=lambda name: (-len(name), name))
    return (live[-1], live[0]) if len(live) >= 2 else None


def _self_test_shared_prose_build_fixture_monorepo(tmp_root: Path, baselined: str) -> Path:
    """A minimal monorepo: one shared package (a manifest registering no
    entry-point group) whose module mentions *baselined* once, frozen at 1."""
    _self_test_write_manifest(tmp_root, "datrix-common", "datrix_common", entry_point_groups={})
    package_src = tmp_root / "datrix-common" / "src" / "datrix_common"
    package_src.mkdir(parents=True, exist_ok=True)
    (package_src / "__init__.py").write_text("", encoding="utf-8")
    module_path = package_src / "sample_bootstrap.py"
    module_path.write_text(f'"""Bootstraps the {baselined} runtime."""\n', encoding="utf-8")
    config_dir = tmp_root / "datrix" / "scripts" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    write_shared_prose_platform_name_baseline(
        config_dir / "shared-prose-platform-name-baseline.toml",
        {f"datrix-common/src/datrix_common/sample_bootstrap.py{_ENTRY_SEPARATOR}{baselined}": 1},
    )
    return module_path


def _self_test_shared_prose_run_cli(tmp_root: Path) -> subprocess.CompletedProcess[str]:
    """Run the boundary scan as a real subprocess against the isolated fixture."""
    return subprocess.run(
        [*CLI_COMMAND, "--base-dir", str(tmp_root), "--check-shared-prose-platform-names"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _self_test_shared_prose_platform_name_cli_non_vacuity() -> bool:
    """End-to-end proof the ratchet FIRES: a baselined mention passes, a second
    mention of it fails, a live platform name with no entry fails naming the
    file and the name, and reverting clears both."""
    report_step(
        "Self-test: shared-prose platform-name ratchet CLI mutation non-vacuity "
        "(baselined mention exits 0; one more, or an unbaselined live name, exits 1)"
    )
    names = _self_test_live_platform_names()
    ok = _check("the live registry has at least two platform names to plant", names is not None)
    if names is None:
        return ok
    baselined, planted = names
    tmp_root = _SELF_TEST_SCRATCH_ROOT / f"shared-prose-cli-{uuid.uuid4().hex}"
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        module_path = _self_test_shared_prose_build_fixture_monorepo(tmp_root, baselined)
        clean_source = module_path.read_text(encoding="utf-8")

        clean_result = _self_test_shared_prose_run_cli(tmp_root)
        ok &= _check(
            f"the baselined mention exits 0, got {clean_result.returncode}: {clean_result.stdout}{clean_result.stderr}",
            clean_result.returncode == 0,
        )

        module_path.write_text(clean_source + f"# Also {baselined}.\n", encoding="utf-8")
        raised = _self_test_shared_prose_run_cli(tmp_root)
        ok &= _check(f"a second mention exits 1, got {raised.returncode}", raised.returncode == 1)
        ok &= _check(
            "the failure names the entry and the delta (1 -> 2)",
            f"sample_bootstrap.py{_ENTRY_SEPARATOR}{baselined}: shared-prose platform-name count "
            "increased from baseline 1 to 2" in raised.stdout,
        )

        module_path.write_text(clean_source + f"# Runs behind a {planted} edge.\n", encoding="utf-8")
        planted_result = _self_test_shared_prose_run_cli(tmp_root)
        ok &= _check(
            f"an unbaselined platform name in a comment exits 1, got {planted_result.returncode}",
            planted_result.returncode == 1,
        )
        ok &= _check(
            "the failure names the file, the platform name and the delta (0 -> 1)",
            f"sample_bootstrap.py{_ENTRY_SEPARATOR}{planted}: shared-prose platform-name count "
            "increased from baseline 0 to 1" in planted_result.stdout,
        )

        module_path.write_text(clean_source, encoding="utf-8")
        reverted = _self_test_shared_prose_run_cli(tmp_root)
        ok &= _check(f"reverting clears the failure, got exit {reverted.returncode}", reverted.returncode == 0)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return ok


def self_test_checks() -> list[NamedCheck]:
    """The shared-prose platform-name scanner's and ratchet's self-tests."""
    return [
        self_test_check(_self_test_shared_prose_platform_name_scanner),
        self_test_check(_self_test_shared_prose_platform_name_cli_non_vacuity),
    ]
