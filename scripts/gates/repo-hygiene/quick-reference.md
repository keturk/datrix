# Quick Reference — Repo-Hygiene Gates

Gates over the repositories themselves: what may be committed, what docs may claim, what examples
must satisfy, and code shapes held at zero. Repo-level validation **scripts**, not pytest suites
(the datrix showcase repo hosts none); each gate's own self-test is its coverage.

> **Bash invocation:** Prefix with `powershell -File`, use forward slashes, quote paths. See [../../quick-reference.md](../../quick-reference.md) for full details.
>
> **Base path:** `d:/datrix/datrix/scripts/`

---

## `gates\repo-hygiene\customer-domain-isolation-gate.ps1`

**The repo's proof that no customer/project domain language lives in a framework repo.** Scans the git-TRACKED content of every framework repo in the workspace (`datrix` plus every `datrix-*` clone, discovered from disk) against the hashed customer-term corpus at `scripts/config/customer-term-hashes.json`. The rule ("no customer name, no customer-specific service names, no terms from a customer's business domain in framework code, docs, tests, or examples") was prose only until this gate: customer cloud-resource names and paths into a customer checkout reached committed files through Claude Code permission entries, and a customer deployment target reached a hook's docstring example.

**The corpus stores digests, not terms.** A plaintext denylist naming the customer would itself be the violation it polices. Only SHA-256 digests of lowercased terms are committed, so the term never exists in any repo, while the check still travels with the checkout and enforces on every machine — an out-of-repo term file would silently not exist on a second machine, which is exactly the failure mode a guard must not have. Register a term with `-AddTerm`; the plaintext is hashed and discarded.

**Reported excerpts are redacted.** The matched token is masked as `<customer-term>`; the file and line are what a fix needs. Echoing the term back invites an agent into copying it onward — into a summary, a task file, or a commit message — re-committing the leak while reporting it.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\gates\repo-hygiene\customer-domain-isolation-gate.ps1` | Scan every tracked file in every framework repo |
| **One repo** | `.\gates\repo-hygiene\customer-domain-isolation-gate.ps1 -Repo datrix` | Scan only the named repo(s) |
| **Pending changes only** | `.\gates\repo-hygiene\customer-domain-isolation-gate.ps1 -PendingOnly` | Scan only what a `git add -A` would stage |
| **Register a term** | `.\gates\repo-hygiene\customer-domain-isolation-gate.ps1 -AddTerm acmecorp -Hint "customer project"` | Append the term's digest to the corpus and exit |
| **Debug** | `.\gates\repo-hygiene\customer-domain-isolation-gate.ps1 -Dbg` | Print the python invocation before running |

**Parameters:** `-Repo <name[,name...]>`, `-PendingOnly`, `-AddTerm <term>`, `-Hint <text>` (default: `customer project`), `-Dbg`

**Self-test runs automatically, every invocation.** Before any real scan, the scanner is fed four synthetic occurrence shapes it must detect (hyphenated resource name, path segment, camelCase identifier, upper-case identifier), two clean strings it must NOT flag, a redaction check (the reported excerpt must not contain the term), and an empty-corpus check (must report nothing). A detector that stopped detecting reports a clean tree, which is indistinguishable from a clean tree — so a self-test failure aborts before any result is trusted.

**Matching shape:** content is split into alphanumeric tokens, each token is additionally camel-split, and every piece of at least `min_token_length` (default 5) characters is lowercased and hashed. That covers `<term>-system-kv-dev`, `//d/g/<Term>/**`, `<term>_rg`, and `<term>Backend`. It does NOT match a term glued to another word with neither separator nor case boundary (`<term>dev`) — a hash denylist cannot substring-search without the plaintext it deliberately does not hold; register such a variant as its own term.

**Also enforced at the commit seam and on every edit.** `git\commit-and-push.ps1` runs the same scanner over every dirty repo's pending changes before it generates a message or stages anything, and refuses the whole run on a violation (`-SkipCustomerDomainCheck` overrides, loudly); the `guard-committed-content.py` hook refuses an edit that adds a registered term. This gate is the tracked-tree counterpart: it also catches what is already committed.

**Exit codes:** 0 = no violations (or zero terms registered, reported as `NOT ENFORCED`), 1 = at least one violation or a failing self-test, 2 = usage error or a missing/malformed corpus.

---

## `gates\repo-hygiene\design-task-reference-gate.ps1`

**The repo's proof that no committed artifact cites a design document or a task file.** `design/` and `.tasks/` are gitignored and are developed on more than one machine, so their numbering collides: two different `044-*` documents can exist, and after a clone neither is present. A reference to one from anything committed is a dangling pointer — it resolves to nothing, or to a different artifact elsewhere. The gate scans the committed trees for the SHAPE of such a reference and fails on any hit.

**Roots are derived from disk, never hand-authored.** Every `datrix*` directory contributes its `src`, `tests`, `docs` and `scripts` subtrees (the `datrix` showcase repo contributes `scripts`, `docs`, `examples` instead — it has no `src`), so a new package is scanned the day it appears. The gitignored orchestration trees themselves (`.tasks/`, `.bugs/`, `design/`) plus build noise are skipped: design and task files referencing **each other** is allowed and expected.

**Item labels are policed too, in every label letter.** Findings, reviews and designs number their own items with a capital letter and digits, in parentheses or before a colon, and a comment carrying one points into a gitignored document. Two shapes, over the same extensions, inside a package's `src`, `tests` and `scripts` and the `datrix` repo's `scripts` — never under `docs` or `examples`, where committed documents number their own items: a parenthesized label (`D`/`G`/`I` with any digit count, every other capital letter with one or two digits, optionally a `/` or `,` list) and a heading label (the same letters followed by a colon, refusing a preceding `.` or word character so `StorageProvider.S3:` is attribute access). One or two digits for the other letters keeps ruff/pylint codes (`F821`, `A002`, `R0801`, `F401/F811/I001`) out. The possessive of a bare task id (`NN-MM's`) is matched in every root; a bare `NN-MM` is not, because dates and line ranges look the same. `LABEL_TOKEN_EXCEPTIONS` in the library module holds exact `(workspace-relative path, token)` pairs with a written reason — today the emitted `P95` percentile chart title in the Azure monitor workbook generator; the token anywhere else is a hit. Hit lines name the shape: `[item label (parenthesized)]`, `[item label (heading)]`, `[task-file id (possessive)]`.

**Also enforced at the commit seam and on every edit.** `git\commit-and-push.ps1` runs the same scan over the pending files of every dirty repo before it generates a message or stages anything, and refuses the whole run on a hit; there is no skip switch. The `guard-committed-content.py` hook applies the same detector to the lines an edit adds.

**Four reference shapes are matched, over all of `.py .ps1 .json .md .j2 .ts .mts .cts .js .mjs .cjs .cs .java .toml .yaml .yml .dtrx`** (spelled here with `N`/`M` placeholders so this page is not itself a hit): a task-file id (`task-NN-MM`, the prose `task NN-MM`, and the three-digit `task-NN-MMM`, case-insensitively), a design path (`design/NNN-slug`), a design number (`design NNN`, `design-NNN`, `design doc NNN` — the word `doc` is optional), and a phase directory (`.tasks/phase-NN`). Each line is also matched joined to the next with that line's comment leader (`#`, `//`, ` * `, `--`) removed, because a wrapped comment splits a reference across the break (`(design` / `# NNN section …`) and a line-at-a-time match sees neither half; a hit is reported at the line it starts on. A **bare** `Phase NN` is deliberately NOT matched: the committed architecture docs use it as product vocabulary for delivery waves, self-contained text rather than a pointer into a gitignored tree.

