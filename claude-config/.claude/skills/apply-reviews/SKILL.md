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

### Step 1: Discover Review Artifacts

1. Find all `*.review.local.json` files in `d:\datrix\{repo}\.tasks\phase-{NN}\`
2. Find `phase-{NN}.review.codex.json` in `d:\datrix\.review\` (if Tier 2 ran)
3. Load all review artifacts as ReviewResult objects (use review_schema.py)
4. Filter by review source if user specified "local" or "codex"

**Discovery pattern:**
```python
# For Tier 1 artifacts
for repo_dir in Path("d:/datrix").glob("datrix*"):
    phase_dir = repo_dir / f".tasks/phase-{phase_num:02d}"
    if phase_dir.exists():
        tier1_artifacts.extend(phase_dir.glob("*.review.local.json"))

# For Tier 2 artifact
tier2_artifact = Path("d:/datrix/.review") / f"phase-{phase_num:02d}.review.codex.json"
if tier2_artifact.exists():
    tier2_artifacts.append(tier2_artifact)
```

### Step 2: Group Findings by Task and Severity

For each review artifact:
1. Extract findings list
2. Group by `target` (task file path)
3. Within each task, sort by severity: blocking → major → minor → nit
4. For Codex phase-level findings (`target: "phase-{NN}"`), identify affected tasks from evidence/description

**Example structure:**
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

For each task file with findings:

1. Read the task file content
2. Read existing `.review.applied.json` marker (if exists) to skip already-applied findings
3. For each finding (highest severity first):
   - If finding ID is in `.review.applied.json`, skip (already applied)
   - Analyze the finding: location, evidence, suggested_fix
   - Apply the fix to the task content
   - Log: `applied_finding task={task} finding_id={id} severity={severity}`
4. Write updated task file
5. Update `.review.applied.json` with newly applied finding IDs

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

Print summary table:

```
Apply Reviews — Phase {NN}

Review Sources:
  - Tier 1 (local): {N} artifacts loaded
  - Tier 2 (Codex): {1 artifact / not available}

Task Fixes:
  task-43-01-foo.md: 2 findings applied (1 blocking, 1 major)
  task-43-02-bar.md: 1 finding applied (1 major)
  task-43-05-baz.md: 1 finding skipped (F-003: ambiguous requirement)

Phase-Level Fixes:
  Dependency cycle (C-001): 2 tasks updated (task-43-02, task-43-05)

Skipped Findings:
  task-43-03-qux.md: F-005 (cannot auto-fix: requires design decision)
    Reason: Design must choose between in-memory cache or Redis

Total: 3 findings applied, 1 skipped

Next Steps:
  1. Review applied changes manually
  2. Run re-review: python d:/datrix/datrix/scripts/library/review/review.py --phase {NN} --verify
  3. If re-review passes, proceed to execution: /execute-tasks
