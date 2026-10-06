# Review Quick Reference

Fast lookup for AI agents reviewing task files.

> **Bash invocation:** Prefix with `powershell -File`, use forward slashes, quote paths. See [../quick-reference.md](../quick-reference.md) for full details.
>
> **Base path:** `d:/datrix/datrix/scripts/`

## `review\review.ps1`

Runs the Task Review System (`review/lib/review.py`); every argument is passed through.

```bash
# Review single task
powershell -File "d:/datrix/datrix/scripts/review/review.ps1" --task <path to one task file>

# Review entire phase (Tier 1 only)
powershell -File "d:/datrix/datrix/scripts/review/review.ps1" --phase 43

# Review with manual Tier 2
powershell -File "d:/datrix/datrix/scripts/review/review.ps1" --phase 43 --codex

# Review with threshold escalation
powershell -File "d:/datrix/datrix/scripts/review/review.ps1" --phase 43 --codex-on-threshold

# Review with phase-gate (recommended)
powershell -File "d:/datrix/datrix/scripts/review/review.ps1" --phase 43 --codex-phase-gate

# Re-review after fixes (manual verification)
powershell -File "d:/datrix/datrix/scripts/review/review.ps1" --phase 43 --verify

# Narrow where Tier 1 runs (each flag repeatable, preference order)
powershell -File "d:/datrix/datrix/scripts/review/review.ps1" --phase 43 --local-machine 10.94.0.102 --local-model qwen3-coder:30b
```

Tier 1 runs on the first local model server `datrix_scripts.local_llm` finds (Ollama, vLLM or llama-server), failing over to the next.

### Exit Codes

- `0` — A complete review found nothing blocking (pass or warnings only)
- `1` — Blocking findings
- `2` — Every task's review failed to parse
- `3` — No local model server answered, so no review ran. `--codex*` does not change this: Tier 2 reviews Tier 1's output and cannot run without it.
- `4` — Tier 2 was due (forced, threshold, or phase gate) but failed or was rate-limited; the phase review is incomplete

### Config

`scripts/review/config.toml` — Edit tier1 context window, tier2 mode, thresholds (`--config` points at another file)

### Files Created

**Per task:**
- `task-NN-TT-{slug}.review.local.json` — Tier 1 review
- `task-NN-TT-{slug}.review.local.verified.json` — Verification review
- `task-NN-TT-{slug}.review.applied.json` — Applied fixes marker
- `.review-debug/{stem}.{model}.attempt-{N}.txt` — Raw model response on parse failure

**Per phase:**
- `.review/phase-NN.review.codex.json` — Tier 2 review
- `.review/.canonical-modules-cache.json` — Module cache

## `review\apply-reviews-prep.ps1`

Builds the `/apply-reviews` worklist: discovers `*.review.local.json` across every repo's `.tasks\phase-{NN}\` plus the codex `phase-{NN}.review.codex.json`, validates findings against `review_schema.py`, filters out findings already recorded in `.review.applied.json` markers, groups by `target`, and sorts blocking → major → minor → nit. Minimal console; details to JSON.

| Mode | Command | Description |
|------|---------|-------------|
| **All sources** | `.\review\apply-reviews-prep.ps1 -Phase 43` | Worklist → `D:\datrix\.tmp\review\phase-43-worklist.json` |
| **Tier 1 only** | `.\review\apply-reviews-prep.ps1 -Phase 43 -Source local` | Local review findings only |
| **Tier 2 only** | `.\review\apply-reviews-prep.ps1 -Phase 43 -Source codex` | Codex findings only |
| **Custom base dir** | `.\review\apply-reviews-prep.ps1 -Phase 43 -BaseDir D:\other` | Different workspace |

**Parameters:** `-Phase <NN>` (required), `-Source local|codex|all` (default all), `-BaseDir`, `-Output <path>`, `-Dbg`. **Exit codes:** 0 = done (also when no review files exist — says so), 2 = usage error.

## `review\review-library-gate.ps1`

Plain-Python behaviour checks (no pytest, no mocks/fakes) for the review library in `review/lib/` (`review_schema.py`, `canonical_modules.py`, `escalation.py`, `review.py`): `Finding`/`ReviewResult` construction and serialization round-trips, canonical-module package discovery/scanning/digest-building/cache validity/prompt formatting, `should_escalate_to_tier2` across every escalation mode and threshold combination, `extract_json_from_response`/`parse_model_response` JSON-extraction strategies (fences, brace-matching, `<think>` tag stripping, largest-review-JSON selection), and the orchestrator core (`resolve_task_context`, `discover_phase_tasks`, `dict_to_review_result`, `build_reviewer_prompt`). Repo-level validation **script**, not a pytest suite (the datrix showcase repo hosts none).

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\review\review-library-gate.ps1` | Run every check |
| **Harness self-test** | `.\review\review-library-gate.ps1 -HarnessSelfTest` | Prove the harness detects a forced failure (always reports [FAIL], exits 1) |
| **Debug** | `.\review\review-library-gate.ps1 -Dbg` | Print the python invocation before running |

**Parameters:** `-HarnessSelfTest`, `-Dbg`

**Assertions:** several checks are inherently adversarial (corrupt/malformed JSON → invalid or `None`, non-review JSON rejected, garbage → `None`, unknown escalation mode never escalates), which already demonstrates discriminating power; `-HarnessSelfTest` additionally proves the pass/fail harness itself is not vacuous by registering one deliberately-failing dummy check and confirming it is reported `[FAIL]` with a nonzero exit.

**Exit codes:** 0 = every check passed, 1 = at least one check (or the harness self-test) failed, 2 = usage error.

## Workflow

1. Generate tasks: `/generate-tasks`
2. Review locally: `.\review\review.ps1 --phase NN`
3. Apply fixes: "Apply reviews to phase NN" (in Claude Code — runs `apply-reviews-prep.ps1` for the worklist)
4. Verify: `.\review\review.ps1 --phase NN --verify`
5. Execute: `/execute-tasks --phase NN`
