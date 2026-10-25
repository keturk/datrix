# Review Quick Reference

Bash: prefix `powershell -File`, forward slashes, quoted path ([../quick-reference.md](../quick-reference.md)). Base path `d:/datrix/datrix/scripts/`. How the tiers work, the review JSON schema, troubleshooting: [README.md](README.md).

Workflow: `/generate-tasks` → `.\review\review.ps1 --phase NN` → apply fixes ("Apply reviews to phase NN", which runs `apply-reviews-prep.ps1`) → `.\review\review.ps1 --phase NN --verify` → `/execute-tasks --phase NN`.

## `review\review.ps1`

Task review (Tier 1 per task, Tier 2 per phase, both on local models). Every argument is passed through to the review's own options (`--help` lists them); options are spelled in full.

| Form | Command |
|------|---------|
| One task | `.\review\review.ps1 --task <path to one task file>` |
| A phase (Tier 1, then Tier 2 per `config.toml`) | `.\review\review.ps1 --phase 43` |
| Force Tier 2 | `.\review\review.ps1 --phase 43 --tier2` |
| Tier 2 only past the `[tier2]` thresholds | `.\review\review.ps1 --phase 43 --tier2-on-threshold` |
| Tier 2 as a gate after Tier 1 | `.\review\review.ps1 --phase 43 --tier2-phase-gate` |
| Re-review after fixes | `.\review\review.ps1 --phase 43 --verify` |
| Pick machine and model (repeatable, preference order) | `.\review\review.ps1 --phase 43 --local-machine 10.94.0.102 --local-model qwen3-coder:30b` |

Exit codes: `0` nothing blocking · `1` blocking findings · `2` every review failed to parse, or usage error · `3` no local model server answered · `4` Tier 2 was due but no tier-2 model answered.

Config: `scripts/review/config.toml` (`--config` points at another file). Results: `.tasks/phase-NN/task-NN-TT-{slug}.review.local.json` per task, `d:\datrix\.review\phase-NN.review.phase.json` per phase.

## `review\apply-reviews-prep.ps1`

Build the `/apply-reviews` worklist from the Tier 1 and Tier 2 review files, minus findings already applied.

| Form | Command |
|------|---------|
| All sources | `.\review\apply-reviews-prep.ps1 -Phase 43` |
| Tier 1 only | `.\review\apply-reviews-prep.ps1 -Phase 43 -Source local` |
| Tier 2 only | `.\review\apply-reviews-prep.ps1 -Phase 43 -Source phase` |
| Other workspace | `.\review\apply-reviews-prep.ps1 -Phase 43 -BaseDir D:\other` |

Parameters: `-Phase <NN>` (required, positional 0), `-Source local|phase|all` (default all), `-BaseDir`, `-Output <path>`, `-Dbg`, `-SelfTest`. Worklist: `D:\datrix\.tmp\review\phase-NN-worklist.json`. Exit: 0 done, 2 usage error.

## `review\review-library-gate.ps1`

Behaviour checks for the review library `datrix_scripts.review`.

| Form | Command |
|------|---------|
| Run the gate | `.\review\review-library-gate.ps1` |
| Some checks | `.\review\review-library-gate.ps1 -Only extract` |
| Harness self-test | `.\review\review-library-gate.ps1 -HarnessSelfTest` |
| Self-test | `.\review\review-library-gate.ps1 -SelfTest` |

Parameters: `-Only <prefix>`, `-HarnessSelfTest`, `-SelfTest`, `-Dbg`. Exit: 0 all passed, 1 a check failed, 2 usage error. Log under `.test-output\gates\review-library\`.
