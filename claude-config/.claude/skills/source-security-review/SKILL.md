---
name: source-security-review
description: >-
  Security-review the SOURCE CODE under a given folder and produce a vulnerability
  report. Use when the user wants a security review, audit, or threat assessment of
  an existing codebase / directory tree (NOT a design doc — use /design-security-review
  for that; NOT just pending changes — use the built-in /security-review for a diff).
  Adapts Anthropic's official claude-code-security-review methodology to whole-tree
  static review: input validation, auth, crypto, injection, and sensitive-data exposure,
  with high-confidence false-positive discipline.
---

# Source Security Review

Security-review the source code under a **given folder** and produce a focused,
high-signal vulnerability report.

**Read `../_shared/security-review-core.md` first and follow it** — injection safety,
the six analysis categories, false-positive discipline, severity guidance, the base
report skeleton, saving-the-report rules, and When-to-STOP all live there. This file
covers only what is specific to reviewing SOURCE CODE under a folder rather than a
design document: tree enumeration/scope control and `file:line` citation.

## Inputs

- **Target folder:** path to the directory to review (passed as an argument). If none
  is given, ask which folder — do not guess or default to the whole repo.
- **Optional scope note:** a language, subsystem, or concern to emphasize.

If the path doesn't exist or isn't a directory, STOP and report that.

## Scope control (do this first — a tree can be huge)

1. **Enumerate** source files under the target (use Glob/Grep, not by reading everything).
2. **Exclude noise** unless explicitly asked to include it: dependency/vendor dirs
   (`node_modules`, `.venv`, `venv`, `vendor`, `dist`, `build`, `target`, `.git`),
   generated code, lockfiles, binaries, and large data fixtures.
3. **Prioritize by attack surface** — review highest-risk files first:
   - Entry points (HTTP/RPC handlers, route definitions, CLI arg parsing, message/queue
     consumers, deserializers, file/upload handlers).
   - Anywhere external input reaches a query, command, template, path, or markup sink.
   - Auth/session/crypto/secret-handling code.
4. **Respect Task Scope Back-Off** (project rule): if the tree is too large to review
   thoroughly in one pass, STOP and report the file inventory + a proposed prioritized
   batching plan rather than skimming everything shallowly. State explicitly what you
   covered and what you did not — never imply full coverage you didn't achieve.

Apply the shared categories and false-positive discipline to real code, citing
`file:line` for every claim — the official review targets ~>80% confidence. Verify the
data actually reaches the sink unsanitized before reporting; don't flag a sink whose
input is provably constant or already validated upstream.

## Report additions specific to source code

Per finding: **Location** is `path/to/file.ext:line` (clickable); **Vulnerability**
quotes the relevant lines; **Recommendation** names the specific code-level fix (and
the secure API/pattern to use).

Add a coverage statement to `## Summary`: files/areas reviewed vs. explicitly NOT
reviewed.

Add a **`## Lower-confidence observations`** section after Findings: things worth a
look that didn't meet the confidence bar, clearly labeled as such.

## When to STOP and report instead of guessing

In addition to the shared conditions: the tree is too large to review thoroughly in one
pass (report inventory + batching plan); a finding's severity hinges on runtime/config
you can't see in the code (report it as a lower-confidence observation with the
assumption stated, rather than inventing facts).
