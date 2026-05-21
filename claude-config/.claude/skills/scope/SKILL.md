---
description: Anchor a session with explicit scope constraints — language, generator, files to read first
model: sonnet
disable-model-invocation: true
---

# Session Scope Anchor

Define explicit scope constraints for the current session to prevent wrong-direction exploration. This skill is injected into context at the start of a session to constrain Claude's investigation and editing scope.

## When to Use

- Starting a debugging or fix session
- Starting any task that involves a specific language generator
- When past sessions have drifted into wrong languages or projects
- Whenever you want to front-load the files Claude should read first

## How to Invoke

```
/scope

LANGUAGE: TypeScript
FILES TO READ FIRST:
- datrix-codegen-typescript/src/datrix_codegen_typescript/generators/entity_generator.py
- datrix-codegen-typescript/src/datrix_codegen_typescript/templates/entity.ts.j2
STAY OUT OF:
- datrix-codegen-python/
```

Minimal form:
```
/scope

LANGUAGE: Python
```

## Scope Rules (Active for Entire Session)

Once `/scope` is invoked, the following rules apply for the **entire session**:

### Language Constraint

If `LANGUAGE` is specified:
- **ONLY** work on the specified language generator
- **DO NOT** read, edit, or investigate files in the other language's codegen package
- If you encounter a cross-language issue, STOP and report it — do not chase it

### Files to Read First

If `FILES TO READ FIRST` is specified:
- Read ALL listed files **before forming any hypothesis**
- Summarize what each file does before proposing a fix
- These files define the ground truth — do not fabricate assumptions about their behavior

### Stay-Out Zones

If `STAY OUT OF` is specified:
- **DO NOT** read or edit files in these directories
- If a root cause traces into a stay-out zone, report it and STOP — do not enter

### Default Constraints (Always Active)

Even without explicit specification:
- Read `generate.ps1` before assuming how the build pipeline works
- Read the category-specific `quick-reference.md` (e.g., `scripts/test/quick-reference.md`) before running unfamiliar scripts
- Confirm which generator package is relevant before editing

## Scope Violation Handling

If at any point during the session you realize you need to work outside the defined scope:

```
Scope violation: I need to look at {what} in {where}, which is outside the defined scope.

Reason: {why this is needed}

Options:
1. Expand scope to include {what}
2. Document as a separate issue and stay in scope
3. Pause and let you decide
```

**WAIT for user decision. Do NOT silently expand scope.**
