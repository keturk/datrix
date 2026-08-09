r"""PreToolUse(Bash|PowerShell): a deploy may not be the thing that tells you a file was wrong.

THE ASYMMETRY THIS EXISTS TO FIX
--------------------------------
CLAUDE.md § "Static Analysis First" and execution-contract §12 are the rules that
matter most in a deployment loop: climb the evidence ladder from the top, compare
every seam's produced/consumed sets, treat a runtime failure as a static-analysis
failure. They were, until this hook, PROSE ONLY.

Meanwhile the rule pointing the other way — §11 Cost Consciousness, "don't
re-read", "ask the cheapest question", "don't re-run a passing check" — has
`guard-full-suite-runs.py` behind it, blocking subagents unconditionally.

When two rules conflict, the one that returns exit code 2 wins every time. The
agent was getting a hard block from the economy rule and a polite suggestion from
the analysis rule, and it behaved accordingly: straight to `deploy.ps1`, learn one
defect per round trip, each round trip costing minutes and real cloud money and
revealing exactly one more member of a class that one static pass would have
listed in full. That is a trained behavior, not a model deficiency.

WHAT IT REQUIRES
----------------
Before a deploy-shaped command runs, a fresh analysis artifact must exist under
`D:\datrix\.tmp\predeploy\`. Writing one means naming both sides of each seam and
computing `consumed - produced` — the specific work §12 asks for. The artifact is
dated, auditable, and reviewable after the fact; a skipped analysis is no longer
invisible.

    {
      "targets": ["curvaero-staging", "deploy-staging.ps1"],   // or ["*"]
      "analyzed_at_epoch": 1770000000,
      "seams": [
        {"name": "compose env interpolation",
         "produced_by": "generated/.env + pipeline vars",
         "consumed_by": "docker-compose.yml ${...} refs",
         "unsatisfied": []}
      ],
      "checks": ["az deployment group create --what-if: no changes flagged"],
      "verdict": "clear",
      "reason": "pre-deploy census for the staging rollout"
    }

WHAT IT NEVER BLOCKS
--------------------
Read-only inspection (`az ... list|show|exists`, `--query` without a mutating
verb), and — deliberately — anything carrying `--what-if`, `--dry-run`,
`-WhatIf`, `--validate`, or `terraform plan`. Those ARE the upper rung of the
evidence ladder. The hook must never make the cheap check harder to reach than
the expensive one; a `--what-if` run is encouraged and is exactly what belongs in
the artifact's `checks` list.

NOT A WEDGE
-----------
A PreToolUse block does not end a turn — the agent does the analysis, writes the
artifact, and proceeds. There is no cap to exhaust and nothing to argue with.
Any unexpected internal error fails OPEN: a hook that can stop Jon deploying is
worse than the defect it prevents.

Exit codes:
  0 - allow
  2 - block; stderr is fed back to the agent
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
import time
from typing import Final

_REPO_ROOT: Final = "d:/datrix"
_ARTIFACT_DIR: Final = os.path.join(_REPO_ROOT, ".tmp", "predeploy")
_AUDIT_PATH: Final = os.path.join(_REPO_ROOT, ".tmp", "predeploy-audit.jsonl")

# Code changes underneath an analysis invalidate it. Two hours is long enough for
# a real deployment session and short enough that yesterday's census cannot
# authorize today's rollout.
_MAX_AGE_S: Final = 2 * 60 * 60

# Commands that put an artifact into an environment. Ordered by how much they cost
# to get wrong.
_DEPLOY_RE: Final = re.compile(
    r"\bdeploy[\w-]*\.ps1\b"
    r"|\bsync-staging\.ps1\b"
    r"|\baz\s+deployment\s+(?:group|sub|mg|tenant)\s+create\b"
    r"|\baz\s+group\s+deployment\s+create\b"
    r"|\baz\s+(?:webapp|functionapp|containerapp|staticwebapp)\s+"
    r"(?:deploy(?:ment)?|create|update|up)\b"
    r"|\baz\s+acr\s+build\b"
    r"|\bterraform\s+apply\b"
    r"|\bkubectl\s+apply\b"
    r"|\bhelm\s+(?:install|upgrade)\b"
    r"|\bdocker\s+stack\s+deploy\b"
    r"|\bdocker\s+compose\s+(?:-[^\s]+\s+)*up\b"
    r"|\bdocker\s+push\b",
    re.IGNORECASE,
)

# The upper rungs of the evidence ladder. Never blocked — making these harder to
# reach than a real deploy would invert the entire point of the hook.
_DRY_RUN_RE: Final = re.compile(
    r"--what-?if\b|--dry-run\b|-WhatIf\b|--validate\b|\bterraform\s+plan\b|--confirm-with-what-if\b",
    re.IGNORECASE,
)


def _artifacts() -> list[dict[str, object]]:
    """Every parseable artifact currently on disk."""
    found: list[dict[str, object]] = []
    for path in glob.glob(os.path.join(_ARTIFACT_DIR, "*.json")):
        try:
            with open(path, encoding="utf-8") as handle:
                loaded = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(loaded, dict):
            loaded["_path"] = path
            found.append(loaded)
    return found


def _targets_match(artifact: dict[str, object], command: str) -> bool:
    targets = artifact.get("targets")
    if not isinstance(targets, list):
        return False
    lowered = command.lower()
    for target in targets:
        if not isinstance(target, str) or not target.strip():
            continue
        if target.strip() == "*" or target.strip().lower() in lowered:
            return True
    return False


def _seam_census_complete(artifact: dict[str, object]) -> tuple[bool, str]:
    """A seam list that actually compares both sides, with nothing unexplained."""
    seams = artifact.get("seams")
    if not isinstance(seams, list) or not seams:
        return False, "no `seams` list — the census is the whole point of the artifact"

    for index, seam in enumerate(seams):
        if not isinstance(seam, dict):
            return False, f"seam[{index}] is not an object"
        for field in ("name", "produced_by", "consumed_by"):
            value = seam.get(field)
            if not isinstance(value, str) or not value.strip():
                return False, f"seam[{index}] is missing `{field}` — name BOTH sides"
        unsatisfied = seam.get("unsatisfied")
        if not isinstance(unsatisfied, list):
            return False, (
                f"seam[{index}] has no `unsatisfied` list — compute `consumed - produced` "
                "and record it, even when empty"
            )
        if unsatisfied and not str(seam.get("explanation", "")).strip():
            return False, (
                f"seam[{index}] has {len(unsatisfied)} unsatisfied item(s) and no "
                "`explanation` — fix them or say why they are acceptable"
            )
    return True, ""


def _verdict(command: str) -> tuple[bool, str]:
    """(allowed, why). Freshness, target match, and a real census are all required."""
    now = time.time()
    candidates = [a for a in _artifacts() if _targets_match(a, command)]
    if not candidates:
        return False, "no pre-deploy analysis artifact matches this command"

    reasons: list[str] = []
    for artifact in candidates:
        stamped = artifact.get("analyzed_at_epoch")
        if not isinstance(stamped, (int, float)):
            reasons.append(f"{os.path.basename(str(artifact['_path']))}: no `analyzed_at_epoch`")
            continue
        age = now - float(stamped)
        if age > _MAX_AGE_S:
            reasons.append(
                f"{os.path.basename(str(artifact['_path']))}: stale "
                f"({int(age // 60)} min old, limit {_MAX_AGE_S // 60})"
            )
            continue
        if str(artifact.get("verdict", "")).strip().lower() != "clear":
            reasons.append(
                f"{os.path.basename(str(artifact['_path']))}: verdict is not `clear`"
            )
            continue
        complete, why = _seam_census_complete(artifact)
        if not complete:
            reasons.append(f"{os.path.basename(str(artifact['_path']))}: {why}")
            continue
        return True, str(artifact["_path"])

    return False, "; ".join(reasons)


def _audit(record: dict[str, object]) -> None:
    try:
        os.makedirs(os.path.dirname(_AUDIT_PATH), exist_ok=True)
        with open(_AUDIT_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    except OSError:
        pass


def _block(command: str, why: str) -> None:
    sys.stderr.write(
        "BLOCKED: this is a deploy, and no fresh pre-deploy analysis exists.\n\n"
        f"Why: {why}\n\n"
        "A deploy is the most expensive and latest-arriving evidence available — "
        "minutes to hours, real money, one defect reported per round trip, after "
        "the artifact is already out. Nearly everything it will tell you is "
        "sitting in a file on disk right now.\n\n"
        "Do this first (execution-contract §12):\n"
        "  1. Name every seam this deploy crosses — env/compose interpolation, "
        "config-store keys, secret names, route inventories, image tags, module "
        "outputs consumed by another module.\n"
        "  2. For each, list what PRODUCES the names and what CONSUMES them, then "
        "compute `consumed - produced`. Parse the artifact; do not eyeball it with "
        "a regex, and prove your matcher finds an instance you know is there.\n"
        "  3. Run the cheap rung that is never blocked: `--what-if` / `--dry-run` / "
        "`terraform plan` / `--validate`. Read what it says.\n"
        "  4. Fix what the census found, then record it:\n\n"
        f"     {_ARTIFACT_DIR}\\<name>.json\n"
        '     {"targets": ["<substring of this command>"], '
        '"analyzed_at_epoch": <now>,\n'
        '      "seams": [{"name": "...", "produced_by": "...", "consumed_by": "...", '
        '"unsatisfied": []}],\n'
        '      "checks": ["what-if: ..."], "verdict": "clear", "reason": "..."}\n\n'
        f"Artifacts expire after {_MAX_AGE_S // 60} minutes — an analysis older than "
        "the code it describes is not an analysis.\n\n"
        "Read-only `az list/show/exists` and every dry-run form are never blocked. "
        "If this command is not actually a deploy, run the read-only form instead."
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
    if not isinstance(command, str) or not command.strip():
        sys.exit(0)

    if not _DEPLOY_RE.search(command):
        sys.exit(0)

    # The upper rung of the ladder is always free.
    if _DRY_RUN_RE.search(command):
        _audit(
            {
                "epoch": int(time.time()),
                "decision": "allow",
                "why": "dry-run / what-if form",
                "command": command[:400],
            }
        )
        sys.exit(0)

    allowed, why = _verdict(command)
    _audit(
        {
            "epoch": int(time.time()),
            "decision": "allow" if allowed else "block",
            "why": why,
            "agent_id": data.get("agent_id", ""),
            "command": command[:400],
        }
    )
    if allowed:
        sys.exit(0)
    _block(command, why)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - a hook must never wedge a deployment session
        sys.exit(0)