```

## Important Rules

1. **Never double-apply:** Check `.review.applied.json` before applying each finding
2. **Highest severity first:** Apply blocking findings before major/minor/nit
3. **Skip unfixable findings:** If a finding requires design decisions, skip and report
4. **Write markers:** Always update `.review.applied.json` after applying fixes
5. **Manual verification:** DO NOT automatically re-run review; user triggers `--verify`
6. **Read before writing:** Always read task file before modifying
7. **Preserve formatting:** Maintain task file structure and markdown formatting

## Anti-Patterns

- **No automatic re-review:** User explicitly runs `review.py --verify` after inspecting changes
- **No double-application:** Always check markers before applying
- **No silent skips:** Report why findings were skipped
- **No guessing:** If suggested_fix is ambiguous, skip and report (don't guess intent)

## Success Criteria

- Discovers all review artifacts for target phase
- Groups findings by task and severity
- Applies fixes in severity order (blocking → major → minor → nit)
- Writes `.review.applied.json` marker for each task
- Skips already-applied findings
- Reports summary with counts and next steps
- Does NOT automatically re-run review (waits for user --verify command)
- Preserves task file structure and formatting

## Example Session

**User:** "Apply reviews to phase 43"

**Assistant:**

Step 1: Discovering review artifacts...
- Found 11 Tier 1 artifacts (*.review.local.json)
- Found 1 Tier 2 artifact (phase-43.review.codex.json)

Step 2: Grouping findings by task...
- 5 findings across 3 tasks

Step 3: Applying fixes...

*Applying to task-43-01-foo.md (2 findings):*
- F-001 (blocking): Missing ## Targeted Tests section → Added section
- F-002 (major): Anti-pattern dict.get(key, None) → Replaced with explicit KeyError

*Applying to task-43-02-bar.md (1 finding):*
- F-003 (major): No test coverage for EntityValidator → Added test task reference

*Skipping task-43-03-baz.md (1 finding):*
- F-005 (major): Cannot auto-fix - requires design decision

Step 4: Handling phase-level findings...

*Applying C-001 (dependency cycle):*
- Affected tasks: task-43-02, task-43-05
- Fix: Removed task-43-02 from task-43-05 dependencies

Step 5: Writing markers...
- task-43-01-foo.md.review.applied.json (2 findings)
- task-43-02-bar.md.review.applied.json (1 finding + C-001)
- task-43-05-baz.md.review.applied.json (C-001)

```
Apply Reviews — Phase 43

Review Sources:
  - Tier 1 (local): 11 artifacts loaded
  - Tier 2 (Codex): 1 artifact loaded

Task Fixes:
  task-43-01-foo.md: 2 findings applied (1 blocking, 1 major)
  task-43-02-bar.md: 1 finding applied (1 major)

Phase-Level Fixes:
  Dependency cycle (C-001): 2 tasks updated (task-43-02, task-43-05)

Skipped Findings:
  task-43-03-baz.md: F-005 (cannot auto-fix: requires design decision)
    Reason: Design must choose between in-memory cache or Redis

Total: 4 findings applied, 1 skipped

Next Steps:
  1. Review applied changes manually
  2. Run re-review: python d:/datrix/datrix/scripts/library/review/review.py --phase 43 --verify
  3. If re-review passes, proceed to execution
```

## Finding-Specific Fix Patterns

### Missing Section

**Finding:**
```json
{
  "category": "missing_section",
  "location": "task-43-01-foo.md",
  "description": "Missing ## Targeted Tests section",
  "suggested_fix": "Add ## Targeted Tests section with pytest command"
}
```

**Fix:**
Insert section before `## Tests` section:
```markdown
## Targeted Tests

**Package:** `datrix`
**Test command:**
```
python -m pytest d:/datrix/datrix/scripts/library/foo/tests/test_foo.py -v
```
```

### Anti-Pattern in Code

**Finding:**
```json
{
  "category": "anti_pattern",
  "location": "task-43-02-bar.md, Files to Create §1, line 45",
  "evidence": "result = data.get('key', None)",
  "suggested_fix": "Replace with: if 'key' not in data: raise KeyError(...)"
}
```

**Fix:**
Locate the code block, replace the line:
```python
if "key" not in data:
    raise KeyError(f"Missing required key 'key'. Available: {list(data.keys())}")
result = data["key"]
```

### Broken Module Reference

**Finding:**
```json
{
  "category": "broken_reference",
  "location": "task-43-03-baz.md, Files to Review §2",
  "evidence": "from datrix_language.parser.entity import Entity",
  "suggested_fix": "Correct import: from datrix_language.datrix_model.entity import Entity"
}
```

**Fix:**
Update the import path in the task file's code skeleton or instructions.

### Dependency Error

**Finding:**
```json
{
  "category": "dependency_error",
  "location": "task-43-04-qux.md",
  "description": "Task depends on task-43-99 which does not exist",
  "suggested_fix": "Remove non-existent dependency task-43-99"
}
```

**Fix:**
Update "**Depends on:**" field:
```markdown
**Depends on:** task-43-03
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
2. **Run `--verify` mode** to confirm fixes resolved the issues
3. **Do NOT proceed to execution** until re-review passes

The skill does NOT make judgment calls on ambiguous fixes — when in doubt, skip and report.
