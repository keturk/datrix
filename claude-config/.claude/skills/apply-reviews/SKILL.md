---
model: sonnet
---

# Apply Reviews Skill

Read review artifacts from Tier 1 (local) and/or Tier 2 (Codex), group findings by task file and severity, apply fixes, and mark applied findings to prevent double-application on re-runs.

## When to Use

- User says "apply reviews to phase NN"
- User says "fix tasks based on local review" or "fix tasks based on codex review"
- After running `review.py` and receiving findings
- User wants to apply fixes from review artifacts automatically

## Trigger Phrases

- "Apply reviews to phase {NN}"
- "Fix tasks from review phase {NN}"
- "Apply local review findings"
- "Apply codex review findings"
- "Apply review fixes for phase {NN}"

## Inputs

User provides:
- **Phase number** — which phase's reviews to apply
- **Review source** (optional) — "local" (Tier 1 only), "codex" (Tier 2 only), or "all" (default: both)

## Workflow

### Steps 1–2: Build the Worklist (scripted)

Discovery, schema-validated loading, already-applied filtering, and grouping/sorting are one script call (read `datrix/scripts/quick-reference.md` first; a pre-tool hook enforces this):

```bash
powershell -File "d:/datrix/datrix/scripts/review/apply-reviews-prep.ps1" -Phase {NN} -Source {local|codex|all}
```

Read the resulting `D:\datrix\.tmp\review\phase-{NN}-worklist.json`: findings are grouped by `target` (task file path), sorted blocking → major → minor → nit within each target, and findings already recorded in `.review.applied.json` markers are pre-filtered out (`skipped_already_applied` reports how many). `-Source` defaults to `all`. "No review files found" (exit 0) means there is nothing to apply — report and stop.

For Codex phase-level findings (`target: "phase-{NN}"`), identify affected tasks from evidence/description (Step 4).

**Example worklist structure:**
```
task-43-01-foo.md:
  - F-001 (blocking): Missing ## Targeted Tests section
  - F-002 (major): Anti-pattern: dict.get(key, None) in code skeleton

task-43-02-bar.md:
  - F-003 (major): No test coverage for EntityValidator class

phase-43 (Codex):
  - C-001 (major): Dependency cycle: 43-02 → 43-05 → 43-02
```

### Step 3: Apply Fixes Per Task

For each task file in the worklist (already-applied findings are pre-filtered by the prep script):

1. Read the task file content
2. For each finding (the worklist is already in severity order):
   - Analyze the finding: location, evidence, suggested_fix
   - Apply the fix to the task content
   - Log: `applied_finding task={task} finding_id={id} severity={severity}`
3. Write updated task file
4. Update `.review.applied.json` with newly applied finding IDs (this marker write stays manual — it is the record the next prep run filters on)

**`.review.applied.json` format:**
```json
{
  "applied_at": "ISO-8601 timestamp",
  "applied_findings": ["F-001", "F-002", "C-001"],
  "skipped_findings": ["F-003"],
  "skipped_reason": {
    "F-003": "Cannot auto-fix: requires design decision (which validation rule to prioritize?)"
  }
}
```

**Finding application logic:**

- **Missing section:** Insert section at appropriate location in task file
- **Anti-pattern in code skeleton:** Rewrite code block with fix
- **Broken reference:** Update file path or module name
- **Dependency error:** Update "**Depends on:**" field
- **Test coverage:** Add missing test case or dedicated test task reference
- **Ambiguity:** Add clarification note in "Implementation notes" section

**Example (anti-pattern in code):** Finding `{"category": "anti_pattern", "location": "task-43-02-bar.md, Files to Create §1, line 45", "evidence": "result = data.get('key', None)", "suggested_fix": "Replace with: if 'key' not in data: raise KeyError(...)"}` → locate the code block and replace with:
```python
if "key" not in data:
    raise KeyError(f"Missing required key 'key'. Available: {list(data.keys())}")
result = data["key"]
```

**Skippable findings (cannot auto-fix):**
- Findings requiring design decisions (user must choose approach)
- Findings with ambiguous suggested_fix (multiple valid interpretations)
- Findings that would introduce breaking changes without user consent

### Step 4: Handle Phase-Level Findings (Codex)

Codex findings with `target: "phase-{NN}"` (e.g., dependency cycles) may affect multiple tasks:

1. Parse the finding description to identify affected tasks
   - Example: "Dependency cycle: 43-02 → 43-05 → 43-02" → affects task-43-02 and task-43-05
2. Apply the fix to each affected task
3. Mark the finding as applied in each task's `.review.applied.json`

**Example (dependency cycle fix):**
- Finding C-001: "Dependency cycle: task-43-02 depends on task-43-05, task-43-05 depends on task-43-02"
- Suggested fix: "Remove task-43-05 dependency on task-43-02"
- Action: Open task-43-05, remove "task-43-02" from "**Depends on:**" field
- Mark C-001 as applied in task-43-05.review.applied.json

### Step 5: Report Summary

Print lean summary — applied count + skipped count, then only list skipped findings (applied is the default):

```
REVIEWS: phase {NN} — {N} applied, {N} skipped
Skipped: {task}: {finding-id} — {reason}  (only if any)
```

Do NOT add "Next Steps" — the user knows what to do.

## Important Rules

1. **Never double-apply:** Check `.review.applied.json` before applying each finding
2. **Highest severity first:** Apply blocking findings before major/minor/nit
3. **Skip unfixable findings:** If a finding requires design decisions, skip and report
4. **Write markers:** Always update `.review.applied.json` after applying fixes
5. **Manual verification:** DO NOT automatically re-run review; user triggers `--verify`
6. **Read before writing:** Always read task file before modifying
7. **Preserve formatting:** Maintain task file structure and markdown formatting

## Anti-Patterns

- **No double-application:** Always check markers before applying
- **No silent skips:** Report why findings were skipped
- **No guessing:** If suggested_fix is ambiguous, skip and report (don't guess intent)
- **NO workarounds** — don't steer around issues, don't paper over them. **Fix the root cause, wherever it lives** (CLAUDE.md rule). This is not a binary between "workaround" and "stop": the third option — do the real work — is the default. Stopping is licensed only by a proven B1–B4 blocker with the four-part proof (`.claude/skills/_shared/execution-contract.md`).
- **NO dodging** — "out of scope", "pre-existing", "categorically behavioral", "should be tracked separately", "not my package" are **not** blockers; they are the work. A `SubagentStop` hook greps reports for this vocabulary.
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)

## Success Criteria

- Every discovered finding for the target phase is applied or explicitly skipped-with-reason
- No finding is ever applied twice across re-runs
- Task file structure and markdown formatting are preserved

## Example Session

**User:** "Apply reviews to phase 43"

**Assistant:** Discovers 11 Tier 1 + 1 Tier 2 artifacts, groups 5 findings across 3 tasks, applies fixes in severity order, writes markers.

```
REVIEWS: phase 43 — 4 applied, 1 skipped
Skipped: task-43-03-baz.md: F-005 — requires design decision (in-memory cache vs Redis)
```

## Validation After Applying

After applying all fixes:
1. **Read each modified task file** to verify markdown is valid
2. **Check that all sections** are present and properly formatted
3. **Verify no duplicate sections** were created
4. **Ensure `.review.applied.json` markers** were written for all modified tasks

If any validation fails, report error and do NOT mark finding as applied.

## Manual Review Required

Always remind the user to:
1. **Review the changes** manually before re-running review
2. **Do NOT proceed to execution** until re-review passes

The skill does NOT make judgment calls on ambiguous fixes — when in doubt, skip and report.
