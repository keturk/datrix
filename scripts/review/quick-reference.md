# Review Quick Reference

Fast lookup for AI agents reviewing task files.

> **Bash invocation:** Prefix with `powershell -File`, use forward slashes, quote paths. See [../quick-reference.md](../quick-reference.md) for full details.
>
> **Base path:** `d:/datrix/datrix/scripts/`

## Architecture

```
Claude Code → Generate Tasks → task-NN-TT-{slug}.md

                  ↓ review.ps1 --phase NN

        Tier 1: one task at a time, on a local model
        first model datrix_scripts.local_llm finds
        (the machines' Ollama servers; fails over to the next)
        Per-task scope ([tier1] context_window)

                  ↓ writes

        task-NN-TT-{slug}.review.local.json

                  ↓ (escalation logic)

        Tier 2: the whole phase, on a larger local model (optional)
        datrix_scripts.review.tier2_local TIER2_MODELS, prompts/phase-reviewer.md
        Phase scope ([tier2] context_window; a phase that does not fit is split by task)
        Reports only what needs the whole phase to see

                  ↓ writes

        phase-NN.review.phase.json

                  ↓ /apply-reviews skill

        Apply fixes to task files
        Mark applied in .review.applied.json

                  ↓ manual --verify

        Re-run Tier 1 to confirm fixes cleared
```

## `review\review.ps1`

Runs the Task Review System; every argument is passed through to the review's own options (`--help` lists them).

**Module:** `datrix_scripts.review.review` (in `common/lib/`), behind a wrapper rendered from `common/templates/entrypoint.ps1`: the `.ps1` hands each argument over as `--review-arguments=<word>`. Its POSIX twin `review/review.sh` takes the review options as they are (`bash review/review.sh --phase 43 --tier2`). `-SelfTest` runs the module's self-test (both argument forms, the refusal of a review naming neither `--task` nor `--phase`, the wrapper seam) and reviews nothing. A review option is spelled in full: an abbreviation is a usage error (exit 2).

```bash
# Review single task
powershell -File "d:/datrix/datrix/scripts/review/review.ps1" --task <path to one task file>

# Review entire phase (Tier 1, then Tier 2 per config.toml [tier2] mode)
powershell -File "d:/datrix/datrix/scripts/review/review.ps1" --phase 43

# Force Tier 2
powershell -File "d:/datrix/datrix/scripts/review/review.ps1" --phase 43 --tier2

# Escalate to Tier 2 only when the [tier2] thresholds are breached (overrides the configured mode)
powershell -File "d:/datrix/datrix/scripts/review/review.ps1" --phase 43 --tier2-on-threshold

# Run Tier 2 after Tier 1 as a quality gate (overrides the configured mode)
powershell -File "d:/datrix/datrix/scripts/review/review.ps1" --phase 43 --tier2-phase-gate

# Re-review after fixes (manual verification)
powershell -File "d:/datrix/datrix/scripts/review/review.ps1" --phase 43 --verify

# Narrow where the tiers run (each flag repeatable, preference order)
powershell -File "d:/datrix/datrix/scripts/review/review.ps1" --phase 43 --local-machine 10.94.0.102 --local-model qwen3-coder:30b
```

Tier 1 runs on the first model `datrix_scripts.local_llm` finds on the local machines' Ollama servers, failing over to the next. Tier 2 runs on the same machines, on `nemotron-3-super:120b` or `qwen3.6:35b` (`TIER2_MODELS`).

### Exit Codes

- `0` — A complete review found nothing blocking (pass or warnings only)
- `1` — Blocking findings
- `2` — Every task's review failed to parse, or a usage error (neither `--task` nor `--phase`, an unknown option)
- `3` — No local model server answered, so no review ran. `--tier2*` does not change this: Tier 2 reviews Tier 1's output and cannot run without it.
- `4` — Tier 2 was due (forced, threshold, or phase gate) but no tier-2 model answered, or none answered with a review; the phase review is incomplete

### Config

`scripts/review/config.toml` — `[tier1] context_window`; `[tier2] enabled`, `mode` (`off`, `manual`, `threshold`, `phase-gate`), thresholds, `context_window` (`--config` points at another file)

### Review JSON Schema