**The terminal state is zero.** There is no baseline and no count to ratchet down. `ALLOWLIST` in `scripts/common/lib/datrix_scripts/design_task_references.py` is the only escape hatch and is for files that document the ID *format* itself (the task-ID parser, the review runner's usage examples, this gate's own patterns) — never for a file that merely happens to carry a reference.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\gates\repo-hygiene\design-task-reference-gate.ps1` | Scan every committed tree in the workspace |
| **One tree** | `.\gates\repo-hygiene\design-task-reference-gate.ps1 -Roots D:/datrix/datrix/scripts/config` | Scan only the named directories |
| **Several trees** | `.\gates\repo-hygiene\design-task-reference-gate.ps1 -Roots D:/datrix/datrix-common/src,D:/datrix/datrix-common/docs` | Comma-separated roots |
| **Self-test only** | `.\gates\repo-hygiene\design-task-reference-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real scan |

**Parameters:** `-Roots <dir[,dir...]>` (default: every committed tree), `-SelfTest`

**Self-test runs automatically, every invocation.** One line per reference shape is planted in a temp directory and every one must be flagged; a clean file must produce zero; and a bare `### Phase 01 capabilities` heading must NOT be flagged. A second fixture workspace with `src/`, `tests/`, `scripts/` and `docs/` trees plants every label shape (each must hit exactly once) and the near misses (attribute access, lint codes, line ranges, a label under `docs/`, the excepted token in its own file) that must hit zero; the same `P95` in another file must hit, and `scan_paths` (the commit-time entry) must agree with `scan` over the same files. A scan that silently matches nothing returns a confident "clean" that will be believed — which is exactly how two holes in this gate let whole phases' worth of references through: matching only the hyphenated `task-NN-MM` form missed the prose `task NN-MM` an agent actually writes, and requiring the literal word `doc` missed the bare `design NNN` entirely.

**Exit codes:** 0 = no references found (or a successful `-SelfTest`), 1 = at least one reference found or the self-test failed.

---

## `gates\repo-hygiene\ignored-source-gate.ps1`

**The repo's proof that no `.gitignore` rule is silently deleting a publishable file.** For the `datrix` showcase repo and every `datrix-*` clone in the workspace (discovered from disk at runtime — a new package is covered with no edit to the gate), it computes the set difference between the working tree and what a `git add -A` would stage. Every element of that difference must be a reviewed, scoped entry in `scripts/config/ignored-source-exemptions.json`; anything else is a source file that exists locally and will not survive a clone. An entry names the ignore rule by its pattern text and by a segment-aware glob over the repo-relative path of the `.gitignore` file git blames (a literal path matches only that file; `examples/**/generated/**/.gitignore` matches the nested files a generator writes into each emitted project), and scopes the paths it excuses with `path_glob`.

**Why it exists.** A package carried the stock Python `.gitignore`'s **unanchored** `MANIFEST` line — intended for setuptools' root `MANIFEST` file. Git matches an unanchored pattern at *any depth*, and `core.ignorecase=true` on this platform makes the match case-insensitive, so it also matched a `templates/manifest/` directory and swallowed both Jinja2 templates inside. Nothing was visible locally: the files were on disk, every test passed, the emitted output compiled. The loss appears only after a clone or a wheel install, as a package that cannot generate — and by then the templates are gone from history. It was found by hand, by comparing a file count against a `git add -A --dry-run` count. This gate is that comparison, living in code.

**Git is the oracle.** Ignore matching is never re-implemented. `git ls-files -o -i --exclude-standard` produces the difference at *file* granularity (directories are not collapsed), and `git check-ignore -v` names the `.gitignore` file, line number, and pattern responsible for each element. Anchoring, negation (`!`), nested `.gitignore` files, `.git/info/exclude`, global excludes and `core.ignorecase` interact in ways a hand-rolled matcher gets wrong — and a wrong matcher returns a confident "clean" that will be believed, which is how the original defect survived. A path git refuses to stage but attributes to no rule is reported with a placeholder rule and fails the gate; it can never match an exemption.

**Every finding names the rule, not just the file.** Output is grouped as `<gitignore>:<line>: <pattern> -- shadows N publishable file(s)`, then the paths. Reporting only the file leaves the fix a hunt through several hundred `.gitignore` lines.

**Exemptions are scoped, and the scope is load-bearing.** Each entry excuses **one** rule (identified by the `.gitignore` file plus the pattern text git reports) over **one** path scope, and carries a written reason. An entry for the root `build/` tree does not excuse the same unanchored `build/` rule swallowing a `templates/build/` directory full of source — that is the same defect wearing a different name, and the self-test proves the scope rejects it. `repos` is a list of repo names or `["*"]` for every framework repo; `path_glob` is segment-aware (`**/` spans whole segments, `**` spans the remainder, `*`/`?` stay inside one segment). `pinned_count` is enforced against `len(exemptions)`, so an entry cannot be added or removed without the reviewed number moving in the same change.

