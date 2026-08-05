"""PreToolUse(Bash|PowerShell) hook: a whole-package test suite is a
phase-boundary act, not something an agent runs to reassure itself.

WHY THIS IS A HARD BLOCK AND NOT AN INSTRUCTION
-----------------------------------------------
CLAUDE.md and the verification strategy already say it: inside a phase you run
the targeted tests your task names; full suites run ONCE, at the phase boundary /
quality gate, over the affected set. It was written down, it was repeated in every
dispatch prompt, and it was violated anyway -- in a single phase, subagents ran
datrix-codegen-aws (1844 tests), datrix-codegen-azure (3294, then 3296),
datrix-codegen-docker (1880) and datrix-codegen-component (427) as bare full
suites. Roughly 8,700 extra test executions bought information the boundary gate
was going to produce once, for free.

The docker case is the exact shape this hook exists to kill: the agent ran its
targeted set (147, green), then ran the full suite as a DISCOVERY mechanism,
found two regressions in it, fixed them, and re-ran. Using the full suite to
discover work mid-task IS the phase-boundary gate, performed early, per package,
per wave, at N times the cost.

An orchestrator reading "full package suite: 1880 passed" in an agent report
tends to bank it as reassurance rather than flag it as a violation -- which is
precisely what happened, four times, in plain text. Judgement did not catch it.
A block does.

THE RULE
--------
A `test.ps1` invocation is TARGETED (always allowed) when it carries `-Specific`
or `-Keyword`. Everything else is a whole-suite run: a bare package name, several
package names, `-All`, `-Rerun`, or a tier sweep (`-Unit` / `-Integration` /
`-Fast` / ...). Whole-suite runs are gated:

  * SUBAGENTS  -- blocked unconditionally. There is no override, no marker, no
    ticket. Every violation in the incident above came from a subagent, and an
    agent has no standing to decide that a phase-boundary sweep should happen
    now. Its task file names the tests it must run; it runs those.

  * MAIN SESSION -- blocked unless an unexpired authorization ticket at
    d:/datrix/.tmp/full-suite-ticket.json covers every package named. The ticket
    carries a written reason and an expiry (6h cap, so a permit can never become
    permanent), and every decision -- allowed AND blocked -- is appended to
    d:/datrix/.tmp/full-suite-audit.jsonl so the count is a fact Jon can read
    rather than something he has to notice in a transcript.

`test-single.ps1` is inherently single and is never touched. So is every other
`*.ps1` whose name merely contains "test".

Exit codes:
  0 -- allow
  2 -- block (stderr becomes feedback to Claude)
"""

import json
import os
import re
import sys
import time
from typing import Final

_SCRATCH_DIR: Final = "d:/datrix/.tmp"
_TICKET_PATH: Final = f"{_SCRATCH_DIR}/full-suite-ticket.json"
_AUDIT_PATH: Final = f"{_SCRATCH_DIR}/full-suite-audit.jsonl"

#: A permit that outlives the gate it was issued for is a standing exemption.
_MAX_TICKET_SECONDS: Final = 6 * 60 * 60

#: `test.ps1` as its own path segment (or bare, or right after a quote), so
#: `test-single.ps1`, `test-specific-selection-gate.ps1` and friends never match.
_TEST_SCRIPT_RE: Final = re.compile(r"""(?:^|[/\\"'\s])test\.ps1\b""", re.IGNORECASE)

#: The only two flags that make a run genuinely targeted -- they select named
#: files / node ids. `-Unit`, `-Fast`, `-Integration` narrow a suite to a TIER,
#: which is still a sweep of everything in it, and are not accepted here.
_NARROWING_FLAGS: Final = ("-specific", "-keyword")

#: Stands in for the package list when `-All` was passed; only a `"*"` ticket
#: can ever cover it.
_ALL_SENTINEL: Final = "*ALL-PACKAGES*"

_PACKAGE_RE: Final = re.compile(r"datrix(?:-[a-z0-9]+)*\Z")


def _invocation_tails(command: str) -> list[str]:
    """One argument tail per `test.ps1` occurrence in the command.

    Segmenting matters: `test.ps1 A; test.ps1 B -Specific x` must not let B's
    narrowing flag vouch for A's bare full-suite run.
    """
    starts = [m.end() for m in _TEST_SCRIPT_RE.finditer(command)]
    if not starts:
        return []
    bounds = [m.start() for m in _TEST_SCRIPT_RE.finditer(command)][1:] + [len(command)]
    return [command[start:end] for start, end in zip(starts, bounds)]


def _is_targeted(tail: str) -> bool:
    lowered = tail.lower()
    return any(re.search(rf"(?:^|\s){re.escape(flag)}\b", lowered) for flag in _NARROWING_FLAGS)


def _packages(tail: str) -> list[str]:
    """Package names this invocation would run whole suites for."""
    lowered = tail.lower()
    if re.search(r"(?:^|\s)-all\b", lowered):
        return [_ALL_SENTINEL]

    found: list[str] = []
    for raw in re.split(r"[\s,;|]+", tail):
        token = raw.strip("\"'()").rstrip("\\/").lstrip(".").lstrip("\\/").lower()
        if not token or "/" in token or "\\" in token:
            continue
        if _PACKAGE_RE.fullmatch(token):
            found.append(token)
    return found


