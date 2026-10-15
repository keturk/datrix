# Phase Review Instructions

You reviewed nothing yet: above are ALL task files of one phase, the per-task (Tier 1) review of
each, and the canonical modules of the framework. Review the phase AS A WHOLE. Do not repeat a
per-task finding the Tier 1 reviews already carry; report only what needs the whole phase to see.

## Review Checklist

### 1. Cross-task dependency gaps (blocking)

A task uses a file, symbol, table, flag or behaviour that another task in the phase creates, but
its `**Depends on:**` line does not name that task -- or the dependency points the wrong way (a
task depends on one that runs after it). Name both tasks and the shared item.

### 2. Duplicated scope between tasks (major)

Two tasks create or change the same file, function or behaviour, so the second either redoes or
undoes the first. Name both tasks and the overlapping item.

### 3. Design-reference coverage (major)

A `**Design reference:**` item the phase's tasks name only once and no task delivers in full, or
tasks that cite the same design item and contradict each other on it.

### 4. Canonical-module reuse (major)

A task creates a module, function or helper whose job a canonical module listed above already
does. Name the task, what it creates, and the canonical module to use instead.

## Output Format

VERDICT must be one of: pass, warnings_only, needs_fixes, blocking
- "pass" = no findings
- "warnings_only" = only minor findings
- "needs_fixes" = any major finding
- "blocking" = any blocking finding

SEVERITY must be one of: blocking, major, minor, nit

LOCATION names the task file(s) and section(s).

Output ONLY this JSON:

{"schema_version":"1.0","source":"phase","model":"MODEL_PLACEHOLDER","scope":"phase","target":"TARGET_PLACEHOLDER","generated_at":"TIMESTAMP_PLACEHOLDER","verdict":"VERDICT","findings":[{"id":"P-001","severity":"SEVERITY","category":"CATEGORY","location":"TASK_FILES_AND_SECTIONS","description":"WHAT_IS_WRONG","evidence":"QUOTED_TEXT","suggested_fix":"HOW_TO_FIX","rule_reference":null}],"summary":"ONE_PARAGRAPH_SUMMARY"}

If no issues found, output:

{"schema_version":"1.0","source":"phase","model":"MODEL_PLACEHOLDER","scope":"phase","target":"TARGET_PLACEHOLDER","generated_at":"TIMESTAMP_PLACEHOLDER","verdict":"pass","findings":[],"summary":"No phase-level issues found."}

Start your response with { and end with }. No other text.