**A stray temp directory is a different finding with a different fix.** Temp, scratch and test-output directories never belong inside a package repo (`guard-repo-temp-dirs.py` refuses to create one; the workspace-level `D:\datrix\.tmp`, `.scripts`, `.test-output` are where they go). One that exists anyway — left by a run before the hook, or by a tool that defaulted its output path — is full of `.py`/`.java`/`.sql` files that an ignore backstop hides, and to a scan that only knows "ignored, unexempted" it looks like hundreds of thousands of shadowed source files whose fix is to edit the ignore line or add an exemption; both are wrong. The gate classifies such paths by the **same name list the hook enforces** (`claude-config/.claude/hooks/_repo_temp_dir_names.py` — one definition, two enforcement points; the gate refuses to run if it cannot load it rather than keep a copy) and reports each directory **once**, as a `WARNING` carrying the file count and the `Remove-Item` command. It never appears in the shadowed-source report, it can never be exempted, and it does not fail the gate: the contents are already unpublishable, and the gate's verdict is about what a clone would lose. `commit-and-push.ps1` prints the same warning and proceeds.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\gates\repo-hygiene\ignored-source-gate.ps1` | Scan every framework repo in the workspace |
| **One repo** | `.\gates\repo-hygiene\ignored-source-gate.ps1 -Repo datrix-language` | Scan only the named repo(s) |
| **Several repos** | `.\gates\repo-hygiene\ignored-source-gate.ps1 -Repo datrix-language,datrix-vscode` | Scan the named repos only |
| **Self-test only** | `.\gates\repo-hygiene\ignored-source-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real scan |
| **Show exemptions** | `.\gates\repo-hygiene\ignored-source-gate.ps1 -ShowExempt` | Print every reviewed entry with its written reason, then scan |
| **Debug** | `.\gates\repo-hygiene\ignored-source-gate.ps1 -Dbg` | DEBUG logging; print the python invocation before running |

**Parameters:** `-Repo <name[,name...]>`, `-SelfTest`, `-ShowExempt`, `-Dbg`

**Self-test runs automatically, every invocation.** Before any real scan, real `git init` repos are created in a temp directory and the scanner must reach the correct verdict on each planted path — a scan that can only return zero is not evidence, which is precisely how the original defect survived. It asserts:

- an unanchored `MANIFEST` rule shadowing `src/pkg/templates/MANIFEST/entry.j2` is **detected**, and blamed on the right `.gitignore` **file, line number and pattern**;
- that finding is **not** excused by any entry in the real exemption file;
- a planted publishable file (`src/pkg/keep.py`) is **not** reported;
- a `__pycache__/` file and a root `build/` file **are** excused by their real entries, while the same `build/` rule shadowing `src/pkg/templates/build/template.j2` is **not** — proving the path scope is load-bearing;
- an empty exemption set excuses nothing (the exemption matcher is not vacuously true);
- two files planted in different subtrees of a `.test-output/` directory fold into **one** stray-temp-directory finding with a count of 2 and a delete command, appear in **no** shadowed-source finding, and do not swallow the `MANIFEST` finding beside them — which also proves the hook's shared name list still names `.test-output`;
- git's own semantics are honoured: a `!`-re-included path is not reported, and a lowercase `manifest` directory under an uppercase `MANIFEST` rule is detected **iff** `core.ignorecase` is true in that repo;
- the scope glob is segment-aware across nine positive and negative cases.

A self-test failure aborts before any real result is trusted (exit 1).

**Unused exemption entries are reported, never failed.** An entry covers output a tool writes only once it has run (a coverage report, an `npm install`), so its absence on a clean checkout is normal and is not evidence the entry is stale.

**Also enforced at the commit seam.** `git\commit-and-push.ps1` runs the same scanner over every dirty repo before it generates a message or stages anything, and refuses the whole run on a violation (`-SkipIgnoredSourceCheck` overrides, loudly); a scanner that fails its own self-test aborts the run rather than returning a verdict nobody can trust. That is the seam this defect is actually about — `git add -A` is where the file is or is not published. This gate is the whole-workspace counterpart: it also covers repos the current run is not committing.

**Exit codes:** 0 = every unstaged working-tree path is a reviewed exemption, 1 = at least one publishable file is shadowed or the self-test failed, 2 = usage error (unknown `-Repo` name, no framework repo found) or a missing/malformed/miscounted exemption file.

---

## `gates\repo-hygiene\polystring-case-roundtrip-gate.ps1`

**The repo's proof that no name goes `str()` → `to_*_case()`.** Every identifier the generator re-cases — an entity, service, block, field, queue or shared-container name, `QualifiedNode.name`, `qualified_name` — is a `PolyString`: a `str` subclass that split its words **once** and exposes `.snake`, `.camel`, `.pascal`, `.kebab`, `.screaming_snake` and `.simple`. The case functions in `datrix_common.utils.text` are for text that is *not* already a name object. For the `datrix` showcase repo and every `datrix-*` clone (discovered from disk at runtime), the gate parses every publishable `.py` file with `ast` and fails on any case-function call — by canonical name, import alias, or module attribute — whose argument is one of four shapes:

| Kind | Shape | Fix |
|------|-------|-----|
| `str-wrapped` | `to_X_case(str(E))` | read `E.X`; if `E` is genuinely plain text, drop the `str()` — case functions accept any `str`, PolyString included |
| `str-bound` | `to_X_case(NAME)` where `NAME = str(E)` is bound in the same function/module scope | read `E.X` off the original name object |
| `nested` | `to_X_case(to_Y_case(E))` | the outer call alone is equivalent; a derived name is `PolyString.compose(...).X` |
| `simple-name` | `to_X_case(extract_simple_name(E))` | `E.simple.X` |

**Held at a hard zero with no exemption file.** No shape above has a legitimate instance: a case function never needs a `str()` around its argument, and a nested call never needs its inner one.

**Why it exists.** The round trip is not merely wasteful (it recomputes the word split the name already paid for): it hides from the next reader that the value was a name, so they treat it as text too, and the pattern spread to several hundred sites across the language and platform packages before anything refused it. A Semgrep rule (`redundant-case-conversion`) named the shape but ran only on demand, as a WARNING — an advisory nobody has to read is the same as no rule.

**What it cannot see.** `to_snake_case(node.name)` — a PolyString passed straight to a case function — is the same waste without the `str()`, but whether `.name` is a PolyString or an `Enum` member's plain-`str` `.name` is a type fact, and no type checker runs in this repo. That shape is left to review.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\gates\repo-hygiene\polystring-case-roundtrip-gate.ps1` | Scan every publishable `.py` file in every framework repo |
| **One repo** | `.\gates\repo-hygiene\polystring-case-roundtrip-gate.ps1 -Repo datrix-codegen-aws` | Scan only the named repo(s) |
| **Pending changes only** | `.\gates\repo-hygiene\polystring-case-roundtrip-gate.ps1 -PendingOnly` | Scan only what a `git add -A` would stage (the commit-path form) |
| **Self-test only** | `.\gates\repo-hygiene\polystring-case-roundtrip-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real scan |
| **Debug** | `.\gates\repo-hygiene\polystring-case-roundtrip-gate.ps1 -Dbg` | DEBUG logging; print the python invocation before running |

**Parameters:** `-Repo <name[,name...]>`, `-SelfTest`, `-PendingOnly`, `-Dbg`

**Self-test runs automatically, every invocation.** A planted module carrying one instance of every kind and every callee spelling (canonical, `as` alias, `text.to_snake_case` attribute, function-level import) plus a nested function must yield exactly the expected `(line, kind, function)` triples — so the scope barrier is proven, not assumed; a clean module (reading `.snake`, casing a value that was never `str()`-wrapped, `str()` applied *after* the case call, `PolyString.compose`) must yield zero; and an unparseable module must refuse (exit 2) rather than report clean. A self-test failure aborts before any real result is trusted (exit 1).

**Also enforced at the commit seam.** `git\commit-and-push.ps1` runs the same scanner over the pending files of every dirty repo before it generates a message or stages anything, and refuses the whole run on a hit (`-SkipPolyStringCaseCheck` overrides, loudly). This gate is the whole-workspace counterpart: it also covers repos the current run is not committing.

**Exit codes:** 0 = zero round trips in every scanned file, 1 = at least one round trip or the self-test failed, 2 = usage error (unknown `-Repo` name, no framework repo found) or a scanned file that could not be parsed.

---

## `gates\repo-hygiene\python-lint-correctness-gate.ps1`

**The repo's proof that no package carries a pyflakes finding.** Unused imports, undefined names, and test functions silently shadowed by a same-named redefinition (the first definition never runs) are `ruff` rule family `F`. Targets are derived from disk, never listed: every workspace `datrix*` directory holding a `pyproject.toml` contributes its `src/` and `tests/` trees when present, and the `datrix` showcase repo contributes `scripts/`. Each tree is linted with `ruff check --select F --output-format json` run from its package root, so that package's own `per-file-ignores` apply; `--select F` is explicit so no package's rule selection can hide a pyflakes finding. Findings print as `package/path:line:col CODE message`.

**Held at a hard zero with no baseline.** A finding that is genuinely required (an import kept for a documented side effect) is suppressed only by a line-level `# noqa: <code>` carrying the reason on the same line; `RUF100` already reports a stale one. The style families (`UP037`, `I001`, `UP031`, …) are out of scope: they are not correctness defects and would bury the pyflakes signal.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\gates\repo-hygiene\python-lint-correctness-gate.ps1` | Lint every package tree in the workspace |
| **Self-test only** | `.\gates\repo-hygiene\python-lint-correctness-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real scan |
| **Debug** | `.\gates\repo-hygiene\python-lint-correctness-gate.ps1 -Dbg` | DEBUG logging; print the python invocation before running |

**Parameters:** `-SelfTest`, `-Dbg`

**Self-test runs automatically, every invocation.** A temporary fixture package with one planted F401 and one F821 must report exactly those two; the same package clean must report zero; a fixture `per-file-ignores` for the F401 must suppress it and leave the F821. The live run additionally fails (exit 2) when any discovered package has no scanned tree — a scan that found no trees is broken, not clean.

**Also enforced at the commit seam.** `git\commit-and-push.ps1` runs `ruff check --select F` over the pending `.py` files of every dirty repo before it generates a message or stages anything, and refuses the whole run on a finding. There is no skip switch. This gate is the whole-workspace counterpart.

**Exit codes:** 0 = zero pyflakes findings, 1 = at least one finding or the self-test failed, 2 = usage error or ruff could not run.

---

## `gates\repo-hygiene\import-name-existence-gate.ps1`

**The repo's proof that no `from <datrix module> import <name>` names something that does not exist.** A half-completed rename leaves a module importing one name and defining another. At runtime that announces itself — the first test to touch the module raises `ImportError`. Inside `if TYPE_CHECKING:` it announces nothing, ever: the block never executes, every package still imports cleanly, and this repo runs no standalone type-checker by policy (`CLAUDE.md`, "Running Python"), so every annotation written against the dead name is silently meaningless. Three half-completed renames landed in one phase and all three were found by accident. This gate looks for them on purpose.

**Resolution, three routes, in order.** (1) A module-level binding in the target module's own source, by AST — `def`/`class`/assignment/import alias, including inside its own top-level `if`/`try`/`with` and its own `TYPE_CHECKING` block, so this gate is never stricter than a type checker. (2) A **submodule** of the target — `from datrix_cli.commands import lsp` imports a module, not an attribute; skipping this step is what made a first attempt report 102 findings of which 100 were not defects. (3) A runtime attribute, by importing the module — reached only for names routes 1 and 2 miss, covering `from x import *` re-exports and module-level `__getattr__`. An import that raises is reported with its exception text, never treated as resolved.

**Roots are derived from disk.** Every `datrix*` package repo contributes its `src/` and `tests/` trees; the `datrix` showcase repo contributes `scripts/`. Relative imports are resolved, and a package's `__init__.py` is resolved as its own package (one dot there means THIS package, not the parent). Relative imports in `tests/`/`scripts/` trees, which have no unambiguous dotted name, are counted and reported rather than silently dropped.

**Deliberate negative-existence assertions are excluded and counted.** An import inside `pytest.raises(ImportError)` / `pytest.raises(ModuleNotFoundError)` or a `try/except ImportError`, written to prove a deleted symbol is really gone, is not a defect. A `raises` naming some other exception tolerates nothing, and the import inside it is still checked.

**The terminal state is zero.** No baseline, no ratchet, no allowlist. A name resolving by none of the three routes is a defect in the importing module — fix the import or the definition.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\gates\repo-hygiene\import-name-existence-gate.ps1` | Scan every datrix package tree |
| **One tree** | `.\gates\repo-hygiene\import-name-existence-gate.ps1 -Roots D:/datrix/datrix-common/src` | Scan only the named directories |
| **Several trees** | `.\gates\repo-hygiene\import-name-existence-gate.ps1 -Roots D:/datrix/datrix-common/src,D:/datrix/datrix-codegen-common/src` | Comma-separated roots |
| **Self-test only** | `.\gates\repo-hygiene\import-name-existence-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real scan |

**Parameters:** `-Roots <dir[,dir...]>` (default: every datrix package tree), `-SelfTest`

**Self-test runs automatically, every invocation.** A synthetic package is built in a temp directory carrying four dead names that MUST be reported (two under `if TYPE_CHECKING:`, one behind a package-relative import, one inside a non-import `raises`) and five shapes that must NOT be: a submodule import, a name re-exported only inside the target module's own `TYPE_CHECKING` block, a single-dot import in a package `__init__.py`, the same statement in a sibling module, and an import written to fail under `pytest.raises(ImportError)`. In-scope and TYPE_CHECKING counts are asserted too, so a walker that stops seeing a shape fails here rather than reporting a confident clean.

**Exit codes:** 0 = every import name resolves (or a successful `-SelfTest`), 1 = at least one dead name found or the self-test failed, 2 = no datrix `src/` tree found to resolve against.

---

## `gates\repo-hygiene\check-docs-conformance.ps1`

Docs-conformance gate: extracts repo-relative path references and Python module references from the curated architecture-doc set (each package's `docs/architecture.md` and/or `docs/architecture/` tree — `datrix-extensions` has neither and contributes zero) and fails if any reference does not resolve to a real file/directory/module in the tree, unless it is recorded in the committed exceptions baseline at `scripts/config/docs-conformance-exceptions.json` (a "what was removed" migration-history claim, a "must never exist" prohibition claim, or another confirmed-intentional non-existence). It follows the same scan-and-baseline shape as `gates\ratchet\check-generated-file-ratchet.ps1`, except the exceptions baseline is hand-edited and reviewed (no `-UpdateBaseline` flag — every entry needs a human-authored reason a script cannot synthesize).

`ARCHITECTURE_DOC_FILES` is a literal, reviewable constant in the script (never a directory glob) — "architecture docs" is a curated concept, and a new architecture doc added later is a deliberate, reviewed one-line addition to that constant. It only checks path-reference candidates that are fully package-qualified (start with a known package name or `D:\datrix\`) and module-reference candidates that are fully import-qualified (start with a known Python import name) — a bare, package-relative shorthand span with no anchor at all is never a candidate (deliberate scope boundary, not a gap).

> **`ARCHITECTURE_DOC_FILES` is the one registry in the repo that does NOT self-update.** Everywhere else the package set is discovered from disk (`Get-DatrixDirectories`, `Get-DatrixPackages`, the metrics reports, `commit-and-push`), so a new package is picked up with no edit. This tuple is deliberately the exception — a curated list, reviewed by a human. Consequence: when a new `datrix-codegen-<lang>` package ships its own `docs/architecture.md`, that entry must be **added to the tuple by hand**, or the new package's architecture doc is silently never scanned by the gate. A package with no architecture doc yet contributes zero entries and is correctly absent — as `datrix-extensions` already is.

`test\shared-library-gate.ps1 -Only check_scripts_tree` separately holds every **script path** a doc names (in any repo) to an existing file.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\repo-hygiene\check-docs-conformance.ps1` | Scan every architecture doc and API/reference doc, fail on unresolved references |
| **Warning mode** | `.\gates\repo-hygiene\check-docs-conformance.ps1 -Warn` | Report unresolved references but exit 0 |
| **Show files** | `.\gates\repo-hygiene\check-docs-conformance.ps1 -ShowFiles` | Print each doc file being scanned |
| **Self-test only** | `.\gates\repo-hygiene\check-docs-conformance.ps1 -SelfTest` | Run only the scanner's own edge-case self-test suite; skip the real docs scan |
| **Custom base dir** | `.\gates\repo-hygiene\check-docs-conformance.ps1 -BaseDir D:\datrix` | Specify monorepo root explicitly |
| **Debug** | `.\gates\repo-hygiene\check-docs-conformance.ps1 -Dbg` | Debug logging |

