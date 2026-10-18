#!/usr/bin/env python3
"""Repo-level gate for line-addressed editing (datrix_scripts.line_edits, dev/lib/line_edit_mcp.py).

Every check builds real files in a temporary workspace and reads or edits them through the library
or the MCP server itself, then compares the bytes on disk. Nothing outside the temporary
directory is touched.

Run through dev/line-edit-gate.ps1.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from datrix_scripts.gate_harness import CheckFunc, check_list_main
from datrix_scripts.line_edits import LineEditError, apply_edits, guard_edit, line_hash, plan_edits, read_lines
from datrix_scripts.mcp_exchange import exchange, tool_call, tool_result
from datrix_scripts.paths import script_env
from line_edit_mcp import LineEditServer

_MCP_SCRIPT = Path(__file__).resolve().parent / "line_edit_mcp.py"

_FIVE = "one\ntwo\nthree\nfour\nfive\n"


@contextmanager
def _workspace(files: dict[str, bytes]) -> Iterator[Path]:
    with TemporaryDirectory(prefix="line-edit-gate-") as temp:
        root = Path(temp) / "workspace"
        for relative, data in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        yield root


def _hashes(*texts: str) -> str:
    return "".join(line_hash(text) for text in texts)


def _replace(path: str, start: int, end: int, hashes: str, text: str) -> dict[str, object]:
    return {"file_path": path, "start": start, "end": end, "hashes": hashes, "text": text}


def _insert(path: str, after: int, hash_: str, text: str) -> dict[str, object]:
    return {"file_path": path, "after": after, "hash": hash_, "text": text}


def _refusal(root: Path, edits: list[dict[str, object]]) -> str:
    try:
        apply_edits(root, edits)
    except LineEditError as exc:
        return str(exc)
    raise AssertionError(f"expected the edits to be refused: {edits}")


# ===========================================================================
# reading
# ===========================================================================


def check_read_shows_numbered_hashed_lines() -> None:
    with _workspace({"a.py": _FIVE.encode()}) as root:
        text = read_lines(root, "a.py", 2, 2)
    assert text.splitlines() == ["a.py: lines 2-3 of 5", f"2:{line_hash('two')}|two",
                                 f"3:{line_hash('three')}|three"], text


# ===========================================================================
# editing
# ===========================================================================


def check_replace_checks_every_line_and_keeps_the_rest() -> None:
    with _workspace({"a.py": _FIVE.encode()}) as root:
        report = apply_edits(root, [_replace("a.py", 2, 3, _hashes("two", "three"), "TWO\nTHREE\nEXTRA\n")])
        assert (root / "a.py").read_bytes() == b"one\nTWO\nTHREE\nEXTRA\nfour\nfive\n", (root / "a.py").read_bytes()
        assert "a.py: 1 change(s), 5 -> 6 lines" in report and "2-3 -> 2-4 (+1)" in report, report


def check_a_wrong_hash_refuses_the_whole_call() -> None:
    with _workspace({"a.py": _FIVE.encode(), "b.py": _FIVE.encode()}) as root:
        message = _refusal(root, [
            _replace("a.py", 1, 1, _hashes("one"), "ONE"),
            _replace("b.py", 2, 3, _hashes("two", "four"), "x"),
        ])
        assert "b.py: lines 2-3 are not the lines you named (1 differ)" in message, message
        assert f"3:{line_hash('three')}|three" in message, f"the refusal must show the line now there: {message}"
        assert (root / "a.py").read_bytes() == _FIVE.encode(), "no file may be written when any edit is refused"


def check_line_numbers_refer_to_the_file_before_the_call() -> None:
    with _workspace({"a.py": _FIVE.encode()}) as root:
        report = apply_edits(root, [
            _insert("a.py", 1, line_hash("one"), "inserted-a\ninserted-b"),
            _replace("a.py", 4, 4, line_hash("four"), "FOUR"),
            _replace("a.py", 5, 5, line_hash("five"), ""),
        ])
        assert (root / "a.py").read_bytes() == b"one\ninserted-a\ninserted-b\ntwo\nthree\nFOUR\n", report
        assert "4-4 -> 6-6 (+0)" in report and "5-5 -> deleted (-1)" in report, report


def check_inserts_at_top_and_end_and_into_an_empty_file() -> None:
    with _workspace({"a.py": b"one\ntwo\n", "empty.txt": b""}) as root:
        apply_edits(root, [_insert("a.py", 0, "", "top"), _insert("a.py", 2, line_hash("two"), "end")])
        apply_edits(root, [_insert("empty.txt", 0, "", "first")])
        assert (root / "a.py").read_bytes() == b"top\none\ntwo\nend\n", (root / "a.py").read_bytes()
        assert (root / "empty.txt").read_bytes() == b"first\n", (root / "empty.txt").read_bytes()


def check_overlapping_or_misshapen_edits_are_refused() -> None:
    with _workspace({"a.py": _FIVE.encode()}) as root:
        overlap = _refusal(root, [_replace("a.py", 1, 2, _hashes("one", "two"), "x"),
                                  _replace("a.py", 2, 3, _hashes("two", "three"), "y")])
        inside = _refusal(root, [_replace("a.py", 1, 3, _hashes("one", "two", "three"), "x"),
                                 _insert("a.py", 2, line_hash("two"), "y")])
        short = _refusal(root, [_replace("a.py", 1, 2, _hashes("one"), "x")])
        mixed = _refusal(root, [{"file_path": "a.py", "start": 1, "after": 1, "text": "x"}])
        assert "two edits touch the same place" in overlap and "two edits touch the same place" in inside, (overlap,
                                                                                                          inside)
        assert "need 4 hash characters" in short and "pass exactly the keys" in mixed, (short, mixed)


def check_line_endings_bom_and_final_newline_are_kept() -> None:
    crlf = "﻿one\r\ntwo\r\nlone-lf\nfour".encode()
    with _workspace({"w.txt": crlf}) as root:
        apply_edits(root, [_replace("w.txt", 2, 2, line_hash("two"), "TWO\nTWO-B"),
                           _insert("w.txt", 4, line_hash("four"), "after-last")])
        assert (root / "w.txt").read_bytes() == "﻿one\r\nTWO\r\nTWO-B\r\nlone-lf\nfour\r\nafter-last".encode(), \
            (root / "w.txt").read_bytes()


def check_a_reply_carries_what_a_follow_up_edit_needs() -> None:
    with _workspace({"a.py": _FIVE.encode()}) as root:
        report = apply_edits(root, [_replace("a.py", 3, 3, line_hash("three"), "THREE\nTHREE-B")])
        listed = report.splitlines()[-1].split(": ", 1)[1].split()
        assert listed == [f"3:{line_hash('THREE')}", f"4:{line_hash('THREE-B')}"], report
        apply_edits(root, [_replace("a.py", 4, 4, listed[1].split(":")[1], "three-b")])
        assert (root / "a.py").read_bytes() == b"one\ntwo\nTHREE\nthree-b\nfour\nfive\n", (root / "a.py").read_bytes()


def check_only_workspace_utf8_text_files_are_touched() -> None:
    with _workspace({"a.py": _FIVE.encode(), "bin.dat": b"x\0y", "latin.txt": "caf\xe9".encode("latin-1")}) as root:
        outside = _refusal(root, [_replace(str(root.parent / "elsewhere.py"), 1, 1, "aa", "x")])
        escape = _refusal(root, [_replace("../elsewhere.py", 1, 1, "aa", "x")])
        missing = _refusal(root, [_insert("new.py", 0, "", "x")])
        binary = _refusal(root, [_insert("bin.dat", 0, "", "x")])
        latin = _refusal(root, [_insert("latin.txt", 0, "", "x")])
    assert "outside the workspace" in outside and "outside the workspace" in escape, (outside, escape)
    assert "not an existing file" in missing and "Create new files with Write" in missing, missing
    assert "NUL bytes" in binary and "not valid UTF-8" in latin, (binary, latin)


def check_guard_edit_spans_only_the_changed_lines() -> None:
    with _workspace({"a.py": _FIVE.encode()}) as root:
        [replace] = plan_edits(root, [_replace("a.py", 2, 2, line_hash("two"), "TWO")])
        [insert] = plan_edits(root, [_insert("a.py", 3, line_hash("three"), "new")])
        [top] = plan_edits(root, [_insert("a.py", 0, "", "new")])
    assert guard_edit(replace) == ("two\n", "TWO\n"), guard_edit(replace)
    assert guard_edit(insert) == ("three\n", "three\nnew\n"), guard_edit(insert)
    assert guard_edit(top) == ("one\n", "new\none\n"), guard_edit(top)


# ===========================================================================
# MCP server
# ===========================================================================


def check_mcp_server_reads_edits_and_refuses() -> None:
    with _workspace({"a.py": _FIVE.encode()}) as root:
        responses = exchange(LineEditServer(root), [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            tool_call(3, "read_lines", {"file_path": "a.py", "offset": 5}),
            tool_call(4, "edit_lines", {"edits": [_replace("a.py", 5, 5, line_hash("five"), "FIVE")]}),
            tool_call(5, "edit_lines", {"edits": [_replace("a.py", 1, 1, "zz", "x")]}),
            tool_call(6, "edit_lines", {}),
        ])
        assert responses[0]["result"]["serverInfo"]["name"] == "datrix-edit", responses[0]
        tools = responses[1]["result"]["tools"]
        assert [(t["name"], t["annotations"]["readOnlyHint"]) for t in tools] == [
            ("read_lines", True), ("edit_lines", False)], tools
        assert tool_result(responses[2]) == (False, f"a.py: lines 5-5 of 5\n5:{line_hash('five')}|five"), responses[2]
        assert not tool_result(responses[3])[0] and (root / "a.py").read_bytes().endswith(b"FIVE\n"), responses[3]
        is_error, text = tool_result(responses[4])
        assert is_error and "not the lines you named" in text, responses[4]
        is_error, text = tool_result(responses[5])
        assert is_error and "'edits' is required" in text, responses[5]


def check_mcp_server_stdout_carries_only_protocol() -> None:
    messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    result = subprocess.run([sys.executable, str(_MCP_SCRIPT)], capture_output=True, timeout=60, check=False,
                            input=b"".join(json.dumps(m).encode("utf-8") + b"\n" for m in messages), env=script_env())
    lines = result.stdout.decode("utf-8").splitlines()
    assert result.returncode == 0 and len(lines) == 2, (result.returncode, lines, result.stderr[-500:])
    assert all(json.loads(line)["jsonrpc"] == "2.0" for line in lines), lines


# ===========================================================================
# harness
# ===========================================================================


_ALL_CHECKS: list[CheckFunc] = [
    check_read_shows_numbered_hashed_lines,
    check_replace_checks_every_line_and_keeps_the_rest,
    check_a_wrong_hash_refuses_the_whole_call,
    check_line_numbers_refer_to_the_file_before_the_call,
    check_inserts_at_top_and_end_and_into_an_empty_file,
    check_overlapping_or_misshapen_edits_are_refused,
    check_line_endings_bom_and_final_newline_are_kept,
    check_a_reply_carries_what_a_follow_up_edit_needs,
    check_only_workspace_utf8_text_files_are_touched,
    check_guard_edit_spans_only_the_changed_lines,
    check_mcp_server_reads_edits_and_refuses,
    check_mcp_server_stdout_carries_only_protocol,
]


def main() -> int:
    return check_list_main("Behaviour checks for line-addressed editing.", "line-edit", _ALL_CHECKS)


if __name__ == "__main__":
    sys.exit(main())
