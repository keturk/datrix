# Review Quick Reference

Fast lookup for AI agents reviewing task files.

## Bash Invocation

```bash
# Review single task
python scripts/library/review/review.py --task d:/datrix/datrix-common/.tasks/phase-43/task-43-01-foo.md

# Review entire phase (Tier 1 only)
python scripts/library/review/review.py --phase 43

# Review with manual Tier 2
python scripts/library/review/review.py --phase 43 --codex

# Review with threshold escalation
python scripts/library/review/review.py --phase 43 --codex-on-threshold

# Review with phase-gate (recommended)
python scripts/library/review/review.py --phase 43 --codex-phase-gate

# Re-review after fixes (manual verification)
python scripts/library/review/review.py --phase 43 --verify

# Narrow where Tier 1 runs (each flag repeatable, preference order)
python scripts/library/review/review.py --phase 43 --local-machine 10.94.0.102 --local-model qwen3-coder:30b
```

Tier 1 runs on the first local model server `library/shared/local_llm.py` finds (Ollama, vLLM or llama-server), failing over to the next.

## Exit Codes

- `0` — A complete review found nothing blocking (pass or warnings only)
- `1` — Blocking findings
- `2` — Every task's review failed to parse
- `3` — No local model server answered, so no review ran. `--codex*` does not change this: Tier 2 reviews Tier 1's output and cannot run without it.
- `4` — Tier 2 was due (forced, threshold, or phase gate) but failed or was rate-limited; the phase review is incomplete

## Config

`scripts/review/config.toml` — Edit tier1 context window, tier2 mode, thresholds

## Files Created

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

## Workflow

1. Generate tasks: `/generate-tasks`
2. Review locally: `python review.py --phase NN`
3. Apply fixes: "Apply reviews to phase NN" (in Claude Code — runs `apply-reviews-prep.ps1` for the worklist)
4. Verify: `python review.py --phase NN --verify`
5. Execute: `/execute-tasks --phase NN`
