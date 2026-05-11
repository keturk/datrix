# Skill: Operationalize Design v2

**Version:** 2.0
**Status:** Production (requires Task Review System)
**Replaces:** None (coexists with `/operationalize-design` v1)

## Description

Converts a design document into actionable task files with **automated review validation** using the Task Review System. This skill integrates Tier 1 (local LLM) and optional Tier 2 (Codex) review, applies fixes automatically, and verifies task quality before marking operationalization as complete.

**Key difference from v1:** v2 ensures generated tasks are validated and corrected before implementation starts, catching common mistakes (anti-patterns, broken references, missing sections, dependency errors) that would otherwise surface during execution.

**When to use v2 vs v1:**
- Use v2 for production-bound designs (quality-critical, multi-repo, complex dependencies)
- Use v1 for rapid prototyping or when review system unavailable
- Default: use v2 unless you need maximum speed over validation

## Trigger Phrases

- `/operationalize-design-v2 <design_doc_path>`
- `operationalize design v2 <design_doc_path>`
- `convert design to tasks with review <design_doc_path>`

## Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `design_doc_path` | Yes | - | Path to design document (e.g., `design/TASK_REVIEW_SYSTEM_DESIGN.md`) |
| `--phase NN` | No | Auto-detect | Explicit phase number |
| `--codex-gate` | No | False | Run Tier 2 (Codex) review as final quality gate |
| `--no-review` | No | False | Skip review entirely (v1 behavior) |
| `--review-timeout` | No | 1800 | Max seconds to wait for review system |

## Dependencies

**Required:**
- Design document with resolved open questions (no prerequisites mode)
- `d:\datrix\.claude\skills\generate-tasks\SKILL.md` (for task generation)
- `d:\datrix\.claude\skills\apply-reviews\SKILL.md` (for fix application)

**Optional (graceful degradation if missing):**
- `d:\datrix\datrix\scripts\review\review.py` (Task Review System orchestrator)
- Ollama endpoint `http://10.94.0.100:11434` (Tier 1 reviewer)
- Codex CLI (Tier 2 reviewer, only if `--codex-gate` specified)

## Workflow

### Phase 1: Task Generation (Same as v1)

1. **Read and validate design document**
   - Check if design exists and is readable
   - Detect if design has unresolved open questions (prerequisites mode)
   - If prerequisites detected: report to user and exit (design not ready)

2. **Generate task files**
   - Use existing Generate Tasks skill logic
   - Parse design into implementation phases
   - Create task markdown files in `{repo}/.tasks/phase-NN/`
   - One task per significant deliverable
   - Include all standard task sections (Files to Create, Implementation Steps, Test Plan, etc.)

3. **Initial report**
   ```
   Task generation complete:
   - 8 tasks created across 3 repos
   - Phase: 05
   - Next: Running Tier 1 review...
   ```

### Phase 2: Tier 1 Review Loop (NEW)

**Skip if `--no-review` flag is set.**

4. **Check review system availability**
   ```python
   review_script = "d:\\datrix\\datrix\\scripts\\review\\review.py"
   if not os.path.exists(review_script):
       warn("Task Review System not installed")
       if args.codex_gate:
           warn("Cannot run Codex gate without Tier 1 baseline")
           ask_user("Continue without review? [y/N]")
       else:
           warn("Tasks generated but NOT validated. Use /operationalize-design (v1) if review not needed.")
           ask_user("Continue without review? [y/N]")
   ```

5. **Run Tier 1 initial review**
   ```bash
   python d:\datrix\datrix\scripts\review\review.py --phase {phase_num}
   ```

   - Review runs on all generated task files
   - Produces `*.review.local.json` artifacts
   - Handles Ollama unreachable gracefully (see step 6)
   - Handles parse failures gracefully (see step 6a)

6. **Handle Ollama unreachable**

   If Ollama is unreachable (exit code 3):
   - If `--codex-gate` is set: log warning, skip to Tier 2 (step 10)
   - If no Codex flag: report error and ask user:
     ```
     ERROR: Tier 1 reviewer unreachable (Ollama at http://10.94.0.100:11434)

     Options:
     1. Fix Ollama and retry
     2. Continue without review (not recommended for production)
     3. Abort operationalization

     Choice [1/2/3]:
     ```

6a. **Handle parse failures (exit code 2)**

   If the review script exits with code 2, ALL tasks failed to parse (models produced
   responses but not valid JSON). This is an infrastructure issue, NOT a pass.

   Read the `*.review.local.json` files — each will have a single `F-000` finding with
   `"Tier 1 models failed to produce valid JSON"`. Raw model responses are dumped to
   `.review-debug/` directories next to task files for inspection.

   Report to user:
   ```
   WARNING: Tier 1 review infrastructure failure — models produced responses
   but none were valid JSON. This is NOT a pass.

   Parse failure count: {N}/{total}
   Raw responses saved to .review-debug/ directories for inspection.

   Options:
   1. Retry review (models may succeed on second run)
   2. Continue without review (tasks not validated)
   3. Abort operationalization
   ```

   If user chooses retry: re-run step 5 (one retry only, no infinite loop).
   If user chooses continue: proceed to step 7 with the caveat that review data is missing.
   Report parse failure count in the final summary (step 17).

