"""Canonical modules scanner with git-based cache invalidation.

Scans all datrix-* packages to build a digest of:
1. Canonical module paths (importable Python modules)
2. Common non-existent module patterns (agents often guess these incorrectly)

Caches results with git-based invalidation to avoid 15s rebuild per run.
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def discover_datrix_packages(datrix_root: Path) -> list[Path]:
    """Discover all datrix-* package directories."""
    packages = []
    for repo_dir in datrix_root.glob("datrix*"):
        if repo_dir.is_dir() and (repo_dir / "src").exists():
            packages.append(repo_dir)
    return sorted(packages)


def scan_package_modules(package_dir: Path) -> list[str]:
    """Scan a package's src/ tree for all importable module paths.

    Example: datrix-common/src/datrix_common/utils/text.py
             → "datrix_common.utils.text"
    """
    src_dir = package_dir / "src"
    if not src_dir.exists():
        return []

    modules = []
    for py_file in src_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            # Package: datrix_common/utils/__init__.py → datrix_common.utils
            relative = py_file.parent.relative_to(src_dir)
            module = str(relative).replace("/", ".").replace("\\", ".")
            modules.append(module)
        else:
            # Module: datrix_common/utils/text.py → datrix_common.utils.text
            relative = py_file.relative_to(src_dir)
            module = str(relative.with_suffix("")).replace("/", ".").replace("\\", ".")
            modules.append(module)

    return sorted(set(modules))


def build_canonical_modules_digest(datrix_root: Path) -> dict[str, list[str]]:
    """Build complete canonical modules digest for all datrix packages.

    Returns:
        {
            "datrix-common": ["datrix_common", "datrix_common.utils.text", ...],
            "datrix-language": ["datrix_language.parser", ...],
            ...
        }
    """
    packages = discover_datrix_packages(datrix_root)
    digest = {}

    for package_dir in packages:
        package_name = package_dir.name
        modules = scan_package_modules(package_dir)
        digest[package_name] = modules
        logger.info(
            "scanned_package package=%s modules=%d",
            package_name,
            len(modules),
        )

    return digest


def get_git_modification_time(repo_path: Path) -> str | None:
    """Get last modification time for Python files in repo via git log.

    Returns ISO-8601 timestamp or None if git fails.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_path),
                "log",
                "-1",
                "--format=%cI",
                "--",
                "src/**/*.py",
                "**/__init__.py",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def check_cache_validity(cache_path: Path, datrix_root: Path) -> bool:
    """Check if cache is valid (no module changes since cache build).

    Uses git diff to detect changes to Python module files since cache build.
    """
    if not cache_path.exists():
        return False

    try:
        with cache_path.open("r", encoding="utf-8") as f:
            cache_data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False

    cache_timestamp = cache_data.get("built_at")
    if not cache_timestamp:
        return False

    # Check each tracked package for module changes since cache build
    packages = discover_datrix_packages(datrix_root)
    for package_dir in packages:
        last_mod = get_git_modification_time(package_dir)
        if last_mod and last_mod > cache_timestamp:
            logger.info(
                "cache_invalid package=%s last_mod=%s cache_built=%s",
                package_dir.name,
                last_mod,
                cache_timestamp,
            )
            return False

    logger.info("cache_valid timestamp=%s", cache_timestamp)
    return True


def load_or_build_cache(cache_path: Path, datrix_root: Path) -> dict[str, list[str]]:
    """Load canonical modules digest from cache, or rebuild if invalid."""
    if check_cache_validity(cache_path, datrix_root):
        logger.info("loading_cache path=%s", cache_path)
        with cache_path.open("r", encoding="utf-8") as f:
            cache_data = json.load(f)
            return cache_data["digest"]

    logger.info("rebuilding_cache path=%s", cache_path)
    digest = build_canonical_modules_digest(datrix_root)

    # Write cache
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_data = {
        "built_at": datetime.now(UTC).isoformat(),
        "digest": digest,
    }
    with cache_path.open("w", encoding="utf-8") as f:
        json.dump(cache_data, f, indent=2)

    logger.info(
        "cache_written path=%s modules=%d",
        cache_path,
        sum(len(m) for m in digest.values()),
    )
    return digest


def format_canonical_modules_for_prompt(digest: dict[str, list[str]]) -> str:
    """Format canonical modules digest for inclusion in reviewer prompt."""
    lines = ["# Canonical Modules (importable Python packages)\n"]
    for package, modules in sorted(digest.items()):
        lines.append(f"## {package}")
        for module in modules[:50]:  # Truncate per package to fit context window
            lines.append(f"- {module}")
        if len(modules) > 50:
            lines.append(f"... ({len(modules) - 50} more modules)")
        lines.append("")

    return "\n".join(lines)
