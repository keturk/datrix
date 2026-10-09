"""Exercise inject-task-orientation.py: a task's ## Orientation answered when the task file is read.

``decide`` is driven in-process against a temp workspace (a framework repository holding real
Python, a task file under ``.tasks/phase-NN``) with the real code index over it and a real
Ollama-shaped server on loopback; the entry point is driven as a subprocess for the cases
that must never reach the index or a model. Both directions, on purpose:

  ANSWER -- the first read of a task file that carries an Orientation block: facts exact from the
            index, an explanation from the model marked as a lead, a stale entry called out.
  SILENT -- the repeat, a ranged read of the middle, a task with no block, a file that is not a task,
            another tool, unparseable input; and no model server, where the facts are still given.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOKS = os.path.dirname(os.path.abspath(__file__))
SESSION = "TEST-inject-task-orientation"
fails: list[str] = []


def check(label: str, got: object, want: object) -> None:
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f"  (got {got!r}, want {want!r})"))
    if not ok:
        fails.append(f"{label}: got {got!r}, want {want!r}")


spec = importlib.util.spec_from_file_location("inject_task_orientation", os.path.join(HOOKS, "inject-task-orientation.py"))
assert spec is not None and spec.loader is not None
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)
hook.add_scripts_lib_to_path()
from datrix_scripts.customer_domain_isolation import corpus_path  # noqa: E402
from datrix_scripts.local_llm import LocalLlmSettings  # noqa: E402
from datrix_scripts.local_llm_loopback import LOOPBACK, LoopbackOllama, answering, closed_port  # noqa: E402

ANSWER = "Tests build the service with a factory and add the enum to its enums, at datrix-alpha/src/a.py:1."


def settings_for(port: int, usage_log: Path) -> LocalLlmSettings:
    return LocalLlmSettings(machines=(LOOPBACK,), reachable_timeout_ms=2000, generate_timeout_ms=5000,
                            allow_load=False, ollama_port=port, usage_log=usage_log, caller=hook.CALLER)


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


TASK = """# Task 90-01: Orientation fixture

## Overview
A fixture.

**Package:** `datrix-alpha`
**Depends on:** None

## Files to Review Before Starting
1. `{rules}` -- the rules

## Orientation

```orientation
# a comment
symbol: alpha_function
refs: alpha_pkg.core.alpha_function
symbol: renamed_away_function
explain: {explained} :: How does this module build its result and which helper does it call?
```

## Files to Create
Nothing.
"""
BARE = "# Task 90-02: No orientation\n\n## Overview\nNothing to answer.\n"
CORE = '"""Core."""\n\n\ndef alpha_function(x: int) -> int:\n    """Add one."""\n    return x + 1\n\n\ndef caller() -> int:\n    return alpha_function(2)\n'


def read(path: Path, agent: str = "", **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {"tool_name": "Read", "tool_input": {"file_path": str(path), **extra},
                                  "session_id": SESSION}
    if agent:
        payload["agent_id"] = agent
    return payload


def run_hook(payload: object, raw: str | None = None) -> tuple[int, str]:
    process = subprocess.run([sys.executable, os.path.join(HOOKS, "inject-task-orientation.py")],
                             input=raw if raw is not None else json.dumps(payload), capture_output=True, text=True,
                             timeout=60)
    return process.returncode, process.stdout


def cleanup_state() -> None:
    for item in Path(hook._STATE_DIR).glob(f"task-orientation-{SESSION}*.json"):
        item.unlink(missing_ok=True)


cleanup_state()
try:
    with tempfile.TemporaryDirectory(prefix="orientation-hook-") as temp, \
            LoopbackOllama(answering(ANSWER), ("orient-model",)) as server:
        workspace = Path(temp)
        for repo in ("datrix", "datrix-alpha"):
            (workspace / repo).mkdir()
            subprocess.run(["git", "-C", str(workspace / repo), "init", "-q"], check=True, capture_output=True)
        core = write(workspace / "datrix-alpha/src/alpha_pkg/core.py", CORE)
        write(workspace / "datrix-alpha/src/alpha_pkg/__init__.py", "")
        task = write(workspace / "datrix-alpha/.tasks/phase-90/task-90-01-orientation-fixture.md",
                     TASK.format(rules=str(core), explained=str(core)))
        bare = write(workspace / "datrix-alpha/.tasks/phase-90/task-90-02-no-orientation.md", BARE)
        notes = write(workspace / "datrix-alpha/docs/notes.md", "# Notes\n")
        # Nothing reaches a local model without the customer-term corpus; an empty one filters nothing.
        write(corpus_path(workspace / "datrix"), json.dumps({"algorithm": "sha256", "terms": []}))
        settings = settings_for(server.port, workspace / "usage.jsonl")

        def decide(payload: dict[str, object], with_settings: LocalLlmSettings = settings) -> str:
            return hook.decide(payload, workspace, with_settings)

        print("== ANSWER: the first read of a task that carries an Orientation block ==")
        text = decide(read(task))
        check("it opens by saying what it is", text.startswith("Orientation for task-90-01"), True)
        check("a fact is the index's exact answer, with file:line",
              "datrix-alpha/src/alpha_pkg/core.py:4  def alpha_function(x: int) -> int" in text, True)
        check("the references name the call site by line", "core.py: 10 call" in text, True)
        check("an explanation is the model's, marked as a lead",
              ANSWER in text and "A lead, not a finding" in text, True)
        check("an entry that no longer exists is called out as a stale premise",
              "STALE TASK PREMISE" in text and "symbol renamed_away_function" in text, True)
        check("the model was asked once", len(server.chats), 1)
        usage = [json.loads(line)["caller"] for line in (workspace / "usage.jsonl").read_text(encoding="utf-8").splitlines()]
        check("its request is in the usage log under the hook's name", set(usage), {"hook:task-orientation"})

        print("== SILENT: every way the hook must add nothing ==")
        check("the repeat read, by the same agent", decide(read(task)), "")
        check("a different agent has its own context", decide(read(task, agent="a1")).startswith("Orientation for"), True)
        check("a ranged read of the middle", decide(read(task, agent="a2", offset=40, limit=20)), "")
        check("a task with no Orientation block", decide(read(bare)), "")
        check("a file that is not a task", decide(read(notes)), "")
        check("a task that does not exist", decide(read(workspace / "datrix-alpha/.tasks/phase-90/task-90-99-x.md")), "")
        check("another tool", decide({"tool_name": "Grep", "tool_input": {"pattern": "x"}}), "")

        print("== no model server: the facts are still given, the explanation says so ==")
        before = len(server.chats)
        down = settings_for(closed_port(), workspace / "usage.jsonl")
        degraded = decide(read(task, agent="a3"), down)
        check("the exact facts are there", "def alpha_function" in degraded, True)
        check("the explanation is reported unavailable, not invented", "UNAVAILABLE" in degraded and ANSWER not in degraded, True)
        check("no model request reached the live server", len(server.chats), before)

        print("== the entry point ==")
        check("a file that is not a task", run_hook(read(notes)), (0, ""))
        check("another tool", run_hook({"tool_name": "Bash", "tool_input": {"command": "ls"}}), (0, ""))
        check("unparseable input", run_hook(None, raw="{not json"), (0, ""))
        check("input that is not an object", run_hook(None, raw="[1]"), (0, ""))
finally:
    cleanup_state()

print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for failure in fails:
        print("  - " + failure)
    sys.exit(1)
print("all checks passed")