7. **Parse Tier 1 results**

   Read `*.review.local.json` files and count findings by severity:
   ```python
   findings = {
       "blocking": 0,
       "major": 0,
       "minor": 0,
       "nit": 0
   }
   ```

8. **Apply Tier 1 fixes (if needed)**

   If `findings["blocking"] > 0` or `findings["major"] > 0`:

   ```
   Tier 1 review found 12 issues:
   - 3 blocking
   - 5 major
   - 4 minor

   Applying fixes...
   ```

   Run Apply Reviews skill:
   ```
   /apply-reviews --phase {phase_num}
   ```

   Apply Reviews reads review artifacts and fixes tasks.

9. **Verify Tier 1 fixes**

   After applying fixes, re-run Tier 1:
   ```bash
   python d:\datrix\datrix\scripts\review\review.py --phase {phase_num}
   ```

   This produces `*.review.local.verified.json` artifacts.

   **If verification still has blocking findings:**
   ```
   ERROR: Tier 1 verification failed

   2 blocking findings remain after fixes:
     [F-003] task-05-03-generator.md: Missing test section
     [F-007] task-05-07-docs.md: Broken module reference

   Review artifacts: d:\datrix\datrix-common\.tasks\phase-05\*.review.local.verified.json

   Options:
   1. Manually fix tasks and re-run skill
   2. Regenerate tasks (fix design doc and re-run)
   3. Skip review for now (use /operationalize-design v1)

   Operationalization INCOMPLETE.
   ```

   Exit with error code 1.

   **If verification passes:**
   ```
   ✓ Tier 1 verification passed
   - Fixed 8 findings
   - Remaining: 4 minor (acceptable)
   - Wall time: 6m 23s
   ```

### Phase 3: Tier 2 Review Loop (OPTIONAL)

**Only runs if `--codex-gate` flag is set AND Tier 1 passed.**

10. **Run Tier 2 phase gate**

    ```bash
    python d:\datrix\datrix\scripts\review\review.py --phase {phase_num} --codex-phase-gate
    ```

    - Codex reviews all tasks with phase-wide context
    - Catches cross-task issues (dependency cycles, missing integration tests, etc.)
    - Produces `phase-{phase_num}.review.codex.json`

11. **Handle Codex rate limit**

    If Codex returns rate limit error:
    ```
    WARNING: Codex rate limit reached (weekly GPT-5.x limit)

    Tier 1 review: PASS
    Tier 2 review: FAILED (rate limit)

    Options:
    1. Wait for rate limit reset and retry later
    2. Proceed without Tier 2 (Tier 1 passed, most issues caught)
    3. Abort operationalization

    Recommendation: Proceed. Tier 2 checks cross-task deps, but Tier 1 caught critical issues.

    Choice [1/2/3]:
    ```

12. **Apply Tier 2 fixes (if needed)**

    If Tier 2 found issues:
    ```
    Tier 2 review found 2 cross-task issues:
    - Task-05-02 depends on Task-05-06 (cycle risk)
    - Missing integration test for end-to-end workflow

    Applying fixes...
    ```

    Run Apply Reviews again:
    ```
    /apply-reviews --phase {phase_num}
    ```

13. **Verify Tier 2 fixes**

    Re-run Tier 2:
    ```bash
    python d:\datrix\datrix\scripts\review\review.py --phase {phase_num} --codex
    ```

    If still failing: same error handling as step 9.

    If passing:
    ```
    ✓ Tier 2 verification passed
    - Fixed 2 cross-task issues
    - Wall time: 2m 47s
    ```

### Phase 4: Documentation Transfer (Same as v1)

14. **Identify permanent docs to update**

    Based on design content, determine which repo docs need updates:
    - `datrix/docs/architecture/*.md`
    - `datrix-common/docs/contributing/*.md`
    - Package-specific docs

15. **Transfer knowledge**

    Move permanent design knowledge from design doc into repo docs:
    - Architecture decisions → `architecture/*.md`
    - Coding rules → `contributing/ai-agent-rules/*.md`
    - Workflow changes → `contributing/workflows.md`
    - Testing patterns → `contributing/test-guidelines/*.md`

16. **Delete design doc**

    Design doc is now absorbed into permanent docs:
    ```bash
    rm design/TASK_REVIEW_SYSTEM_DESIGN.md
    ```

