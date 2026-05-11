# Review Instructions

Review the task file above for SUBJECTIVE defects only. Structural checks
(required sections, metadata, title format) are handled separately. Focus on:

## Review Checklist

### 1. Module References (blocking if broken)

If canonical modules are listed above, verify that import paths referenced in
the task file match real modules. Flag any import path that does NOT exist in
the canonical modules list.

### 2. Anti-Pattern Violations (major)

Check code skeletons in "Files to Create" for prohibited patterns:
- `type_map.get(t, "Any")` — must fail on unknown types
- String concatenation for code generation — must use templates/Jinja2
- Overly broad exception handling without re-raise

### 3. Test Coverage (major if missing)

Tasks creating >100 lines of code need a `## Tests` section or a separate test task.
If the task has a `## Targeted Tests` section, this is satisfied.

### 4. Ambiguity (minor)

Flag vague language: "handle appropriately", "clean up", "make it better",
"fix issues", "optimize" — without specifying concrete actions.

## Output Format

VERDICT must be one of: pass, warnings_only, needs_fixes, blocking
- "pass" = no findings
- "warnings_only" = only minor findings
- "needs_fixes" = any major finding
- "blocking" = any blocking finding

SEVERITY must be one of: blocking, major, minor, nit

Output ONLY this JSON:

{"schema_version":"1.0","source":"local","model":"MODEL_PLACEHOLDER","scope":"task","target":"TARGET_PLACEHOLDER","generated_at":"TIMESTAMP_PLACEHOLDER","verdict":"VERDICT","findings":[{"id":"F-001","severity":"SEVERITY","category":"CATEGORY","location":"SECTION_NAME","description":"WHAT_IS_WRONG","evidence":"QUOTED_TEXT","suggested_fix":"HOW_TO_FIX","rule_reference":null}],"summary":"ONE_PARAGRAPH_SUMMARY"}

If no issues found, output:

{"schema_version":"1.0","source":"local","model":"MODEL_PLACEHOLDER","scope":"task","target":"TARGET_PLACEHOLDER","generated_at":"TIMESTAMP_PLACEHOLDER","verdict":"pass","findings":[],"summary":"No subjective issues found. Task content is clear and well-specified."}

Start your response with { and end with }. No other text.
