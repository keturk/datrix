"""Score the cognitive complexity of every function in Python sources read from stdin.

The edit guard (``claude-config/.claude/hooks/guard-code-standards.py``) runs under whatever
``python`` the harness finds, which does not carry the shared venv's tools, so it asks the shared
venv's interpreter to score the sources an edit compares:

    python -m datrix_scripts.cognitive_scores < sources.json > scores.json

stdin is a JSON array of source texts; stdout is a JSON array with one entry per source, each a
list of ``[line, column, score]`` for every ``def`` and ``async def`` in it. A source that does not
parse scores no function. A function the scorer cannot read is left out (``complexity.py`` reports
it). A missing ``cognitive_complexity`` refuses with exit 1 and the venv repair on stderr.
"""

from __future__ import annotations

import ast
import json
import sys

from datrix_scripts.venv import SCRIPTS_DEPENDENCY_GROUP, missing_declared_tool

try:
    from cognitive_complexity.api import get_cognitive_complexity
except ImportError as exc:
    raise SystemExit(missing_declared_tool("cognitive_complexity", SCRIPTS_DEPENDENCY_GROUP)) from exc

FunctionScore = tuple[int, int, int]

# What the scorer raises on a construct it cannot read.
_UNSCORABLE_ERRORS = (RecursionError, ValueError, TypeError, AttributeError)


def function_scores(source: str) -> list[FunctionScore]:
    """``(line, column, score)`` of every function in ``source``; empty when it does not parse."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    scores: list[FunctionScore] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        try:
            scores.append((node.lineno, node.col_offset, get_cognitive_complexity(node)))
        except _UNSCORABLE_ERRORS:
            continue
    return scores


def main() -> int:
    try:
        sources = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        sources = exc
    if not isinstance(sources, list) or not all(isinstance(source, str) for source in sources):
        print(f"Error: stdin must be a JSON array of source texts, e.g. [\"def f(): ...\"]; got: {sources!r:.200}",
              file=sys.stderr)
        return 1
    json.dump([function_scores(source) for source in sources], sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
