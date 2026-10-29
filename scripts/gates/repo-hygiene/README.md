# Repo-Hygiene Gates

Gates over the repositories themselves: what may be committed, what docs may claim, what examples must
satisfy, and code shapes held at zero. Repo-level validation **scripts**, not pytest suites (the datrix
showcase repo hosts none); each gate's own self-test is its coverage. The commands, parameters and exit
codes of each gate are in [quick-reference.md](quick-reference.md); this file holds what each proves and
how it decides. The family overview is [../README.md](../README.md).

Each gate has a POSIX twin `gates/repo-hygiene/<name>.sh` taking the module's flags as `--kebab-name`; its
Python is `datrix_scripts.gates.repo_hygiene.<wrapper stem>`, and its last line is
`[GATE] <name> PASSED|FAILED exit=<n> log=<path>`.

## `customer-domain-isolation-gate.ps1`

**The repo's proof that no customer/project domain language lives in a framework repo.** Scans every
PUBLISHABLE file of every framework repo in the workspace (`datrix` plus every `datrix-*` clone,
discovered from disk) — tracked files plus untracked-but-not-ignored ones, since a new file is untracked
right up until the `git add` that commits it — against the hashed customer-term corpus at
`scripts/config/customer-term-hashes.json`. One hit fails the gate. The rule ("no customer name, no
customer-specific service names, no terms from a customer's business domain in framework code, docs,
tests, or examples") was prose only until this gate: customer cloud-resource names and paths into a
customer checkout reached committed files through Claude Code permission entries, and a customer
deployment target reached a hook's docstring example.

**The corpus stores digests, not terms.** A plaintext denylist naming the customer would itself be the
violation it polices. Only SHA-256 digests of lowercased terms are committed, so the term never exists in
any repo, while the check still travels with the checkout and enforces on every machine — an out-of-repo
term file would silently not exist on a second machine, which is exactly the failure mode a guard must
not have. Register a term with `-AddTerm`; the plaintext is hashed and discarded. `-Hint` (default
`customer project`) is stored beside it. `-PendingOnly` scans only what a `git add -A` would stage.

**Reported excerpts are redacted.** The matched token is masked as `<customer-term>`; the file and line
are what a fix needs. Echoing the term back invites an agent into copying it onward — into a summary, a
task file, or a commit message — re-committing the leak while reporting it.

**Self-test runs automatically, every invocation.** Before any real scan, the scanner is fed four
synthetic occurrence shapes it must detect (hyphenated resource name, path segment, camelCase identifier,
upper-case identifier), two clean strings it must NOT flag, a redaction check (the reported excerpt must
not contain the term), and an empty-corpus check (must report nothing). On real temp git repos it then
proves the file listings reach what a commit would publish: an untracked file is listed and its term
found, an ignored one is not scanned, an untracked path holding a space and a non-ASCII character is
listed verbatim, and a `git mv` rename is listed under its new name only. Planted files prove every file
is read: a term in UTF-16, Latin-1, past 2 MB and behind binary bytes is found, a path that cannot be read
stops the scan, and a corpus that is not a JSON object is refused. The `-AddTerm` checks prove only a
digest is stored, a term that could never match or that a hint would leak is refused, and the `-Dbg` echo
redacts the term. A detector that stopped detecting reports a clean tree, which is indistinguishable from
a clean tree — so a self-test failure aborts before any result is trusted. `-SelfTest` runs only that and
scans nothing real.

**Matching shape:** content is split into alphanumeric tokens, each token is additionally camel-split, and
every piece of at least `min_token_length` (default 5) characters is lowercased and hashed. That covers
`<term>-system-kv-dev`, `//d/g/<Term>/**`, `<term>_rg`, and `<term>Backend`. It does NOT match a term
glued to another word with neither separator nor case boundary (`<term>dev`) — a hash denylist cannot
substring-search without the plaintext it deliberately does not hold; register such a variant as its own
term.

**Also enforced at the commit seam and on every edit.** `git\commit-and-push.ps1` runs the same scanner
over every dirty repo's pending changes before it generates a message or stages anything, and refuses the
whole run on a violation (`-SkipCustomerDomainCheck` overrides, loudly); the `guard-committed-content.py`
hook refuses an edit that adds a registered term. This gate is the whole-tree counterpart: it also
catches what is already committed.

Exit code 0 also covers zero terms registered, reported as `NOT ENFORCED`; exit 2 covers a missing or
malformed corpus, a repo git cannot list, or a publishable file that exists but cannot be read. Every
file is read whatever its size or encoding (NUL bytes dropped, so UTF-16 text is matched too); an
unreadable one is never skipped, so the gate names it and stops.

Module: `datrix_scripts.gates.repo_hygiene.customer_domain_isolation_gate`; POSIX twin options `--repo`,
`--pending-only`, `--add-term`, `--hint`, `--self-test`, `--dbg`.

## `retired-dsl-names-gate.ps1`

**The repo's proof that no retired internal-DSL name survives a rename.** When an internal language is
renamed or replaced, its old name leaves every identifier, module, package, entry-point group, feature
tag, script, resource file and document. The gate scans every publishable file (tracked plus
untracked-but-not-ignored) of every framework repo, discovered from disk — file content, file names and
directory names — and fails listing `path:line` per hit (`path: name segment '<segment>'` for a file or
directory name; a directory is reported once). The terminal state is zero: there is no baseline and no
allowlist.

**The spellings are data.** `config/retired-dsl-names.json` holds one entry per retired family: `name`,
`replacement` (printed in the failure message), `patterns` (case-insensitive regular expressions) and
`samples` (concrete spellings the self-test plants; each must match one of its family's patterns or the
gate refuses to run). That file is the only path the scan skips, so the gate's own module, wrapper and
this page are scanned and never spell a retired name. Retiring another language is one new entry.

**Self-test runs automatically, every invocation.** It creates a scratch git repo under
`D:\datrix\.tmp\`, plants every sample of every family in file content, in a file name and in a directory
name of untracked files, plus a git-ignored copy, a clean file and an exempt spellings file, lists it with
the same lister the real scan uses, and fails unless every planted spelling is reported and nothing else
is.

Exit code 2 covers a malformed spellings file, a repo git cannot list, or a publishable file that exists
but cannot be read (for example, locked by another process on Windows). An unreadable file is never
skipped: skipping it would leave its content unscanned and report a clean tree, so the gate names the file
and stops.

**Security posture.** The gate only reads files (and, in the self-test, writes a scratch repo under
`D:\datrix\.tmp\`); it opens no network connection and changes nothing in the repos it scans.

Module: `datrix_scripts.gates.repo_hygiene.retired_dsl_names_gate`; POSIX twin options `--repo`,
`--self-test`, `--dbg`.

## `design-task-reference-gate.ps1`

**The repo's proof that no committed artifact cites a design document or a task file.** `design/` and
`.tasks/` are gitignored and are developed on more than one machine, so their numbering collides: two
different `044-*` documents can exist, and after a clone neither is present. A reference to one from
anything committed is a dangling pointer — it resolves to nothing, or to a different artifact elsewhere.
The gate scans the committed trees for the SHAPE of such a reference and fails on any hit.

**Roots are derived from disk, never hand-authored.** Every package directory
`framework_repos.workspace_package_dirs` discovers (`datrix` and every `datrix-*`) contributes its `src`,
`tests`, `docs` and `scripts` subtrees (the `datrix` showcase repo contributes `scripts`, `docs`,
`examples` instead — it has no `src`), so a new package is scanned the day it appears. The gitignored
orchestration trees themselves (`.tasks/`, `.bugs/`, `design/`) plus build noise are skipped: design and
task files referencing **each other** is allowed and expected. `-Roots` scans only the named directories
(comma-separated).

**Item labels are policed too, in every label letter.** Findings, reviews and designs number their own
items with a capital letter and digits, in parentheses or before a colon, and a comment carrying one
points into a gitignored document. Two shapes, over the same extensions, inside a package's `src`,
`tests` and `scripts` and the `datrix` repo's `scripts` — never under `docs` or `examples`, where
committed documents number their own items: a parenthesized label (`D`/`G`/`I` with any digit count,
every other capital letter with one or two digits, optionally a `/` or `,` list) and a heading label (the
same letters followed by a colon, refusing a preceding `.` or word character so `StorageProvider.S3:` is
attribute access). One or two digits for the other letters keeps ruff/pylint codes (`F821`, `A002`,
`R0801`, `F401/F811/I001`) out. The possessive of a bare task id (`NN-MM's`) is matched in every root; a
bare `NN-MM` is not, because dates and line ranges look the same. `LABEL_TOKEN_EXCEPTIONS` in the library
module holds exact `(workspace-relative path, token)` pairs with a written reason — today the emitted
`P95` percentile chart title in the Azure monitor workbook generator; the token anywhere else is a hit.
Hit lines name the shape: `[item label (parenthesized)]`, `[item label (heading)]`,
`[task-file id (possessive)]`.

**Also enforced at the commit seam and on every edit.** `git\commit-and-push.ps1` runs the same scan over
the pending files of every dirty repo before it generates a message or stages anything, and refuses the
whole run on a hit; there is no skip switch. The `guard-committed-content.py` hook applies the same
detector to the lines an edit adds.

**Four reference shapes are matched, over every text type the framework repos commit**
(`SCAN_EXTENSIONS` in the library module: source and templates, the `.ps1` wrappers and their `.sh`
twins, `.psm1`/`.psd1` modules, Dart, C, web assets, data files, prose, and the Datrix documents and
fixtures `.dtrx .dcfg .dseed .dal`, including disabled `*.dtrx.false` fixtures; only binaries are left
out) (spelled here with `N`/`M` placeholders so this page is not itself a hit): a task-file id
(`task-NN-MM`, the prose `task NN-MM`, and the three-digit `task-NN-MMM`, case-insensitively), a design
path (`design/NNN-slug`), a design number (`design NNN`, `design-NNN`, `design doc NNN` — the word `doc`
is optional), and a phase directory (`.tasks/phase-NN`). Each line is also matched joined to the next with
that line's comment leader (`#`, `//`, ` * `, `--`) removed, because a wrapped comment splits a reference
across the break (`(design` / `# NNN section …`) and a line-at-a-time match sees neither half; a hit is
reported at the line it starts on. A **bare** `Phase NN` is deliberately NOT matched: the committed
architecture docs use it as product vocabulary for delivery waves, self-contained text rather than a
pointer into a gitignored tree.

**The terminal state is zero.** There is no baseline and no count to ratchet down. `ALLOWLIST` in
`scripts/common/lib/datrix_scripts/design_task_references.py` is the only escape hatch and is for files
that document the ID *format* itself (the task-ID parser, the review runner's usage examples, this gate's
own patterns) — never for a file that merely happens to carry a reference.

**Self-test runs automatically, every invocation.** One line per reference shape is planted in a temp
directory and every one must be flagged, including in a `.sh` twin, a `.psm1` module and a `.dcfg`
fixture; a clean file must produce zero; a path that cannot be read must stop the scan rather than be
skipped; and a bare `### Phase 01 capabilities` heading must NOT be flagged. A second fixture workspace
with `src/`, `tests/`, `scripts/` and `docs/` trees plants every label shape (each must hit exactly once)
and the near misses (attribute access, lint codes, line ranges, a label under `docs/`, the excepted token
in its own file) that must hit zero; the same `P95` in another file must hit, and `scan_paths` (the
commit-time entry) must agree with `scan` over the same files. A scan that silently matches nothing
returns a confident "clean" that will be believed — which is exactly how two holes in this gate let whole
phases' worth of references through: matching only the hyphenated `task-NN-MM` form missed the prose
`task NN-MM` an agent actually writes, and requiring the literal word `doc` missed the bare `design NNN`
entirely.

Exit code 1 also covers a scanned file that could not be read (never skipped: the gate names it and
stops).

Module: `datrix_scripts.gates.repo_hygiene.design_task_reference_gate`; POSIX twin options `--roots`,
`--self-test`.

## `package-data-coverage-gate.ps1`

**The repo's proof that every runtime resource a package loads ships in its built wheel.** A generator
package loads its Jinja2 templates (`*.j2`) and its DAL generator definitions (`*.dal`) from its
installed package directory. Neither is Python, so a wheel carries them only when a
`[tool.setuptools.package-data]` glob of the package's `pyproject.toml` matches them. An editable install
reads the source tree directly, so a missing glob is invisible locally. Every test passes, every
generation works, and the loss appears only after installing the built wheel, as a package that cannot
render a file. Every `datrix-*` package with a package-data table is scanned, discovered from disk.

**Why it exists.** The python and typescript backends shipped two of their three hundred templates each.
Their glob, `**/templates/*.j2`, matches only files *directly* inside a `templates/` directory, while
nearly every template sits one level deeper (`templates/messaging/…`).

**Setuptools is the oracle for matching.** Each pattern is expanded the way setuptools expands it:
`glob.glob(<package dir>/<pattern>, recursive=True)`, with a dotted key naming a sub-package directory.
`fnmatch` is never used, because its `*` crosses directory separators and reports a confident "shipped"
for a file setuptools leaves out.

**Self-test runs automatically, every invocation.** A planted package whose glob is `**/templates/*.j2`
must report its nested `templates/messaging/consumer.py.j2`, and only that file. A recursive
`templates/**/*.j2` over the same tree must report nothing.

Exit code 2 is an unknown `-Package` name.

Module: `datrix_scripts.gates.repo_hygiene.package_data_coverage_gate`; POSIX twin options `--package`,
`--self-test`, `--dbg`.

## `line-ending-gate.ps1`

**The repo's proof that every framework repo normalizes text to LF and commits no CRLF line.** With
`core.autocrlf=false` (this workspace's setting) and no attribute rule, a file an editor or a bulk edit
rewrote with CRLF is committed as CRLF: every line of it shows as changed, `git blame` loses its history,
and the file differs byte-for-byte between checkouts. A package with no `.gitattributes` once had
forty-two modified files switched to CRLF in its working tree by one bulk edit, one commit away from
rewriting all of them. The showcase repo and every `datrix-*` git checkout are discovered from disk, so a
new package is checked the day it is cloned.

**Git is the oracle.** Two facts per repo, neither re-implemented:

| Rule | Fact |
|------|------|
| `policy` | `git check-attr text eol` on a probe path no per-extension rule names resolves to `text: auto` and `eol: lf` — the catch-all `* text=auto eol=lf` line is in force, so a CRLF working-tree file is staged as LF |
| `committed-crlf` | `git ls-files --eol` reports no tracked file whose index blob is `i/crlf` or `i/mixed`; binary files (`i/-text`) are never reported |

A per-extension `eol=crlf` line (`*.ps1`) is untouched by either rule: the index copy is still LF, only
the checkout differs. A working tree whose files differ in line endings from their index copy is
`git\fix-line-endings.ps1`'s job; this gate holds what is, or would be, committed.

**Self-test runs automatically, every invocation.** Two scratch git repos under `D:\datrix\.tmp\` stage
the same CRLF text file and a binary file carrying CR LF bytes: the one with no attributes must report
exactly the `policy` fact and the text file, and the one under `* text=auto eol=lf` must report nothing. A
self-test failure aborts before any real result is trusted (exit 1). `-SelfTest` also runs the wrapper
seam checks.

Exit code 2 is a usage error (unknown `-Repo` name, no framework repo found) or a failing git command.

Module: `datrix_scripts.gates.repo_hygiene.line_ending_gate`; POSIX twin options `--repo`, `--self-test`,
`--dbg`.

## `hidden-code-point-gate.ps1`

**The repo's proof that no generator source holds a code point a reader cannot see.** A generator's
templates and modules are what every generated project is built from: a bidi control (Trojan Source,
CVE-2021-42574), a zero-width character, a non-ASCII space or a control written raw in one of them makes
the source a reviewer reads differ from the source a compiler reads, in the framework and in every
project it emits. What counts as hidden is `datrix_common.utils.hidden_text.hidden_in_source`, the one set
every escaper reads: every code point that is not printable, every Default_Ignorable_Code_Point, and
U+2800 BRAILLE PATTERN BLANK.

Every file a commit could publish under `src/` of every `datrix-codegen-*` git checkout (tracked files and
untracked files git does not ignore, discovered from disk, so a new generator package is checked the day
it is cloned) is read as UTF-8, and every flagged code point other than TAB, LF and CR is reported as
`<repo>/<path>:<line>:<column>: U+HHHH`. Lines count LF alone (U+0085, U+2028 and U+2029 are reported,
never taken as line breaks); columns count code points; both start at 1. A file that is not UTF-8 text
cannot be judged and is reported too. The fix is an escape of the file's language (a `\u` escape of the
hex in a string literal), or deleting the code point.

**Self-test runs automatically, every invocation.** Every row of the shared hidden-text corpus
(`datrix_testing.hidden_text_corpus`) must be reported at the line and column of each of its hidden code
points (the joiner of an emoji sequence, not its glyphs); TAB, LF and CR must pass; U+2028 must be
reported on its own line, not split it; and planted files under `D:\datrix\.tmp\` (one with a zero-width
space, one not UTF-8, one clean) must report exactly the first two. A self-test failure aborts before any
real result is trusted (exit 1). `-SelfTest` also runs the wrapper seam checks.

Exit code 1 also covers a file that is not UTF-8 or package installs that are not current; exit 2 is a
usage error (unknown `-Repo` name, no generator repo found) or a failing git command or file read.

Module: `datrix_scripts.gates.repo_hygiene.hidden_code_point_gate`; POSIX twin options `--repo`,
`--self-test`, `--dbg`.

## `ignored-source-gate.ps1`

**The repo's proof that no `.gitignore` rule is silently deleting a publishable file.** For the `datrix`
showcase repo and every `datrix-*` clone in the workspace (discovered from disk at runtime — a new
package is covered with no edit to the gate), it computes the set difference between the working tree and
what a `git add -A` would stage. Every element of that difference must be a reviewed, scoped entry in
`scripts/config/ignored-source-exemptions.json`; anything else is a source file that exists locally and
will not survive a clone. An entry names the ignore rule by its pattern text and by a segment-aware glob
over the repo-relative path of the `.gitignore` file git blames (a literal path matches only that file;
`examples/**/generated/**/.gitignore` matches the nested files a generator writes into each emitted
project), and scopes the paths it excuses with `path_glob`. `-ShowExempt` prints every reviewed entry with
its written reason, then scans.

**Why it exists.** A package carried the stock Python `.gitignore`'s **unanchored** `MANIFEST` line —
intended for setuptools' root `MANIFEST` file. Git matches an unanchored pattern at *any depth*, and
`core.ignorecase=true` on this platform makes the match case-insensitive, so it also matched a
`templates/manifest/` directory and swallowed both Jinja2 templates inside. Nothing was visible locally:
the files were on disk, every test passed, the emitted output compiled. The loss appears only after a
clone or a wheel install, as a package that cannot generate — and by then the templates are gone from
history. It was found by hand, by comparing a file count against a `git add -A --dry-run` count. This gate
is that comparison, living in code.

**Git is the oracle.** Ignore matching is never re-implemented. `git ls-files -o -i --exclude-standard`
produces the difference at *file* granularity (directories are not collapsed), and `git check-ignore -v`
names the `.gitignore` file, line number, and pattern responsible for each element. Anchoring, negation
(`!`), nested `.gitignore` files, `.git/info/exclude`, global excludes and `core.ignorecase` interact in
ways a hand-rolled matcher gets wrong — and a wrong matcher returns a confident "clean" that will be
believed, which is how the original defect survived. A path git refuses to stage but attributes to no
rule is reported with a placeholder rule and fails the gate; it can never match an exemption.

**Every finding names the rule, not just the file.** Output is grouped as
`<gitignore>:<line>: <pattern> -- shadows N publishable file(s)`, then the paths. Reporting only the file
leaves the fix a hunt through several hundred `.gitignore` lines.

**Exemptions are scoped, and the scope is load-bearing.** Each entry excuses **one** rule (identified by
the `.gitignore` file plus the pattern text git reports) over **one** path scope, and carries a written
reason. An entry for the root `build/` tree does not excuse the same unanchored `build/` rule swallowing a
`templates/build/` directory full of source — that is the same defect wearing a different name, and the
self-test proves the scope rejects it. `repos` is a list of repo names or `["*"]` for every framework
repo; `path_glob` is segment-aware (`**/` spans whole segments, `**` spans the remainder, `*`/`?` stay
inside one segment). `pinned_count` is enforced against `len(exemptions)`, so an entry cannot be added or
removed without the reviewed number moving in the same change.

**A stray temp directory is a different finding with a different fix.** Temp, scratch and test-output
directories never belong inside a package repo (`guard-repo-temp-dirs.py` refuses to create one; the
workspace-level `D:\datrix\.tmp`, `.scripts`, `.test-output` are where they go). One that exists anyway —
left by a run before the hook, or by a tool that defaulted its output path — is full of
`.py`/`.java`/`.sql` files that an ignore backstop hides, and to a scan that only knows "ignored,
unexempted" it looks like hundreds of thousands of shadowed source files whose fix is to edit the ignore
line or add an exemption; both are wrong. The gate classifies such paths by the **same name list the hook
enforces** (`claude-config/.claude/hooks/_repo_temp_dir_names.py` — one definition, two enforcement
points; the gate refuses to run if it cannot load it rather than keep a copy) and reports each directory
**once**, as a `WARNING` carrying the file count and the `Remove-Item` command. It never appears in the
shadowed-source report, it can never be exempted, and it does not fail the gate: the contents are already
unpublishable, and the gate's verdict is about what a clone would lose. `commit-and-push.ps1` prints the
same warning and proceeds.

**Self-test runs automatically, every invocation.** Before any real scan, real `git init` repos are
created in a temp directory and the scanner must reach the correct verdict on each planted path — a scan
that can only return zero is not evidence, which is precisely how the original defect survived. It
asserts:

- an unanchored `MANIFEST` rule shadowing `src/pkg/templates/MANIFEST/entry.j2` is **detected**, and blamed on the right `.gitignore` **file, line number and pattern**;
- that finding is **not** excused by any entry in the real exemption file;
- a planted publishable file (`src/pkg/keep.py`) is **not** reported;
- a `__pycache__/` file and a root `build/` file **are** excused by their real entries, while the same `build/` rule shadowing `src/pkg/templates/build/template.j2` is **not** — proving the path scope is load-bearing;
- an empty exemption set excuses nothing (the exemption matcher is not vacuously true);
- two files planted in different subtrees of a `.test-output/` directory fold into **one** stray-temp-directory finding with a count of 2 and a delete command, appear in **no** shadowed-source finding, and do not swallow the `MANIFEST` finding beside them — which also proves the hook's shared name list still names `.test-output`;
- git's own semantics are honoured: a `!`-re-included path is not reported, and a lowercase `manifest` directory under an uppercase `MANIFEST` rule is detected **iff** `core.ignorecase` is true in that repo;
- the scope glob is segment-aware across nine positive and negative cases.

A self-test failure aborts before any real result is trusted (exit 1).

**Unused exemption entries are reported, never failed.** An entry covers output a tool writes only once it
has run (a coverage report, an `npm install`), so its absence on a clean checkout is normal and is not
evidence the entry is stale.

**Also enforced at the commit seam.** `git\commit-and-push.ps1` runs the same scanner over every dirty
repo before it generates a message or stages anything, and refuses the whole run on a violation
(`-SkipIgnoredSourceCheck` overrides, loudly); a scanner that fails its own self-test aborts the run
rather than returning a verdict nobody can trust. That is the seam this defect is actually about —
`git add -A` is where the file is or is not published. This gate is the whole-workspace counterpart: it
also covers repos the current run is not committing.

Exit code 2 is a usage error (unknown `-Repo` name, no framework repo found) or a
missing/malformed/miscounted exemption file.

Module: `datrix_scripts.gates.repo_hygiene.ignored_source_gate`; POSIX twin options `--repo`,
`--self-test`, `--show-exempt`, `--dbg`.

## `polystring-case-roundtrip-gate.ps1`

**The repo's proof that no name goes `str()` → `to_*_case()`.** Every identifier the generator re-cases —
an entity, service, block, field, queue or shared-container name, `QualifiedNode.name`,
`qualified_name` — is a `PolyString`: a `str` subclass that split its words **once** and exposes
`.snake`, `.camel`, `.pascal`, `.kebab`, `.screaming_snake` and `.simple`. The case functions in
`datrix_common.utils.text` are for text that is *not* already a name object. For the `datrix` showcase
repo and every `datrix-*` clone (discovered from disk at runtime), the gate parses every publishable
`.py` file with `ast` and fails on any case-function call — by canonical name, import alias, or module
attribute — whose argument is one of four shapes:

| Kind | Shape | Fix |
|------|-------|-----|
| `str-wrapped` | `to_X_case(str(E))` | read `E.X`; if `E` is genuinely plain text, drop the `str()` — case functions accept any `str`, PolyString included |
| `str-bound` | `to_X_case(NAME)` where `NAME = str(E)` is bound in the same function/module scope | read `E.X` off the original name object |
| `nested` | `to_X_case(to_Y_case(E))` | the outer call alone is equivalent; a derived name is `PolyString.compose(...).X` |
| `simple-name` | `to_X_case(extract_simple_name(E))` | `E.simple.X` |

**Held at a hard zero with no exemption file.** No shape above has a legitimate instance: a case function
never needs a `str()` around its argument, and a nested call never needs its inner one.

**Why it exists.** The round trip is not merely wasteful (it recomputes the word split the name already
paid for): it hides from the next reader that the value was a name, so they treat it as text too, and the
pattern spread to several hundred sites across the language and platform packages before anything refused
it. A Semgrep rule (`redundant-case-conversion`) named the shape but ran only on demand, as a WARNING — an
advisory nobody has to read is the same as no rule.

**What it cannot see.** `to_snake_case(node.name)` — a PolyString passed straight to a case function — is
the same waste without the `str()`, but whether `.name` is a PolyString or an `Enum` member's plain-`str`
`.name` is a type fact, and no type checker runs in this repo. That shape is left to review.

**Self-test runs automatically, every invocation.** A planted module carrying one instance of every kind
and every callee spelling (canonical, `as` alias, `text.to_snake_case` attribute, function-level import)
plus a nested function must yield exactly the expected `(line, kind, function)` triples — so the scope
barrier is proven, not assumed; a clean module (reading `.snake`, casing a value that was never
`str()`-wrapped, `str()` applied *after* the case call, `PolyString.compose`) must yield zero; and an
unparseable module must refuse (exit 2) rather than report clean. A self-test failure aborts before any
real result is trusted (exit 1).

**Also enforced at the commit seam.** `git\commit-and-push.ps1` runs the same scanner over the pending
files of every dirty repo before it generates a message or stages anything, and refuses the whole run on
a hit (`-SkipPolyStringCaseCheck` overrides, loudly). This gate is the whole-workspace counterpart: it
also covers repos the current run is not committing. `-PendingOnly` is the commit-path form (scan only
what a `git add -A` would stage).

Exit code 2 is a usage error (unknown `-Repo` name, no framework repo found) or a scanned file that could
not be parsed.

Module: `datrix_scripts.gates.repo_hygiene.polystring_case_roundtrip_gate`; POSIX twin options `--repo`,
`--self-test`, `--pending-only`, `--dbg`.

## `python-lint-correctness-gate.ps1`

**The repo's proof that no package carries a pyflakes or top-level blank-line finding.** Unused imports,
undefined names, and test functions silently shadowed by a same-named redefinition (the first definition
never runs) are `ruff` rule family `F`. Two blank lines before a top-level def/class (`E302`) and after
one (`E305`) are pycodestyle rules that ruff ships only in preview, so no package's
`select = ["E", ...]` activates them. Targets are derived from disk, never listed: every workspace
`datrix*` directory holding a `pyproject.toml` contributes its `src/` and `tests/` trees when present,
and the `datrix` showcase repo contributes `scripts/`. Each tree is linted in two passes run from its
package root, so that package's own `per-file-ignores` apply: `ruff check --select F --output-format json`
on stable ruff (a preview change to an F rule never shifts the verdict), and
`ruff check --select E302,E305 --preview --output-format json`. Both selections are explicit so no
package's rule selection can hide a finding. Findings print as `package/path:line:col CODE message`.

**Held at a hard zero with no baseline.** A finding that is genuinely required (an import kept for a
documented side effect) is suppressed only by a line-level `# noqa: <code>` carrying the reason on the
same line; `RUF100` already reports a stale one. The other style families (`UP037`, `I001`, `UP031`, …)
are out of scope: they are not correctness defects and would bury the pyflakes signal. A package's root
`vulture_whitelist.py` is never linted: it is Vulture's input, a list of bare names and `_.attr` reads
that nothing binds (every line an F821 by construction); the tree scan never reaches it and the commit
path skips it. A same-named file below the root is linted like any other.

**Self-test runs automatically, every invocation.** A temporary fixture package with one planted F401 and
one F821 must report exactly those two; one with a planted E302 and E305 must report exactly those two;
the same package clean must report zero; a fixture `per-file-ignores` for the F401 must suppress it and
leave the F821. The live run additionally fails (exit 2) when any discovered package has no scanned tree
— a scan that found no trees is broken, not clean.

**Also enforced at the commit seam.** `git\commit-and-push.ps1` runs the same two passes over the pending
`.py` files of every dirty repo before it generates a message or stages anything, and refuses the whole
run on a finding. There is no skip switch. This gate is the whole-workspace counterpart.

Exit code 2 is a usage error or ruff could not run.

Module: `datrix_scripts.gates.repo_hygiene.python_lint_correctness_gate`; POSIX twin options
`--self-test`, `--dbg`.

## `import-name-existence-gate.ps1`

**The repo's proof that no `from <datrix module> import <name>` names something that does not exist.** A
half-completed rename leaves a module importing one name and defining another. At runtime that announces
itself — the first test to touch the module raises `ImportError`. Inside `if TYPE_CHECKING:` it announces
nothing, ever: the block never executes, every package still imports cleanly, and this repo runs no
standalone type-checker by policy (`CLAUDE.md`, "Running Python"), so every annotation written against
the dead name is silently meaningless. Three half-completed renames landed in one phase and all three
were found by accident. This gate looks for them on purpose.

**Resolution, three routes, in order.** (1) A module-level binding in the target module's own source, by
AST — `def`/`class`/assignment/import alias, including inside its own top-level `if`/`try`/`with` and its
own `TYPE_CHECKING` block, so this gate is never stricter than a type checker. (2) A **submodule** of the
target — `from datrix_cli.commands import lsp` imports a module, not an attribute; skipping this step is
what made a first attempt report 102 findings of which 100 were not defects. (3) A runtime attribute, by
importing the module — reached only for names routes 1 and 2 miss, covering `from x import *` re-exports
and module-level `__getattr__`. An import that raises is reported with its exception text, never treated
as resolved.

**Roots are derived from disk.** Every `datrix*` package repo contributes its `src/` and `tests/` trees;
the `datrix` showcase repo contributes `scripts/`. Relative imports are resolved, and a package's
`__init__.py` is resolved as its own package (one dot there means THIS package, not the parent). Relative
imports in `tests/`/`scripts/` trees, which have no unambiguous dotted name, are counted and reported
rather than silently dropped. `-Roots` scans only the named directories (comma-separated).

**Deliberate negative-existence assertions are excluded and counted.** An import inside
`pytest.raises(ImportError)` / `pytest.raises(ModuleNotFoundError)` or a `try/except ImportError`,
written to prove a deleted symbol is really gone, is not a defect. A `raises` naming some other exception
tolerates nothing, and the import inside it is still checked.

**The terminal state is zero.** No baseline, no ratchet, no allowlist. A name resolving by none of the
three routes is a defect in the importing module — fix the import or the definition.

**Self-test runs automatically, every invocation.** A synthetic package is built in a temp directory
carrying four dead names that MUST be reported (two under `if TYPE_CHECKING:`, one behind a
package-relative import, one inside a non-import `raises`) and five shapes that must NOT be: a submodule
import, a name re-exported only inside the target module's own `TYPE_CHECKING` block, a single-dot import
in a package `__init__.py`, the same statement in a sibling module, and an import written to fail under
`pytest.raises(ImportError)`. In-scope and TYPE_CHECKING counts are asserted too, so a walker that stops
seeing a shape fails here rather than reporting a confident clean.

Exit code 2 is no datrix `src/` tree found to resolve against.

Module: `datrix_scripts.gates.repo_hygiene.import_name_existence_gate`; POSIX twin options `--roots`,
`--self-test`.

## `check-docs-conformance.ps1`

Docs-conformance gate: extracts repo-relative path references and Python module references from the
curated architecture-doc set (each package's `docs/architecture.md` and/or `docs/architecture/` tree —
`datrix-extensions` has neither and contributes zero) and fails if any reference does not resolve to a
real file/directory/module in the tree, unless it is recorded in the committed exceptions baseline at
`scripts/config/docs-conformance-exceptions.json` (a "what was removed" migration-history claim, a "must
never exist" prohibition claim, or another confirmed-intentional non-existence). It follows the same
scan-and-baseline shape as `gates\ratchet\check-generated-file-ratchet.ps1`, except the exceptions
baseline is hand-edited and reviewed (no `-UpdateBaseline` flag — every entry needs a human-authored
reason a script cannot synthesize).

`ARCHITECTURE_DOC_FILES` is a literal, reviewable constant in the script (never a directory glob) —
"architecture docs" is a curated concept, and a new architecture doc added later is a deliberate,
reviewed one-line addition to that constant. It only checks path-reference candidates that are fully
package-qualified (start with a known package name or `D:\datrix\`) and module-reference candidates that
are fully import-qualified (start with a known Python import name) — a bare, package-relative shorthand
span with no anchor at all is never a candidate (deliberate scope boundary, not a gap).

It also checks **class member claims**: when a doc binds a class name to a workspace class (a
`from <package module> import Name` line in a code fence, or a qualified `package.module.Name` span) and
writes `Name.member` in a backtick span or a code-fence line, the class must have that member — declared
in its body (functions, nested classes, assignments, `self.x` assignments, including inside
`if TYPE_CHECKING:`), reached through re-exports, or inherited from a base (a base outside the workspace
is introspected). A class whose members cannot be enumerated (a `__getattr__`, an unresolvable base, a
module-level name that is not a class) is never failed. A name the doc imports from a workspace module
that does not define it fails as well. An intentional "before" example of removed code is a baseline
entry keyed by its `Name.member` span.

> **`ARCHITECTURE_DOC_FILES` is the one registry in the repo that does NOT self-update.** Everywhere else
> the package set is discovered from disk (`Get-DatrixDirectories`, the venv install order
> `common\venv.ps1 -ListPackages`, the metrics reports, `commit-and-push`), so a new package is picked up
> with no edit. This tuple is deliberately the exception — a curated list, reviewed by a human.
> Consequence: when a new `datrix-codegen-<lang>` package ships its own `docs/architecture.md`, that entry
> must be **added to the tuple by hand**, or the new package's architecture doc is silently never scanned
> by the gate. A package with no architecture doc yet contributes zero entries and is correctly absent —
> as `datrix-extensions` already is.

`test\shared-library-gate.ps1 -Only check_scripts_tree` separately holds every **script path** a doc
names (in any repo) to an existing file.

**Self-test runs automatically, every invocation.** A plain-Python self-test suite (`--self-test` on the
underlying `.py`; no pytest -- real `tempfile.TemporaryDirectory()` fixtures and `assert` statements)
covers `extract_path_candidates`, `extract_module_candidates`, `resolve_path_candidate` (Tier 1 + Tier 2,
including the adversarial ambiguous-Tier-2-match case, which must stay unresolved),
`resolve_module_candidate`, `load_exceptions`, and `check_against_exceptions`. This suite runs,
unconditionally, as step 1 of every invocation (self-test failure aborts before the real scan, exit 2);
`-SelfTest` runs it in isolation and skips the real scan. `-SelfTest` first runs the harness self-test,
which registers one intentionally-failing dummy check to prove the `[OK]`/`[FAIL]` harness itself is not
vacuous.

**Assertions:**
- Every single-backtick inline code span in each curated architecture doc is extracted as a path-reference or module-reference candidate per the fixed extraction rules (package/drive-prefixed for paths, import-name-prefixed dotted chains for modules); a span containing `...`, `<`/`>`, or `*` is rejected outright.
- A path candidate resolves via Tier 1 (exact path exists under the monorepo root; a trailing-slash candidate must be a directory) or Tier 2 (an unambiguous `src/`/`tests/`-relative suffix match — never attempted when the candidate already starts with `src`/`tests`, and never resolved when the suffix matches 2+ files).
- A module candidate resolves when any decreasing-length prefix of its segments after the import name matches a real `.py` file or package `__init__.py` (tolerating a trailing symbol/attribute/function name).
- A candidate unresolved by both tiers is checked against the exceptions baseline (span text -> reason); present spans never fail the gate, absent spans do.
- Every Markdown anchor link (`[text](<doc>.md#anchor)` or `[text](#anchor)`) in a curated doc names a heading that exists in the target doc, by the GitHub-flavoured slug the heading text produces (duplicates numbered); a missing target doc fails the same way. Reported with kind `anchor`, span `<target>#<anchor>`.
- Every `### Decision N:` heading in a curated doc carries a status from the closed vocabulary (`Adopted`, `Implemented`, `Stable`, `Approved — Implementation In Progress`); a `**Status:**` paragraph in the section, when present, opens with a status of the same class (`Adopted`/`Landed`/`Implemented`/`Stable` vs `Approved`); an in-progress decision must carry a `**Status:**` paragraph; and every `` `*.ps1` `` a decision section names exists somewhere under `datrix/scripts`. Reported with kind `decision`. The self-test plants each disagreement and each accepted shape.
- The `## Dependency Graph` mermaid block of `datrix/docs/architecture/architecture-overview.md` draws exactly the Datrix edges the package manifests declare: its `Id[label]` nodes map to package names, every `A --> B` reads "A's `[project] dependencies` name B" (dependent --> dependency), and its edge set must equal the union of every `datrix-*/pyproject.toml`'s declared `datrix-*` runtime dependencies (names PEP 503-normalized), in both directions -- a reversed edge fails both ways. A line of any other shape, a node with no label, or a missing block fails rather than being skipped. Reported with kind `graph`, span `dependency graph: <what differs>`.
- No prose line of an architecture doc (`ARCHITECTURE_DOC_FILES`; code fences excluded) states a numeric package or repository count: a number (digits or an English number word) directly before `packages`/`repos`/`repositories`, optionally through up to two of `installable`/`core`/`package`/`toolchain`; Markdown emphasis around the number (`**nineteen**`) does not hide it. The list lives in `.claude/docs/repo-boundaries.md`. Reported with kind `count`, span `package count: <the claim with up to five words of its line on each side>`; a count of something other than the package set is a baseline entry keyed by that span, so it excuses one sentence and not every later "two packages".
- Every tool the overview's `## Technology Stack` / `### Code Quality` lines name (`- **tool**`) appears, as a whole word, in some `datrix/scripts/**/quick-reference.md`. A missing subsection, or one naming no tool, fails. Reported with kind `tooling`.
- The self-test plants a reversed edge, a missing edge, an unreadable graph line, a "17 packages" sentence (bare, emphasized, and through two qualifiers) and an undocumented tool (each must fail) beside the accepted shapes (the exact manifest graph, a count of another noun or inside a fence, tools outside the Code Quality subsection).

Exit code 2 is a usage error, a missing exceptions baseline, a doc in `ARCHITECTURE_DOC_FILES` (or the
architecture overview the graph and tooling checks read) that no longer exists, or the automatic
self-test step failing on a normal invocation. `-Warn` reports unresolved references but exits 0.

Module: `datrix_scripts.gates.repo_hygiene.check_docs_conformance`; POSIX twin options `--warn`,
`--show-files`, `--base-dir`, `--self-test`, `--dbg`.

## `instruction-surface-gate.ps1`

Instruction-surface gate: no agent-facing document may PRESCRIBE a whole-suite run — a whole-suite
`test.ps1` form or any `affected-gate.ps1` sweep. `guard-full-suite-runs.py` blocks an agent from
EXECUTING a whole-suite run, but a skill or rule doc can still tell an agent, in prose and command
examples, to run one; nothing made that PRESCRIPTION visible until this gate. Scans
`claude-config/.claude/CLAUDE.md`, the four read-when docs under `claude-config/.claude/docs/`
(design-and-docs, harness-guards, repo-boundaries, task-orchestration), and
`claude-config/.claude/skills/**/*.md` (including `_shared/`) for every fenced code block and inline code
span, walking fence/backtick delimiters directly (a real parser, never a line regex — a fenced block's
contents are never re-scanned for inline backticks, and an inline span sharing a prose line is still
found).

**Shares its classification with the runtime guard, never re-derives it.** Every code fragment found is
handed to `_suite_invocation.py` (`claude-config/.claude/hooks/_suite_invocation.py`, loaded by path via
`importlib.util.spec_from_file_location` — the same precedent `ignored-source-gate.ps1`'s
`load_temp_dir_segment` uses to share `_repo_temp_dir_names.py` with its own hook) — the SAME module
`guard-full-suite-runs.py` imports as a sibling, so the hook that BLOCKS a whole-suite run at execution
time and the gate that COUNTS its prescription in prose can never disagree about what one looks like. A
fragment classified whole-suite (bare package, several packages, `-All`, `-Rerun`, a tier switch with
none of `-Specific`/`-Keyword`/`-Tag`, or any `affected-gate.ps1` invocation other than `-SelfTest`) is a
hit unless an HTML comment `<!-- forbidden-example -->` sits on the same line, or the line immediately
before (for a fenced block: the line before the opening fence).

A `-Tag` run and a `-ListTags` listing are never hits (targeted / runs nothing). A vacuous tail (the
fragment is just the bare word `test.ps1` or `affected-gate.ps1`, naming the tool with no argument at all
— e.g. "the `test.ps1` script") is never a hit either: a prescription to run a whole suite must name
enough to actually run. A fragment yields a tail only where it EXECUTES the runner, as
`_command_shape.invoked_scripts` reads it (the statement starts with the script, a PowerShell host
running it, or a call operator), and the tail is that statement's arguments — so a `test.ps1:529` line
citation, a `#` comment, an `echo`, a `python -c` source string or a prose line inside a fence that merely
names the runner is never a hit, exactly as the guard never refuses one.

**Self-test runs automatically, every invocation.** A plain-Python self-test suite (`--self-test` on the
underlying `.py`; no pytest — real `tempfile.TemporaryDirectory()` fixtures) plants ten fixtures and
requires each classification boundary to hold: a bare `test.ps1 {pkg}` form (1 hit), a `-Specific` form
(0 hits), a bare form immediately preceded by `<!-- forbidden-example -->` (0 hits, 1 exempted), an
`affected-gate.ps1 -Projects {pkg}` form (1 hit — a whole-suite sweep), a `-Tag` run plus an
`-All -ListTags` listing (0 hits), a five-tag run plus a cross-package `-Keyword` run (2 hits — sweeps
wearing a targeting flag), an inline code span sharing a prose line (1 hit — proves the scanner is not
fenced-block-only), a bare `test.ps1` mention with no argument at all (0 hits — a vacuous tail is not a
prescription), a `test.ps1:529`-shaped line citation (0 hits), and a whole-suite command held in a
`python -c` string, an `echo` and a `#` comment (0 hits — named, not run). This suite runs,
unconditionally, as step 1 of every invocation (self-test failure aborts before the real scan, exit 1);
`-SelfTest` runs it in isolation and skips the real scan.

**Assertions:** zero un-exempted whole-suite `test.ps1` fragments across the scanned document set.

Exit code 2 is a usage error, or `_suite_invocation.py`/`_command_shape.py` could not be loaded.

Module: `datrix_scripts.gates.repo_hygiene.instruction_surface_gate`; POSIX twin options `--self-test`,
`--dbg`.

## `check-cross-package-fixture-reads.ps1`

**No package's tests resolve a path inside another package's `tests/` directory.** AST-scans every `.py`
file under every discovered `datrix*` package's `tests/` tree and statically evaluates the pathlib
expressions test fixtures use to locate `.dtrx`/`.dcfg`/`.json` files (`Path(__file__)`, `.resolve()`,
`.parent`/`.parents[N]`, `/` joins against literals or previously-resolved names, including
`from tests.<module> import NAME` — always the same package's own `tests/` namespace). Reports two things:
(a) a resolved directory constant that points inside ANOTHER package's own `tests/` tree — the violation
itself, regardless of whether the file it names still exists there; (b) a statically-resolved fixture path
that does not exist on disk (skipping any path a test explicitly asserts is absent, e.g.
`assert not X.exists()`). This is the exact shape that turned one datrix-common fixture cleanup into a red
`datrix-codegen-typescript` suite: `COMMON_FIXTURES_DIR / "system-with-jobs.dtrx"` pointed at a file
datrix-common's own tests no longer read.

**A fixture read by one package lives in that package's own `tests/fixtures/`. A fixture read by several
packages lives in `datrix-testing` as shared package data** (`datrix_testing.shared_fixtures`), reached
through a function or constant — never a relative path into another package's `tests/` tree.

**Self-test runs automatically, every invocation.** It plants a cross-package directory constant and a
missing-fixture reference (both must be found) alongside a clean, own-package, existing-file case (must
not be found), then separately plants the real incident's exact shape (a two-step `_MONOREPO_ROOT` /
`COMMON_FIXTURES_DIR` chain, imported cross-module via `from tests.conftest import ...`, joined against
`"system-with-jobs.dtrx"`) and requires both halves caught — so the self-test stays meaningful even after
the real incident is fixed and no longer visible in the live workspace.

Module: `datrix_scripts.gates.repo_hygiene.check_cross_package_fixture_reads`; POSIX twin options
`--base-dir`, `--self-test`, `--show-files`, `--dbg`.

## `check-enum-value-literals.ps1`

**Hard-zero gate: no generator may branch on a user enum's member values.** AST-scans every
`datrix-codegen-*`, `datrix-common` and `datrix-language` `src/` tree for two shapes: a member looked up by
literal name (`.get_value("X")` / `.require_value("X")`), and a string literal tested against a collection
of member names (`"X" in value_names`). A `.dtrx` enum's members are the declaring project's vocabulary — a
generator reading one by literal turns somebody else's spelling into policy, so renaming a member silently
changes behaviour and naming an unrelated enum the same way silently triggers it. Declared contracts (see
`work { }`) reference the model instead.

**There is no exemption file, on purpose.** A legitimate need to branch on a member value is a design
defect, not an entry to record. The baseline is zero and only zero passes.

**Self-test runs automatically, every invocation.** It plants one instance of each detected shape and
requires both to be found, then requires clean source to report none — so a scanner that can only return
zero fails here rather than being believed. A run that discovers no package source also fails rather than
passing vacuously.

Module: `datrix_scripts.gates.repo_hygiene.check_enum_value_literals`; POSIX twin options `--base-dir`,
`--self-test`, `--show-files`, `--dbg`.

## `check-handler-name-dedup.ps1`

**Hard-zero gate: no `datrix-codegen-*` package may de-duplicate a handler name.** AST-scans every
`datrix-codegen-*` package's `src/` tree for the retired
`while <name> in used: <name> = f"{base}{suffix}"; suffix += 1` shape over a derived REST handler /
controller method name. Every handler name is derived ONCE, in the shared API-level derivation
(`datrix_codegen_kernel.generation.api_helpers` — `compute_rest_api_handler_names` /
`rest_api_handler_names_by_endpoint`), which refuses to hand two endpoints of one `rest_api` a single name:
it raises, naming both routes. A package-local de-duplicator does the opposite — it renames one side of the
collision (`getOrders` / `getOrders2`) while the browser client, the API test generator and every other
language target keep calling that route by the un-numbered name, so the collision is hidden rather than
resolved.

**A match needs all three parts together**, which is what keeps the gate off the retired shape's legitimate
neighbours: (1) the numeric-suffix allocation loop; (2) an **accumulating** container — named like a claim
set (`used`, `used_names`, `seen`, `taken`, `claimed`, `existing`, …) or mutated by the enclosing function
(`.add`/`.append`/`.update`/`.extend`/`|=`/item assignment) — which is what makes the rename
order-dependent and invisible to other consumers; (3) a **handler-shaped subject** — a
`handler`/`controller`/`endpoint`/`route`/`action` token in the module path, the enclosing function's name,
or an identifier the loop touches. Part 2 clears deterministic shadow avoidance against a fixed set of
other symbols (a serverless handler `def` renamed away from a service function's name); part 3 clears
local-variable, generated-test-method and temp-file name allocation, which no second emitter consumes.

**There is no exemption file, on purpose.** A REST handler name that needs local de-duplication is a name
that should have come from the shared table. The baseline is zero and only zero passes.

**Self-test runs automatically, every invocation.** It plants each retired form (a path-fold
de-duplicator, a nested-handler de-duplicator, and a nested-action de-duplicator whose function name says
"method" rather than "handler" and is caught by the module path) and requires each to be detected, then
plants each legitimate near-miss (serverless shadow avoidance, generated-test-method disambiguation,
local-variable allocation) and requires each to be reported clean — so neither a scanner that can only
return zero nor one that flags everything is believed. A run that discovers fewer than two
`datrix-codegen-*` packages with a `src/` tree, or no Python source in them, fails rather than passing
vacuously.

Module: `datrix_scripts.gates.repo_hygiene.check_handler_name_dedup`; POSIX twin options `--base-dir`,
`--self-test`, `--show-files`, `--dbg`.

## `check-observability-native-only.ps1`

Native-only observability providers conformance gate: scans every `datrix/examples/**/config/system.dcfg`
(every declared profile, not just the default) for a portable observability provider
(`prometheus`/`datadog` metrics, `jaeger`/`zipkin` tracing, `loki` logging, `grafana` visualization,
`alertmanager` alerting) paired with a cloud deployment target (`provider = aws` or `azure`) in the same
resolved profile — a pairing the native-only platform-boundary validator rejects. Uses the real
`datrix_common.config.unified_loader.load_system_config` resolution pipeline over datrix-language's disk
config document source (`parse_dcfg`) (never a hand-rolled regex scan of the DSL, which cannot follow
profile inheritance correctly). It follows the same self-test-first shape as `check-docs-conformance.ps1`.
`-ExamplesRoot` points the scan at a hand-crafted tree, e.g.
`D:\datrix\.tmp\obs-guard-check\examples`.

**Self-test runs automatically, every invocation.** A plain-Python self-test suite (`--self-test` on the
underlying `.py`; no pytest — real `tempfile.TemporaryDirectory()` fixtures and `assert` statements)
covers a deliberately-crafted cloud+portable-metrics violation (must be flagged), a clean LOCAL example
with the same portable metrics provider (must NOT be flagged — proves the guard checks the pairing, not the
provider alone), and a clean cloud example using its platform-native metrics provider (must NOT be flagged
— proves the guard doesn't reject every cloud example). This suite runs, unconditionally, as step 1 of
every invocation (self-test failure aborts before the real scan, exit 2); `-SelfTest` runs it in isolation
and skips the real scan.

**Assertions:**
- Every profile of every `examples/**/config/system.dcfg` is resolved via the real `load_system_config` pipeline and checked — not just the default profile.
- A configured portable-category provider value paired with a resolved `deployment.provider` of `aws` or `azure` is a violation; `local` is never a violation target.
- A `logging` block with `provider = None` (stdout-only) is never flagged, even on a cloud target.

Exit code 1 also covers `-SelfTest` reporting a failing check; exit 2 covers a missing examples root or the
automatic self-test step failing on a normal invocation. `-Warn` reports violations but exits 0.

Module: `datrix_scripts.gates.repo_hygiene.check_observability_native_only`; POSIX twin options `--warn`,
`--examples-root`, `--self-test`, `--show-files`, `--dbg`.

## `emitted-escape-integrity-gate.ps1`

Escaped-escape gate for **Python-emitting** templates. Jinja copies template text through verbatim, so a
doubled backslash before `n`/`t`/`r` in a `*.py.j2` template reaches the emitted Python source still
doubled — an escaped BACKSLASH rather than the escape that was meant — and the generated program builds a
string carrying two literal characters where a line break belonged. Nothing downstream notices: the
emitted Python compiles, the function writing the artifact returns the right count, and any validator that
accepts comments passes. Found in production as a gateway trusted-peer fragment whose whole body landed on
one physical line behind a leading `#`, so every directive in it was read as part of that comment and the
proxy trusted nobody — through a green smoke gate and a successful deploy. Scope is deliberately templates
that emit **Python**: a doubled backslash is ordinary and correct in shell-, TypeScript- and
regex-emitting templates. The package set is walked from disk, so a new `datrix-codegen-<lang>` package is
covered with no edit.

**Self-test runs automatically, every invocation.** The run length IS the rule — one backslash is the
correct escape, two are the defect, four are a deliberate deeper escape — so the self-test covers all three
and requires the detector to flag exactly the middle one. A detector that cannot tell them apart would
either miss the defect or flag correct code until someone exempted it away. Self-test failure aborts before
the real scan (exit 2).

**Assertions:**
- No `*.py.j2` template carries a run of exactly two backslashes before `n`, `t`, or `r`, outside the reviewed exemptions.
- Discovering zero templates is a failure, not a clean result (the scan would pass vacuously).
- Every exemption in `scripts/config/emitted-escape-exemptions.json` still matches a live line; one that matches nothing fails the gate rather than lingering.
- Every baseline entry names a file, the exact matched line, and a reason.

Exit code 2 also covers an unreadable or self-inconsistent exemptions baseline, no templates discovered,
and a template that cannot be read (never skipped: the gate names it and stops).

Module: `datrix_scripts.gates.repo_hygiene.emitted_escape_integrity_gate`; POSIX twin options `--base-dir`,
`--show-files`, `--self-test`.

## `app-probe-path-literal-gate.ps1`

Application probe-path literal gate: no platform package may hardcode a route a registered language
declares as its readiness or liveness probe. The route a traffic-routing probe consults (Compose
`healthcheck`, ECS / App Runner health check, ALB / NLB target-group health check, Front Door origin probe,
App Service health monitor) is a route the LANGUAGE's generated application mounts, declared on
`LanguageRuntimeSpec.readiness_probe_path()` / `app_service_liveness_probe_path()`; every platform reads it
from the resolved plugin. Platform packages are discovered from disk (every `datrix-*/pyproject.toml`
registering `datrix.platforms`); the declared routes come from the installed `datrix.languages` plugins;
each platform `src/` tree is scanned for Python string constants (`ast`, docstrings excluded) and quoted
`.j2` literals (comment lines excluded) equal to a declared route. Exists because a shared `"/ready"`
constant was once consumed identically by every platform while one registered language never mounted
`/ready`, so its containers were probed at a 404 on three platforms and never became healthy.

**Assertions:**
- Every literal hit is either absent or covered by a reviewed entry in `datrix/scripts/config/app-probe-path-exemptions.json` (file + exact snippet + written reason). An exemption is legitimate only for a literal that is NOT an application probe target (an infrastructure container's own probe, a gateway framework-path list); an application probe is never exempted. A stale entry whose snippet no longer matches a hit fails the gate.
- Non-vacuity self-test (every invocation): a planted platform package yields exactly its code-line hits (a docstring and a template comment carrying the same route are NOT reported), a clean planted package yields none, a workspace with fewer than two platform packages or fewer than two registered languages is refused, and the **live** scan of the language packages' own `src/` trees finds every declared route — so the matcher is proven against the real literals the languages mount, not only against fixtures.

Exit code 2 also covers too few packages/languages discovered, or a manifest/exemption file that could not
be parsed.

Module: `datrix_scripts.gates.repo_hygiene.app_probe_path_literal_gate`; POSIX twin options `--base-dir`,
`--self-test`, `--show-files`, `--dbg`.

## `template-reachability-gate.ps1`

Template reachability gate: every Jinja template a framework package ships is named by something that can
render it. Every `.j2` below a `templates/` directory of every `datrix-*/src` tree is discovered from disk;
a template counts as named when a Python string constant in any framework `src/` (`ast`, docstrings
excluded) equals its path below `templates/` or its file name, when an f-string / `+` concatenation /
`{placeholder}` constant matches it with at least one literal character left in the file-name part, when a
template statically includes, imports or extends it (`jinja2.meta`), or when a compiled DAL generator
`FileDefinition` of any registered generator target names it (definition modules imported, IR walked).
Exists because dead templates are reviewed and shipped while no generator can render them — two
cache-access templates once sat beside the live one that way.

**Assertions:**
- Every shipped template is named by one of the four mechanisms above (a literal may also name a template by its bare file stem, the way a render plan composing `{dir}/{stem}.{ext}.j2` does); a DAL generator template name that matches no template on disk is a dangling reference and fails too.
- An unnamed template that a declared contract requires to exist is listed in `datrix/scripts/config/template-reachability-exemptions.json` (template path + written reason); dead output is otherwise deleted. An entry whose template is named or gone is stale and fails the gate.
- A pattern names every variant it can spell (`f"pubsub_connection_{engine}.py.j2"` names every engine's template), so the gate proves each template is reachable by a name, not that every placeholder value is produced at runtime.
- Non-vacuity self-test (every invocation): a planted workspace with a literal-named, a pattern-named, an included, a docstring-only and an unnamed template yields exactly the docstring-only and unnamed ones; the live DAL generator walk must find template names; and the real workspace must hold templates.

Exit code 2 also covers a template that does not parse, or a missing or malformed exemptions file.

Module: `datrix_scripts.gates.repo_hygiene.template_reachability_gate`; POSIX twin options `--base-dir`,
`--self-test`, `--dbg`.

## `example-registry-gate.ps1`

Example-universe consistency **and layout** gate: every `system.dtrx` under `datrix/examples/` must appear
in >= 1 named test set of `scripts/config/test-projects.json`, or carry a reviewed entry in
`scripts/config/test-set-exclusions.json`. An unregistered example is never built by
`generate.ps1 -All`/`run-complete.ps1 -All`, which select their corpus FROM `test-projects.json`'s test
sets — this is exactly how the `config-store` and `replayable-ingestion` whole-example parked defects
(tracked in `parity-known-nongenerating.json`) went unnoticed for a full generation cycle before this gate
landed.

The gate also enforces the examples tree's layout contract, since an example's identity IS its directory
(`example_id`, its parity-baseline key and its `test-projects.json` path are all derived from the path its
`system.dtrx` sits under): no example may live inside another example, and no `.dtrx`/`.dcfg` may belong
to two examples or to none.

**Assertions:**
- Every `system.dtrx` under `datrix/examples/` has an id reachable from >= 1 `testSets` entry, or a `test-set-exclusions.json` entry.
- An exclusion naming an example with no `system.dtrx` on disk is a stale-exclusion violation.
- An example both excluded AND registered in some test set is a redundant-exclusion violation.
- An example directory inside another example directory is a nested-example violation — the host's whole-tree operations would silently absorb the guest.
- A `.dtrx`/`.dcfg` contained in more than one example directory is a shared-file violation; one contained in no example directory is an unowned-file violation (a leftover nothing can parse).
- Non-vacuity self-test (every invocation, no file I/O): synthetic ids and paths prove both pure comparators detect each of the six violation classes and report a clean state as clean.

Exit code 2 also covers zero examples on disk, or a config file that is missing, malformed or miscounted.

Module: `datrix_scripts.gates.repo_hygiene.example_registry_gate`; POSIX twin options `--dbg`,
`--self-test`.

## `example-snapshot-gate.ps1`

Committed example-snapshot gate. An example may carry `generated/<language>-<platform>/` snapshots of its
own output; nothing else compares them with the generator, so they rot (a tree for a language nobody can
generate any more, an import of a framework module that has since moved). Two checks, both derived from the
registered entry points and from `importlib`, never from a hand-written list:

- **Snapshot identity.** Every directory directly under any `datrix/examples/**/generated/` is named `<language>-<platform>` with `<language>` a registered `datrix.languages` name and `<platform>` a registered `datrix.platforms` name (parsed by matching a registered language prefix, then the remainder against the platform set, since platform names contain hyphens). For each example and each platform it carries, the snapshot languages equal the registered language set.
- **Framework references resolve.** Every dotted `datrix_*` reference in every text file of every snapshot and in every `datrix-*/src/**/*.j2` template resolves through the shared resolver (`common/lib/datrix_scripts/framework_references.py`): the longest prefix `importlib.util.find_spec` finds is imported and the remaining segments resolve as members (an attribute, or on a class a Pydantic, dataclass or annotated field). A `datrix_*` segment inside a longer dotted chain is not a reference of its own. A reference rooted at a name the same file binds with `import ... as <name>` (a Dart import prefix) is that file's own binding, not a framework module. Framework Python comments and docstrings are held by `source-comment-reference-gate.ps1`.

It does not regenerate and diff (a whole-system generation per language per run); refresh a snapshot with
`generation\refresh-example-snapshot.ps1`.

**Self-test (every invocation):** a fixture holding every registered language passes; a planted
unregistered language fails naming it; a fixture missing one registered language fails naming it; a planted
`datrix_common.migration.live_snapshot_export` fails and `datrix_rdbms_schema.live_snapshot_export` passes;
`datrix_common.utils.identifier_case.to_snake_case` passes and a missing attribute fails; a file-local import alias is
exempt only in the file that binds it.

Each violation names `file:line` and the reference, or the directory, the installed sets and the refresh
command. Exit code 2 also covers fewer than two registered languages, no snapshot on disk, or no template
reference found.

Module: `datrix_scripts.gates.repo_hygiene.example_snapshot_gate`; POSIX twin options `--dbg`,
`--self-test`.

## `source-comment-reference-gate.ps1`

**Every module a framework `src/` comment or docstring cites exists.** Imports are proven by importing; a
comment naming a module is proven by nothing, so a module that is moved, split or renamed leaves every
comment naming it pointing at code that is not there. The gate reads prose only — comment tokens and
string-literal expression statements (docstrings of every kind) in every `.py` under every `datrix-*`
package's `src/` (packages discovered from disk) — and resolves two citation shapes:

- **Dotted references.** Every `datrix_*` dotted reference resolves through the shared resolver the example-snapshot gate uses.
- **File citations** (`foo.py`, `a/b/foo.py`; a `.py.j2` template name is not a module citation). An anchored citation — at a framework repository (`datrix-codegen-x/...`, `datrix/scripts/...`), an import name (`datrix_codegen_x/...`) or an importable third-party package (`pygls/io_.py`) — must name a file that exists there. A bare or relative citation must name a `.py` file of the citing package or of a package in its runtime dependency closure (read from each `pyproject.toml`). **A module of any other package is cited by its anchored or dotted path**: a bare name is otherwise satisfied by any unrelated package that happens to own a file of that name, which is how comments in a language package kept citing an Azure `resource_mapper.py` long after Azure split it — the only `resource_mapper.py` left belonged to AWS.

A citation that resolves none of those ways still passes when it names a file the generators emit: a
`*.py.j2` template's output name, a DAL generator output path (`=> "cdk/app.py"`) declared in a package's
`.dal` generator resource or in a code string, or a code string literal whose whole value is a `*.py` path
(`"settings_loader.py"`). A longer string that only mentions a `.py` name — an error message's "Fix: edit
x.py" — names a framework module, not an output, and excuses nothing. A citation inside a URL is skipped.

**The terminal state is zero.** No baseline, no exemption file. A failing citation is rewritten to the
module's current home, to its anchored or dotted path, or to a description of the behaviour.

**Self-test (every invocation):** a planted three-package workspace (a core package and two packages
depending on it) carries every passing shape — an own module, a dependency's module, anchored repository
and import-name paths, template/DAL generator/code-string emitted names, a template name, placeholders and
globs, a URL, a resolving dotted reference, a `datrix_*` segment inside a longer chain, an instance
attribute, a model field, a resolving package-relative reference — and every failing shape: a bare name
owned only by a package outside the closure, a name owned by nobody, a name only an error message mentions,
an anchored path to a missing file, a removed dotted module, a missing member and a missing
package-relative reference. Exactly the failing lines must be reported, with the expected citation counts.

Each violation names `file:line`, the citation and the citing package's dependency closure. Exit code 2
also covers no package found, or a scan that saw no citation of either shape.

Module: `datrix_scripts.gates.repo_hygiene.source_comment_reference_gate`; POSIX twin options `--dbg`,
`--self-test`.

## `example-secret-seed-gate.ps1`

Example secret-seed gate: every example's deploy test can start its stack. A handle a service declares in
its `secrets { }` table is mounted into the container as a file, and the generated deployment script
refuses to start while that file is absent, writing nothing in its place; on a local secret profile the
generator writes the file only from the handle's `localDefault`. The corpus is deploy-tested on the `test`
profile by an unattended harness, so for every example, on that profile, every `required = true`
operator-provisioned handle must carry a `localDefault` — or no full-corpus run can ever bring the example
up. A handle the profile does not consume (a live-model API key on a profile that binds `replay`) is
dropped from that profile with `replace secrets { ... }`, never seeded with a fake value.

Resolves each example's service `.dcfg` files (kind detected by parsing, so identity/system configs are
skipped) through `datrix_common.config.unified_loader.load_service_config` on the `test` profile — the same
resolution the pipeline applies — and never parses a `.dtrx`.

**Assertions:**
- For every `system.dtrx` under `datrix/examples/` and every service-kind `.dcfg` under its `config/`, the `test`-profile secret table has no handle that is `required = true`, `provisioningAuthority = "operator"` and without `localDefault`.
- Non-vacuity self-test (every invocation, no file I/O): a synthetic table with seeded, unseeded, optional and Datrix-owned handles must report exactly the unseeded ones, and an empty table must report nothing.

Exit code 2 also covers zero examples or zero service configs on disk, or a config that fails to parse or
resolve.

Module: `datrix_scripts.gates.repo_hygiene.example_secret_seed_gate`; POSIX twin options `--dbg`,
`--self-test`.

## `example-config-load-gate.ps1`

Example config load gate: every declared profile of every example `.dcfg` loads. Every model a config
document validates into rejects unknown keys, so a key the model does not declare is an error at load time
rather than a value silently dropped. The gate loads every declared profile of every `.dcfg` under
`datrix/examples` through the real loaders (`service`, `shared`, `system`, `identity`, `app`, `strings`,
`extern`; the kind is read from the parsed declaration) and fails on any parse, resolution or validation
error.

**Assertions:**
- Every profile declared by every `.dcfg` under `datrix/examples` loads without error.
- Non-vacuity self-test (every invocation): a planted temp `.dcfg` with an unknown nested key is reported with the key named and the value not echoed, and its clean twin loads.

Exit code 2 also covers zero `.dcfg` files on disk, or a file that does not parse.

Module: `datrix_scripts.gates.repo_hygiene.example_config_load_gate`; POSIX twin options `--dbg`,
`--self-test`.

## `docs-fence-gate.ps1`

Docs fence gate: every `datrix` fence under `datrix/docs` states a fact that holds. The showcase repo hosts
no test suite, so its docs tree is checked here through the same collector, stages and comparison a
package's case runner applies to its own `docs/` (`CaseSuite(..., docs_root=...)`; the shared entry point
is `datrix_testing.cases.runner.fence_failures`): an example parses, a `context=` fragment parses in its
construct, a whole application analyzes clean or to exactly the codes its `expect=` names, and `rejected`
syntax stays rejected.

**Assertions:**
- Every fence under `datrix/docs` passes as its info string says; a refused fence (an unknown info string, a `dtrx` fence, a `datrix-grammar` fence with no `<placeholder>`, a string that looks like a raw secret) fails the gate.
- Non-vacuity self-test (every invocation): a planted fence that does not parse is reported with its file and line, and its fixed twin passes.

Module: `datrix_scripts.gates.repo_hygiene.docs_fence_gate`; POSIX twin options `--dbg`, `--self-test`.

## `no-body-walk-gate.ps1`

**A generator function walks a model body only where the allowlist says so.** Analysis records what every
body reads, calls, writes and resolves (`datrix_common.datrix_model` `effects` / `usage` / `reads` /
`resolution`); a generator reads those facts instead of walking the body again. The gate parses every
`*.py` under every `datrix-codegen-*/src` (globbed from the workspace root, so a new target repo is
covered the moment it exists) with Python `ast` and flags, by innermost enclosing function
(`<path>::<function>`, `<module>` at module level), a call of a walk function (`iter_tree`,
`iter_expressions`, `walk_expression`, `expression_children`, `find_call_nodes`, `iter_ast_walk_edges`,
`iter_body_nodes`, by bare name or as an attribute), a walk method (`.walk()`, `.child_nodes()`,
`.children()`, `.child_expressions()`, `.child_statements()`, except on the bare receivers `ast` and `os`),
or `getattr(<x>, "<walk method>")`. Recursion by `isinstance` dispatch without those calls is not flagged.
The definition is syntactic: receiver types are never inferred, so a false-positive form (a renderer's
`context.children(...)`) is listed once with its category.

The flagged set must equal `scripts\config\no_body_walk_allowlist.json` exactly — an array of
`{"site", "category", "reason"}` whose category is one of `render-traversal`, `emission-syntax`,
`emission-decision`, `literal-content`, `no-facts-boundary`. An unlisted function fails
(`UNLISTED path::function  .walk()@604`), and so does an entry whose function no longer walks (`STALE`), so
the list only shrinks when code is removed. Adding an entry needs Jon's approval; a new category is a
design change. `guard-code-standards.py` imports the same matcher and refuses an edit that adds a flagged
call to an unlisted function.

| Category | Meaning |
|---|---|
| `render-traversal` | walks to **emit** output for each child (a renderer, not a query) |
| `emission-syntax` | a local syntax question that never consults a declaration (does this block return, is this local reassigned, which names does this body declare) |
| `emission-decision` | a decision inside transpiler dispatch whose answer depends on the transpiler's own lowering |
| `literal-content` | searches literal values, not names |
| `no-facts-boundary` | reads code that analysis records no facts on: `CLIENT_DECLARATION` bodies or `UI_VOCABULARY_HOLDERS` (`datrix_semantic/bodies/inventory.py`) |

A function flagged on neither the list nor a pending deletion is new code: it is not classified alone but
put to Jon with its call forms and a proposed category. A listed entry whose function no longer exists is
removed from the list. Walks that recurse by `isinstance` dispatch without a flagged call (local
expression-shape analyses) are outside the gate, and walks in `datrix-semantic` and `datrix-common` model
code are outside it by scope: they walk bodies to produce the facts.

**Self-test runs automatically, every invocation.** An embedded source holding one call of every flagged
form (a module-level call, the attribute form of a walk function, the `getattr` form and a nested function
included) plus `ast.walk`, `os.walk`, `isinstance` recursion and a `getattr` of another name must flag
exactly the former, by unit; and the comparison must report one planted unlisted site and one planted stale
entry.

Exit code 2 = the gate cannot judge (a failed self-test, a malformed allowlist or unknown category, a
source file that does not parse or cannot be read). It runs no generation and no tests.

**Security posture.** The gate only reads files; it opens no network connection and changes nothing.

Module: `datrix_scripts.gates.repo_hygiene.no_body_walk_gate`; POSIX twin options `--self-test`, `--dbg`.
`-SelfTest` also runs the wrapper seam checks.

## `no-import-registration-gate.ps1`

**Importing a framework module registers nothing.** A registry filled as a side effect of importing a
module answers differently depending on what was imported first, so registries are handed to the run as
values: the builtin definitions are the `BUILTIN_OBJECTS` tuple plus each extension's `builtin_objects()`,
type maps are plugin declarations, and a run builds its registries from what it discovered.
`datrix_scripts.gates.repo_hygiene.no_import_registration` parses every `*.py` under every
`datrix-*/src` tree on disk (a new package is covered the moment it carries `src/`) with Python `ast` and
fails on two shapes:

- **import-time-register-call** — a call statement that runs on import (the module body, or an `if`/`for`/`while`/`try`/`with`/`match`/`class` body beneath it; never inside a function) whose callee name (`f` of `f()`, `g` of `a.b.g()`) contains `register`, case-insensitively. `X = register_capability(...)` is an assignment of a value the module keeps, not a call statement, and is not reported.
- **registration-import** — an `import` or `from … import` carrying `# noqa: F401` whose comment mentions registration (`regist…`): an import kept only for what importing it does.

The terminal state is zero: there is no baseline and no allowlist. One gate covers every package; no
package carries a test copy of the check.

**Self-test runs automatically, every invocation.** A planted `datrix-*` package under `D:\datrix\.tmp\`
carries, in its `src/`, two registration imports, five import-time register calls (module body, `if`,
`for`, `try` and `class` bodies) and four clean shapes (a re-export `noqa: F401` import, an assignment from
a register call, a call to another name, a register call inside a function); the same file under its
`tests/` must not be read. The gate must report exactly the seven planted lines.

**Output:** one line per hit, `FAIL <path>:<line>: <kind>: <detail>`, then a count of files and trees read
and the verdict line. Exit code 2 = the gate cannot judge (a failed self-test, a source file that does not
parse or is not UTF-8).

**Security posture.** The gate only reads files (and, in the self-test, writes a scratch tree under
`D:\datrix\.tmp\`); it opens no network connection and changes nothing in the repos it scans.

Module: `datrix_scripts.gates.repo_hygiene.no_import_registration`; POSIX twin options `--roots`,
`--self-test`, `--dbg`.

## `stateless-generator-gate.ps1`

**A generator holds no run state.** A generator is a function of `(Application, CodegenContext,
output_dir)`: the context is a `generate` argument, and nothing a run computes is kept on the instance, so
a second run never answers with the first run's facts.
`datrix_scripts.gates.repo_hygiene.stateless_generator` parses every `*.py` under every `datrix-*/src`
tree on disk (a new package is covered the moment it carries `src/`) with Python `ast`, builds the class
graph of every scanned module (top-level classes and classes local to a function, each base resolved
through the module's imports with re-exports followed), takes every class whose base chain reaches the
kernel's `datrix_codegen_kernel.generation.generator.Generator` together with every scanned class such a
class mixes in, and fails on two shapes:

- **generator-attribute-assigned** — inside any method of a generator class other than `__init__`, an assignment to an attribute of `self` (or `cls`): plain, augmented or annotated assignment, a `for` or `with ... as` target, tuple unpacking, `setattr(self, ...)` / `object.__setattr__(self, ...)`, or `self.__dict__[...] =`; and, in any function, an assignment to an attribute of a name typed as a generator class (a parameter or variable annotation naming one, or a `for` target iterating such a name). Writing into an attribute's own value (`self.cache[key] = ...`) is not reported.
- **generator-init-takes-context** — a parameter of a generator class's `__init__` annotated with `CodegenContext` (string annotations included).

The terminal state is zero: there is no baseline and no allowlist. It is a gate rather than a package test
because a package test may not scan other packages' sources. `-Roots` must include the kernel's `src`,
e.g. `D:/datrix/datrix-codegen-kernel/src,D:/datrix/datrix-codegen-docker/src`.

**Self-test runs automatically, every invocation.** A planted workspace under `D:\datrix\.tmp\` holds a
kernel package (`Generator`, `PlatformGenerator`, re-exported from the package `__init__`) and a target
package whose `src/` carries a `PlatformGenerator` subclass imported through the re-export, a
function-local subclass of it, a second `Generator` subclass that mixes in a plain class whose method
writes to `self` (the mixin is a generator class too: its methods run on the generator instance), and
every reported shape: a constructor parameter typed `CodegenContext` through a module alias, plain,
augmented, annotated, unpacked and `for`-target writes to `self`, `setattr`, `object.__setattr__`, a
`self.__dict__` write, a write in a nested function, a `cls` write in a class method, a `for` target over a
parameter typed `list[Generator]` (string annotation), and a parameter typed with the subclass. Its clean
shapes (writes in `__init__`, a subscript write into an attribute's value, a write to a local, a static
method's parameter, an unrelated class's `self.context`) and the same file under its `tests/` must not be
reported. The gate must find exactly six generator classes and report exactly the seventeen planted
findings.

**Output:** one line per hit, `FAIL <path>:<line>: <kind>: <detail>`, then a count of files, trees,
generator classes and findings and the verdict line. Exit code 2 = the gate cannot judge (a failed
self-test, no generator class found, a source file that does not parse or is not UTF-8).

**Security posture.** The gate only reads files (and, in the self-test, writes a scratch tree under
`D:\datrix\.tmp\`); it opens no network connection and changes nothing in the repos it scans.

Module: `datrix_scripts.gates.repo_hygiene.stateless_generator`; POSIX twin options `--roots`,
`--self-test`, `--dbg`.

## `seal-integrity-gate.ps1`

**Only the model seals or unseals a node.** A sealed `Node` refuses every attribute assignment; the flag
that marks it sealed lives in the node's `__dict__` under `_SEAL_FLAG` (`"_sealed"`), and only
`Node.seal()` and `Node.__deepcopy__` in `datrix_common/datrix_model/base.py` write it.
`datrix_scripts.gates.repo_hygiene.seal_integrity` parses every `*.py` under every `datrix-*/src` tree on
disk with Python `ast` and fails on every other write of the flag, where the key is the literal
`"_sealed"`, the name `_SEAL_FLAG` (or a name it is imported as, or a module-level name bound to
`"_sealed"`) or an attribute `<module>._SEAL_FLAG`:

- **seal-flag-dict-write** — `X.__dict__[key]` or `vars(X)[key]` assigned (plain, augmented, annotated, unpacked, a `for` or `with` target) or deleted, and `__setitem__` / `__delitem__` / `pop` / `setdefault` with the key, or `update` carrying it, called on `X.__dict__` or `vars(X)`.
- **seal-flag-attribute-write** — `X._sealed` assigned or deleted, and `setattr` / `delattr` / `__setattr__` / `__delattr__` called with the key.

A write is permitted only directly inside `seal` or `__deepcopy__` of the top-level class `Node` in a file
ending `datrix_common/datrix_model/base.py`: a function nested inside one of them, another `Node` method,
another class's `seal`, or a `Node` class in another file is reported. The terminal state is zero: there is
no baseline. The real scan must find the permitted write in `Node.seal`, or it cannot tell a clean tree
from a matcher that stopped matching. `-Roots` must include datrix-common's `src`, e.g.
`D:/datrix/datrix-common/src,D:/datrix/datrix-cli/src`.

**Self-test runs automatically, every invocation.** A planted workspace under `D:\datrix\.tmp\` holds a
model file (`datrix-common/src/datrix_common/datrix_model/base.py`) whose `Node.seal` and
`Node.__deepcopy__` each write the flag (both must be recognised as permitted) beside three reported
writes: one in a function nested inside `Node.seal`, one in a third `Node` method, one in another class's
`seal`. A target package's `src/` carries every reported shape (twenty-three lines: the key as a literal,
as `_SEAL_FLAG`, as an import alias, as `base._SEAL_FLAG` and as a module-level copy; each dict and
attribute form above) and a `Node.seal` outside the model's file; its clean shapes (a `__dict__` read,
other keys, a key held in a local, a write into an unrelated dict, an unrelated attribute) and the same
file under its `tests/` must not be reported. The gate must report exactly the twenty-seven planted
findings and the two permitted writes.

**Output:** one line per hit, `FAIL <path>:<line>: <kind>: <detail>`, then a count of files, trees,
permitted writes and findings and the verdict line. Exit code 2 = the gate cannot judge (a failed
self-test, no permitted write found in `Node.seal`, a source file that does not parse or is not UTF-8).

**Security posture.** The gate only reads files (and, in the self-test, writes a scratch tree under
`D:\datrix\.tmp\`); it opens no network connection and changes nothing in the repos it scans.

Module: `datrix_scripts.gates.repo_hygiene.seal_integrity`; POSIX twin options `--roots`, `--self-test`,
`--dbg`.

## `script-catalogue-gate.ps1`

Holds the scripts tree's documentation to what the tree holds, reading Markdown's token stream
(`markdown-it-py`) and PowerShell's own parser, never regex over prose. Three rules, each a hard zero:

1. **undocumented-script** — every `.ps1` directly in a folder that has a `quick-reference.md` is a `##`/`###` heading of it (the root `scripts\quick-reference.md` is the folder index and is exempt).
2. **undeclared-flag** — every `-Flag` written after a script's name in one inline code span or one fence line is a parameter or alias the script's `param()` block declares (PowerShell's common parameters excepted). A flag after `|`, `;` or `&&` belongs to the next command. This holds for the `README.md` beside a quick reference as much as for the quick reference.
3. **dangling-link** — every relative link in a `quick-reference.md` or `README.md` under `scripts\` resolves to a file (anchors are not checked).

A quick reference holds only how to run a script; what the script proves, how it decides and why it exists
belong in the `README.md` beside it, which the quick reference links.

Output: one line per hit, `[<rule>] <path>[:<line>]: <detail>`, then the verdict line. `-Only <prefix>`
skips the planted checks and runs the real tree.

Module: `datrix_scripts.gates.repo_hygiene.script_catalogue_gate`; POSIX twin options `--self-test`,
`--only`, `--dbg`.

## `thin-entrypoint-gate.ps1`

Holds every `.ps1` under `scripts\` (the template `common\templates\entrypoint.ps1` excepted) to a thin
wrapper whose behaviour lives in a `datrix_scripts` module, read with PowerShell's own parser. Four rules,
each a hard zero with no baseline:

1. **code-lines** — at most 40 lines carry a token other than a comment. The comment-based help is the wrapper's documentation and does not count; the `param()` block and the template's lines do.
2. **not-rendered** — the wrapper is `common\templates\entrypoint.ps1` rendered with its parameter block and module, and its twin is `common\templates\entrypoint.sh` rendered with the same module (text compared after the substitution, so a byte-order mark is a difference; line endings are the checkout's and belong to `line-ending-gate.ps1`).
3. **missing-twin** — a `.sh` twin sits beside the wrapper.
4. **parse-error** — PowerShell parses the wrapper.

Output: one line per hit, `[<rule>] <path>: <detail>`, then the verdict line. `-Only <prefix>` skips the
planted checks and runs the real tree.

Module: `datrix_scripts.gates.repo_hygiene.thin_entrypoint_gate`; POSIX twin options `--self-test`,
`--only`, `--dbg`.