def _ticket_verdict(packages: list[str]) -> tuple[bool, str, dict[str, object]]:
    """(authorized, why, ticket) for the main session's whole-suite request."""
    try:
        # utf-8-sig, not utf-8: PowerShell 5.1's `Set-Content -Encoding utf8`
        # and `Out-File` both prepend a BOM, so every ticket written the
        # obvious way on this platform starts with one and plain utf-8 decoding
        # fails the whole file with a JSONDecodeError. utf-8-sig strips a BOM
        # when present and is identical to utf-8 when absent.
        with open(_TICKET_PATH, encoding="utf-8-sig") as handle:
            ticket = json.load(handle)
    except FileNotFoundError:
        return False, "no authorization ticket exists", {}
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"ticket unreadable ({exc.__class__.__name__})", {}

    if not isinstance(ticket, dict):
        return False, "ticket is not a JSON object", {}

    expires = ticket.get("expires_epoch")
    if not isinstance(expires, (int, float)):
        return False, "ticket has no numeric expires_epoch", ticket

    now = time.time()
    if expires <= now:
        return False, "ticket expired", ticket
    if expires > now + _MAX_TICKET_SECONDS:
        return False, f"ticket lifetime exceeds the {_MAX_TICKET_SECONDS // 3600}h cap", ticket

    reason = ticket.get("reason")
    if not isinstance(reason, str) or len(reason.strip()) < 10:
        return False, "ticket has no written reason", ticket

    allowed = ticket.get("packages")
    if not isinstance(allowed, list) or not allowed:
        return False, "ticket names no packages", ticket

    allowed_set = {str(entry).lower() for entry in allowed}
    if "*" in allowed_set:
        return True, "wildcard ticket", ticket

    missing = [pkg for pkg in packages if pkg not in allowed_set]
    if missing:
        return False, f"ticket does not cover {', '.join(missing)}", ticket
    return True, "covered by ticket", ticket


def _audit(record: dict[str, object]) -> None:
    """Append the decision. The count of full-suite runs must be a readable fact."""
    try:
        os.makedirs(_SCRATCH_DIR, exist_ok=True)
        with open(_AUDIT_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    except OSError:
        return


def _block_subagent(packages: list[str]) -> None:
    named = ", ".join(packages) if packages else "this package"
    sys.stderr.write(
        f"BLOCKED: you are a subagent and you may not run a whole test suite ({named}).\n\n"
        "Full suites are a PHASE-BOUNDARY act, run once by the orchestrator over the "
        "affected set. Inside a task you run exactly the tests your task file's "
        "`## Targeted Tests` section names, and nothing else.\n\n"
        "Use the targeted form -- comma-separated files run in ONE pytest session:\n"
        '  powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package} '
        '-Specific "tests/unit/test_a.py,tests/integration/test_b.py"\n\n'
        "This block has no override. In particular:\n"
        "  - 'I want to check I did not regress anything' is what the boundary gate is "
        "for. Running it yourself does that work N times instead of once.\n"
        "  - Using a full suite to DISCOVER further work mid-task is the specific "
        "anti-pattern this exists to stop.\n"
        "  - If your task file's `## Targeted Tests` itself names a bare full suite, "
        "that task file is defective: run the specific test files covering the code you "
        "changed, and say so in your report.\n"
        "  - To prove a change generalises, write a test in the owning package. A test "
        "proves the invariant forever; a sweep proves it once and evaporates."
    )
    sys.exit(2)


def _block_main(packages: list[str], why: str) -> None:
    named = ", ".join(packages) if packages else "unnamed package(s)"
    expires_hint = int(time.time()) + 2 * 60 * 60
    sys.stderr.write(
        f"BLOCKED: whole test suite requested for {named} -- {why}.\n\n"
        "Full suites run ONCE, at a phase boundary or quality gate, over the affected "
        "set (changed packages + their reverse-dependency closure). Inside a phase, run "
        "the targeted tests:\n"
        '  ... test.ps1 {package} -Specific "tests/unit/test_a.py,tests/unit/test_b.py"\n\n'
        "If this genuinely IS the phase-boundary / quality gate, authorize it explicitly "
        f"by writing {_TICKET_PATH}:\n"
        "  {\n"
        '    "packages": ["datrix-common", "datrix-codegen-docker"],   // or ["*"]\n'
        '    "reason": "phase-45 boundary gate, sweep set = closure of datrix-common",\n'
        '    "granted_by": "orchestrator",                             // or "jon"\n'
        f'    "expires_epoch": {expires_hint}\n'
        "  }\n\n"
        f"The ticket is capped at {_MAX_TICKET_SECONDS // 3600}h and every use is "
        f"appended to {_AUDIT_PATH}, so issuing one is a visible, counted act -- not a "
        "way to make the rule go away. Do not write a ticket to get past a mid-phase "
        "check you merely want reassurance from."
    )
    sys.exit(2)


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    if data.get("tool_name") not in ("Bash", "PowerShell"):
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if not isinstance(command, str) or not command:
        sys.exit(0)

    whole_suite_packages: list[str] = []
    for tail in _invocation_tails(command):
        if _is_targeted(tail):
            continue
        whole_suite_packages.extend(_packages(tail) or ["<unnamed>"])

    if not whole_suite_packages:
        sys.exit(0)

    is_subagent = bool(data.get("agent_id"))
    record: dict[str, object] = {
        "ts": int(time.time()),
        "session_id": data.get("session_id", ""),
        "agent_id": data.get("agent_id", ""),
        "packages": whole_suite_packages,
        "command": command[:400],
    }

    if is_subagent:
        _audit({**record, "decision": "block", "why": "subagent: no override exists"})
        _block_subagent(whole_suite_packages)

    authorized, why, ticket = _ticket_verdict(whole_suite_packages)
    if not authorized:
        _audit({**record, "decision": "block", "why": why})
        _block_main(whole_suite_packages, why)

    _audit(
        {
            **record,
            "decision": "allow",
            "why": why,
            "granted_by": ticket.get("granted_by", ""),
            "reason": ticket.get("reason", ""),
        }
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
