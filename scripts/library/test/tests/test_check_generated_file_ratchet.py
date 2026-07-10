"""Unit tests for the I5 GeneratedFile-construction ratchet scanner.

Real temporary files and real AST parsing only -- no mocks, no
SimpleNamespace -- per project test guidelines. Covers design 025,
Invariant I5.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_SCANNER_PATH = (
    Path(__file__).resolve().parents[4] / "scripts" / "test" / "check-generated-file-ratchet.py"
)

_MODULE_ALIAS = "check_generated_file_ratchet"

if _MODULE_ALIAS not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_MODULE_ALIAS, _SCANNER_PATH)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Could not load scanner module from {_SCANNER_PATH}")
    _mod: types.ModuleType = importlib.util.module_from_spec(_spec)
    sys.modules[_MODULE_ALIAS] = _mod
    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_scanner = sys.modules[_MODULE_ALIAS]

count_generated_file_constructions = _scanner.count_generated_file_constructions
discover_packages = _scanner.discover_packages
scan_package = _scanner.scan_package
check_ratchet = _scanner.check_ratchet
PackageInfo = _scanner.PackageInfo


@pytest.mark.unit
class TestCountGeneratedFileConstructions:
    def test_bare_constructor_call_counted(self, tmp_path: Path) -> None:
        source = (
            "from datrix_common.generation.generator import GeneratedFile\n"
            "def f():\n"
            "    return GeneratedFile(path=None, content='', language='python', source_hash='x')\n"
        )
        file_path = tmp_path / "sample.py"
        file_path.write_text(source, encoding="utf-8")
        assert count_generated_file_constructions(file_path) == 1

    def test_qualified_constructor_call_counted(self, tmp_path: Path) -> None:
        source = (
            "import datrix_common.generation.generator as gen\n"
            "def f():\n"
            "    return gen.GeneratedFile(path=None, content='', language='python', source_hash='x')\n"
        )
        file_path = tmp_path / "sample.py"
        file_path.write_text(source, encoding="utf-8")
        assert count_generated_file_constructions(file_path) == 1

    def test_from_content_factory_not_counted(self, tmp_path: Path) -> None:
        source = (
            "from datrix_common.generation.generator import GeneratedFile\n"
            "def f():\n"
            "    return GeneratedFile.from_content(path=None, content='', language='python')\n"
        )
        file_path = tmp_path / "sample.py"
        file_path.write_text(source, encoding="utf-8")
        assert count_generated_file_constructions(file_path) == 0

    def test_multiple_constructions_counted(self, tmp_path: Path) -> None:
        source = (
            "from datrix_common.generation.generator import GeneratedFile\n"
            "def f():\n"
            "    a = GeneratedFile(path=None, content='', language='python', source_hash='a')\n"
            "    b = GeneratedFile(path=None, content='', language='python', source_hash='b')\n"
            "    return [a, b]\n"
        )
        file_path = tmp_path / "sample.py"
        file_path.write_text(source, encoding="utf-8")
        assert count_generated_file_constructions(file_path) == 2

    def test_no_construction_returns_zero(self, tmp_path: Path) -> None:
        file_path = tmp_path / "sample.py"
        file_path.write_text("def f():\n    return 1\n", encoding="utf-8")
        assert count_generated_file_constructions(file_path) == 0


@pytest.mark.unit
class TestScanPackageExcludesTestsAndExecutor:
    def test_tests_directory_never_scanned(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "datrix-codegen-fake"
        src_dir = pkg_dir / "src" / "datrix_codegen_fake"
        src_dir.mkdir(parents=True)
        (src_dir / "gen.py").write_text("x = 1\n", encoding="utf-8")

        tests_dir = pkg_dir / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_gen.py").write_text(
            "from datrix_common.generation.generator import GeneratedFile\n"
            "GeneratedFile(path=None, content='', language='python', source_hash='x')\n",
            encoding="utf-8",
        )

        package = PackageInfo(name="datrix-codegen-fake", src_dir=pkg_dir / "src")
        total = scan_package(package, tmp_path, verbose=False)
        assert total == 0

    def test_excluded_executor_file_never_counted(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "datrix-codegen-common"
        executor_dir = pkg_dir / "src" / "datrix_codegen_common" / "gendsl"
        executor_dir.mkdir(parents=True)
        (executor_dir / "executor.py").write_text(
            "from datrix_common.generation.generator import GeneratedFile\n"
            "GeneratedFile(path=None, content='', language='python', source_hash='x')\n",
            encoding="utf-8",
        )

        package = PackageInfo(name="datrix-codegen-common", src_dir=pkg_dir / "src")
        total = scan_package(package, tmp_path, verbose=False)
        assert total == 0


@pytest.mark.unit
class TestCheckRatchet:
    def test_no_regression_when_equal_to_baseline(self) -> None:
        messages = check_ratchet({"pkg": 5}, {"pkg": 5})
        assert messages == []

    def test_no_regression_when_below_baseline(self) -> None:
        messages = check_ratchet({"pkg": 3}, {"pkg": 5})
        assert messages == []

    def test_regression_when_above_baseline(self) -> None:
        messages = check_ratchet({"pkg": 6}, {"pkg": 5})
        assert len(messages) == 1
        assert "pkg" in messages[0]
        assert "5" in messages[0]
        assert "6" in messages[0]

    def test_missing_baseline_entry_treated_as_zero(self) -> None:
        messages = check_ratchet({"pkg": 1}, {})
        assert len(messages) == 1
        assert "baseline 0" in messages[0]


@pytest.mark.unit
class TestDiscoverPackages:
    def test_only_datrix_prefixed_dirs_with_src_are_discovered(self, tmp_path: Path) -> None:
        (tmp_path / "datrix-codegen-fake" / "src").mkdir(parents=True)
        (tmp_path / "datrix-no-src").mkdir()
        (tmp_path / "not-datrix-prefixed" / "src").mkdir(parents=True)

        packages = discover_packages(tmp_path)

        assert "datrix-codegen-fake" in packages
        assert "datrix-no-src" not in packages
        assert "not-datrix-prefixed" not in packages