Both tiers emit JSON conforming to `datrix_scripts.review.review_schema`:

```json
{
  "schema_version": "1.0",
  "source": "local" | "phase",
  "model": "<the local model that answered>",
  "scope": "task" | "phase",
  "target": "task-NN-TT-slug.md" | "phase-NN",
  "generated_at": "ISO-8601 timestamp",
  "verdict": "pass" | "warnings_only" | "needs_fixes" | "blocking",
  "findings": [
    {
      "id": "F-001" | "P-001",
      "severity": "blocking" | "major" | "minor" | "nit",
      "category": "anti_pattern" | "missing_section" | "broken_reference" | "dependency_error" | "test_coverage" | "doc_coverage" | "ambiguity" | "scope" | "other",
      "location": "task file section or line reference",
      "description": "What is wrong",
      "evidence": "Quoted text from task file",
      "suggested_fix": "What to change",
      "rule_reference": "ai-agent-rules/prohibited-patterns.md §N" | null
    }
  ],
  "summary": "One-paragraph summary"
}
```

Task findings are numbered `F-NNN`, phase findings `P-NNN`, so an applied marker never confuses the two.

### Troubleshooting

**No local model server** — `ERROR: No local model server can answer` followed by the machines searched and the last failure: none of the searched machines runs an Ollama server that answered on port 11434, or every model that did failed. The stderr lines before the error list what each machine offered (`Local machine <ip>: ...`); start Ollama on one of them, or pass `--local-machine` for a machine that runs it.

**Parse failure stub reviews** — a review with `verdict: "warnings_only"` and the finding `"Tier 1 models failed to produce valid JSON"`: three attempts failed to emit parseable JSON; raw answers are in `.review-debug/`. Check the prompt length against the model's window, simplify the task file or reduce the canonical-modules context, or retry with `--local-model <name>`.

**Tier 2 missing (exit 4)** — no machine holds or can load a `TIER2_MODELS` model, or its answers never parsed as a review. Tier 1 artifacts are still written; `local-llm.ps1 -Status` shows what each machine holds.

### Files and Artifacts

**Tooling:**
```
scripts/review/
  review.ps1, review.sh        # Rendered wrappers of datrix_scripts.review.review; pass every argument through
  config.toml                  # Configuration
  apply-reviews-prep.ps1, .sh  # /apply-reviews worklist
  review-library-gate.ps1, .sh # Behaviour checks for datrix_scripts.review
  prompts/
    local-reviewer.md          # Tier 1 prompt
    phase-reviewer.md          # Tier 2 prompt
scripts/common/lib/datrix_scripts/review/
    review.py                  # Orchestrator
    review_reply.py            # The review request and the parsing of its answer (both tiers)
    review_schema.py           # JSON schema dataclasses
    canonical_modules.py       # Module scanning + caching
    escalation.py              # Tier 1 → Tier 2 decision logic
    tier2_local.py             # Tier 2 phase review on a local model
    apply_reviews_prep.py      # Worklist builder
    review_library_gate.py     # The gate's checks
```

**Per task** (in `.tasks/phase-NN/`):
- `task-NN-TT-{slug}.review.local.json` — Tier 1 review
- `task-NN-TT-{slug}.review.local.verified.json` — Verification review (`--verify`)
- `task-NN-TT-{slug}.review.applied.json` — Applied fixes marker
- `.review-debug/{stem}.{model}.attempt-{N}.txt` — Raw model response on parse failure