**Parameters:** `-Warn`, `-ShowFiles`, `-BaseDir`, `-SelfTest`, `-Dbg`

**Self-test runs automatically, every invocation.** A plain-Python self-test suite (`--self-test` on the underlying `.py`; no pytest -- real `tempfile.TemporaryDirectory()` fixtures and `assert` statements) covers `extract_path_candidates`, `extract_module_candidates`, `resolve_path_candidate` (Tier 1 + Tier 2, including the adversarial ambiguous-Tier-2-match case, which must stay unresolved), `resolve_module_candidate`, `load_exceptions`, and `check_against_exceptions`. This suite runs, unconditionally, as step 1 of every invocation (self-test failure aborts before the real scan, exit 2); `-SelfTest` runs it in isolation and skips the real scan. `--harness-self-test` (no `.ps1` switch -- diagnostic only) registers one intentionally-failing dummy check to prove the `[OK]`/`[FAIL]` harness itself is not vacuous.

**Assertions:**
- Every single-backtick inline code span in each curated architecture doc is extracted as a path-reference or module-reference candidate per the fixed extraction rules (package/drive-prefixed for paths, import-name-prefixed dotted chains for modules); a span containing `...`, `<`/`>`, or `*` is rejected outright.
- A path candidate resolves via Tier 1 (exact path exists under the monorepo root; a trailing-slash candidate must be a directory) or Tier 2 (an unambiguous `src/`/`tests/`-relative suffix match — never attempted when the candidate already starts with `src`/`tests`, and never resolved when the suffix matches 2+ files).
- A module candidate resolves when any decreasing-length prefix of its segments after the import name matches a real `.py` file or package `__init__.py` (tolerating a trailing symbol/attribute/function name).
- A candidate unresolved by both tiers is checked against the exceptions baseline (span text -> reason); present spans never fail the gate, absent spans do.
- Every Markdown anchor link (`[text](<doc>.md#anchor)` or `[text](#anchor)`) in a curated doc names a heading that exists in the target doc, by the GitHub-flavoured slug the heading text produces (duplicates numbered); a missing target doc fails the same way. Reported with kind `anchor`, span `<target>#<anchor>`.
- Every `### Decision N:` heading in a curated doc carries a status from the closed vocabulary (`Adopted`, `Implemented`, `Stable`, `Approved — Implementation In Progress`); a `**Status:**` paragraph in the section, when present, opens with a status of the same class (`Adopted`/`Landed`/`Implemented`/`Stable` vs `Approved`); an in-progress decision must carry a `**Status:**` paragraph; and every `` `*.ps1` `` a decision section names exists somewhere under `datrix/scripts`. Reported with kind `decision`. The self-test plants each disagreement and each accepted shape.

