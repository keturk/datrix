# Execution Contract — Security (§13)

Part of the [execution contract](./execution-contract.md); section numbers are stable and cited by number across the repo.

**Read when:** your change touches authentication or authorization, secrets, TLS, input at a trust boundary, SQL/shell/path/markup construction, permissions or network exposure, errors and logs, cryptography, dependencies or base images — in framework code **or** in anything the generator emits — or a check fails against a security control, or a design/task/bug report asks for a weaker option than the available alternative.

---

## 13. Security is a ranked requirement, not a trade-off axis

**When two implementations differ in security posture, you build the more secure one.** Not
"consider it", not "recommend it and offer the convenient alternative", not "note the risk and ship
the easy path". Build it. **Never propose or implement a less secure option when a more secure one
is available.**

This is a *ranking*, not a preference to balance. Convenience, brevity, familiarity, fewer moving
parts, and finishing sooner do not outrank it. If the secure option costs more code, more
configuration, an extra dependency, or an extra hour, **that cost is the price of the correct
option** — it is not evidence that the other option was reasonable.

### 13.1 It is never a B2, and never Jon's problem to notice

A difference in security posture **settles** a design choice; it does not create a tie. Two options
that differ only in that one is safer are not "two genuinely defensible designs" — that is one
defensible design and one defect (§1, B2). Do not escalate it, do not present it as a menu, and do
not implement the weaker one because it was easier to explain.

The **one** case where a less-secure option is on the table is **B3 USER_FORBADE**: Jon's explicit
constraint rules the secure option out. Then, and only then, you say so in one line, **name the
exposure the constraint creates**, and implement **the most secure option compatible with the
constraint**. You never present the weaker option as your recommendation, and you never implement
one silently.

### 13.2 What the generator emits counts double

Datrix writes production code and production infrastructure for someone else's system. **An
insecure default in a generator is not one defect — it is one defect per project generated from
then on, in codebases nobody on this team will ever read.** A default emitted by a template is a
security policy applied to every future user of that template.

So the rule applies with equal force to both surfaces:

- **The framework code you write** — parsers, resolvers, validators, CLI, scripts.
- **Every artifact the generator emits** — service code, SQL, Dockerfiles and compose files, IaC
  templates, gateway config, CI/ops scripts, generated defaults, and sample/example projects.
  Examples are copied; an example that authenticates weakly teaches weak authentication.

### 13.3 The surfaces this covers

You do not get to decide a task is "not a security task". Relevance is set by the surface you
touched, not by whether the word appeared in the request:

- **Authentication and authorization** — per-request enforcement, object-level/tenant isolation, no
  ambient authority, no "trust the caller", no client-supplied identity.
- **Secrets and credentials** — never hardcoded, never logged, never defaulted to a literal, never
  committed; sourced from the platform's secret mechanism.
- **Transport and storage** — TLS on by default and verified; encryption at rest where the platform
  offers it; no plaintext channel because it was simpler to wire.
- **Input handling at trust boundaries** — validate and normalize where untrusted data crosses in,
  not three layers later "where it's convenient".
- **Injection surfaces** — parameterized queries, argument vectors instead of shell strings, safe
  template/path/deserialization handling. Never compose a query, command, path, or markup by string
  concatenation from external input.
- **Exposure and permissions** — no public bind, no `0.0.0.0/0`, no wildcard IAM, no public bucket,
  no permissive CORS, no debug endpoint, and no default-open port because closing it needed a
  config field.
- **Error and log content** — no credentials, tokens, PII, or internal detail in responses or logs.
- **Cryptography** — standard primitives, current parameters, a CSPRNG for anything
  security-bearing. Never home-rolled.
- **Dependencies and base images** — pinned, current, from the expected registry.

### 13.4 Fail closed

A security control whose input is missing, unparseable, or unknown **denies**. A guard that permits
when it cannot evaluate its condition is the banned silent fallback (CLAUDE.md § Anti-patterns)
applied to the one place it is most expensive: it converts an unknown into an approval, and it is
invisible in every green test suite. An unrecognized identity provider, an absent claim, an
unresolved policy, a missing key — each raises with a message naming what was missing and what to
supply. Never `except: pass` around a check, and never `if not configured: allow`.

### 13.5 Never weaken a control to make something pass

If a test, build, generation run, or deploy fails **against** a security control, the control is the
requirement and the thing failing it is the defect. Disabling it, loosening it, adding an exemption,
or widening a permission so the red turns green is a workaround (CLAUDE.md § No Workarounds) *and* a
silent change to the product's threat model. It is banned even when it is the only thing standing
between you and a green suite, and especially then.

An existing insecure pattern is not a licence either. "The neighbouring module does it this way" is
evidence about the neighbour, not permission (§12.7). Found it → §5: fix it, or file it.

### 13.6 A security assumption is a fact you confirm by reading

"That input is validated upstream", "that endpoint is internal-only", "that secret never reaches the
client" are claims, and §2A governs them: open the file and confirm. The seam discipline of §12.2 is
the tool — name the producer and the consumer of every trust boundary, compute what crosses it, and
land the comparison as a validator. A trust boundary nobody compares is the same defect class as an
unsupplied compose variable, with a worse blast radius.

When a change touches any surface in §13.3, the mandatory second question of §12.3 has a security
form: **what check would have caught this insecure state before the run, and where does it live?**
Land it with the fix.

### 13.7 When the design itself specifies the weaker option

A design doc is a scope boundary (`.claude/rules/design-and-docs.md`) and you never edit one during
implementation. But a security downgrade is not a scope question — it changes the product's threat
model, which is a decision reserved to Jon. So:

1. **Say it in one line, before you implement that part.** Name the weaker option the design
   specifies, the exposure it creates, and the secure alternative. That is the whole message.
2. **Keep working everything that does not depend on the answer** (§6, §8A). This is an escalation
   to keep going, not a stop.
3. **Never silently implement the weaker option, and never silently substitute the stronger one.**
   Silently downgrading is §13; silently overriding the design is a scope violation. One line to
   Jon settles both.

The same applies to a task file, an issue report, or a bug report that asks for the weaker option.
An instruction to build something less secure than the available alternative is worth one sentence
of confirmation, every time.
