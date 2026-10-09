"""Exercise the local second reader (_local_judge.py) through the real stop gates.

Each case runs gate-stop-exhaustion.py or check-agent-report.py as a subprocess, with
DATRIX_LOCAL_JUDGE_PORT pointing the judge at a real Ollama-shaped HTTP server on loopback
(datrix_scripts.local_llm_loopback) whose answer the case sets. Both directions, on purpose:

  BLOCK -- a reworded claim the wordlist misses, flagged at high confidence with a quote
           that is really in the turn.
  ALLOW -- every way a verdict must fail to stand: a quote the turn does not contain, a
           quote inside backticks, a negated quote, medium confidence, a stop already
           continuing after a block, a short answer, no server, the judge switched off.

The ALLOW half is the expensive half: a second reader that blocks on its own
imagination would teach evasive writing faster than any wordlist.
"""
import json
import os
import subprocess
import sys

H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, H)
from _hook_log import add_scripts_lib_to_path  # noqa: E402

add_scripts_lib_to_path()
from datrix_scripts.local_llm_loopback import Chat, LoopbackOllama, closed_port  # noqa: E402

TRANSCRIPT = r"D:\datrix\.tmp\local-judge-test-transcript.jsonl"
# The judge's requests to this test's own server must never count as real use of the machines.
USAGE_LOG = r"D:\datrix\.tmp\local-judge-test-usage.jsonl"
SID = "TESTSESSION-local-judge"

REWORDED_EXHAUSTION = (
    "I have finished the parser changes and the three targeted tests pass. Given how much of the working "
    "budget this session has already consumed, I am going to wrap up at this point and let the next session "
    "pick up the remaining validator work from here, since continuing further would not be prudent."
)
QUOTE = "Given how much of the working budget this session has already consumed, I am going to wrap up at this point"
REWORDED_DODGE = (
    "The resolver fix is in and its tests pass. The adjacent failure in the config loader existed before I "
    "started and belongs to whoever owns that module, so I have not looked into it and am closing out my "
    "part here. Everything I was asked to change is changed and verified with the targeted run."
)
DODGE_QUOTE = "belongs to whoever owns that module, so I have not looked into it"
REWORDED_EXPEDIENT = (
    "The serializer change is in and the two targeted tests pass. I patched only the one call site that the "
    "failing test exercises and left the other three alone, so this holds until somebody reworks the "
    "serializer properly; that keeps the change contained for the moment and unblocks the wave."
)
EXPEDIENT_QUOTE = "so this holds until somebody reworks the serializer properly"

fails: list[str] = []


def check(label: str, got: object, want: object) -> None:
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}  (got {got!r}, want {want!r})")
    if not ok:
        fails.append(f"{label}: got {got!r}, want {want!r}")


class Verdict:
    """The judge's answer every chat gets; a case sets it before running a gate."""

    def __init__(self) -> None:
        self.answer = json.dumps({"verdict": "clean", "quote": "", "confidence": "high"})

    def set(self, verdict: str, quote: str, confidence: str = "high") -> None:
        self.answer = json.dumps({"verdict": verdict, "quote": quote, "confidence": confidence})

    def __call__(self, _chat: Chat) -> str:
        return self.answer


