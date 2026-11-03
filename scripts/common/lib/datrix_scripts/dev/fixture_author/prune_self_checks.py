"""The self-test of pruning a package, on planted workspaces.

A planted workspace holds one package and an empty shared corpus. Its module reads one fixture by name (whose
system names a config file) and walks one directory; one fixture under its own directory nothing reads. The
prune deletes the unread file and the directory it leaves empty and keeps every file read by name, by a walk
and through the system's config, regenerates the package's semantic manifest with the deleted key gone, and banks the planted
workspace's fixture budget. A planted manifest whose kept fixture's hash differs refuses the run, as does a
deletion taking a model's last contract sample, and every deleted file is written back byte for byte; a sample
the corpus holds lets the file go. A queued module refuses the run before anything is read; an undo record an
interrupted prune left is written back first; ``-Prune`` belongs to ``repoint`` and needs ``-Package``; the
tool runs no git command.
"""

from __future__ import annotations

import ast
import io
import json
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from datrix_scripts.gate_harness import CheckFunc

if TYPE_CHECKING:
    from datrix_testing.model_contracts.discovery import ModelSet

_PACKAGE: Final = "datrix-planted"
_CORPUS: Final = "datrix-testing/src/datrix_testing/fixtures_data/corpus"
_BUDGET_BASELINE: Final = "datrix/scripts/config/fixture-budget-baseline.json"
_KEPT: Final = "tests/fixtures/kept.dtrx"
_SYSTEM_CONFIG: Final = "tests/fixtures/config/system.dcfg"
_WALKED: Final = "tests/fixtures/walked/walked.dtrx"
_UNREAD: Final = "tests/fixtures/old/unread.dtrx"
_SAMPLED: Final = "tests/fixtures/ledger-extern.dcfg"
_MANIFEST: Final = "tests/fixtures/semantic_baseline/manifest.json"
_QUEUED: Final = f"repoint-{_PACKAGE}--tests.test_reads.md"
_LOST_MODEL: Final = "datrix_common.config.extern_service.models.ExternServiceProfileConfig"

_READS_SOURCE: Final = '''"""Planted: reads one fixture by name and walks one directory."""

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def test_kept_names_its_system() -> None:
    assert "system" in (FIXTURES / "kept.dtrx").read_text(encoding="utf-8")


def test_walked_fixtures_are_there() -> None:
    assert sorted((FIXTURES / "walked").glob("*.dtrx"))
'''
_CONTRACTS_SOURCE: Final = '''"""Planted: hands its tests/ to the model contract capture."""

from pathlib import Path

from datrix_testing.model_contracts.runner import package_contracts

CONTRACTS = package_contracts(Path(__file__).resolve().parent)
'''
_KEPT_FIXTURE: Final = "system test.Kept('config/system.dcfg') : version('1.0.0') {\n}\n"
_SYSTEM_CONFIG_TEXT: Final = """config system test.Kept {
  base {
  }

  profile test as "test" extends base {
  }
}
"""
_WALKED_FIXTURE: Final = "system test.Walked('config/system.dcfg') : version('1.0.0') {\n}\n"
_UNREAD_FIXTURE: Final = "system test.Unread('config/system.dcfg') : version('1.0.0') {\n}\n"
_SAMPLED_FIXTURE: Final = """config extern shop.LedgerApi {
  base {
    deployment = "external";
    url = "https://ledger.partner.example.com";
    auth {
    }
  }

  profile test as "test" extends base {
  }
}
"""


