"""One-off: move ``subscribe`` blocks from inside ``pubsub`` to service level (Phase 01).

Assumes space-indented DSL sources (examples/fixtures). Run from repo root:

  python datrix/scripts/dev/migrate_subscribe_out_of_pubsub.py path1.dtrx path2.dtrx ...
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


_PUBSUB_START = re.compile(r"^(\s*)pubsub\s")


def _brace_balance_to_zero(lines: list[str], start: int) -> int:
    """Return index after line that closes brace depth to zero (start at first line with ``{``)."""
    depth = 0
    started = False
    j = start
    while j < len(lines):
        for ch in lines[j]:
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1
        j += 1
        if started and depth == 0:
            return j
    raise ValueError("Unbalanced braces while scanning pubsub block")


def _dedent_lines(lines: list[str], strip_prefix_len: int) -> list[str]:
    out: list[str] = []
    for ln in lines:
        if ln.strip() == "":
            out.append(ln)
            continue
        lead = 0
        while lead < len(ln) and ln[lead] == " ":
            lead += 1
        if lead >= strip_prefix_len:
            out.append(ln[strip_prefix_len:])
        else:
            out.append(ln.lstrip() if ln.strip() else ln)
    return out


def _extract_subscribe_blocks(
    body_lines: list[str],
    service_indent_len: int,
) -> tuple[list[str], list[str]]:
    """Return (body_without_subscribes, subscribe_blocks_concat_each_trailing_newline)."""
    i = 0
    kept: list[str] = []
    extracted: list[str] = []
    inner_base = service_indent_len + 4
    sub_start = re.compile("^" + (" " * inner_base) + r"subscribe\s")

    while i < len(body_lines):
        line = body_lines[i]
        if sub_start.match(line):
            # subscribe block: brace depth from first `{` on this or following lines
            block_lines: list[str] = []
            depth = 0
            started = False
            while i < len(body_lines):
                cur = body_lines[i]
                block_lines.append(cur)
                for ch in cur:
                    if ch == "{":
                        depth += 1
                        started = True
                    elif ch == "}":
                        depth -= 1
                i += 1
                if started and depth == 0:
                    break
            strip_n = inner_base - service_indent_len
            extracted.extend(_dedent_lines(block_lines, strip_n))
            if not extracted[-1].endswith("\n"):
                extracted[-1] += "\n"
            continue
        kept.append(line)
        i += 1
    return kept, extracted


def migrate_file(path: Path) -> bool:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    changed = False
    while i < len(lines):
        line = lines[i]
        m = _PUBSUB_START.match(line)
        if not m:
            out.append(line)
            i += 1
            continue
        service_indent_len = len(m.group(1))
        block_start = i
        # include header line through opening brace line(s)
        j = i
        while j < len(lines) and "{" not in lines[j]:
            j += 1
        if j >= len(lines):
            out.extend(lines[block_start:])
            break
        header_end = j + 1
        close_end = _brace_balance_to_zero(lines, j)
        pubsub_lines = lines[block_start:close_end]
        # body: between first `{` line and last `}` before outer close
        first_brace = j
        inner_close = close_end - 1  # index of line with final `}`
        body_lines = lines[header_end:inner_close]
        kept_body, subs = _extract_subscribe_blocks(body_lines, service_indent_len)
        while kept_body and kept_body[-1].strip() == "":
            kept_body.pop()
        while kept_body:
            stripped = kept_body[-1].strip()
            if stripped.startswith("//") and "subscribe" in stripped.lower():
                kept_body.pop()
                while kept_body and kept_body[-1].strip() == "":
                    kept_body.pop()
            else:
                break
        if not subs:
            out.extend(pubsub_lines)
            i = close_end
            continue
        changed = True
        rebuilt = (
            lines[block_start:header_end]
            + kept_body
            + [lines[inner_close]]
        )
        out.extend(rebuilt)
        out.extend(subs)
        i = close_end
    if not changed:
        return False
    new_text = "".join(out)
    path.write_text(new_text, encoding="utf-8")
    return True


_DEFAULT_ROOTS = (
    Path("datrix/examples"),
    Path("datrix-common/tests/fixtures"),
    Path("datrix-codegen-python/tests/fixtures"),
    Path("datrix-codegen-typescript/tests/fixtures"),
    Path("datrix-language/tests/fixtures"),
    Path("datrix-projects"),
)


def main() -> None:
    if "--default-roots" in sys.argv[1:]:
        paths: list[Path] = []
        for root in _DEFAULT_ROOTS:
            if root.exists():
                paths.extend(root.rglob("*.dtrx"))
    else:
        paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        print(
            "usage: migrate_subscribe_out_of_pubsub.py <files...> | --default-roots",
            file=sys.stderr,
        )
        sys.exit(2)
    for p in sorted(set(paths)):
        if migrate_file(p):
            print(f"updated {p}")


if __name__ == "__main__":
    main()
