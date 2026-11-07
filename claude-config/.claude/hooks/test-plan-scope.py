"""Exercise guard-plan-scope.py end to end with synthetic payloads.

The failure this holds: a `/fix-test-suites` session wrote `scripts: test/failure-ledger.ps1,
test/test.ps1` and `paths: d:/datrix/**`. The guard split on spaces only and compared raw entries,
so the locked scope named no script and no file, and it refused the job's first script as "not part
of Jon's order" when working every repo and running their suites is exactly what that skill orders.

Both directions, on purpose: every spelling of an entry reaches the same scope, a call outside the
scope is still refused, and only a workspace-wide skill lifts the fence.

The second failure: `guard-test-run-discipline.py` refused every test run until the edited fixture
was probed, this guard refused the probe, and a locked scope left a headless session no way out. The
checks send the guard's own `PROBE_COMMAND` through here, so the two cannot drift apart again.

The third failure: a headless `UNIT:` session wrote a scope too narrow for its unit. Only a message of
Jon's could widen it and none ever comes, so the unit stayed unticked until the chain stopped. The
checks run both ways: unattended, the plan widens and what it does not declare stays refused;
attended, a plan edit still widens nothing.
"""
import json
import os
import subprocess
import sys

H = r"d:\datrix\.claude\hooks"
sys.path.insert(0, H)
sys.path.insert(0, r"d:\datrix\datrix\scripts\common\lib")

from _agent_plan import UNATTENDED_ENV as UNATTENDED_VARIABLE  # noqa: E402
from _fixture_probe import PROBE_COMMAND  # noqa: E402
from datrix_scripts.skill.chain import UNATTENDED_VARIABLE as CHAIN_VARIABLE  # noqa: E402

SID ="TESTSESSION-plan-scope"
PLAN = os.path.join(r"d:\datrix\.agent_output", f"plan-{SID}.md")
STATE = os.path.join(H, ".state", f"scope-{SID}.json")
TRANSCRIPT = r"D:\datrix\.tmp\plan-scope-test-transcript.jsonl"
MISSING_TRANSCRIPT = r"D:\datrix\.tmp\nonexistent.jsonl"
LEDGER = 'powershell -File "d:/datrix/datrix/scripts/test/failure-ledger.ps1" -Status'
SPLIT = 'powershell -File "d:/datrix/datrix/scripts/dev/split-module.ps1" a.py'
ASSIST = 'powershell -File "d:/datrix/datrix/scripts/skill/skill-assist.ps1" absorb-references --design x.md'
COMMON_SOURCE = r"D:\datrix\datrix-common\src\datrix_common\x.py"

fails = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}  (got {got!r}, want {want!r})")
    if not ok:
        fails.append(f"{label}: got {got!r}, want {want!r}")


def reset(*extra):
    for path in (STATE, PLAN, *extra):
        if os.path.isfile(path):
            os.remove(path)