@dataclass(frozen=True)
class _Planted:
    """A planted workspace with its package, and the undo record and queue a prune reads beside it."""

    workspace: Path
    undo: Path
    queue: Path

    @property
    def package_dir(self) -> Path:
        return self.workspace / _PACKAGE

    @property
    def corpus(self) -> Path:
        return self.workspace / _CORPUS

    def files(self) -> dict[str, bytes]:
        """Every file of the planted package, by package-relative path, with its bytes."""
        return {path.relative_to(self.package_dir).as_posix(): path.read_bytes()
                for path in sorted(self.package_dir.rglob("*")) if path.is_file()}


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_manifest(planted: _Planted, changed: str | None = None) -> dict[str, str]:
    """Write the package's semantic manifest as the planted fixtures build it, the key *changed* with another
    hash; the manifest written."""
    from datrix_testing.parsing import register_installed_parsers
    from datrix_testing.semantic_baseline import (
        SemanticBaselineCorpus,
        build_semantic_baseline,
        write_semantic_baseline,
    )

    register_installed_parsers()
    corpus = SemanticBaselineCorpus(planted.package_dir, planted.corpus)
    manifest = build_semantic_baseline(corpus)
    if changed is not None:
        manifest[changed] = "0" * 64
    write_semantic_baseline(corpus, manifest)
    return manifest


@contextmanager
def _planted(*, contracts: bool = False) -> Iterator[_Planted]:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp) / "workspace"
        (workspace / _CORPUS).mkdir(parents=True)
        package = workspace / _PACKAGE
        files = {
            "pyproject.toml": f'[project]\nname = "{_PACKAGE}"\n',
            "tests/test_reads.py": _READS_SOURCE,
            _KEPT: _KEPT_FIXTURE,
            _SYSTEM_CONFIG: _SYSTEM_CONFIG_TEXT,
            _WALKED: _WALKED_FIXTURE,
            _UNREAD: _UNREAD_FIXTURE,
        }
        if contracts:
            files.update({"tests/test_model_contracts.py": _CONTRACTS_SOURCE, _SAMPLED: _SAMPLED_FIXTURE})
        for relative, text in files.items():
            _write(package, relative, text)
        yield _Planted(workspace, Path(tmp) / "undo", Path(tmp) / "queue")


def _common_models(_package_dir: Path) -> ModelSet:
    """The models of datrix-common: a planted package declares none of its own."""
    from datrix_testing.model_contracts.discovery import model_set

    from datrix_scripts.paths import WORKSPACE_DIR

    return model_set(WORKSPACE_DIR / "datrix-common")


def _prune(planted: _Planted) -> tuple[int, str]:
    from datrix_testing.model_contracts.discovery import model_set

    from datrix_scripts.dev.fixture_author.prune import Pruner, run_prune
    from datrix_scripts.dev.fixture_author.repoint_jobs import UndoStore

    has_contracts = (planted.package_dir / "tests" / "test_model_contracts.py").is_file()
    pruner = Pruner(planted.package_dir, planted.workspace, UndoStore(planted.undo), planted.queue,
                    _common_models if has_contracts else model_set)
    printed = io.StringIO()
    with redirect_stdout(printed):
        code = run_prune(pruner)
    return code, printed.getvalue()


def _check_an_unread_file_is_deleted_and_every_read_file_kept() -> None:
    with _planted() as planted:
        before = _write_manifest(planted)
        code, printed = _prune(planted)
        after = planted.files()
        manifest = json.loads(after[_MANIFEST])
        budget = (planted.workspace / _BUDGET_BASELINE).is_file()
        emptied = (planted.package_dir / _UNREAD).parent.exists()
        undo_left = planted.undo.exists() and any(planted.undo.iterdir())
    assert code == 0, printed
    assert _UNREAD not in after and not emptied, "the unread file is deleted, and the directory it left empty"
    assert {_KEPT, _SYSTEM_CONFIG, _WALKED} <= after.keys(), f"named, reached and walked files are kept: {sorted(after)}"
    assert set(before) - set(manifest) == {_UNREAD} and all(manifest[key] == before[key] for key in manifest), (
        before, manifest)
    assert f"[DEL ] {_PACKAGE}/{_UNREAD}" in printed and "[BASE]" in printed, printed
    assert "files 4 - kept 3 (named 1, tree 1, harness 0, reached 1) = 1 deleted" in printed, printed
    assert budget, "the planted workspace's fixture budget baseline is written"
    assert not undo_left, "no undo record is left"


