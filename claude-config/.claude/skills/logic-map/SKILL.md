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

**Kinds:** `@canonical` (source-of-truth), `@pattern` (approved approach), `@boundary` (data transformation point), `@invariant` (system-wide rule)

**Sub-directives:** `@rule:` (constraint), `@anti-pattern:` (common mistake), `@see:` (cross-reference)

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

- **NO workarounds** — don't steer around issues, don't paper over them; fix the root cause or STOP and report (CLAUDE.md rule)
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
