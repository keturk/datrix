---
description: Logic map reference — query, add, and maintain canonical implementation markers
model: sonnet
disable-model-invocation: true
---

# Logic Map

A system of marked comments in source code documenting canonical implementations, approved patterns, system boundaries, and invariants. Markers are extracted into a SQLite database at `d:/datrix/.logic-map/markers.db`.

## Query Before Writing New Code

```bash
# Query by topic
sqlite3 d:/datrix/.logic-map/markers.db "SELECT topic, summary, file, line FROM markers WHERE topic LIKE '%text%'"

# Check for canonical implementations in a domain
sqlite3 d:/datrix/.logic-map/markers.db "SELECT topic, summary FROM markers WHERE kind='canonical' AND topic LIKE '%parser%'"

# Find approved patterns
sqlite3 d:/datrix/.logic-map/markers.db "SELECT topic, summary FROM markers WHERE kind='pattern'"
```

## When to Add Markers

- New **canonical implementation** (source-of-truth function/class)
- New **pattern** that other code should follow
- New **system boundary** (data transformation point)
- New **invariant** (rule that must hold system-wide)

## Marker Syntax

```python
# @canonical(topic/subtopic): One-line summary
# Description paragraph (optional, multi-line).
# @rule: A rule that must be followed
# @anti-pattern: What NOT to do
# @see: other/topic
def canonical_function(...):
```

**Kinds:** `@canonical` (source-of-truth), `@pattern` (approved approach), `@boundary` (data transformation point), `@invariant` (system-wide rule), `@test-rule` (conformance rule on a test function)

**Sub-directives:** `@rule:` (constraint), `@anti-pattern:` (common mistake), `@see:` (cross-reference)

## Test Rules (conformance matrix)

Annotate **test functions** to record what rule the test enforces and how it differs across targets. The shared `topic` is the join key; one `@test-rule` per target.

```python
# @test-rule(operators/equality): Equality maps to the target strict-equality operator.
# @dim: language=typescript
# @behavior: == → ===, != → !==
# @differs: python keeps ==/!= ; sql uses =/<>
# @see: operators/logical
def test_equality_maps_to_strict(self) -> None:
```

**Test-rule sub-directives:**
- `@dim: key=value` — repeatable, **open vocabulary**. Use whatever dimensions a rule varies on (e.g. `language=typescript`, `provider=aws`, `variant=msk-serverless`). Never hardcode a fixed language/provider set — Datrix is multi-language, multi-platform.
- `@behavior:` — this target's expected outcome (the matrix cell).
- `@differs:` — free-text note on how it diverges from other targets.

Reuse the **same `topic`** on each target's test so the report can pivot them into one row group. Query the matrix:

```sql
-- All targets + behaviors for a rule
SELECT m.topic, d.key||'='||d.value AS target, m.behavior, m.file, m.line
FROM markers m JOIN dimensions d ON d.marker_id = m.id
WHERE m.kind='test-rule' AND m.topic LIKE 'operators/%'
ORDER BY m.topic, target;
```

The `logic-map-report.ps1` report renders a **Rule Matrix** section (one pivot table per topic) plus a "single-target rules" list flagging rules asserted for only one target.

## Scripts

| Task | Command |
|------|---------|
| Rebuild all | `powershell -File "d:/datrix/datrix/scripts/dev/logic-map.ps1" -All` |
| Rebuild one project | `powershell -File "d:/datrix/datrix/scripts/dev/logic-map.ps1" datrix-language` |
| Rebuild src only | `powershell -File "d:/datrix/datrix/scripts/dev/logic-map.ps1" -All -Src` |
| Readable report | `powershell -File "d:/datrix/datrix/scripts/dev/logic-map-report.ps1"` |
| Report to path | `powershell -File "d:/datrix/datrix/scripts/dev/logic-map-report.ps1" -Output docs/logic-map.md` |

## Maintaining Markers

- When modifying a marked function, **update the marker** if behavior changes
- When deleting marked code, **remove the marker**
- After changes, rebuild: `powershell -File "d:/datrix/datrix/scripts/dev/logic-map.ps1" -All`

## Anti-Patterns

- **NO workarounds** — don't steer around issues, don't paper over them. **Fix the root cause, wherever it lives** (CLAUDE.md rule). This is not a binary between "workaround" and "stop": the third option — do the real work — is the default. Stopping is licensed only by a proven B1–B4 blocker with the four-part proof (`.claude/skills/_shared/execution-contract.md`).
- **NO dodging** — "out of scope", "pre-existing", "categorically behavioral", "should be tracked separately", "not my package" are **not** blockers; they are the work. A `SubagentStop` hook greps reports for this vocabulary.
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
