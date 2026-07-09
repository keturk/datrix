---
name: design-security-review
description: >-
  Threat-model a DESIGN DOCUMENT and produce a security review report. Use when
  the user wants a security review, threat model, or risk assessment of a design
  doc, architecture proposal, RFC, or spec (NOT a code diff — for changed code use
  the built-in /security-review). Adapts Anthropic's official claude-code-security-review
  methodology to design-level analysis: trust boundaries, data flows, auth, crypto,
  injection surfaces, and sensitive-data exposure.
---

# Design Security Review

Produce a focused, high-signal security review report for a **design document**
(architecture proposal, RFC, spec, or `design/` doc).

**Read `../_shared/security-review-core.md` first and follow it** — injection safety,
the six analysis categories, false-positive discipline, severity guidance, the base
report skeleton, saving-the-report rules, and When-to-STOP all live there. This file
covers only what is specific to reviewing a DESIGN DOCUMENT rather than code.

## Inputs

- **Target:** path to the design document (passed as an argument). If none is given,
  ask which document to review — do not guess.
- **Optional scope note:** any specific concern the user wants emphasized.

If the target path doesn't exist or isn't readable, STOP and report that — do not
proceed against a guessed file.

## Process — trust-boundary / data-flow / threat-model framing

1. **Read the full document** (and only the explicitly cross-referenced architecture
   docs it names, read-only) so findings are grounded in what the design actually says.
   Cite the section/heading for every claim.
2. **Map the system before judging it:**
   - **Trust boundaries** — where does control/data cross from less-trusted to
     more-trusted (network edge, tenant boundary, service-to-service, user→system,
     third-party integrations)?
   - **Data flows** — what sensitive data moves where, and over what channel?
   - **Attack surface** — every externally reachable entry point named or implied.
3. **Analyze each category** (from the shared core doc) against the design. For a
   design (vs. code), a "finding" is a *design-level risk*: a control that is missing,
   underspecified, placed on the wrong side of a trust boundary, or assumed but never
   stated.
4. **Apply false-positive discipline** (shared core doc) before writing anything down.
   Because a design doc is necessarily incomplete, do **not** flag every unmentioned
   control as a vulnerability. Distinguish:
   - **Missing control** — the design needs it and doesn't address it (report it).
   - **Unspecified detail** — reasonably deferred to implementation (note once under
     "Assumptions & open questions", don't inflate into N findings).
5. **Write the report** using the shared skeleton plus the additions below.

## Report additions specific to a design doc

Insert a **`## System model`** section after `## Summary` and before `## Findings`:
- Trust boundaries (bulleted)
- Sensitive data flows (bulleted)
- External attack surface (bulleted)

Per finding: **Location** is the design doc section/heading (not a file:line);
**Recommendation** names the specific design change that closes the finding (the
control + where it belongs relative to the trust boundary).

Add a **`## Assumptions & open questions`** section after Findings: controls assumed
but not stated, details deferred to implementation, anything that would change a
finding's severity if clarified.

## When to STOP and report instead of guessing

In addition to the shared conditions: the document references architecture it depends
on that you cannot locate.
