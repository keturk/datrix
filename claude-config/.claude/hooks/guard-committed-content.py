"""PreToolUse hook (Write|Edit): refuse an edit that writes a design/task reference or a customer term
into a file a package repository commits.

Both rules already have a gate and a commit-time scan (`test/design-task-reference-gate.ps1`,
`test/customer-domain-isolation-gate.ps1`, `git/commit-and-push.ps1`). Those fire after the work is
done -- a whole commit run aborts on one hit, and the agent that wrote it is long gone. This fires
on the edit that adds it, with the same detectors:

  * DESIGN/TASK REFERENCES. `test.design_task_references.text_hits`, on files the gate scans (a
    package's src/tests/docs/scripts, the showcase repo's scripts/docs/examples). Design docs and task
    files are gitignored and numbered per machine, so a reference to one from committed content is a
    dangling pointer.
  * CUSTOMER TERMS. `dev.customer_domain_isolation.scan_text` against the hashed term corpus, on every
    file inside a framework repository that git does not ignore. The message shows only the redacted
    excerpt, never the term.

A DELTA, NEVER A SCAN. The hits in the file as it would be after the edit are compared with the hits
in it now (a multiset over (label, line text)); only what the edit ADDS blocks. Paths are resolved
first, so an edit through the `d:/datrix/.claude` link lands on the repository file it really is.

Fails open: an unreadable corpus, an Edit whose old_string is not in the file, or any error allows.

Exit codes:
  0 -- allow
  2 -- block (stderr becomes feedback to Claude)
"""

import collections
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Final

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _hook_log import LIBRARY_DIR, WORKSPACE  # noqa: E402

_GIT_TIMEOUT_S: Final = 10
_CORPUS_OVERRIDE: Final = "DATRIX_TERM_CORPUS"
_MAX_SHOWN: Final = 6
_DESIGN_REMEDY: Final = (
    "Design docs (design/) and task files (.tasks/) are gitignored and numbered per machine, so a "
    "reference to one from committed content resolves to the wrong thing, or nothing, after a clone "
    "(.claude/rules/design-and-docs.md). Say WHAT the code does and WHY instead; carry over content, "
    "never a pointer to its source document."
)
_TERM_REMEDY: Final = (
    "A registered customer term may not appear in a framework repository "
    "(.claude/rules/design-and-docs.md, 'Project domain isolation'). Use the neutral e-commerce domain "
    "(Product, Order, Customer, Warehouse) or a fictional one."
)

Hit = tuple[str, str]


def _library() -> None:
    if LIBRARY_DIR not in sys.path:
        sys.path.insert(0, LIBRARY_DIR)


def _relative(path: str) -> str | None:
    """Workspace-relative posix path inside a framework repository, or None outside every one."""
    real = os.path.realpath(path).replace("\\", "/")
    root = os.path.realpath(WORKSPACE).replace("\\", "/").rstrip("/") + "/"
    if not real.lower().startswith(root.lower()):
        return None
    rel = real[len(root):]
    repo = rel.split("/", 1)[0]
    if not repo.startswith("datrix") or "/" not in rel or "/.git/" in f"/{rel}":
        return None
    return rel


def _git_ignored(rel: str) -> bool:
    repo, inner = rel.split("/", 1)
    try:
        result = subprocess.run(["git", "-C", os.path.join(WORKSPACE, repo), "check-ignore", "-q", inner],
                                capture_output=True, timeout=_GIT_TIMEOUT_S, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def _after_text(tool: str, tool_input: dict[str, object], before: str | None) -> str | None:
    if tool == "Write":
        return str(tool_input.get("content", ""))
    if before is None:
        return None
    old = str(tool_input.get("old_string", ""))
    new = str(tool_input.get("new_string", ""))
    if not old or old not in before:
        return None
    return before.replace(old, new) if tool_input.get("replace_all") else before.replace(old, new, 1)


def design_hits(text: str, rel: str) -> collections.Counter[Hit]:
    _library()
    from test.design_task_references import in_scanned_tree, text_hits

    if not in_scanned_tree(rel):
        return collections.Counter()
    return collections.Counter((label, line) for _lineno, label, line in text_hits(text, rel))


def term_hits(text: str) -> collections.Counter[Hit]:
    _library()
    from dev.customer_domain_isolation import corpus_path, load_term_corpus, scan_text

    # The override lets the hook's test plant a term of its own; hook subprocesses inherit Claude
    # Code's environment, not a shell the agent can export into, so it is no escape hatch.
    override = os.environ.get(_CORPUS_OVERRIDE)
    corpus = load_term_corpus(Path(override) if override else corpus_path(Path(WORKSPACE) / "datrix"))
    return collections.Counter(("customer term", excerpt) for _lineno, excerpt in scan_text(text, corpus))


def decide(tool: str, tool_input: dict[str, object]) -> str:
    """The refusal message, or the empty string to allow."""
    raw_path = str(tool_input.get("file_path", ""))
    rel = _relative(raw_path) if raw_path else None
    if rel is None:
        return ""
    before = _read(raw_path)
    after = _after_text(tool, tool_input, before)
    if after is None or _git_ignored(rel):
        return ""
    added_refs = design_hits(after, rel) - design_hits(before or "", rel)
    added_terms = term_hits(after) - term_hits(before or "")
    if not added_refs and not added_terms:
        return ""
    lines = [f"  - [{label}] {text}" for (label, text), count in [*added_refs.items(), *added_terms.items()]
             for _ in range(count)][:_MAX_SHOWN]
    remedies = ([_DESIGN_REMEDY] if added_refs else []) + ([_TERM_REMEDY] if added_terms else [])
    return (f"BLOCKED: this edit to `{raw_path}` writes content a package repository may not commit:\n"
            + "\n".join(lines) + "\n\n" + "\n\n".join(remedies)
            + "\n\nOnly what this edit ADDS is judged; existing content in the file never blocks an edit.")


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)
    tool = str(data.get("tool_name", ""))
    tool_input = data.get("tool_input")
    if tool not in ("Write", "Edit") or not isinstance(tool_input, dict):
        sys.exit(0)
    try:
        message = decide(tool, tool_input)
    except Exception as exc:  # noqa: BLE001 -- a guard must never wedge an edit it cannot judge
        sys.stderr.write(f"guard-committed-content: skipped: {type(exc).__name__}: {exc}\n")
        sys.exit(0)
    if message:
        sys.stderr.write(message)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