**Exit codes:** 0 = no unresolved references (or a successful `-Warn` or `-SelfTest` run), 1 = at least one unresolved, non-excepted reference found (or `-SelfTest`/`--harness-self-test` reports a failing check), 2 = usage error, missing exceptions baseline, a doc in `ARCHITECTURE_DOC_FILES` that no longer exists, or the automatic self-test step failing on a normal invocation.

---

## `gates\repo-hygiene\instruction-surface-gate.ps1`

Instruction-surface gate: no agent-facing document may PRESCRIBE a whole-suite run — a whole-suite `test.ps1` form or any `affected-gate.ps1` sweep. `guard-full-suite-runs.py` blocks an agent from EXECUTING a whole-suite run, but a skill or rule doc can still tell an agent, in prose and command examples, to run one; nothing made that PRESCRIPTION visible until this gate. Scans `claude-config/.claude/CLAUDE.md`, `claude-config/.claude/rules/*.md`, and `claude-config/.claude/skills/**/*.md` (including `_shared/`) for every fenced code block and inline code span, walking fence/backtick delimiters directly (a real parser, never a line regex — a fenced block's contents are never re-scanned for inline backticks, and an inline span sharing a prose line is still found).

**Shares its classification with the runtime guard, never re-derives it.** Every code fragment found is handed to `_suite_invocation.py` (`claude-config/.claude/hooks/_suite_invocation.py`, loaded by path via `importlib.util.spec_from_file_location` — the same precedent `ignored-source-gate.ps1`'s `load_temp_dir_segment` uses to share `_repo_temp_dir_names.py` with its own hook) — the SAME module `guard-full-suite-runs.py` imports as a sibling, so the hook that BLOCKS a whole-suite run at execution time and the gate that COUNTS its prescription in prose can never disagree about what one looks like. A fragment classified whole-suite (bare package, several packages, `-All`, `-Rerun`, a tier switch with none of `-Specific`/`-Keyword`/`-Tag`, or any `affected-gate.ps1` invocation other than `-SelfTest`) is a hit unless an HTML comment `<!-- forbidden-example -->` sits on the same line, or the line immediately before (for a fenced block: the line before the opening fence).

A `-Tag` run and a `-ListTags` listing are never hits (targeted / runs nothing). A vacuous tail (the fragment is just the bare word `test.ps1` or `affected-gate.ps1`, naming the tool with no argument at all — e.g. "the `test.ps1` script") is never a hit either: a prescription to run a whole suite must name enough to actually run. A tail whose first character is not whitespace, a quote, or end-of-string (e.g. a `file.py:123` line citation immediately after the script name) is never a hit — a real command's next argument is always separated from the script name by whitespace or a closing quote.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\repo-hygiene\instruction-surface-gate.ps1` | Scan every agent-facing instruction document, fail on any un-exempted whole-suite form |
| **Self-test only** | `.\gates\repo-hygiene\instruction-surface-gate.ps1 -SelfTest` | Run only the scanner's own self-test suite; skip the real census |
| **Debug** | `.\gates\repo-hygiene\instruction-surface-gate.ps1 -Dbg` | Debug logging |

**Parameters:** `-SelfTest`, `-Dbg`

**Self-test runs automatically, every invocation.** A plain-Python self-test suite (`--self-test` on the underlying `.py`; no pytest — real `tempfile.TemporaryDirectory()` fixtures) plants eight fixtures and requires each classification boundary to hold: a bare `test.ps1 {pkg}` form (1 hit), a `-Specific` form (0 hits), a bare form immediately preceded by `<!-- forbidden-example -->` (0 hits, 1 exempted), an `affected-gate.ps1 -Projects {pkg}` form (1 hit — a whole-suite sweep), a `-Tag` run plus an `-All -ListTags` listing (0 hits), an inline code span sharing a prose line (1 hit — proves the scanner is not fenced-block-only), a bare `test.ps1` mention with no argument at all (0 hits — a vacuous tail is not a prescription), and a `file.py:123`-shaped line citation immediately after the script name with no argument-separating whitespace (0 hits). This suite runs, unconditionally, as step 1 of every invocation (self-test failure aborts before the real scan, exit 1); `-SelfTest` runs it in isolation and skips the real scan.

**Assertions:** zero un-exempted whole-suite `test.ps1` fragments across the scanned document set.

**Exit codes:** 0 = zero un-exempted whole-suite forms (or a successful `-SelfTest` run), 1 = at least one un-exempted whole-suite form found, or the self-test failed, 2 = usage error, or `_suite_invocation.py`/`_command_shape.py` could not be loaded.

---

## `gates\repo-hygiene\check-cross-package-fixture-reads.ps1`

**No package's tests resolve a path inside another package's `tests/` directory.** AST-scans every `.py` file under every discovered `datrix*` package's `tests/` tree and statically evaluates the pathlib expressions test fixtures use to locate `.dtrx`/`.dcfg`/`.json` files (`Path(__file__)`, `.resolve()`, `.parent`/`.parents[N]`, `/` joins against literals or previously-resolved names, including `from tests.<module> import NAME` — always the same package's own `tests/` namespace). Reports two things: (a) a resolved directory constant that points inside ANOTHER package's own `tests/` tree — the violation itself, regardless of whether the file it names still exists there; (b) a statically-resolved fixture path that does not exist on disk (skipping any path a test explicitly asserts is absent, e.g. `assert not X.exists()`). This is the exact shape that turned one datrix-common fixture cleanup into a red `datrix-codegen-typescript` suite: `COMMON_FIXTURES_DIR / "system-with-jobs.dtrx"` pointed at a file datrix-common's own tests no longer read.

**A fixture read by one package lives in that package's own `tests/fixtures/`. A fixture read by several packages lives in `datrix-testing` as shared package data** (`datrix_testing.shared_fixtures`), reached through a function or constant — never a relative path into another package's `tests/` tree.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\repo-hygiene\check-cross-package-fixture-reads.ps1` | Scan every package, fail on any cross-package reference or missing fixture |
| **Self-test only** | `.\gates\repo-hygiene\check-cross-package-fixture-reads.ps1 -SelfTest` | Prove the scanner detects both defect shapes (including the exact two-step, cross-module incident chain) and clears the clean case; skip the real scan |
| **Show files** | `.\gates\repo-hygiene\check-cross-package-fixture-reads.ps1 -ShowFiles` | Print each file as it is scanned |
| **Custom base dir** | `.\gates\repo-hygiene\check-cross-package-fixture-reads.ps1 -BaseDir D:\datrix` | Specify monorepo root explicitly |
| **Debug** | `.\gates\repo-hygiene\check-cross-package-fixture-reads.ps1 -Dbg` | Debug logging |

**Parameters:** `-BaseDir`, `-SelfTest`, `-ShowFiles`, `-Dbg`

**Self-test runs automatically, every invocation.** It plants a cross-package directory constant and a missing-fixture reference (both must be found) alongside a clean, own-package, existing-file case (must not be found), then separately plants the real incident's exact shape (a two-step `_MONOREPO_ROOT` / `COMMON_FIXTURES_DIR` chain, imported cross-module via `from tests.conftest import ...`, joined against `"system-with-jobs.dtrx"`) and requires both halves caught — so the self-test stays meaningful even after the real incident is fixed and no longer visible in the live workspace.

**Exit codes:** 0 = clean (or a successful `-SelfTest`), 1 = a cross-package reference or missing fixture was found, 2 = usage error, no packages discovered, or the self-test failed.

---

## `gates\repo-hygiene\check-enum-value-literals.ps1`

**Hard-zero gate: no generator may branch on a user enum's member values.** AST-scans every `datrix-codegen-*`, `datrix-common` and `datrix-language` `src/` tree for two shapes: a member looked up by literal name (`.get_value("X")` / `.require_value("X")`), and a string literal tested against a collection of member names (`"X" in value_names`). A `.dtrx` enum's members are the declaring project's vocabulary — a generator reading one by literal turns somebody else's spelling into policy, so renaming a member silently changes behaviour and naming an unrelated enum the same way silently triggers it. Declared contracts (see `work { }`) reference the model instead.

**There is no exemption file, on purpose.** A legitimate need to branch on a member value is a design defect, not an entry to record. The baseline is zero and only zero passes.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\repo-hygiene\check-enum-value-literals.ps1` | Scan every package, fail on any violation |
| **Self-test only** | `.\gates\repo-hygiene\check-enum-value-literals.ps1 -SelfTest` | Prove the scanner detects both shapes; skip the real scan |
| **Show files** | `.\gates\repo-hygiene\check-enum-value-literals.ps1 -ShowFiles` | Print each file as it is scanned |
| **Custom base dir** | `.\gates\repo-hygiene\check-enum-value-literals.ps1 -BaseDir D:\datrix` | Specify monorepo root explicitly |
| **Debug** | `.\gates\repo-hygiene\check-enum-value-literals.ps1 -Dbg` | Debug logging |

**Parameters:** `-BaseDir`, `-SelfTest`, `-ShowFiles`, `-Dbg`

**Self-test runs automatically, every invocation.** It plants one instance of each detected shape and requires both to be found, then requires clean source to report none — so a scanner that can only return zero fails here rather than being believed. A run that discovers no package source also fails rather than passing vacuously.

**Exit codes:** 0 = clean (or a successful `-SelfTest`), 1 = a violation was found, 2 = usage error, no packages discovered, or the self-test failed.

---

## `gates\repo-hygiene\check-handler-name-dedup.ps1`

**Hard-zero gate: no `datrix-codegen-*` package may de-duplicate a handler name.** AST-scans every `datrix-codegen-*` package's `src/` tree for the retired `while <name> in used: <name> = f"{base}{suffix}"; suffix += 1` shape over a derived REST handler / controller method name. Every handler name is derived ONCE, in the shared API-level derivation (`datrix_codegen_kernel.generation.api_helpers` — `compute_rest_api_handler_names` / `rest_api_handler_names_by_endpoint`), which refuses to hand two endpoints of one `rest_api` a single name: it raises, naming both routes. A package-local de-duplicator does the opposite — it renames one side of the collision (`getOrders` / `getOrders2`) while the browser client, the API test generator and every other language target keep calling that route by the un-numbered name, so the collision is hidden rather than resolved.

**A match needs all three parts together**, which is what keeps the gate off the retired shape's legitimate neighbours: (1) the numeric-suffix allocation loop; (2) an **accumulating** container — named like a claim set (`used`, `used_names`, `seen`, `taken`, `claimed`, `existing`, …) or mutated by the enclosing function (`.add`/`.append`/`.update`/`.extend`/`|=`/item assignment) — which is what makes the rename order-dependent and invisible to other consumers; (3) a **handler-shaped subject** — a `handler`/`controller`/`endpoint`/`route`/`action` token in the module path, the enclosing function's name, or an identifier the loop touches. Part 2 clears deterministic shadow avoidance against a fixed set of other symbols (a serverless handler `def` renamed away from a service function's name); part 3 clears local-variable, generated-test-method and temp-file name allocation, which no second emitter consumes.

**There is no exemption file, on purpose.** A REST handler name that needs local de-duplication is a name that should have come from the shared table. The baseline is zero and only zero passes.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\repo-hygiene\check-handler-name-dedup.ps1` | Scan every `datrix-codegen-*` package, fail on any violation |
| **Self-test only** | `.\gates\repo-hygiene\check-handler-name-dedup.ps1 -SelfTest` | Prove the scanner detects every retired form and clears every near-miss; skip the real scan |
| **Show files** | `.\gates\repo-hygiene\check-handler-name-dedup.ps1 -ShowFiles` | Print each file as it is scanned |
| **Custom base dir** | `.\gates\repo-hygiene\check-handler-name-dedup.ps1 -BaseDir D:\datrix` | Specify monorepo root explicitly |
| **Debug** | `.\gates\repo-hygiene\check-handler-name-dedup.ps1 -Dbg` | Debug logging |

**Parameters:** `-BaseDir`, `-SelfTest`, `-ShowFiles`, `-Dbg`

**Self-test runs automatically, every invocation.** It plants each retired form (a path-fold de-duplicator, a nested-handler de-duplicator, and a nested-action de-duplicator whose function name says "method" rather than "handler" and is caught by the module path) and requires each to be detected, then plants each legitimate near-miss (serverless shadow avoidance, generated-test-method disambiguation, local-variable allocation) and requires each to be reported clean — so neither a scanner that can only return zero nor one that flags everything is believed. A run that discovers fewer than two `datrix-codegen-*` packages with a `src/` tree, or no Python source in them, fails rather than passing vacuously.

**Exit codes:** 0 = clean (or a successful `-SelfTest`), 1 = a violation was found, 2 = usage error, too few packages discovered, or the self-test failed.

---

## `gates\repo-hygiene\check-observability-native-only.ps1`

Native-only observability providers conformance gate: scans every `datrix/examples/**/config/system.dcfg` (every declared profile, not just the default) for a portable observability provider (`prometheus`/`datadog` metrics, `jaeger`/`zipkin` tracing, `loki` logging, `grafana` visualization, `alertmanager` alerting) paired with a cloud deployment target (`provider = aws` or `azure`) in the same resolved profile -- a pairing the native-only platform-boundary validator rejects. Uses the real `datrix_common.config.unified_loader.load_system_config` + `datrix_common.config.dcfg.parser.parse_dcfg` resolution pipeline (never a hand-rolled regex scan of the DSL, which cannot follow profile inheritance correctly). It follows the same self-test-first shape as `check-docs-conformance.ps1`.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\repo-hygiene\check-observability-native-only.ps1` | Scan every example/profile, fail on any cloud+portable pairing |
| **Warning mode** | `.\gates\repo-hygiene\check-observability-native-only.ps1 -Warn` | Report violations but exit 0 |
| **Scratch examples root** | `.\gates\repo-hygiene\check-observability-native-only.ps1 -ExamplesRoot D:\datrix\.tmp\obs-guard-check\examples` | Scan a hand-crafted examples tree instead of the real one |
| **Self-test only** | `.\gates\repo-hygiene\check-observability-native-only.ps1 -SelfTest` | Run only the scanner's own edge-case self-test suite |
| **Show files** | `.\gates\repo-hygiene\check-observability-native-only.ps1 -ShowFiles` | Print each `system.dcfg` being scanned |
| **Debug** | `.\gates\repo-hygiene\check-observability-native-only.ps1 -Dbg` | Print the python invocation |

**Parameters:** `-Warn`, `-ExamplesRoot`, `-SelfTest`, `-ShowFiles`, `-Dbg`

**Self-test runs automatically, every invocation.** A plain-Python self-test suite (`--self-test` on the underlying `.py`; no pytest -- real `tempfile.TemporaryDirectory()` fixtures and `assert` statements) covers a deliberately-crafted cloud+portable-metrics violation (must be flagged), a clean LOCAL example with the same portable metrics provider (must NOT be flagged -- proves the guard checks the pairing, not the provider alone), and a clean cloud example using its platform-native metrics provider (must NOT be flagged -- proves the guard doesn't reject every cloud example). This suite runs, unconditionally, as step 1 of every invocation (self-test failure aborts before the real scan, exit 2); `-SelfTest` runs it in isolation and skips the real scan.

**Assertions:**
- Every profile of every `examples/**/config/system.dcfg` is resolved via the real `load_system_config` pipeline and checked -- not just the default profile.
- A configured portable-category provider value paired with a resolved `deployment.provider` of `aws` or `azure` is a violation; `local` is never a violation target.
- A `logging` block with `provider = None` (stdout-only) is never flagged, even on a cloud target.

**Exit codes:** 0 = no violations found (or a successful `-Warn` or `-SelfTest` run), 1 = at least one violation found (or `-SelfTest` reports a failing check), 2 = usage error, missing examples root, or the automatic self-test step failing on a normal invocation.

---

## `gates\repo-hygiene\emitted-escape-integrity-gate.ps1`

Escaped-escape gate for **Python-emitting** templates. Jinja copies template text through verbatim, so a doubled backslash before `n`/`t`/`r` in a `*.py.j2` template reaches the emitted Python source still doubled — an escaped BACKSLASH rather than the escape that was meant — and the generated program builds a string carrying two literal characters where a line break belonged. Nothing downstream notices: the emitted Python compiles, the function writing the artifact returns the right count, and any validator that accepts comments passes. Found in production as a gateway trusted-peer fragment whose whole body landed on one physical line behind a leading `#`, so every directive in it was read as part of that comment and the proxy trusted nobody — through a green smoke gate and a successful deploy. Scope is deliberately templates that emit **Python**: a doubled backslash is ordinary and correct in shell-, TypeScript- and regex-emitting templates. The package set is walked from disk, so a new `datrix-codegen-<lang>` package is covered with no edit.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\repo-hygiene\emitted-escape-integrity-gate.ps1` | Scan every `*.py.j2` template under every package's `src/` |
| **Show files** | `.\gates\repo-hygiene\emitted-escape-integrity-gate.ps1 -ShowFiles` | Print each template as it is read |
| **Custom base dir** | `.\gates\repo-hygiene\emitted-escape-integrity-gate.ps1 -BaseDir D:\datrix` | Specify monorepo root explicitly |
| **Self-test only** | `.\gates\repo-hygiene\emitted-escape-integrity-gate.ps1 -SelfTest` | Run only the detector's non-vacuity self-test; skip the real scan |

**Parameters:** `-BaseDir` (default: `D:/datrix`), `-ShowFiles`, `-SelfTest`

**Self-test runs automatically, every invocation.** The run length IS the rule — one backslash is the correct escape, two are the defect, four are a deliberate deeper escape — so the self-test covers all three and requires the detector to flag exactly the middle one. A detector that cannot tell them apart would either miss the defect or flag correct code until someone exempted it away. Self-test failure aborts before the real scan (exit 2).

**Assertions:**
- No `*.py.j2` template carries a run of exactly two backslashes before `n`, `t`, or `r`, outside the reviewed exemptions.
- Discovering zero templates is a failure, not a clean result (the scan would pass vacuously).
- Every exemption in `scripts/config/emitted-escape-exemptions.json` still matches a live line; one that matches nothing fails the gate rather than lingering.
- Every baseline entry names a file, the exact matched line, and a reason.

**Exit codes:** 0 = clean, 1 = an escaped escape was found or an exemption matches nothing, 2 = usage error, unreadable/self-inconsistent exemptions baseline, no templates discovered, or a failing self-test.

---

## `gates\repo-hygiene\app-probe-path-literal-gate.ps1`

Application probe-path literal gate: no platform package may hardcode a route a registered language declares as its readiness or liveness probe. The route a traffic-routing probe consults (Compose `healthcheck`, ECS / App Runner health check, ALB / NLB target-group health check, Front Door origin probe, App Service health monitor) is a route the LANGUAGE's generated application mounts, declared on `LanguageRuntimeSpec.readiness_probe_path()` / `app_service_liveness_probe_path()`; every platform reads it from the resolved plugin. Platform packages are discovered from disk (every `datrix-*/pyproject.toml` registering `datrix.platforms`); the declared routes come from the installed `datrix.languages` plugins; each platform `src/` tree is scanned for Python string constants (`ast`, docstrings excluded) and quoted `.j2` literals (comment lines excluded) equal to a declared route. Exists because a shared `"/ready"` constant was once consumed identically by every platform while one registered language never mounted `/ready`, so its containers were probed at a 404 on three platforms and never became healthy.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\repo-hygiene\app-probe-path-literal-gate.ps1` | Scan every platform package, fail on any unexempted probe-route literal |
| **Self-test only** | `.\gates\repo-hygiene\app-probe-path-literal-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real scan |
| **Show files** | `.\gates\repo-hygiene\app-probe-path-literal-gate.ps1 -ShowFiles` | Print each file as it is scanned |
| **Debug** | `.\gates\repo-hygiene\app-probe-path-literal-gate.ps1 -Dbg` | Print the python invocation |

**Parameters:** `-BaseDir <path>`, `-SelfTest`, `-ShowFiles`, `-Dbg`

**Assertions:**
- Every literal hit is either absent or covered by a reviewed entry in `datrix/scripts/config/app-probe-path-exemptions.json` (file + exact snippet + written reason). An exemption is legitimate only for a literal that is NOT an application probe target (an infrastructure container's own probe, a gateway framework-path list); an application probe is never exempted. A stale entry whose snippet no longer matches a hit fails the gate.
- Non-vacuity self-test (every invocation): a planted platform package yields exactly its code-line hits (a docstring and a template comment carrying the same route are NOT reported), a clean planted package yields none, a workspace with fewer than two platform packages or fewer than two registered languages is refused, and the **live** scan of the language packages' own `src/` trees finds every declared route — so the matcher is proven against the real literals the languages mount, not only against fixtures.

**Exit codes:** 0 = clean (or a successful `-SelfTest`), 1 = an unexempted hit or a stale exemption was found, 2 = the self-test failed, too few packages/languages were discovered, or a manifest/exemption file could not be parsed.

---

## `gates\repo-hygiene\example-registry-gate.ps1`

Example-universe consistency **and layout** gate: every `system.dtrx` under `datrix/examples/` must appear in >= 1 named test set of `scripts/config/test-projects.json`, or carry a reviewed entry in `scripts/config/test-set-exclusions.json`. An unregistered example is never built by `generate.ps1 -All`/`run-complete.ps1 -All`, which select their corpus FROM `test-projects.json`'s test sets -- this is exactly how the `config-store` and `replayable-ingestion` whole-example parked defects (tracked in `parity-known-nongenerating.json`) went unnoticed for a full generation cycle before this gate landed.

The gate also enforces the examples tree's layout contract, since an example's identity IS its directory (`example_id`, its parity-baseline key and its `test-projects.json` path are all derived from the path its `system.dtrx` sits under): no example may live inside another example, and no `.dtrx`/`.dcfg` may belong to two examples or to none.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\repo-hygiene\example-registry-gate.ps1` | Compare disk examples against test-projects.json + test-set-exclusions.json, and check the examples tree's layout |
| **Debug** | `.\gates\repo-hygiene\example-registry-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\gates\repo-hygiene\example-registry-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- Every `system.dtrx` under `datrix/examples/` has an id reachable from >= 1 `testSets` entry, or a `test-set-exclusions.json` entry.
- An exclusion naming an example with no `system.dtrx` on disk is a stale-exclusion violation.
- An example both excluded AND registered in some test set is a redundant-exclusion violation.
- An example directory inside another example directory is a nested-example violation -- the host's whole-tree operations would silently absorb the guest.
- A `.dtrx`/`.dcfg` contained in more than one example directory is a shared-file violation; one contained in no example directory is an unowned-file violation (a leftover nothing can parse).
- Non-vacuity self-test (every invocation, no file I/O): synthetic ids and paths prove both pure comparators detect each of the six violation classes and report a clean state as clean.

**Exit codes:** 0 = registry and layout both consistent (or a successful `-SelfTest`), 1 = at least one violation, 2 = the self-test failed, zero examples exist on disk, or a config file is missing/malformed/miscounted.

---

## `gates\repo-hygiene\example-snapshot-gate.ps1`

Committed example-snapshot gate. An example may carry `generated/<language>-<platform>/` snapshots of its own output; nothing else compares them with the generator, so they rot (a tree for a language nobody can generate any more, an import of a framework module that has since moved). Two checks, both derived from the registered entry points and from `importlib`, never from a hand-written list:

- **Snapshot identity.** Every directory directly under any `datrix/examples/**/generated/` is named `<language>-<platform>` with `<language>` a registered `datrix.languages` name and `<platform>` a registered `datrix.platforms` name (parsed by matching a registered language prefix, then the remainder against the platform set, since platform names contain hyphens). For each example and each platform it carries, the snapshot languages equal the registered language set.
- **Framework references resolve.** Every dotted `datrix_*` reference in every text file of every snapshot and in every `datrix-*/src/**/*.j2` template resolves: the longest prefix `importlib.util.find_spec` finds is imported and the remaining segments resolve by attribute access. A reference rooted at a name the same file binds with `import ... as <name>` (a Dart import prefix) is that file's own binding, not a framework module.

It does not regenerate and diff (a whole-system generation per language per run); refresh a snapshot with `generation\refresh-example-snapshot.ps1`.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\repo-hygiene\example-snapshot-gate.ps1` | Both checks over the live tree |
| **Debug** | `.\gates\repo-hygiene\example-snapshot-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\gates\repo-hygiene\example-snapshot-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the live run |

**Parameters:** `-Dbg`, `-SelfTest`

**Self-test (every invocation):** a fixture holding every registered language passes; a planted unregistered language fails naming it; a fixture missing one registered language fails naming it; a planted `datrix_common.migration.live_snapshot_export` fails and `datrix_migration.live_snapshot_export` passes; `datrix_common.utils.text.to_snake_case` passes and a missing attribute fails; a file-local import alias is exempt only in the file that binds it.

**Exit codes:** 0 = clean (or a successful `-SelfTest`), 1 = at least one violation (each names `file:line` and the reference, or the directory, the installed sets and the refresh command), 2 = fewer than two registered languages, a failed self-test, no snapshot on disk, or no template reference found.

---

## `gates\repo-hygiene\example-secret-seed-gate.ps1`

Example secret-seed gate: every example's deploy test can start its stack. A handle a service
declares in its `secrets { }` table is mounted into the container as a file, and the generated
deployment script refuses to start while that file is absent, writing nothing in its place; on
a local secret profile the generator writes the file only from the handle's `localDefault`. The
corpus is deploy-tested on the `test` profile by an unattended harness, so for every example,
on that profile, every `required = true` operator-provisioned handle must carry a `localDefault`
-- or no full-corpus run can ever bring the example up. A handle the profile does not consume
(a live-model API key on a profile that binds `replay`) is dropped from that profile with
`replace secrets { ... }`, never seeded with a fake value.

Resolves each example's service `.dcfg` files (kind detected by parsing, so identity/system
configs are skipped) through `datrix_common.config.unified_loader.load_service_config` on the
`test` profile -- the same resolution the pipeline applies -- and never parses a `.dtrx`.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\repo-hygiene\example-secret-seed-gate.ps1` | Check every example's resolved `test`-profile secret tables |
| **Debug** | `.\gates\repo-hygiene\example-secret-seed-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\gates\repo-hygiene\example-secret-seed-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real check |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- For every `system.dtrx` under `datrix/examples/` and every service-kind `.dcfg` under its `config/`, the `test`-profile secret table has no handle that is `required = true`, `provisioningAuthority = "operator"` and without `localDefault`.
- Non-vacuity self-test (every invocation, no file I/O): a synthetic table with seeded, unseeded, optional and Datrix-owned handles must report exactly the unseeded ones, and an empty table must report nothing.

**Exit codes:** 0 = every handle seeded (or a successful `-SelfTest`), 1 = at least one unseeded handle, 2 = the self-test failed, zero examples or zero service configs exist on disk, or a config fails to parse or resolve.

---

## `gates\repo-hygiene\example-config-load-gate.ps1`

Example config load gate: every declared profile of every example `.dcfg` loads. Every model a
ConfigDSL document validates into rejects unknown keys, so a key the model does not declare is an
error at load time rather than a value silently dropped. The gate loads every declared profile of
every `.dcfg` under `datrix/examples` through the real loaders (`service`, `shared`, `system`,
`identity`, `app`, `strings`, `extern`; the kind is read from the parsed declaration) and fails on
any parse, resolution or validation error.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\repo-hygiene\example-config-load-gate.ps1` | Load every declared profile of every example `.dcfg` |
| **Debug** | `.\gates\repo-hygiene\example-config-load-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\gates\repo-hygiene\example-config-load-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real check |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- Every profile declared by every `.dcfg` under `datrix/examples` loads without error.
- Non-vacuity self-test (every invocation): a planted temp `.dcfg` with an unknown nested key is reported with the key named and the value not echoed, and its clean twin loads.

**Exit codes:** 0 = every profile loads (or a successful `-SelfTest`), 1 = at least one profile failed to load, 2 = the self-test failed, zero `.dcfg` files exist on disk, or a file does not parse.