def transcript(*entries):
    os.makedirs(os.path.dirname(TRANSCRIPT), exist_ok=True)
    with open(TRANSCRIPT, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return TRANSCRIPT


def jon(text):
    return {"type": "user", "message": {"content": [{"type": "text", "text": text}]}}


def typed_skill(name):
    return {"type": "user", "message": {"content": (
        f"<command-message>{name}</command-message>\n<command-name>/{name}</command-name>\n"
        "<command-args>x/index.json</command-args>")}}


def skill_body(name):
    return {"type": "user", "isMeta": True, "message": {"content": [{"type": "text", "text": (
        f"Base directory for this skill: d:\\datrix\\.claude\\skills\\{name}\n\n# {name}\n")}]}}


def run_guard(payload):
    run = subprocess.run([sys.executable, os.path.join(H, "guard-plan-scope.py")],
                         input=json.dumps(payload), capture_output=True, text=True)
    return "block" if run.returncode == 2 else "allow"


def guard(scope_lines, tool_name, tool_input, transcript_path=MISSING_TRANSCRIPT):
    """Run the guard once on a fresh lock; return "allow" or "block"."""
    reset()
    os.makedirs(os.path.dirname(PLAN), exist_ok=True)
    with open(PLAN, "w", encoding="utf-8") as f:
        f.write(f"## Steps\n- [ ] step\n\n## Scope\n{scope_lines}\n\n## Verification\n")
    return run_guard({"session_id": SID, "transcript_path": transcript_path, "tool_name": tool_name, "tool_input": tool_input})


def shell(command):
    return "PowerShell", {"command": command}


def edit(path):
    return "Edit", {"file_path": path}


print("script entries, every spelling")
for spelling in ("failure-ledger", "failure-ledger, test", "test/failure-ledger.ps1, test/test.ps1",
                 r"test\failure-ledger.ps1", "Failure-Ledger.PS1"):
    check(f"`scripts: {spelling}` admits failure-ledger", guard(f"paths: **\nscripts: {spelling}", *shell(LEDGER)), "allow")
check("a script not named is refused", guard("paths: **\nscripts: failure-ledger, test", *shell(SPLIT)), "block")

print("path entries, every spelling")
for spelling in ("datrix-*/src/**", "datrix-common/**, datrix-cli/**", "d:/datrix/**", "D:/datrix/datrix-*/src/**", r"d:\datrix\datrix-*\src\**"):
    check(f"`paths: {spelling}` admits a package source file", guard(f"paths: {spelling}\nscripts: test", *edit(COMMON_SOURCE)), "allow")
check("a file outside the paths is refused", guard("paths: datrix-cli/**\nscripts: test", *edit(COMMON_SOURCE)), "block")
check("a workspace glob stops at the workspace", guard("paths: d:/datrix/**\nscripts: test", *edit(r"C:\Users\x\notes.md")), "block")
check("the scratchpad stays writable", guard("paths: datrix-cli/**\nscripts: test", *edit(r"C:\t\scratchpad\x.md")), "allow")
check("a memory file stays writable",
      guard("paths: datrix-cli/**\nscripts: test", *edit(r"C:\Users\x\.claude\projects\d--datrix\memory\m.md")), "allow")
check("the memory index stays writable",
      guard("paths: datrix-cli/**\nscripts: test", *edit(r"C:\Users\x\.claude\projects\d--datrix\memory\MEMORY.md")), "allow")
check("a session transcript is no memory file",
      guard("paths: datrix-cli/**\nscripts: test", *edit(r"C:\Users\x\.claude\projects\d--datrix\s.jsonl")), "block")
check("user settings are no memory file",
      guard("paths: datrix-cli/**\nscripts: test", *edit(r"C:\Users\x\.claude\settings.json")), "block")

print("path entries outside the workspace")
PRODUCT_DOC = r"D:\g\datrix-code\docs\requirements.md"
for spelling in ("D:/g/datrix-code/**", r"d:\g\datrix-code\**", "datrix-cli/**, d:/g/datrix-code/**"):
    check(f"`paths: {spelling}` admits a file in that tree",
          guard(f"paths: {spelling}\nscripts: test", *edit(PRODUCT_DOC)), "allow")
check("an absolute glob admits only its own tree",
      guard("paths: D:/g/datrix-code/**\nscripts: test", *edit(r"D:\g\other\x.md")), "block")
check("an absolute glob outside the workspace admits nothing inside it",
      guard("paths: D:/g/datrix-code/**\nscripts: test", *edit(COMMON_SOURCE)), "block")
check("a relative glob never leaves the workspace",
      guard("paths: datrix-cli/**\nscripts: test", *edit(PRODUCT_DOC)), "block")
check("`**` alone never leaves the workspace", guard("paths: **\nscripts: test", *edit(PRODUCT_DOC)), "block")

print("a lock written by the old parser still reads")
reset()
os.makedirs(os.path.dirname(STATE), exist_ok=True)
with open(STATE, "w", encoding="utf-8") as f:
    json.dump({"paths": ["d:/datrix/**"], "scripts": ["test/failure-ledger.ps1,", "test/test.ps1,"]}, f)
check("the locked entries are read canonically",
      run_guard({"session_id": SID, "tool_name": "PowerShell", "tool_input": {"command": LEDGER}}), "allow")

print("workspace-wide skill")
narrow = "paths: datrix-cli/**\nscripts: test"
typed = transcript(typed_skill("fix-test-suites"), skill_body("fix-test-suites"))
check("/fix-test-suites runs any script", guard(narrow, *shell(LEDGER), typed), "allow")
check("/fix-test-suites edits any repo", guard(narrow, *edit(COMMON_SOURCE), typed), "allow")
followed = transcript(typed_skill("fix-test-suites"), skill_body("fix-test-suites"), jon("keep going"))
check("a later message of Jon's keeps the skill", guard(narrow, *shell(LEDGER), followed), "allow")
check("the Skill tool form counts", guard(narrow, *shell(LEDGER), transcript(skill_body("fix-test-suites"))), "allow")
other = transcript(typed_skill("fix-cli"), skill_body("fix-cli"))
check("a package skill stays fenced", guard(narrow, *shell(LEDGER), other), "block")
later = transcript(typed_skill("fix-test-suites"), typed_skill("fix-cli"))
check("the latest skill decides", guard(narrow, *shell(LEDGER), later), "block")
quoted = transcript(jon("why did <command-name>/fix-test-suites</command-name> fail?"))
check("a quoted command is no invocation", guard(narrow, *shell(LEDGER), quoted), "block")
finding = transcript(typed_skill("implement-finding"), skill_body("implement-finding"))
check("/implement-finding edits a package the scope left out", guard(narrow, *edit(COMMON_SOURCE), finding), "allow")
check("/implement-finding runs any script", guard(narrow, *shell(LEDGER), finding), "allow")
batch = transcript(typed_skill("implement-finding"))
check("a batch session's typed form counts", guard(narrow, *edit(COMMON_SOURCE), batch), "allow")
after = transcript(typed_skill("implement-finding"), typed_skill("fix-cli"))
check("a package skill after /implement-finding is fenced", guard(narrow, *edit(COMMON_SOURCE), after), "block")

print("a skill's own scripts")
absorb = transcript(typed_skill("absorb-design"), skill_body("absorb-design"))
check("/absorb-design runs the script its steps name", guard(narrow, *shell(ASSIST), absorb), "allow")
check("/absorb-design stays fenced for other scripts", guard(narrow, *shell(LEDGER), absorb), "block")
check("another skill may not run that script",
      guard(narrow, *shell(ASSIST), transcript(typed_skill("fix-cli"), skill_body("fix-cli"))), "block")

print("the script the test guard demands")
for skill in ("implement-finding", "implement-design-direct", "fix-cli"):
    check(f"/{skill} runs the probe the test guard demands",
          guard(narrow, *shell(PROBE_COMMAND), transcript(typed_skill(skill), skill_body(skill))), "allow")
check("no skill runs that probe too", guard(narrow, *shell(PROBE_COMMAND)), "allow")
check("the probe opens no door for a script chained to it",
      guard(narrow, *shell(f"{PROBE_COMMAND}; {LEDGER}")), "block")

print("a skill's own paths")
DESIGN =r"D:\datrix\design\010-example-design.md"
absorbing = transcript(typed_skill("absorb-design"), skill_body("absorb-design"))
DOC = r"D:\datrix\datrix-language\docs\reference\datrix-syntax-reference.md"
README = r"D:\datrix\datrix-common\README.md"
check("/absorb-design edits another design", guard(narrow, *edit(DESIGN), absorbing), "allow")
check("/absorb-design edits a repo's docs", guard(narrow, *edit(DOC), absorbing), "allow")
check("/absorb-design edits a repo's Markdown", guard(narrow, *edit(README), absorbing), "allow")
check("/absorb-design stays fenced outside documents", guard(narrow, *edit(COMMON_SOURCE), absorbing), "block")
check("/absorb-design stays fenced outside the repos",
      guard(narrow, *edit(r"D:\datrix\findings\x.md"), absorbing), "block")
check("another skill may not edit a project document",
      guard(narrow, *edit(DOC), transcript(typed_skill("fix-cli"), skill_body("fix-cli"))), "block")
check("no skill may not edit a project document", guard(narrow, *edit(DOC)), "block")
check("another skill may not edit a design",
      guard(narrow, *edit(DESIGN), transcript(typed_skill("fix-cli"), skill_body("fix-cli"))), "block")
check("no skill may not edit a design", guard(narrow, *edit(DESIGN)), "block")

print("a new message of Jon's")
ORDER = jon("fix datrix-cli")
NEXT = jon("now fix datrix-common")
SEMANTIC_SOURCE = r"D:\datrix\datrix-semantic\src\datrix_semantic\x.py"


def write_plan(paths):
    with open(PLAN, "w", encoding="utf-8") as f:
        f.write(f"## Steps\n- [ ] step\n\n## Scope\n{paths}\nscripts: test\n\n## Verification\n")


def call(path, *entries):
    tool_name, tool_input = edit(path)
    return run_guard({"session_id": SID, "transcript_path": transcript(*entries), "tool_name": tool_name, "tool_input": tool_input})


def widened_plan(*entries):
    """A lock taken on ORDER, the plan since widened to datrix-common, and an edit there under *entries*."""
    guard("paths: datrix-cli/**\nscripts: test", *edit(r"D:\datrix\datrix-cli\src\x.py"), transcript(ORDER))
    write_plan("paths: datrix-common/**")
    return call(COMMON_SOURCE, *entries)


check("a plan edit cannot widen the lock", widened_plan(ORDER), "block")
check("Jon's next message reads the plan afresh", widened_plan(ORDER, NEXT), "allow")
check("hook feedback is not his message",
      widened_plan(ORDER, jon("Stop hook feedback:\nSTOP REJECTED")), "block")
check("a harness frame is not his message",
      widened_plan(ORDER, jon("<task-notification>done</task-notification>")), "block")
check("a skill body the agent invoked is not his message", widened_plan(ORDER, skill_body("fix-cli")), "block")
check("a compaction summary is not his message",
      widened_plan(ORDER, {**jon("This session is being continued"), "isCompactSummary": True}), "block")

widened_plan(ORDER, NEXT)
write_plan("paths: datrix-semantic/**")
check("one message widens once", call(SEMANTIC_SOURCE, ORDER, NEXT), "block")
check("the next message widens again", call(SEMANTIC_SOURCE, ORDER, NEXT, jon("and datrix-semantic")), "allow")

guard("paths: datrix-cli/**\nscripts: test", *edit(r"D:\datrix\datrix-cli\src\x.py"), transcript(ORDER))
check("a refusal before the plan changes is refused", call(COMMON_SOURCE, ORDER, NEXT), "block")
write_plan("paths: datrix-common/**")
check("and does not spend his message", call(COMMON_SOURCE, ORDER, NEXT), "allow")

print("an unattended session")
UNATTENDED = {**os.environ, UNATTENDED_VARIABLE: "1"}
ATTENDED = {key: value for key, value in os.environ.items() if key != UNATTENDED_VARIABLE}
CATALOG = r"D:\datrix\datrix-common\catalog.toml"


def unit_call(tool_name, tool_input, environment):
    """A call from a `UNIT:` session, whose only user entry is the prompt the chain sent."""
    payload = {"session_id": SID, "transcript_path": transcript(typed_skill("implement-design-direct")),
               "tool_name": tool_name, "tool_input": tool_input}
    run = subprocess.run([sys.executable, os.path.join(H, "guard-plan-scope.py")], input=json.dumps(payload),
                         capture_output=True, text=True, env=environment)
    return ("block" if run.returncode == 2 else "allow"), run.stderr


def locked_unit(environment):
    """Lock a narrow unit scope, then widen the plan to the file and script the unit turned out to need."""
    guard("paths: datrix-cli/**\nscripts: test", *edit(r"D:\datrix\datrix-cli\src\x.py"),
          transcript(typed_skill("implement-design-direct")))
    refused = unit_call(*edit(CATALOG), environment)
    with open(PLAN, "w", encoding="utf-8") as f:
        f.write("## Steps\n- [ ] step\n\n## Scope\npaths: datrix-cli/** datrix-common/catalog.toml\n"
                "scripts: test split-module\n\n## Verification\n")
    return refused


check("the chain and the hooks name one variable", UNATTENDED_VARIABLE, CHAIN_VARIABLE)
verdict, message = locked_unit(UNATTENDED)
check("an unattended session is still fenced", verdict, "block")
check("its refusal offers the remedy that works", "locked until Jon" in message, False)
check("its widened plan admits the file", unit_call(*edit(CATALOG), UNATTENDED)[0], "allow")
check("its widened plan admits the script", unit_call(*shell(SPLIT), UNATTENDED)[0], "allow")
check("what it did not declare stays refused", unit_call(*edit(COMMON_SOURCE), UNATTENDED)[0], "block")
check("a script it did not declare stays refused", unit_call(*shell(LEDGER), UNATTENDED)[0], "block")
write_plan("paths: datrix-cli/** datrix-common/**")
check("a second widening counts too", unit_call(*edit(COMMON_SOURCE), UNATTENDED)[0], "allow")

verdict, message = locked_unit(ATTENDED)
check("an attended session is fenced", verdict, "block")
check("its refusal names Jon's message", "locked until Jon" in message, True)
check("its plan edit widens nothing", unit_call(*edit(CATALOG), ATTENDED)[0], "block")


def plan_instruction(environment):
    """What `inject-agent-plan.py` tells a session with no plan yet about filling `## Scope`."""
    run = subprocess.run([sys.executable, os.path.join(H, "inject-agent-plan.py")],
                         input=json.dumps({"session_id": SID}), capture_output=True, text=True, env=environment)
    return json.loads(run.stdout)["hookSpecificOutput"]["additionalContext"]


reset()
check("an unattended session is told to add what its order needs",
      "add what the order turns out to need" in plan_instruction(UNATTENDED), True)
check("and is not told the scope locks", "locks on first sight" in plan_instruction(UNATTENDED), False)
check("an attended session is told it locks", "locks on first sight" in plan_instruction(ATTENDED), True)

reset(TRANSCRIPT)
print()
if fails:
    print(f"{len(fails)} check(s) failed:")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print("all checks passed")
