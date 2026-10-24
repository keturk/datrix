#!/usr/bin/env python3
"""Repo-level gate for line-addressed editing (``datrix_scripts.line_edits``, ``datrix_scripts.dev.line_edit_mcp``).

Every check builds real files in a temporary workspace and reads or edits them through the library
or the MCP server itself, then compares the bytes on disk. Nothing outside the temporary
directory is touched.

Run through ``dev/line-edit-gate.ps1`` (and its ``.sh`` twin). ``--only PREFIX`` runs the checks
whose name starts with PREFIX. ``--harness-self-test`` proves the harness reports a deliberately
failing check as failed; ``--self-test`` adds the wrapper seam checks.

Exit codes: 0 = every check passed, 1 = at least one check failed, 2 = usage error.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from datrix_scripts.dev.line_edit import MCP_SERVER_MODULE, MCP_SERVER_NAME
from datrix_scripts.dev.line_edit_mcp import LineEditServer
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, CheckFunc, check_list_main, check_list_parser
from datrix_scripts.gate_log import run_as_gate
from datrix_scripts.line_edits import (
    LineEditError,
    apply_edits,
    guard_edit,
    line_hash,
    plan_edits,
    read_lines,
    read_symbols,
)
from datrix_scripts.mcp_exchange import exchange, tool_call, tool_result
from datrix_scripts.paths import script_env
from datrix_scripts.symbol_spans import find_spans, span_hash
from datrix_scripts.test.wrappers import DEV_SCRIPTS_DIR, seam_checks

MODULE = "datrix_scripts.dev.line_edit_gate"
WRAPPER = "line-edit-gate"
GATE = "line-edit"

_FIVE = "one\ntwo\nthree\nfour\nfive\n"

_SOURCE_LINES = [
    "import os",
    "",
    "LIMIT: int = 3",
    "",
    "# note on helper",
    "@staticmethod",
    "def helper(x):",
    "    return x",
    "",
    "",
    "class Box:",
    "    size = 1",
    "",
    "    def get(self):",
    "        return self.size",
    "",
    "    async def put(self, v):",
    "        self.size = v",
    "",
    "",
    "if os.name == 'nt':",
    "    def plat():",
    "        return 'nt'",
    "else:",
    "    def plat():",
    "        return 'posix'",
]
_SOURCE = "\n".join(_SOURCE_LINES) + "\n"


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


def _replace_symbol(path: str, symbol: str, hash_: str, text: str) -> dict[str, object]:
    return {"file_path": path, "symbol": symbol, "span_hash": hash_, "text": text}


def _insert_after_symbol(path: str, symbol: str, hash_: str, text: str) -> dict[str, object]:
    return {"file_path": path, "after_symbol": symbol, "span_hash": hash_, "text": text}


def _source_hash(first: int, last: int) -> str:
    """The span hash of source lines ``first``..``last`` (1-based, inclusive) of ``_SOURCE``."""
    return span_hash(_SOURCE_LINES[first - 1:last])


def _refusal(root: Path, edits: list[dict[str, object]]) -> str:
    try:
        apply_edits(root, edits)
    except LineEditError as exc:
        return str(exc)
    raise AssertionError(f"expected the edits to be refused: {edits}")


def _read_refusal(root: Path, path: str, symbols: list[str]) -> str:
    try:
        read_symbols(root, path, symbols)
    except LineEditError as exc:
        return str(exc)
    raise AssertionError(f"expected the read of {symbols} in {path} to be refused")


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
# symbols
# ===========================================================================


def check_symbol_read_shows_lines_with_the_span_hash() -> None:
    with _workspace({"m.py": _SOURCE.encode()}) as root:
        text = read_symbols(root, "m.py", ["helper", "Box.get", "LIMIT"])
    expected = [
        f"m.py: helper (def) lines 5-8 of 26, span hash {_source_hash(5, 8)}",
        *(f"{n}:{line_hash(_SOURCE_LINES[n - 1])}|{_SOURCE_LINES[n - 1]}" for n in range(5, 9)),
        "",
        f"m.py: Box.get (def) lines 14-15 of 26, span hash {_source_hash(14, 15)}",
        *(f"{n}:{line_hash(_SOURCE_LINES[n - 1])}|{_SOURCE_LINES[n - 1]}" for n in range(14, 16)),
        "",
        f"m.py: LIMIT (variable) lines 3-3 of 26, span hash {_source_hash(3, 3)}",
        f"3:{line_hash(_SOURCE_LINES[2])}|{_SOURCE_LINES[2]}",
    ]
    assert text.splitlines() == expected, text


def check_symbol_names_cover_nesting_blocks_and_comments() -> None:
    spans = [(s.qualname, s.kind, s.start, s.end) for s in find_spans("m.py", _SOURCE_LINES)]
    assert spans == [
        ("LIMIT", "variable", 3, 3), ("helper", "def", 5, 8), ("Box", "class", 11, 18), ("Box.size", "variable", 12, 12),
        ("Box.get", "def", 14, 15), ("Box.put", "async def", 17, 18), ("plat", "def", 22, 23), ("plat", "def", 25, 26),
    ], spans


def check_replace_symbol_swaps_the_whole_symbol() -> None:
    new = "    def get(self):\n        # one\n        return 1"
    with _workspace({"m.py": _SOURCE.encode()}) as root:
        [change] = plan_edits(root, [_replace_symbol("m.py", "Box.get", _source_hash(14, 15), new)])
        # The guards see the lines that differ: the shared "def" line is trimmed from both sides.
        assert guard_edit(change) == ("        return self.size\n", "        # one\n        return 1\n"), guard_edit(change)
        report = apply_edits(root, [_replace_symbol("m.py", "Box.get", _source_hash(14, 15), new)])
        expected = "\n".join([*_SOURCE_LINES[:13], *new.split("\n"), *_SOURCE_LINES[15:]]) + "\n"
        assert (root / "m.py").read_bytes() == expected.encode(), (root / "m.py").read_bytes()
        assert "m.py: 1 change(s), 26 -> 27 lines" in report and "14-15 -> 14-16 (+1)" in report, report


def check_replace_symbol_with_nothing_deletes_it() -> None:
    with _workspace({"m.py": _SOURCE.encode()}) as root:
        apply_edits(root, [_replace_symbol("m.py", "helper", _source_hash(5, 8), "")])
        expected = "\n".join([*_SOURCE_LINES[:4], *_SOURCE_LINES[8:]]) + "\n"
        assert (root / "m.py").read_bytes() == expected.encode(), (root / "m.py").read_bytes()


def check_insert_after_symbol_lands_below_its_last_line() -> None:
    text = "\n    def size_of(self):\n        return 1"
    with _workspace({"m.py": _SOURCE.encode()}) as root:
        apply_edits(root, [_insert_after_symbol("m.py", "Box.put", _source_hash(17, 18), text)])
        expected = "\n".join([*_SOURCE_LINES[:18], *text.split("\n"), *_SOURCE_LINES[18:]]) + "\n"
        assert (root / "m.py").read_bytes() == expected.encode(), (root / "m.py").read_bytes()


def check_a_stale_span_hash_refuses_and_shows_the_symbol() -> None:
    with _workspace({"m.py": _SOURCE.encode()}) as root:
        message = _refusal(root, [_replace_symbol("m.py", "Box.get", "00000000", "x"),
                                  _replace_symbol("m.py", "helper", _source_hash(5, 8), "y")])
        assert "Box.get (lines 14-15) is not the text you named" in message, message
        assert f"now {_source_hash(14, 15)}" in message and "14:" in message, message
        assert (root / "m.py").read_bytes() == _SOURCE.encode(), "no file may be written when any edit is refused"


def check_unknown_ambiguous_and_unparsable_symbols_are_refused() -> None:
    with _workspace({"m.py": _SOURCE.encode(), "n.txt": b"x = 1\n", "bad.py": b"def (:\n"}) as root:
        unknown = _read_refusal(root, "m.py", ["nope"])
        twice = _read_refusal(root, "m.py", ["plat"])
        pinned = read_symbols(root, "m.py", ["plat@25"])
        not_python = _read_refusal(root, "n.txt", ["x"])
        unparsable = _read_refusal(root, "bad.py", ["x"])
        no_symbols = _read_refusal(root, "m.py", [])
    assert "has no symbol 'nope'" in unknown and "Box.get" in unknown, unknown
    assert "'plat' is defined more than once" in twice and "plat@22" in twice and "plat@25" in twice, twice
    assert "return 'posix'" in pinned and "return 'nt'" not in pinned, pinned
    assert "Python (.py) files only" in not_python and "does not parse" in unparsable, (not_python, unparsable)
    assert "'symbols' is required" in no_symbols, no_symbols


def check_symbol_and_line_edits_mix_and_overlaps_are_refused() -> None:
    with _workspace({"m.py": _SOURCE.encode()}) as root:
        apply_edits(root, [_replace("m.py", 1, 1, line_hash("import os"), "import os, sys"),
                           _replace_symbol("m.py", "Box.get", _source_hash(14, 15), "    def get(self):\n        pass")])
        expected = "\n".join(["import os, sys", *_SOURCE_LINES[1:13], "    def get(self):", "        pass",
                              *_SOURCE_LINES[15:]]) + "\n"
        assert (root / "m.py").read_bytes() == expected.encode(), (root / "m.py").read_bytes()
    with _workspace({"m.py": _SOURCE.encode()}) as root:
        overlap = _refusal(root, [_replace_symbol("m.py", "Box", _source_hash(11, 18), "class Box: ..."),
                                  _replace_symbol("m.py", "Box.get", _source_hash(14, 15), "    def get(self): ...")])
    assert "two edits touch the same place" in overlap, overlap


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
        assert responses[0]["result"]["serverInfo"]["name"] == MCP_SERVER_NAME, responses[0]
        tools = responses[1]["result"]["tools"]
        assert [(t["name"], t["annotations"]["readOnlyHint"]) for t in tools] == [
            ("read_lines", True), ("read_symbol", True), ("edit_lines", False)], tools
        assert tool_result(responses[2]) == (False, f"a.py: lines 5-5 of 5\n5:{line_hash('five')}|five"), responses[2]
        assert not tool_result(responses[3])[0] and (root / "a.py").read_bytes().endswith(b"FIVE\n"), responses[3]
        is_error, text = tool_result(responses[4])
        assert is_error and "not the lines you named" in text, responses[4]
        is_error, text = tool_result(responses[5])
        assert is_error and "'edits' is required" in text, responses[5]


def check_mcp_server_reads_and_edits_symbols() -> None:
    with _workspace({"m.py": _SOURCE.encode()}) as root:
        responses = exchange(LineEditServer(root), [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            tool_call(2, "read_symbol", {"file_path": "m.py", "symbols": ["Box.get"]}),
            tool_call(3, "edit_lines", {"edits": [_replace_symbol("m.py", "Box.get", _source_hash(14, 15),
                                                                  "    def get(self):\n        return 2")]}),
            tool_call(4, "read_symbol", {"file_path": "m.py", "symbols": ["Box.get"]}),
            tool_call(5, "read_symbol", {"file_path": "m.py"}),
            tool_call(6, "read_symbol", {"file_path": "m.py", "symbols": ["nope"]}),
        ])
        first, edited, reread = tool_result(responses[1]), tool_result(responses[2]), tool_result(responses[3])
    assert not first[0] and first[1].startswith(f"m.py: Box.get (def) lines 14-15 of 26, span hash "
                                                f"{_source_hash(14, 15)}"), first
    assert not edited[0] and "14-15 -> 14-15 (+0)" in edited[1], edited
    new_hash = span_hash(["    def get(self):", "        return 2"])
    assert not reread[0] and f"span hash {new_hash}" in reread[1] and "return 2" in reread[1], reread
    is_error, text = tool_result(responses[4])
    assert is_error and "'symbols' is required" in text, responses[4]
    is_error, text = tool_result(responses[5])
    assert is_error and "has no symbol 'nope'" in text, responses[5]


def check_mcp_server_stdout_carries_only_protocol() -> None:
    messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    # Started as .mcp.json starts it (line-edit.ps1 -Setup): the module, under this interpreter.
    result = subprocess.run([sys.executable, "-m", MCP_SERVER_MODULE], capture_output=True, timeout=60, check=False,
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
    check_symbol_read_shows_lines_with_the_span_hash,
    check_symbol_names_cover_nesting_blocks_and_comments,
    check_replace_symbol_swaps_the_whole_symbol,
    check_replace_symbol_with_nothing_deletes_it,
    check_insert_after_symbol_lands_below_its_last_line,
    check_a_stale_span_hash_refuses_and_shows_the_symbol,
    check_unknown_ambiguous_and_unparsable_symbols_are_refused,
    check_symbol_and_line_edits_mix_and_overlaps_are_refused,
    check_mcp_server_reads_edits_and_refuses,
    check_mcp_server_reads_and_edits_symbols,
    check_mcp_server_stdout_carries_only_protocol,
]


def build_parser() -> argparse.ArgumentParser:
    """The options of ``dev/line-edit-gate.ps1``: one per wrapper parameter, spelled exactly."""
    return check_list_parser(
        "Behaviour checks for line-addressed editing.",
        debug_flag=WRAPPER_DEBUG_FLAG,
        allow_abbrev=False,
    )


def _gate(argv: Sequence[str] | None) -> int:
    # --self-test: the harness reports a deliberate failure, and the wrapper is the template rendered
    # with this parser's options.
    parser = build_parser()
    return check_list_main(
        parser.description or "",
        GATE,
        _ALL_CHECKS,
        self_test=seam_checks(wrapper=WRAPPER, module=MODULE, parser=parser, folder=DEV_SCRIPTS_DIR),
        argv=argv,
        parser=parser,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the verdict, in gate mode."""
    return run_as_gate(GATE, MODULE, _gate, argv)


if __name__ == "__main__":
    sys.exit(main())
