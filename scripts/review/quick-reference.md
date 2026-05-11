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
```

## Exit Codes

- `0` — Pass (or warnings only)
- `1` — Blocking findings
- `2` — Parse failures
- `3` — Infrastructure errors

## Config

`scripts/review/config.toml` — Edit tier1 endpoint, tier2 mode, thresholds

## Files Created

**Per task:**
- `task-NN-TT-{slug}.review.local.json` — Tier 1 review
- `task-NN-TT-{slug}.review.local.verified.json` — Verification review
- `task-NN-TT-{slug}.review.applied.json` — Applied fixes marker
- `.review-debug/{stem}.{model}.attempt-{N}.txt` — Raw model response on parse failure

**Per phase:**
- `.review/phase-NN.review.codex.json` — Tier 2 review
- `.review/.canonical-modules-cache.json` — Module cache

## Workflow

1. Generate tasks: `/generate-tasks`
2. Review locally: `python review.py --phase NN`
3. Apply fixes: "Apply reviews to phase NN" (in Claude Code)
4. Verify: `python review.py --phase NN --verify`
5. Execute: `/execute-tasks --phase NN`
