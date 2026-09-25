# Repo Boundaries & File Placement

Read this before creating a directory, adding a test outside the package you are fixing, or
writing anything into `D:\datrix\datrix`.

## The 19 package repos

Each of these is its own **git repository**. Anything dropped inside one gets committed and
pushed unless a human notices:

`datrix`, `datrix-cli`, `datrix-codegen-angular`, `datrix-codegen-aws`,
`datrix-codegen-azure`, `datrix-codegen-common`, `datrix-codegen-component`,
`datrix-codegen-docker`, `datrix-codegen-dotnet`, `datrix-codegen-flutter`,
`datrix-codegen-java`, `datrix-codegen-python`, `datrix-codegen-react`,
`datrix-codegen-sql`, `datrix-codegen-typescript`, `datrix-common`, `datrix-extensions`,
`datrix-language`, `datrix-vscode`

**The count is not a constant.** This list grows as targets are added — a new language, a
new platform, or a new frontend target is a new repo. Update the list and the heading in
the same edit; never leave a package out to preserve the number.

**`datrix-codegen-angular`, `datrix-codegen-react` and `datrix-codegen-flutter` are
frontend TARGETS, not languages.** Angular and React emit TypeScript, Flutter emits Dart,
and each registers as an artifact-phase `datrix.generators` plugin, so none appears in
`registered_language_names()` and `--language` never selects them. Each activates only
when an application declares its own `clients { <target> { … } }` block, and each owns its
own manifest target so its stale-file pruning is confined to `clients/<target>/`.
`datrix-codegen-react` and `datrix-codegen-flutter` are cloned, not-yet-populated
repositories: each joins the venv install set and the Python scans the moment it carries a
`pyproject.toml`, and `test.ps1` the moment it carries a `tests/` directory — no script
edit is needed then.

**`datrix-vscode` is not a Python package.** It is the TypeScript VS Code client: no
`pyproject.toml`, so it is absent from the venv install set and from every Python scan, but
it IS a testable package (its suite runs under Node via `test.ps1`, and it appears in
`status-tests.ps1`) and it IS a publishable git repo the isolation and reference gates scan.
It also **packages itself into a `.vsix`**, so a file dropped inside it can reach an
installed extension, not just a commit — `.vscodeignore` governs that, and
`verify-package-contents.mjs` fails the build on anything in the archive naming a framework
package or carrying an internal path. That is why a fact naming a framework package is never
written into a publishable package: the cross-ecosystem dependency edges live in
`datrix/scripts/config/cross-ecosystem-dependencies.json`, and only publish-safe facts (which
files hold the tests, which script builds them) go in the package's own manifest.

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

Shared layers (`datrix-common`, `datrix-codegen-common`, any shared contract) are imported by
EVERY generator. A fix for one language/platform must never break another: when touching a
shared layer, identify every package the change *reaches* and run, in each of them, the
tests of the behaviour you changed — by feature tag (`test.ps1 <pkg-a> <pkg-b> -Tag <tag>`).
A package is reached when its code consumes the changed surface — it references a changed
module or name (or an unchanged caller of one), or it runs a changed generator through the
pipeline. Importing the changed *package* is not enough, and "just in case" is not a reason.
A cross-language parity gate is a backstop, not a substitute. Procedure:
`.claude/skills/_shared/verification-strategy.md`.

## Agents never run a whole test suite

Run only the tests related to the code you changed:

- the test files you added or edited, and the tests beside the code you edited —
  `test.ps1 <pkg> -Specific "a.py,b.py"`, batched into one invocation;
- the tests of the behaviour you changed, in every package it reaches —
  `test.ps1 <pkg-a> <pkg-b> -Tag <tag>[,<tag>]`. `test.ps1 <pkg> -ListTags` shows a
  package's tags and runs nothing.

A `test.ps1` run naming a package with none of `-Specific`/`-Keyword`/`-Tag`, any `-All` or
`-Rerun`, a tier sweep (`-Unit`/`-Fast`/…), and every `affected-gate.ps1` sweep are
whole-suite runs. **No agent runs one** — not inside a task, not at a wave or phase boundary,
not as a quality gate, not to "check for regressions", not to discover further work. Jon runs
full suites himself.

Every test carries at least one feature tag, and a test you add carries one too
(`datrix-common/docs/contributing/test-guidelines/feature-tags.md`). A behaviour no tagged
test covers is untested: write the test in the owning package and tag it — a test proves the
invariant forever; a sweep proves it once and evaporates. If a task file's `## Targeted Tests`
names a bare full suite, the task file is defective: run the tests of the code you changed and
say so.

Enforced by `guard-full-suite-runs.py`, for every agent including the main session, with no
override and no ticket. Every blocked attempt is appended to
`D:\datrix\.tmp\full-suite-audit.jsonl`. `test-single.ps1`, targeted
`-Specific`/`-Keyword`/`-Tag` runs, `-ListTags`, and `affected-gate.ps1 -SelfTest` are never
touched.
