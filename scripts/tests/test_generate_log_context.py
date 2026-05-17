"""Tests for log-only generation context output."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_generate_module():
    module_path = Path(__file__).resolve().parent.parent / "library" / "dev" / "generate.py"
    spec = importlib.util.spec_from_file_location("datrix_scripts_generate", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    real_platform = sys.platform
    sys.platform = "testing"  # Avoid Windows stdout/stderr wrapping during import.
    try:
        spec.loader.exec_module(module)
    finally:
        sys.platform = real_platform

    return module


@pytest.mark.unit
def test_append_log_only_lines_writes_to_log_without_console(tmp_path: Path, monkeypatch, capsys) -> None:
    mod = _load_generate_module()
    log_file = tmp_path / "generate-results.log"
    monkeypatch.setenv("DATRIX_GENERATE_LOG_FILE", str(log_file))

    mod._append_log_only_lines(
        [
            "Generating project: example",
            " Source: D:/src/example.dtrx",
            " Output: D:/out/example",
            "",
        ]
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert log_file.read_text(encoding="utf-8") == (
        "Generating project: example\n"
        " Source: D:/src/example.dtrx\n"
        " Output: D:/out/example\n"
        "\n"
    )

