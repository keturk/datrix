# Repo Boundaries & File Placement

Read this before creating a directory, adding a test outside the package you are fixing, or
writing anything into `D:\datrix\datrix`.

## The 15 package repos

Each of these is its own **git repository**. Anything dropped inside one gets committed and
pushed unless a human notices:

`datrix`, `datrix-cli`, `datrix-codegen-aws`, `datrix-codegen-azure`,
`datrix-codegen-common`, `datrix-codegen-component`, `datrix-codegen-docker`,
`datrix-codegen-dotnet`, `datrix-codegen-java`, `datrix-codegen-python`,
`datrix-codegen-sql`, `datrix-codegen-typescript`, `datrix-common`, `datrix-extensions`,
`datrix-language`

## Temporary files

| Purpose | Location |
|---|---|
| Temporary scripts (runners, one-off helpers) | `D:\datrix\.scripts\` |
| Test output / result logs | `D:\datrix\.test-output\` |
| All other temp / scratch files | `D:\datrix\.tmp\` |

These folders are cleared regularly — never store anything important in them. Create them at
the workspace root if missing. If a tool defaults to writing elsewhere, redirect it here.

**Never create a temp/scratch/output directory inside a package repo** — no `.test-output\`,
`.tmp\`, `.temp\`, `.scratch\`, `.scripts\`, `.agent_output\`, `tmp\`, `temp\`, `scratch\`,
at any depth. (`.test_results\`, written by `test.ps1`, is the one sanctioned exception and
is already ignored.)

- **Adding it to `.gitignore` is not the fix.** The ignore entries are a backstop for
  accidents, not permission. The folder does not belong in the repo at all.
- **A tool that defaults to writing inside the package gets an explicit output path** under
  one of the workspace folders. Do not let it create its own.
- **New non-temp directories** (a real source, test, or docs folder) are part of the
  package's structure: create one only when the work calls for it, never as a run side effect.

Enforced by `guard-repo-temp-dirs.py` and `guard-temp-file-policy.py`, which block the write,
the `mkdir`, the redirect, and the `-Output*` argument. Inspecting or deleting an existing
stray directory stays allowed, so cleanup is never blocked.

## The datrix showcase repo hosts no test suite

`D:\datrix\datrix` (the public **datrix** showcase repo) holds **only docs, examples, and
scripts**. It is NOT an installable toolchain package and **hosts no test suite of any
kind**. Do not create `D:\datrix\datrix\tests\`, do not add pytest config to its
`pyproject.toml`, and do not write docs claiming datrix "can have tests." If you find such a
directory, file, or claim, treat it as a defect to remove.

- **No product tests.** Tests of generated/customer projects never live in the framework.
  Generated-project tests live with the generated project; generator behavior is tested in
  the owning `datrix-*` package.
- **No cross-package unit tests.** Each `datrix-*` package tests only its own surface. A
  *unit test* that imports two generator packages, or asserts on the combined output of
  several, does not belong in any package.
- **Parity/conformance gates are allowed — keep them target-agnostic.** A cross-language
  parity gate (verifying every supported language/provider realizes the shared domains
  equivalently) is legitimate. It must enumerate its targets from the registered set of
  languages/providers — never a hardcoded `LOCAL/AWS/Azure` or `python+typescript` literal,
  which would silently assert the generator is only those targets.
- **Repo-level validation = scripts, not pytest.** Genuine cross-cutting checks (example
  generation, type-map completeness, the cross-language parity/conformance gate) belong as
  **scripts under `datrix/scripts/test/`**, invoked by the runner — never as a
  `datrix/tests/` pytest suite.

## Cross-surface impact

Shared layers (`datrix-common`, `datrix-codegen-common`, any shared contract) are consumed by
EVERY generator. A fix for one language/platform must never break another: when touching a
shared layer, identify all consuming packages and pass each one's test suite — not just the
package you were fixing. A cross-language parity gate is a backstop, not a substitute.

**Affected-only verification:** gates run the changed packages + their reverse-dependency
closure, never a reflexive `-All`. Closure table, derivation commands, and tier rules:
`.claude/skills/_shared/verification-strategy.md`. The closure IS the consumer list above,
computed instead of guessed.

## Whole test suites are a phase-boundary act

Inside a task, run exactly the tests named in its `## Targeted Tests` —
`test.ps1 <pkg> -Specific "a.py,b.py"`, batched into one invocation. A bare
`test.ps1 <pkg>`, `-All`, `-Rerun`, or a tier sweep (`-Unit`/`-Fast`/…) is a full run,
reserved for the phase-boundary / quality gate where it happens **once** over the affected
set. Using a full suite to *discover* further work mid-task is the same anti-pattern wearing
a better excuse.

To prove a change generalises, write a test in the owning package — a test proves the
invariant forever; a sweep proves it once and evaporates. If a task file's
`## Targeted Tests` names a bare full suite, the task file is defective: run the specific
files covering the code you changed and say so.

Enforced by `guard-full-suite-runs.py`. **For subagents the block is unconditional.** The
main session may authorize one by writing `D:\datrix\.tmp\full-suite-ticket.json` (explicit
package list or `"*"`, a written reason, `expires_epoch` capped at 6h). Every decision,
allowed and blocked, is appended to `D:\datrix\.tmp\full-suite-audit.jsonl`.
`test-single.ps1` and targeted `-Specific`/`-Keyword` runs are never touched.