def _check_a_changed_hash_refuses_the_prune_and_every_file_is_written_back() -> None:
    with _planted() as planted:
        _write_manifest(planted, changed=_KEPT)
        before = planted.files()
        code, printed = _prune(planted)
        after = planted.files()
        budget = (planted.workspace / _BUDGET_BASELINE).is_file()
    assert code == 1, printed
    assert "REFUSED" in printed and f"{_KEPT}: semantic output CHANGED" in printed, printed
    assert after == before, "every deleted file is written back byte for byte and the manifest is unchanged"
    assert not budget, "a refused prune banks no budget"


def _check_a_model_losing_its_last_sample_refuses_the_prune() -> None:
    with _planted(contracts=True) as planted:
        before = planted.files()
        code, printed = _prune(planted)
        after = planted.files()
    assert code == 1, printed
    assert "REFUSED" in printed and f"model {_LOST_MODEL} loses its last sample" in printed, printed
    assert _SAMPLED in printed, "the refusal names the fixture the sample came from"
    assert after == before, "every deleted file is written back byte for byte"


def _check_a_sample_the_corpus_holds_lets_its_file_go() -> None:
    with _planted(contracts=True) as planted:
        _write(planted.corpus, "config/ledger-extern.dcfg", _SAMPLED_FIXTURE)
        code, printed = _prune(planted)
        after = planted.files()
    assert code == 0, printed
    assert _SAMPLED not in after and _UNREAD not in after, sorted(after)


def _check_a_queued_module_refuses_the_prune() -> None:
    with _planted() as planted:
        _write(planted.queue, _QUEUED, "queued\n")
        before = planted.files()
        code, printed = _prune(planted)
        after = planted.files()
    assert code == 1, printed
    assert "REFUSED" in printed and _QUEUED in printed, printed
    assert after == before, "nothing is deleted while a module is queued"


def _check_an_interrupted_prune_is_written_back_first() -> None:
    from datrix_scripts.dev.fixture_author.prune import RECORD_PREFIX
    from datrix_scripts.dev.fixture_author.repoint_jobs import UndoStore

    with _planted() as planted:
        kept = planted.package_dir / _KEPT
        original = kept.read_bytes()
        UndoStore(planted.undo).save(f"{RECORD_PREFIX}{_PACKAGE}", [kept])
        kept.unlink()
        code, printed = _prune(planted)
        restored = kept.read_bytes() if kept.is_file() else b""
    assert code == 0, printed
    assert f"[UNDO] {RECORD_PREFIX}{_PACKAGE}" in printed, printed
    assert restored == original, "the file the interrupted prune deleted is written back byte for byte, and kept"


def _check_prune_belongs_to_repoint_and_needs_a_package() -> None:
    from datrix_scripts.dev.fixture_author.cli import LIBRARY_KIND, REPOINT_KIND, main
    from datrix_scripts.gate_harness import EXIT_USAGE

    for argv in (["--kind", LIBRARY_KIND, "--prune"], ["--kind", REPOINT_KIND, "--prune"]):
        printed = io.StringIO()
        with redirect_stdout(printed):
            code = main(argv)
        assert code == EXIT_USAGE, (argv, code, printed.getvalue())


def _check_the_prune_runs_no_git_command() -> None:
    from datrix_scripts.dev.fixture_author import prune, prune_reads

    for module in (prune, prune_reads):
        source = Path(str(module.__file__)).read_text(encoding="utf-8")
        commands = [node.value for node in ast.walk(ast.parse(source))
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and node.value.split()[:1] in (["git"], ["git.exe"])]
        assert commands == [], f"{module.__name__} holds a git command: {commands}"


CHECKS: Final[list[CheckFunc]] = [
    _check_an_unread_file_is_deleted_and_every_read_file_kept,
    _check_a_changed_hash_refuses_the_prune_and_every_file_is_written_back,
    _check_a_model_losing_its_last_sample_refuses_the_prune,
    _check_a_sample_the_corpus_holds_lets_its_file_go,
    _check_a_queued_module_refuses_the_prune,
    _check_an_interrupted_prune_is_written_back_first,
    _check_prune_belongs_to_repoint_and_needs_a_package,
    _check_the_prune_runs_no_git_command,
]