### Phase 5: Final Report

17. **Generate review summary**

    ```
    ✓ Operationalization complete for phase-05

    Task Generation:
    - 8 tasks created across 3 repos (datrix-common, datrix-cli, datrix)
    - 0 prerequisites identified

    Tier 1 Review (deepseek-r1:32b @ Ollama):
    - Initial: 12 findings (3 blocking, 5 major, 4 minor)
    - Applied fixes to 8 findings
    - Verification: 4 findings (0 blocking, 0 major, 4 minor)
    - Final: PASS
    - Wall time: 6m 23s

    Tier 2 Review (GPT-5.x-codex @ Codex CLI):
    - Phase gate: 2 findings (0 blocking, 2 major)
      * Cross-task: Task-05-02 depends on Task-05-06 (cycle risk)
      * Missing: No integration test task for end-to-end workflow
    - Applied fixes
    - Verification: PASS
    - Wall time: 2m 47s

    Documentation:
    - Updated: datrix/docs/architecture/pipeline-and-capabilities.md
    - Updated: datrix-common/docs/contributing/ai-agent-rules.md
    - Deleted: design/TASK_REVIEW_SYSTEM_DESIGN.md (absorbed)

    Tasks ready for execution at:
    - d:\datrix\datrix-common\.tasks\phase-05\
    - d:\datrix\datrix-cli\.tasks\phase-05\
    - d:\datrix\datrix\.tasks\phase-05\

    Next: Run /execute-tasks --phase 05 to implement
    ```

    **If parse failures occurred**, include in the summary:
    ```
    Tier 1 Review:
    - Parse failures: {N}/{total} tasks (models returned text but not valid JSON)
    - Raw responses: .review-debug/ directories
    - Final: DEGRADED (review data incomplete)
    ```

    Do NOT report "PASS" when parse failures occurred. Use "DEGRADED" or "FAILED"
    to make it clear the review was not fully successful.

18. **Exit successfully**

    Return exit code 0.

## Error Handling

### Review System Not Available

If `review.py` not found:
- Warn user that tasks are not validated
- Offer to continue without review or abort
- If user continues: behaves like v1 (no validation)

### Review Verification Failures

If Tier 1 or Tier 2 verification still fails after fixes:
- Report which findings remain
- Point to review artifact files
- Offer options (manual fix, regenerate, skip review)
- Exit with error code 1 (operationalization incomplete)

### Codex Rate Limit

If Codex hits weekly limit:
- Report that Tier 1 passed (most issues caught)
- Offer to proceed without Tier 2 or wait and retry
- Document that cross-task checks were skipped

### Design Prerequisites Mode

If design doc has unresolved open questions:
- Report that design is not ready for operationalization
- List the open questions from prerequisites report
- Exit with instructions to resolve questions first

## Integration Points

**Calls these skills:**
- `/generate-tasks` (implicitly, via shared logic)
- `/apply-reviews` (explicitly, via Skill tool)

**Calls these scripts:**
- `python d:\datrix\datrix\scripts\review\review.py --phase NN`
- `python d:\datrix\datrix\scripts\review\review.py --phase NN --codex-phase-gate`

**Produces artifacts:**
- `{repo}/.tasks/phase-NN/task-*.md` (task files)
- `{repo}/.tasks/phase-NN/*.review.local.json` (Tier 1 reviews)
- `{repo}/.tasks/phase-NN/*.review.local.verified.json` (Tier 1 verification)
- `{repo}/.tasks/phase-NN/*.review.applied.json` (fix tracking)
- `d:\datrix\.review\phase-NN.review.codex.json` (Tier 2 review, if `--codex-gate`)

## Implementation Notes

**Graceful degradation:**
- If review system unavailable, warn and offer to continue
- If Ollama unreachable but Codex available, skip to Tier 2
- If Codex rate-limited, proceed with Tier 1 only

**No retry loops:**
- Review → apply → verify is ONE iteration
- If verification fails, human intervention required
- Do not silently retry multiple times

**Review artifacts are preserved:**
- All `.review.*.json` files stay in place for debugging
- User can manually inspect what was found and what was fixed
- Orchestrator run logs available at `d:\datrix\.review\phase-NN.run-log.json`

**Backwards compatibility:**
- v1 (`/operationalize-design`) remains unchanged
- v2 is opt-in; v1 is still the default in existing workflows
- Both skills can coexist; no migration required

## Testing Strategy

1. **Happy path:** Simple design doc (3-4 tasks), no review errors
2. **Tier 1 fixes:** Design that generates tasks with known issues
3. **Review unavailable:** Ollama down, verify graceful degradation
4. **Parse failures:** Models return text but not valid JSON, verify exit code 2 and retry offer
5. **Prerequisites mode:** Design doc with open questions, verify clean exit