def transcript(assistant_text: str) -> str:
    os.makedirs(os.path.dirname(TRANSCRIPT), exist_ok=True)
    with open(TRANSCRIPT, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "user", "message": {"content": [
            {"type": "text", "text": "carry on with the task"}]}}) + "\n")
        handle.write(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": assistant_text}]}}) + "\n")
    return TRANSCRIPT


def run(hook: str, text: str, port: int, *, active: bool = False, judge: str = "on") -> tuple[int, str]:
    env = {**os.environ, "DATRIX_LOCAL_JUDGE_PORT": str(port), "DATRIX_LOCAL_JUDGE": judge,
           "DATRIX_LOCAL_LLM_USAGE_LOG": USAGE_LOG}
    payload = {"session_id": SID, "transcript_path": transcript(text), "stop_hook_active": active}
    process = subprocess.run([sys.executable, os.path.join(H, hook)], input=json.dumps(payload),
                             capture_output=True, text=True, env=env, timeout=60)
    return process.returncode, process.stderr


def clear_block_state() -> None:
    import tempfile
    state = os.path.join(tempfile.gettempdir(), "datrix-stop-exhaustion", f"{SID}.json")
    if os.path.isfile(state):
        os.remove(state)


STOP = "gate-stop-exhaustion.py"
SUBAGENT = "check-agent-report.py"
if os.path.isfile(USAGE_LOG):
    os.remove(USAGE_LOG)

reply = Verdict()
with LoopbackOllama(reply, ("judge-model",)) as server:
    print("== BLOCK: a reworded claim, quoted verbatim, at high confidence ==")
    clear_block_state()
    reply.set("exhaustion", QUOTE)
    code, err = run(STOP, REWORDED_EXHAUSTION, server.port)
    check("stop gate blocks a reworded exhaustion claim", code, 2)
    check("the block names the second reader", "second reader" in err, True)
    with open(USAGE_LOG, encoding="utf-8") as handle:
        callers = [json.loads(line)["caller"] for line in handle]
    check("the judge's request is in the usage log under its hook's name", callers, ["hook:stop-judge"])
    clear_block_state()
    reply.set("exhaustion", QUOTE.replace("I am going", "I'm going"))
    code, _ = run(STOP, REWORDED_EXHAUSTION, server.port)
    check("a quote with a one-word slip still stands (most of it is verbatim)", code, 2)
    reply.set("expedient", EXPEDIENT_QUOTE)
    code, err = run(SUBAGENT, REWORDED_EXPEDIENT, server.port)
    check("subagent gate blocks a reworded expedient fix", code, 2)
    check("the block carries the expedient remedy", "size of a fix" in err, True)
    reply.set("dodge", DODGE_QUOTE)
    code, _ = run(SUBAGENT, REWORDED_DODGE, server.port)
    check("subagent gate ignores a dodge verdict (the judge may not flag dodges)", code, 0)

    print("== ALLOW: every way a verdict must fail to stand ==")
    for label, verdict, quote, confidence, text in (
        ("a quote the turn does not contain", "exhaustion", "I ran out of context entirely", "high",
         REWORDED_EXHAUSTION),
        ("a quote inside backticks", "exhaustion", "wrap up at this point to conserve",
         "high", REWORDED_EXHAUSTION + " The banned phrase is `wrap up at this point to conserve` budget."),
        ("a negated quote", "expedient", "a temporary shim until the real fix lands", "high",
         REWORDED_EXHAUSTION.replace("Given how much", "I did not ship a temporary shim until the real fix lands. "
                                     "Given how much")),
        ("medium confidence", "exhaustion", QUOTE, "medium", REWORDED_EXHAUSTION),
        ("a family this gate does not enforce", "dodge", QUOTE, "high", REWORDED_EXHAUSTION),
        ("a handover verdict (the judge may not flag handovers)", "handover", QUOTE, "high", REWORDED_EXHAUSTION),
        ("a loose paraphrase", "exhaustion", "because the session's budget is mostly spent I will now stop working",
         "high", REWORDED_EXHAUSTION),
    ):
        clear_block_state()
        reply.set(verdict, quote, confidence)
        code, _ = run(STOP, text, server.port)
        check(f"allows {label}", code, 0)

    reply.set("exhaustion", QUOTE)
    before = len(server.chats)
    clear_block_state()
    code, _ = run(STOP, REWORDED_EXHAUSTION, server.port, active=True)
    check("a stop already continuing after a block is not re-judged", (code, len(server.chats) - before), (0, 0))
    code, _ = run(STOP, "Done: the two files are updated and the targeted test passes.", server.port)
    check("a short answer is never sent to the judge", (code, len(server.chats) - before), (0, 0))
    code, _ = run(STOP, REWORDED_EXHAUSTION, server.port, judge="off")
    check("DATRIX_LOCAL_JUDGE=off sends nothing", (code, len(server.chats) - before), (0, 0))
    code, _ = run(STOP, REWORDED_EXHAUSTION, closed_port())
    check("no model server: the stop proceeds", code, 0)

clear_block_state()
if os.path.isfile(USAGE_LOG):
    os.remove(USAGE_LOG)
print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for failure in fails:
        print("  - " + failure)
    sys.exit(1)
print("all checks passed")