**Per phase** (in `d:\datrix\.review\`, `[paths] review_artifacts`):
- `phase-NN.review.phase.json` — Tier 2 review
- `.canonical-modules-cache.json` — Module cache

## `review\apply-reviews-prep.ps1`

Builds the `/apply-reviews` worklist: discovers `*.review.local.json` across every repo's `.tasks\phase-{NN}\` plus the Tier 2 `phase-{NN}.review.phase.json`, validates findings against `datrix_scripts.review.review_schema`, filters out findings already recorded in `.review.applied.json` markers, groups by `target`, and sorts blocking → major → minor → nit. Minimal console; details to JSON.

| Mode | Command | Description |
|------|---------|-------------|
| **All sources** | `.\review\apply-reviews-prep.ps1 -Phase 43` | Worklist → `D:\datrix\.tmp\review\phase-43-worklist.json` |
| **Tier 1 only** | `.\review\apply-reviews-prep.ps1 -Phase 43 -Source local` | Task review findings only |
| **Tier 2 only** | `.\review\apply-reviews-prep.ps1 -Phase 43 -Source phase` | Phase review findings only |
| **Custom base dir** | `.\review\apply-reviews-prep.ps1 -Phase 43 -BaseDir D:\other` | Different workspace |

**Parameters:** `-Phase <NN>` (required, positional 0), `-Source local|phase|all` (default all), `-BaseDir` (default: this workspace), `-Output <path>`, `-Dbg` (DEBUG logging), `-SelfTest` (a planted phase; reads nothing of the workspace). **Exit codes:** 0 = done (also when no review files exist — says so), 2 = usage error (no phase, a missing base directory, a malformed artifact or marker).

**Module:** `datrix_scripts.review.apply_reviews_prep`; POSIX twin `review/apply-reviews-prep.sh` (`--phase`, `--source`, `--base-dir`, `--output`, `--dbg`, `--self-test`).

## `review\review-library-gate.ps1`

Plain-Python behaviour checks (no pytest, no mocks/fakes) for the review library `datrix_scripts.review` (`review_schema`, `canonical_modules`, `escalation`, `review_reply`, `review`, `tier2_local`): `Finding`/`ReviewResult` construction and serialization round-trips, canonical-module package discovery/scanning/digest-building/cache validity/prompt formatting, `should_escalate_to_tier2` across every escalation mode and threshold combination, `extract_json_from_response`/`parse_model_response` JSON-extraction strategies (fences, brace-matching, `<think>` tag stripping, largest-review-JSON selection), the orchestrator core (`resolve_task_context`, `discover_phase_tasks`, `dict_to_review_result`, `build_reviewer_prompt`), and Tier 2 against a loopback Ollama: a phase review with a canned phase verdict writes `phase-NN.review.phase.json` (`P-001`) and exits 0, a pool with no tier-2 model exits 4, and a phase too large for the window is split by task. Repo-level validation **script**, not a pytest suite (the datrix showcase repo hosts none).

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\review\review-library-gate.ps1` | Run every check |
| **Harness self-test** | `.\review\review-library-gate.ps1 -HarnessSelfTest` | Prove the harness detects a forced failure (always reports [FAIL], exits 1) |
| **Debug** | `.\review\review-library-gate.ps1 -Dbg` | Print the python invocation before running |
| **Some checks** | `.\review\review-library-gate.ps1 -Only extract` | Only the checks whose name starts with the prefix |
| **Self-test** | `.\review\review-library-gate.ps1 -SelfTest` | Harness self-test, then the wrapper seam checks |

**Parameters:** `-Only <prefix>`, `-HarnessSelfTest`, `-SelfTest`, `-Dbg`

**Module:** `datrix_scripts.review.review_library_gate`, run in gate mode: it ends with the gate's verdict line (`[GATE] review-library PASSED|FAILED exit=<n> log=<path>`, the log under `.test-output\gates\review-library\`). POSIX twin `review/review-library-gate.sh` (`--only`, `--harness-self-test`, `--self-test`, `--dbg`).

**Assertions:** several checks are inherently adversarial (corrupt/malformed JSON → invalid or `None`, non-review JSON rejected, garbage → `None`, unknown escalation mode never escalates, no tier-2 model → exit 4), which already demonstrates discriminating power; `-HarnessSelfTest` additionally proves the pass/fail harness itself is not vacuous by registering one deliberately-failing dummy check and confirming it is reported `[FAIL]` with a nonzero exit.

**Exit codes:** 0 = every check passed, 1 = at least one check (or the harness self-test) failed, 2 = usage error.

## Workflow

1. Generate tasks: `/generate-tasks`
2. Review locally: `.\review\review.ps1 --phase NN`
3. Apply fixes: "Apply reviews to phase NN" (in Claude Code — runs `apply-reviews-prep.ps1` for the worklist)
4. Verify: `.\review\review.ps1 --phase NN --verify`
5. Execute: `/execute-tasks --phase NN`
