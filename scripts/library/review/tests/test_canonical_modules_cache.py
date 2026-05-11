"""Unit tests for canonical modules cache."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from canonical_modules import (
    build_canonical_modules_digest,
    check_cache_validity,
    discover_datrix_packages,
    format_canonical_modules_for_prompt,
    scan_package_modules,
)


def test_discover_datrix_packages(tmp_path):
    """Test package discovery."""
    (tmp_path / "datrix-common/src").mkdir(parents=True)
    (tmp_path / "datrix-language/src").mkdir(parents=True)
    (tmp_path / "not-a-datrix-package/src").mkdir(parents=True)

    packages = discover_datrix_packages(tmp_path)

    assert len(packages) == 2
    assert any("datrix-common" in str(p) for p in packages)
    assert any("datrix-language" in str(p) for p in packages)


def test_scan_package_modules(tmp_path):
    """Test module scanning."""
    package_dir = tmp_path / "datrix-common"
    (package_dir / "src/datrix_common/utils").mkdir(parents=True)
    (package_dir / "src/datrix_common/utils/__init__.py").write_text("")
    (package_dir / "src/datrix_common/utils/text.py").write_text("")

    modules = scan_package_modules(package_dir)

    assert "datrix_common.utils" in modules
    assert "datrix_common.utils.text" in modules


def test_build_canonical_modules_digest(tmp_path):
    """Test digest building."""
    (tmp_path / "datrix-common/src/datrix_common").mkdir(parents=True)
    (tmp_path / "datrix-common/src/datrix_common/__init__.py").write_text("")

    digest = build_canonical_modules_digest(tmp_path)

    assert "datrix-common" in digest
    assert "datrix_common" in digest["datrix-common"]


def test_check_cache_validity_missing_cache(tmp_path):
    """Test cache validity when cache file missing."""
    cache_path = tmp_path / "cache.json"

    valid = check_cache_validity(cache_path, tmp_path)

    assert not valid


def test_check_cache_validity_malformed_json(tmp_path):
    """Test cache validity with malformed JSON."""
    cache_path = tmp_path / "cache.json"
    cache_path.write_text("{ invalid json", encoding="utf-8")

    valid = check_cache_validity(cache_path, tmp_path)

    assert not valid


def test_format_canonical_modules_for_prompt():
    """Test prompt formatting."""
    digest = {
        "datrix-common": ["datrix_common", "datrix_common.utils.text"],
        "datrix-language": ["datrix_language.parser"],
    }

    formatted = format_canonical_modules_for_prompt(digest)

    assert "# Canonical Modules" in formatted
    assert "## datrix-common" in formatted
    assert "- datrix_common.utils.text" in formatted
