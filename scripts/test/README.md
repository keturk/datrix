# Testing Scripts

The test runner, status and failure analysis, and the gates that hold the test tooling itself. The
commands, parameters and exit codes of each script are in [quick-reference.md](quick-reference.md); this
file holds how each one works, what it records and what it proves. Cross-target and repository gates are
in [../gates/README.md](../gates/README.md).

Each script has a POSIX twin `test/<name>.sh`; its Python lives in `datrix_scripts.test.<module>` (or
`datrix_scripts.<module>` where noted).

## `test.ps1`

Runs tests for one or more Datrix projects.

**Who runs which form.** Agents run only targeted forms — `-Specific`, `-Keyword`, `-Tag` (never with
`-All`/`-Rerun`), plus `-ListTags`, which runs nothing. Every whole-suite form (a package with none of
those, several bare packages, `-All`, `-Rerun`, a tier switch) is **Jon's alone**: `guard-full-suite-runs.py`
refuses it from every agent tool call, main session included, with no override. Whole-suite modes: a bare
package (`test.ps1` + package names), a folder path, `-All`, `-Rerun` (re-run projects whose latest log
reports failures), and the tier switches `-Unit` / `-Integration` / `-E2E` / `-Fast` (excludes slow) /
`-Slow`.

**Several files in one session.** `-Specific` takes comma-separated files/node-IDs and runs them in ONE
pytest session — always batch a targeted set this way instead of one invocation per file (commas inside
parametrized IDs `[1,2]` are literal). A test runs under `-Tag` when it carries ANY named tag.

**`-ListTags`** prints every tag with its test count, and the untagged tests; it runs nothing and exits 1
while any test is untagged or a module fails to collect. It then lists each package's tags missing from the
vocabulary table in `feature-tags.md`, with where each is first applied
(`datrix_scripts.test.tag_vocabulary`, a static AST read; report only, never changes the exit code).
Enforcement happens at collection: every `test.ps1` run passes the feature-tag plugin's
`--datrix-require-tags`, which refuses a collected item carrying an unlisted tag. With `-Specific` the
listing is over the named files/directories only.

**Module.** `datrix_scripts.test.test` (in `common/lib/`), behind a wrapper rendered from
`common/templates/entrypoint.ps1`. Its POSIX twin `test\test.sh` takes the module's own flags: each
parameter as `--kebab-name` (`--specific`, `--keyword`, `--tag`, `--list-tags`, `--self-test`; `-E2E` is
`--e2-e`), with the packages positional — `bash test/test.sh datrix-common --list-tags`. The full-suite
guard reads both spellings alike. Every module behind a `test\` wrapper takes its options spelled in full:
an abbreviation (`--al` for `--all`) is a usage error (exit 2), never expanded, since the guard reads flags
by their exact spelling. Each package runs in its own `datrix_scripts.test_project` child. `-SelfTest` is
the module's self-test; it runs no package's tests.

**Failure digest.** After the summary table, every failed package whose run was saved gets a short digest
from `common/lib/datrix_scripts/run_digest.py`, written to `digest.txt` in the run directory. The console
gets one line, `Failure digest written: <path>`, never the digest itself. It lists the run's failure groups
(the `collect-failure-data.ps1` families, labelled `E1..` for errors and `F1..` for failures) with count,
pattern, source location and a re-run command. It also says what changed since the newest earlier completed
run of the package with the same `selection` — an interrupted `INCOMPLETE` run ran nothing to compare with
and is passed over (new failing tests, still failing, fixed — `classify-run-delta.ps1`'s counts; each group
is marked `[new]` or `[seen before]`). From a resident local model it adds a one-paragraph hint per group
(first 5) and, when there are several groups, one reading of which share a cause and which to fix first.
Model text is labelled with its model and is a lead to confirm, never a finding. Every prompt goes through
the customer-term filter, and nothing is sent without the corpus. Only resident models are used (no cold
load), with a 60 s request timeout. When no model answers, one `Model: no hint (...)` line says why and the
digest carries the deterministic part alone. A digest that cannot be written prints
`No failure digest for <package> ...` and never changes the exit code. The run also gains
`failure-data.json` and, when an earlier comparable run exists, `run-delta.json`. About 15 s on a
three-group run. The `digest-red-test-run.py` hook asks no model for a run that has `digest.txt`, because
the run folder already holds the digest. `-NoDigest` writes none.

**Feature tags.** Every test carries one or more feature tags (pytest `tag` marker; Node `#tag` token in a
test or `describe()` name). They are declared by `datrix_common.testing.feature_tags`, a `pytest11` plugin
every session in the venv loads; `test.ps1` runs every session with `--datrix-require-tags`, so an untagged
test fails at setup (an untagged Node test fails the run). `-Tag` fails a package in which no test carries a
named tag (a misspelling never shrinks a run silently), refuses a selection that keeps every test of a
package's whole test tree (the full suite in disguise), and cannot be combined with `-Keyword` on a Node
suite. Both refusals are decided **before any test phase starts**: a pytest package's `-Tag` run first does
one collection-only pass in a single process over the run's own targets (with its tier marker and
`-Keyword`, and the phases' `addopts` and `--datrix-require-tags`), and a refused selection exits 4 with the
plugin's message and no run directory — never discovered inside every xdist worker after each has collected
the whole tree. **That pass is the run's only whole-tree collection.** It loads
`datrix_scripts.selection_export` (`-p`,
`--datrix-selection-out=<workspace>/.tmp/test-selection/<package>-<pid>-<ns>.json`), which writes the node
ID and `serial` mark of every item the session kept after tags, `-k` and `-m` filtered; the run copies it to
`selection.json` in its run directory and writes `parallel-args.txt` (non-serial node IDs),
`serial-args.txt` (serial ones) and `selected-args.txt` (all), one per line. Every phase then runs exactly
those node IDs from an argument file (`@<file>`), with no `--datrix-tags` and no marker or keyword filter,
so workers import only the modules holding selected items and no phase deselects anything. The plugin's 25%
ceiling fires only when an invocation collects the whole test tree, so the phases, given explicit node IDs,
never re-trip it: the preflight's item list is the exact selection. The serial phase runs only when the
selection holds serial items (otherwise `index.json` records
`"Serial": "skipped (0 serial items in the selection)"`); a selection of only serial items skips the
parallel phase (`"Parallel": "skipped (0 non-serial items in the selection)"`). A selection no larger than
`os.cpu_count()` (or any `-Tag` run without xdist, or with `-Coverage`) runs in one process, without xdist,
as the single `Tests` phase writing `junit.xml`: a worker pool would give each worker at most one item. A
preflight that exits with anything but 0 or 4 (a module that fails to import during collection, an internal
error, `-Keyword` leaving nothing) **fails the run closed**: the run directory gets the preflight's output
in `full.log` and a `FAILED` `index.json` whose `runner_errors` names the exit code, no phase runs, and the
run exits with the preflight's code. A preflight that exits 0 without a readable export is a runner error
naming the file (exit 3). A tier name (`unit`, `slow`, `serial`, …) is never a tag. Rules and vocabulary:
`datrix-common/docs/contributing/test-guidelines/feature-tags.md`. A run's `index.json` records
`selection.tags`.

**Log output.** Unless `-NoSave` is used, `test.ps1` creates one timestamped log folder for each project it
runs under that project's `.test_results` directory. AI agents do not need to capture full console output;
read the final console lines to find the saved log folder, then inspect the files in that folder.

**Test temp folders.** Every pytest session `test.ps1` starts gets
`PYTEST_DEBUG_TEMPROOT=<workspace>/.tmp/pytest`, so `tmp_path` trees land in
`<workspace>/.tmp/pytest/pytest-of-<user>/pytest-<N>/` instead of the system temp folder. pytest keeps its
own numbering, its three-run retention and its per-user, owner-checked folder; nothing shared is wiped
between concurrent sessions, as `--basetemp` would do. Code that calls `tempfile` directly still uses the
system temp folder.

**Selection and suite-input stamp (`index.json` `schema_version: 2`).** Every saved run records
`selection` — `{"kind": "full"}` for a bare `test.ps1 <package>`, otherwise
`{"kind": "targeted", "specific", "keyword", "tier", "marker", "tags"}` for
`-Specific`/`-Keyword`/`-Tag`/any tier switch; a `-Tag` run adds `selected_items`, `serial_items` and
`execution` (`"single-process"` or `"parallel+serial"`). Only a full run whose every phase completed records
`inputs` (the suite-input fingerprint over the package's cone, installed set, interpreter, and observed
foreign paths and executables); a targeted run never has an `inputs` key, so it can never stand in for a
full one. A full run loads `datrix_scripts.runner_plugin` (`-p`) in every phase and also leaves
`observed-*.json` / `deselected-*.json` / `timings-*.json` / `workers-controller.json` records and a merged
`timings.json`; any other saved run except a `-Tag` run loads it in its parallel phase only and is never
stamped. **The serial phase runs only when needed:** a `-Tag` run decides from its exported selection (see
Feature tags above) and reads no deselected counts; every other run decides as follows: when every parallel
worker's `deselected-<worker>.json` says it deselected 0 items (so no collected test is `serial`), the
serial phase is skipped — `full.log` says `Phase 2: serial tests SKIPPED -- …` and `index.json` records
`"phases": {"Serial": "skipped (0 serial items)"}` with no `junit-serial.xml`. It runs on any missing
evidence (`-NoSave`, a worker the controller listed with no record, a parallel phase that did not
complete), under a marker or keyword filter (`-Unit`/`-Fast`/`-Keyword`/…; `-Specific` is not a filter),
and when workers deselected items. Workers disagreeing on the count, or an unreadable record, is a runner
error: the serial phase runs and the run is FAILED with the reason in `index.json` `runner_errors`. Each
worker's `deselected-<worker>.json` carries per-file `deselected_files` counts, and a disagreement error
names every file whose count differs and lists the package files modified since the parallel phase started:
a file saved by another session mid-run adds or removes test functions, so workers that collected before
and after it count different items. Collection itself is deterministic (a solo run agrees on every worker),
so such a FAILED run is correct and the fix is to re-run on an unchanged tree. When a full run cannot be
stamped (a phase did not complete, a session's records are missing, or a cone tree changed while it ran),
`full.log` says why and `index.json` has `selection` but no `inputs`. Field reference:
[Package-run `index.json`](#package-run-indexjson-schema-version-2).

**Never run two `test.ps1` invocations at once — batch the projects into ONE call instead.** `-Projects` is
variadic and iterates sequentially, so `test.ps1 a b c` is the supported way to cover several packages.
Before running anything, `test.ps1` runs the venv install check
(`scripts/common/venv.ps1 -EnsurePackages -SkipIfInstalled`, run in-process as
`datrix_scripts.venv.require_packages`), which takes a **workspace-wide exclusive package lock**
(`<workspace>\.venv-package.lock`, 120s acquisition timeout) shared with `generate.ps1` — it guards the
install/repair phase against concurrent writers of the one shared venv. A second concurrent invocation
therefore blocks for up to two minutes and then dies with
`Could not acquire package lock - another process may be installing packages`, having run **no** tests. The
one sanctioned concurrency is `affected-gate.ps1` (Jon's tool — agents never run it), and it does not
contend here: it runs that install check **once**, before any child, and launches every `test.ps1` child
with `DATRIX_PACKAGES_ENSURED=1`, which makes `test.ps1` skip its own check (with `DATRIX_VENV_VERBOSE=1`
it prints `Package install check skipped: the caller already ran it` instead) and makes `test_project.py`
skip its per-project dev-dependency probes (the `python -c "import <tool>"` run per declared test tool),
since the caller's check already covered every package's `[dev]` extras. `test.ps1` sets that variable only
in its children's environment, never in its own process or its caller's, so a run started in your own shell
never leaves it set for the next direct run — a direct `test.ps1` always performs its own check.

**Concurrency here buys nothing and costs a lot.** The runs serialize on the lock whatever you do, and the
loser fails outright rather than queueing. A sweep launched as N parallel invocations finishes later than
the same sweep as one invocation, and reports failures that are pure contention.

### Node suites (`datrix-vscode`)

A package is testable when it carries a `tests/` folder (pytest) **or** a `package.json` declaring a `test`
script (Node). `test.ps1` dispatches on which it has, and both write the same
`.test_results/test-results-<stamp>/` artifacts — `full.log`, JUnit XML, `index.json` — so
`status-tests.ps1`, `-Rerun`, `gate-verdict.ps1` and `affected-gate.ps1` work on either without knowing the
difference. Which files hold a package's tests and which npm script builds them are declared in a `datrix`
block in its own `package.json`.

A Node package's dependency on a framework package is **not** declared there. That edge is invisible to the
Python import scan (it is a subprocess contract, not an import), and it cannot live in a manifest that
ships inside a distributable artifact — datrix-vscode's `verify-package-contents.mjs` fails the build when
any archived file names a framework package. It is declared in the monorepo instead:
`datrix/scripts/config/cross-ecosystem-dependencies.json`, read by `affected-set.ps1` as a SOURCE edge. A
name there that resolves to no package on disk is an error, never an empty result.

Options that have no counterpart in a Node suite are reported, never silently dropped:

| Option | On a Node suite |
|--------|-----------------|
| `-Specific "serverResolution.test.ts"` | Selects test files. The source-side `.ts` name is accepted for the compiled `.js` file; naming a file that does not exist is an error, not a smaller run |
| `-Keyword <expr>` | Passed to Node's `--test-name-pattern`, which is a **regex** where pytest's `-k` is a boolean name expression. An expression that matches nothing selects zero tests and is reported as a non-pass |
| `-Fast` | Excludes slow-marked tests; a Node suite marks none, so the whole suite runs (stated on stdout). The run is still recorded as the targeted `fast` selection and is never stamped with `inputs` |
| `-Unit` / `-Integration` / `-E2E` / `-Slow` | Select a marked subset a Node suite has none of. The package is skipped with a message, exit 0 — the same convention as pytest collecting nothing for a marker |
| `-Coverage` | Collects no data; the suite runs uninstrumented (stated on stdout) |

## `run-complete.ps1`

Complete workflow: syntax check, code generation, unit tests, deployment tests. `-Language`/`-L` is
**mandatory**.

**Steps:** Step 1 (syntax checker, `scan\syntax-checker.ps1`) → Step 2 (code generation) → Step 3 (unit
tests) → Step 4 (deployment tests: spec + integration). Step 5 is deprecated (merged into Step 4);
`-Skip5` is accepted but does nothing.

**How a project's tests run.** Steps 3 and 4 run every generated project, whatever language generated it,
through the `tests/run-tests.ps1` entry point every language emits
(`datrix_codegen_kernel.generation.test_runner_entry_point`): Step 3 as `-Unit --parallel`, Step 4 as
`-Deploy --results-dir <project>/.test_results/deploy-test-<stamp>` (`--verbose` added under
`-VerboseOutput`), with the workspace venv activated for the runners. A project whose entry point declares
no `-Deploy` switch has no deploy tests and is skipped by Step 4; a project with no entry point at all
fails both steps as a generation defect.

**Module.** `datrix_scripts.test.run_complete` (the rerun selection in
`datrix_scripts.test.run_complete_rerun`); POSIX twin `test\run-complete.sh` (`--kebab-name` flags:
`--language`, `--test-set`, `--skip1` … `--skip5`, `--debug-logging`; the aliases `-L`/`-P`/`-H`/`-Dbg`
reach the module as `--language`/`--platform`/`--hosting`/`--debug-logging`). It checks the request before
any step runs: no `-Language`, or neither an example path nor `-All`/`-Domains`/`-TestSet`/`-Rerun`,
prints what is missing and exits 1; a language that is not registered exits 1; an example outside
`examples/` exits 2. `-Rerun` runs each selected project's workflow in the same process, in order, and
stops at a Ctrl-C (exit 130). `-SelfTest` checks the argument validation and the rerun selection on a
planted workspace.

**Project environments.** Steps 3 and 4 run a generated Python project's own runners
(`tests/unit_tests.py`, `tests/deploy_test.py`) in that project's own virtual environment,
`<project>\.venv`, never in the framework venv. The module starts each runner through the project's
`tests/run-tests.ps1` in the activated workspace venv and does nothing else to the environment. The emitted
`tests/_project_venv.py` is the one owner of `<project>\.venv`, however the runner is launched: it creates
it from the launching interpreter's base installation when absent, reuses it while its `pyvenv.cfg` `home`
names that installation, rebuilds it (`venv --clear`) when `home` names another or its interpreter is
missing, installs into it and runs pytest with its interpreter, so a runner started outside `run-complete`
never installs into the interpreter that launched it either. Each runner installs every service's
`requirements.txt` and `requirements-dev.txt` into it, one service at a time, before any test runs. If pip
cannot install a file, the runner prints pip's output, the file, the interpreter and pip's exit code, and
stops with a non-zero exit: the unit runner tests no service, and the deploy runner builds nothing. A
directory at `<project>\.venv` that is not a virtual environment fails the project rather than being
replaced.

**Deploy cache.** Deploy tests (Step 4) use Docker cache by default for faster builds and better network
resilience. `-FreshBuild` forces `--no-cache` for maximum validation confidence.

**LLM advisory summary.** `-LlmSummary` prints a post-run advisory summary generated by a local model
against the aggregate result indexes. The model is whichever model `common/lib/datrix_scripts/local_llm.py`
finds first on the local machines' Ollama servers, failing over to the next. All `-Llm*` and
`-LocalMachines` parameters only take effect when `-LlmSummary` is set.

## `dual-target.ps1`

Runs generation of one test set for every registered `datrix.languages` target (in name order, discovered
at run time) and compares the per-project results: a Markdown table with one column per language and a
parity column (`OK` when every language reports the same outcome, `Mismatch` otherwise, `(missing)` where a
language's newest `generate-results-*.log` does not name the project).

Module: `datrix_scripts.test.dual_target`. Each language runs `dev\generate.ps1` through the PowerShell
host, or with `-Skip4 -Skip5` the module `datrix_scripts.test.run_complete` as a child process (the complete
run: syntax check, generation and unit tests, no deployment; `-FreshBuild` then applies to the deploy
tests). `-Platform` takes any installed `datrix.platforms` plugin name, discovered at runtime, and fails
loud listing the installed platforms if unknown. Exit 1 also covers a missing project, an unregistered
platform, no registered language or no results log. `-SelfTest` checks the log parse, the newest-log
choice, the table and parity marks, the child commands and the platform refusal.

## `test-single.ps1`

Lightweight single-test runner for checkpoint-based debugging. Runs exactly what you specify with minimal
overhead. Auto-detects the project from a full test path; use `-Project` when providing relative paths or
keyword-only searches.

Module: `datrix_scripts.test.test_single`.

## `cases.ps1`

The authoring tool for declarative test cases (`datrix_testing.cases.cli`). A **case** is one row of a
package's `tests/cases/<area>.cases.yaml`: a stage run on a committed named input, one value read by an
observer through a selector, and an expectation a person wrote. The package's one runner module,
`tests/test_cases.py`, runs every row as a pytest item carrying the row's feature tags, so
`test.ps1 <pkg> -Tag <tag>` selects cases exactly as it selects tests. Rules and the case format:
`datrix-common/docs/contributing/test-guidelines/unit-test-guidelines.md` §4, "Decision facts as cases".

| Command | What it does |
|---------|--------------|
| `check` | Layout, schema (secret refusal included), registered stages and observers (an unregistered one names the packages registering it), inputs, selectors and expectation shapes, duplicate ids and facts, tags in the vocabulary, and every selector resolved on its input. Exit 1 on any problem |
| `observe` | Run the stage, print the value with its shape and parsed context. Writes nothing |
| `observe -At <file>:<line>` | What each annotation kind would observe on that fixture line: the diagnostics firing there (by variant), the code the package's `transpile` stage emits for the function declared there, the `lsp` hover and definition at the line's `$0` cursor; a kind that does not apply says why. Writes nothing |
| `new` | Append a row you wrote; refused when it breaks the schema, repeats an id or fact, does not resolve, or while the approval gate is armed for the package. Omit `-Expectation` for an `absent` case |
| `migrate` | Inventory every assertion of the named modules and write `D:\datrix\.tmp\case-proposals\<package>-modules-<hash>.proposal.json` (one disposition per record: case, drop R-dup/R-path/R-syntax, or unplaced with the reason) |
| `migrate -Annotations` | For the named modules' diagnostic-code, transpiled-expression and language-server-answer tests, propose the annotation on the fixture line that provokes each fact (`// @expect`, `// @emits`, `// @hover`, …) or, for an inline source provoking exactly one variant, a per-code fixture `tests/fixtures/diagnostics/<CODE>.<variant>.dtrx`; writes `D:\datrix\.tmp\case-proposals\<package>-annotations.proposal.json` |
| `accept` | Requires Jon's `<name>.cases.approved` in the approval-gate directory (proposal name, sha256, and every security or `not in` row id). Writes the rows, removes the replaced code by AST, lowers the package's pins. With case ids, only those rows and only their records' code |

Module: `datrix_scripts.test.cases`, which runs `datrix_testing.cases.cli`.

## `model-contracts.ps1`

The schema-derived model contract tool (`datrix_testing.model_contracts.cli`). A package whose `src/`
declares a `.dcfg` model carries one runner module, `tests/test_model_contracts.py`: one pytest item per
(model, fact) — each required field, default, bound, pattern and the unknown-key refusal, read off
`model_fields` — proven by mutating a sample the real loader fed the model while it loaded a committed
`.dcfg` fixture, plus `test_every_model_has_a_fixture_sample`, which names every model a document can reach
that no fixture does. Items carry `dcfg`, `model-contracts` and the fixture's `// @tags`, so
`test.ps1 <pkg> -Tag model-contracts` runs them. Rules:
`datrix-common/docs/contributing/test-guidelines/unit-test-guidelines.md`, "Model facts are derived".

| Command | What it does |
|---------|--------------|
| `facts <package>` | The model set, each sampled model's items and the fixture its sample came from, then `UNSAMPLED` (the fixture backlog), `CODE-BUILT` (no document can reach the model) and `REFUSED` (negative fixtures) lines. Writes nothing |
| `facts <package> <Model>` | That model's item ids and sample source |
| `inventory` | Resolve every schema-shaped test (a `pytest.raises` around one construction, or one construction and default asserts) to the model, field and fact it restates: `covered` (an item proves it), `uncovered` (no fixture sample yet), `validator` (a validator's rule, stays code), `mixed`, `not-a-model`. Writes `D:\datrix\.tmp\case-proposals\<package>.model-contracts.inventory.txt` |
| `migrate` | Write `D:\datrix\.tmp\case-proposals\<package>.model-contracts.proposal.json`: `delete` for every covered test, `stays` with the reason for every other one |
| `accept` | Requires Jon's `<proposal name>.cases.approved` (proposal name, sha256, and the `<module>::<test>` key of every security test it deletes). Re-resolves every test, refuses a deletion no current item proves, removes the tests by AST with the dead code they leave, lowers the pins |

Module: `datrix_scripts.test.model_contracts`, which runs `datrix_testing.model_contracts.cli`. Exit 1 =
refused (an unapproved or stale proposal, a capture or discovery error).

## `tables.ps1`

The table-contract tool (`datrix_testing.tables.cli`). A package that owns a table in `src/` — the builtin
registry for its language, a type map, an emit table, the file declarations of a DAL generator document —
registers a table contract for it from `tests/conftest.py` and carries one runner module,
`tests/test_tables.py`: one pytest item per row (per row × axis cell of a matrix table), named
`test_table[<table>::<row id>]`, proving the row's property through the real code path. Items carry the
contract's tags, so `test.ps1 <pkg> -Tag <table tag>` runs a table's rows. Rules:
`datrix-common/docs/contributing/test-guidelines/unit-test-guidelines.md`, "Table rows".

| Command | What it does |
|---------|--------------|
| `rows <package>` | Every registered table, its tags, tier and lookup names, and every item id. Writes nothing |
| `rows <package> <table>` | That table's item ids |
| `inventory` | Resolve every per-row hand test (a test whose whole body looks a registered table's row up and compares it) to the rows it reads: `covered` (only presence checks of rows the table yields: an item proves it), `decision` (a row's value compared with a literal: a case row or code, never deleted), `uncovered` (a row no table yields). Writes `D:\datrix\.tmp\case-proposals\<package>.tables.inventory.txt` |
| `migrate` | Write `D:\datrix\.tmp\case-proposals\<package>.tables.proposal.json`: `delete` for every covered test, `stays` with the reason for every other one |
| `accept` | Requires Jon's `<proposal name>.cases.approved` (proposal name, sha256, and the `<module>::<test>` key of every security test it deletes). Re-resolves every test, refuses a deletion no current item covers, removes the tests by AST with the dead code they leave, lowers the pins |

Module: `datrix_scripts.test.tables`, which runs `datrix_testing.tables.cli`. Exit 1 = refused (an
unapproved or stale proposal, a package with no `tests/test_tables.py`, a malformed contract).

## `retag.ps1`

Renames feature tags across every tag carrier of the package test trees, from a mapping file: pytest
`tag(...)` calls (module `pytestmark`, class, function and `pytest.param(..., marks=...)`, located with
`ast` and rewritten at the exact string literal) and fixture `// @tags` / `# @tags` header lines (`.dtrx`,
`.dcfg`, `.dseed`). How tags are curated against the vocabulary:
`datrix-common/docs/contributing/test-guidelines/feature-tags.md`.

- **Scoped rules:** a rule with `paths` applies to those files only and wins over the tag's unscoped rule. A tag that has only scoped rules must name every file that uses it, or the whole run is refused (exit 1) and nothing is written.
- **No duplicates:** when the new tag is already in the same `tag(...)` call or on the same header line, the old one is removed instead.
- **Preview first:** the default writes nothing. It lists the changed files and writes a unified diff to `D:\datrix\.tmp\retag\retag.diff`; `-Apply` writes.
- **Byte fidelity:** only the tag literal changes. Files are read and written as bytes, so each keeps its line endings, and a span is located by `ast`'s own line breaks and UTF-8 byte columns, so a multi-byte character or a form feed earlier on the line or in the file does not shift it. A renamed literal keeps its string prefix and quote delimiter.
- **Self-test:** runs first on every invocation, over planted files (rename, de-duplicate, path scope, refusal, fixture headers, planted tree, byte fidelity). `-SelfTest` also checks the wrapper seam.

Mapping: `{"retags": [{"from": "<old>", "to": "<new>", "paths": ["<workspace-relative POSIX path>", ...]}]}`
(`paths` optional).

Module: `datrix_scripts.test.retag`. Exit 1 = a refused occurrence or a bad mapping (nothing written); exit
2 = self-test failure or usage error.

## `cleanup.ps1`

Lists/deletes `.test_results` folders (containing timestamped test result directories) under each
`datrix*` package, under `.generated/` (a walk that stops at each generated project) and under `.projects/`
(any depth).

Module: `datrix_scripts.test.cleanup` (the confirmation and the empty-parent removal in
`datrix_scripts.cleanup_utils`). `-Force` asks `Are you sure? {yes/no}` and deletes nothing without a typed
`yes`; an end of input is a no. After deleting, the parents left empty below `-BaseDir` are removed. No
search follows a symbolic link or junction below `-BaseDir`, `.generated` or `.projects` (the listing shows
one as `[LINK]`), so nothing a link leads to is listed, trimmed or deleted. `-Trim` keeps the 10 newest runs
and deletes older ones. Exit 1 also covers a failed `-SelfTest`.

## `compare-tests.ps1`

Compares timestamped test runs inside one explicit `.test_results` folder. It does not scan multiple
projects.

Module: `datrix_scripts.test.compare_tests`. The positional path may also be spelled `--test-results` in the
POSIX twin.

**Comparison behavior.** `unit-tests-*` folders are compared only with unit-test runs, and `deploy-test-*`
folders only with deploy-test runs. When more than two timestamps exist, all runs are listed and the
service-level delta compares the second-newest run to the newest run; the history column shows all runs.

## `mypy.ps1`

Runs mypy type checking for one or more Datrix projects. Accepts the same flags as `test.ps1` for
command-line symmetry, but the test-selection flags (`-Coverage`, `-NoAutoInstall`, `-Unit`,
`-Integration`, `-E2E`, `-Fast`, `-Slow`, `-Keyword`) are accepted for parity and ignored by the mypy
runner, which prints a note naming each one given.

**A human-only tool, enforced.** No skill, hook, orchestrator, or other script runs it: its only caller is
`affected-gate.ps1`'s opt-in `-Mypy` switch. The agent contract forbids agents to run any standalone
type-checker (`CLAUDE.md`, "Running Python"), and that is now a harness block rather than prose —
`guard-forbidden-commands.py` refuses `mypy`/`dmypy`/`pyright`, the `python -m mypy` form, this wrapper,
its `mypy.sh` twin, the module `datrix_scripts.test.mypy_check`, and `affected-gate.ps1 -Mypy` from any
agent tool call; the wrapper's `-SelfTest` alone, which launches no type-checker, passes. A person running
it in his own terminal is not a tool call and is unaffected. For agents, the tests of the code they changed
are the gate for type correctness; this wrapper exists so a person can run a full type-check on demand.

**The cache never lands in a package repo.** mypy writes `.mypy_cache/` into its working directory, which
here is the package root, so the runner passes an explicit `--cache-dir D:\datrix\.tmp\mypy-cache\<project>`.
Left at the default, one sweep of the installable packages buried ~51,400 cache files in 15 separate git
repositories and failed `ignored-source-gate.ps1`. Run logs still go to
`<project>/.test_results/mypy-results-<timestamp>.log`, which is the sanctioned in-repo location the test
runner already owns.

A named project that is not a Datrix package with a `pyproject.toml` is an error listing the valid names;
`-All` together with names is a usage error (exit 2); an unreadable `pyproject.toml` fails that project.

Module: `datrix_scripts.test.mypy_check`; POSIX twin `test\mypy.sh` (`-E2E` is `--e2-e`).

**The `datrix` showcase repo itself is a valid explicit project name** (e.g.
`mypy.ps1 datrix -Specific "scripts/common/lib/datrix_scripts/gates/ratchet/check_generated_file_ratchet.py"`)
even though it is excluded from `-All`'s package sweep — `datrix/pyproject.toml` carries its own
`[tool.mypy]` (strict) section for its repo-level validation scripts, but the sweep takes only `datrix-*`
packages (it is not an installable toolchain package). Always pass `-Specific` for `datrix` — there is no
`src/` layout to default to.

## Status Scripts

### `status-tests.ps1`

Reports test results from latest test logs for all datrix projects. Reads structured `index.json` when
available (new directory format), falls back to regex-parsing flat log files.

Module: `datrix_scripts.status_tests` (shared with the test runner and the tooling gates).

### `status-deploy-tests.ps1`

Reports deployment test results from the `.generated/` tree. `-Language` restricts the report to
`.generated\<language>` (any language directory present in the tree); omit it to report on every language.

Module: `datrix_scripts.test.status_deploy_tests`.

### `status-unit-tests.ps1`

Reports run test results from the `.generated/` tree. `-Language` restricts the report to
`.generated\<language>` (any language directory present in the tree); omit it to report on every language.

Module: `datrix_scripts.test.status_unit_tests`.

## Failure-Analysis Scripts (agent-oriented: minimal console, details to JSON)

These parse structured test-results run directories so AI agents read compact JSON instead of raw logs.
Each prints a 1-2 line summary plus a `Details:` path; the full detail is in the JSON it writes.

### `collect-failure-data.ps1`

Builds `failure-data.json` inside a run directory: every error/failure cluster with its representative's
traceback tail embedded, `codegen_hint`/`generated_file` when present, and (package runs only) a
ready-to-run `test_command`. That command's shape follows the suite the package actually carries — a pytest
package gets a `test-single.ps1` node-ID re-run, a Node package (`datrix-vscode`, which has no
single-test runner) gets `test.ps1 <pkg> -Specific "<source .ts file>"`, and a package carrying no
recognizable suite gets no `test_command` key at all rather than an invocation that cannot run. Supports
all three index schemas: package (`structured_log_writer`), generated-project unit
(`generated_test_log_writer`), and deploy-test (`deploy_test_log_writer` — deploy adds `failed_phase`;
infra errors are keyed `phase#id` and may have `traceback_tail: null`). Runs
`datrix_scripts.collect_failure_data` as a module (shared with `run_digest`).

**Kept small without losing anything (bundle schema 2).** Clusters sharing one `(kind, pattern)` form a
**family** (`families[]`, and `family_id` on each cluster): only the family's first cluster embeds
`traceback_tail`, the others carry `traceback_tail_in_cluster: <id>` and keep their own `log_file`. An
`error_message` over 20 lines or 2000 characters is cut, marked `error_message_truncated: true`, and ends
`[message cut: ...]` — the whole message is in that entry's `log_file`. On an 18-failure datrix-common run
this took the bundle from 136 KB to 74 KB (five "drifted" clusters became one family; one 36 KB baseline
diff was cut).

**Advisory hints.** The first `-LlmHintLimit` families (default 5, errors first) get a `hint` from a local
model server found by `common/lib/datrix_scripts/local_llm.py`: the model is given the message, the
traceback and the source around the traceback's in-workspace frames, and answers with a probable defect
site, cause and first check. `hint.source` names the server and model, or says `unavailable` (no server
answered, or no customer-term corpus) or `skipped` (past the limit / `-NoLlmHints`). Every prompt line
carrying a registered customer term is withheld before it is sent (the filter `local_reading` applies), and
without the corpus no hint is requested. A hint is a hypothesis to verify in the code, never a root cause.
Adds seconds, not minutes (9 s for 5 hints on the run above).

**Schema-shape self-test.** The three writers do not spell their cluster keys identically —
`structured_log_writer` and `deploy_test_log_writer` use `failure_ids`/`representative_failure_id` inside
`failure_clusters`, while `generated_test_log_writer` builds both of its cluster lists from one
`ErrorCluster` shape and therefore spells them `error_ids`/`representative_error_id` there too. Test ids
differ the same way: a pytest id carries a lowercase dotted module prefix that maps to a source path, a
non-python id (`Class::method`) carries none, so the representative's `file` is null and the locator is its
`generated_file`. `-SelfTest` parses one minimal fixture index per shape plus a deliberate unknown-spelling
case that MUST be rejected (non-vacuity), so a writer that changes its spelling fails here rather than at
an agent's first read of a real run.

**Re-run-command shape self-test.** The same run also pins the `test_command` emitted for each suite kind
against a fixture package tree — pytest markers must yield the `test-single.ps1` form and Node markers the
`test.ps1 -Specific` form, each asserted to carry none of the other's markers, plus a suite-less package
that must yield no command at all. Handing a Node package the pytest invocation is worse than emitting
nothing: it reads as ready-to-run and cannot run.

**Output:** `{run-dir}\failure-data.json`. Exit 1 = a failing `-SelfTest` case; exit 2 = usage / input not
found / unrecognized schema.

### `extract-warnings.ps1`

Parses the pytest `warnings summary` section of a run's `full.log` into deduplicated `warnings.json` (file,
line, category, message, triggering code line, dedup count, per-category totals). Accepts a run directory,
its `index.json` or its `full.log`.

Module: `datrix_scripts.test.extract_warnings`. **Output:** `{run-dir}\warnings.json` (empty `warnings` list
when the run had no warnings section).

### `classify-run-delta.ps1`

Compares two runs of the same package and classifies the delta: `SUCCESS` (all previously-failing fixed,
none new), `PARTIAL`, `NO_CHANGE`, or `REGRESSION` (new failures). Writes `run-delta.json` (with
`now_passing` / `still_failing` / `new_failures` / cluster-level resolution lists) into the CURRENT run dir.
`-SelfTest` checks each verdict over planted runs, the refusals, and the wrapper seam.

Module: `datrix_scripts.classify_run_delta`.

### `failure-ledger.ps1`

The finish line of a multi-suite fix job, kept by test id. `-Runs` stores the job's starting `index.json`
files; `-Status` loads, per package, every `.test_results/test-results-*/index.json` at or after its earliest
starting run and replays them in time order. A test id's verdict is that of the last run that mentioned it:
failed (`FAILING`), or passed by a later run that covers its test file (a full run, or a `-Specific` run naming
the file or a directory holding it). An id no later run has covered is `NOT-RERUN`; an id that failed in a
later run and in no starting run is `NEW`. `index.json` lists failures only, so a `-Tag` or `-Keyword` run
covers nothing here. The job is finished at zero open ids. Warnings are not in `index.json`
(`extract-warnings.ps1`).

Module: `datrix_scripts.test.failure_ledger`; POSIX twin `test\failure-ledger.sh` (`--runs`, `--status`,
`--dbg`, `--self-test`).

### `gate-verdict.ps1`

Aggregates the newest run of each requested package into a GREEN/RED gate verdict — one console line per
package plus `OVERALL`. A package with no results, an in-progress/UNKNOWN result, or any failure is RED
(fail-loud; never falsely green). `-SelfTest` runs only the verdict logic over planted run directories and
reads no real run.

**Output:** `D:\datrix\.tmp\test\gate-verdict.json` (schema 2: per-package counts + capped failing-test
list). The console output is also written to the gate log under `.test-output\gates\gate-verdict\`.

Module: `datrix_scripts.test.gate_verdict`.

**CARRIED verdict kind.** Rows have a third verdict, `CARRIED`, produced only through
`evaluate_projects(carried=...)` by `affected-gate.ps1` (this CLI judges newest runs and never carries). A
CARRIED row names a recorded green **full** run that stood in for a fresh one because its suite-input
fingerprint still matches; it counts as green for `OVERALL` but is never rendered or serialized as `GREEN`.
Every row carries two fields for it: `carried` (true only on a CARRIED row) and `fingerprint` (the
fingerprint computed now that equals the run's recorded one; null otherwise). A CARRIED row's `run_dir`,
`counts` and `age_minutes` are the carried run's own. The claim is re-checked against that run's
`index.json` — `selection.kind` must be `full`, `result` `PASSED` with zero failed/errors, and
`inputs.fingerprint` equal to the claimed one; anything else is `RED` with reason `CARRY_REJECTED: …`,
never a fall-through to another run. Console line:
`datrix-extensions: CARRIED 54 passed (run test-results-20260923-204821, age 3.2m, fingerprint 3c6f31f30e7e022b)`.

## Affected Packages

### `affected-set.ps1`

Derives the reverse-dependency closure of every `datrix-*` package from actual imports (never a
hand-maintained table). Discovers packages from disk by `pyproject.toml` presence, builds the import graph
from each package's `src/`, `tests/`, and root-level `conftest.py` (the file class that hides test-time-only
edges like datrix-common's consumption of datrix-language/datrix-cli) unioned with declared
`pyproject.toml` dependencies, and computes each requested package's transitive reverse closure — the
packages whose code may consume a change. It answers "which packages might this change reach"; an agent
then confirms each by surface and runs the changed behaviour's feature tags there
(`test.ps1 <pkgs> -Tag <tag>`), never their whole suites. `affected-gate.ps1` (human-only) consumes this
module directly.

Module: `datrix_scripts.affected_set`. `-SelfTest` adds the wrapper seam checks to the suite below.

**Self-test runs automatically, every invocation.** A plain-Python self-test suite (`--self-test`; no
pytest — real `tempfile.TemporaryDirectory()` fixtures and `assert` statements) covers
`discover_packages`, the root-conftest-only import edge (must be detected when the conftest scan is
enabled, and adversarially proven ABSENT when it is disabled), BOM-prefixed source files, a
cyclic/self-referential edge (must terminate, not hang), the non-vacuity guard
(`check_closure_not_smaller_than_declared`), and unreadable/corrupt `pyproject.toml` input. This suite
runs, unconditionally, as step 1 of every invocation (self-test failure aborts before the real derivation,
exit 1); `-SelfTest` runs it in isolation and skips the real derivation.

**Assertions:**
- Package discovery is by `pyproject.toml` presence under a `datrix-*`-prefixed directory name — never a hardcoded list or count.
- An import edge from a package's root-level `conftest.py` (outside both `src/` and `tests/`) is detected exactly as an import from `src/` or `tests/` would be.
- The full (import+declared) reverse closure of every package is never a strict subset of its declared-pyproject-deps-only closure; a violation fails the run loud (exit 1), never silently.

Exit 2 covers unreadable input (corrupt/unreadable `pyproject.toml` or source file), an unknown `-Projects`
name, or no `datrix-*` packages found.

### `affected-gate.ps1`

**A human-only tool, enforced.** It runs whole package suites, and no agent — subagent or main session, in
any skill, gate, or phase — ever runs a whole suite: `guard-full-suite-runs.py` refuses every invocation
from an agent tool call except `-SelfTest` (which launches no suite), with no override. Agents verify a
change with `test.ps1 -Specific` / `-Tag` (see `test.ps1` above). Jon runs this in his own terminal, where
no hook applies.

Runs the affected set of Datrix package suites concurrently and returns one GREEN/RED verdict. The affected
set is the changed packages (`-Projects`) plus the consumers the change reaches (`-Consumers`), established
per "Which packages a change reaches" in `.claude/skills/_shared/verification-strategy.md` — importing a
changed package does not make a package affected. Unless `-All`, one of `-Consumers` / `-NoConsumers` is
required; without either the gate stops with a usage error listing the packages that import the changed
ones. Every such importer not named is printed as `Excluded (…): …` and recorded as `excluded` in
`affected-gate.json` and the completion row. The gate schedules `test.ps1 <pkg>` child processes
longest-first under a `PYTEST_XDIST_AUTO_NUM_WORKERS` budget so concurrently running children never
oversubscribe the machine, and aggregates the final verdict by reusing `gate-verdict.ps1`'s own
per-project evaluation — never reimplementing `index.json` parsing. It only SCHEDULES existing runners; it
never duplicates `test.ps1`'s or `gate-verdict.ps1`'s own logic. `-Mypy` also type-checks the changed
packages with the same budget (human-only; `guard-forbidden-commands.py` refuses this switch from an agent
tool call) and runs `-MaxConcurrent` mypy children at once, or one per logical core without it. `-Force`
starts even if a requested package's newest run looks in-progress. `-NoCarry` runs every named package even
when its recorded green run still matches (flakiness hunts, a scheduled full sweep).

**Worker allotment (proportional share).** Only the packages that did not carry are scheduled, and only
they share the cores. Each one's CPU demand `c` is its newest **full** run's `test_time_seconds` (per-test
time summed across xdist workers, roughly workers × wall — not `duration_seconds`); a run whose
`selection.kind` is not `full`, a run recording no `selection` (older runs of both kinds carry none, so one
cannot be told from a targeted subset), an unreadable run, and a full run that recorded no value are passed
over, and with no usable full run the package's `src/` line count stands in. With `n` logical cores and
`L = Σc / n` computed once over the scheduled set, a package gets `w = clamp(ceil(c / L), 2, n)` workers as
its `PYTEST_XDIST_AUTO_NUM_WORKERS` (on a machine with fewer than 2 cores, the core count). Children start
longest-first — by the newest full run's `duration_seconds`, same run selection and fallback — and the next
one starts only while the running children's allotments plus its own fit in `n` (and, under
`-MaxConcurrent`, fewer than the cap are running); `simulate_schedule` applies the identical rule.
`-MaxConcurrent` is a cap, never a divisor of the cores: `-MaxConcurrent 1` runs the packages one at a
time, each with its own allotment. `-WorkersPerChild` replaces the allotment with one uniform count; a
value above the core count is a usage error, since one child alone would exceed the budget.

**Carry (default on).** Before any child is launched, each affected package's **newest full run**
(`selection.kind == "full"`; targeted runs are skipped over, never consulted) is checked. It is **CARRIED**
— no `test.ps1` child is launched, and that run stands in — only when it is schema 2, `result` `PASSED`
with zero failed/errors, not `INCOMPLETE`, younger than the 24 h carry window (a named constant in
`suite_inputs.py`, not a flag), and its recorded `inputs.fingerprint` equals the fingerprint recomputed now
over the same components (cone trees, installed set, interpreter, and the foreign / ignored-in-cone /
executable paths that run itself observed). Every unknown **runs** the package instead: no full run, RED,
INCOMPLETE, over-age or future-dated, no `selection`/`inputs` (a run that predates stamps), a malformed
stamp or a different algorithm, a newer run whose `index.json` cannot be read, or any error while computing
a digest. The gate prints one line per package — `datrix-x: CARRIED run=<dir> fingerprint=<hex>` or
`datrix-x: running -- <reason>`, e.g. `datrix-common tree changed; foreign tree datrix/examples changed`.
The workspace's cones are derived once per invocation, and only when some package reaches the fingerprint
comparison.

**`affected-gate.json` rows** are `gate-verdict.ps1` rows (including its `CARRIED` verdict, `carried` and
`fingerprint` fields — see that section) plus two carry fields: `carry_reason` (why the package ran instead
of carrying; null on a CARRIED row; `carry disabled (-NoCarry)` under `-NoCarry`) and `diff_components`
(every fingerprint component that no longer matched, e.g. `["datrix-common tree changed"]`; empty when the
refusal came before any component was compared). A CARRIED row: `verdict: "CARRIED"`, `carried: true`,
`run_dir` (the carried run), `age_minutes`, `fingerprint`, the run's own `counts`. CARRIED counts as green
for `OVERALL`.

**One install check per gate.** After its usage checks and before the carry decision, every non-`-SelfTest`
invocation runs `scripts/common/venv.ps1 -Ensure -EnsurePackages -SkipIfInstalled` once, the same check
`test.ps1` uses (so the carry fingerprint's installed-distributions component is computed over the venv
exactly as the children will find it — the check runs even when every package then carries). Every child is
launched with `DATRIX_PACKAGES_ENSURED=1` and skips its own check. With `DATRIX_VENV_VERBOSE=1` set, the
check's `All packages are importable and up-to-date, skipping reinstall (SkipIfInstalled mode)` line
appears exactly once, before the first child, and each child prints
`Package install check skipped: the caller already ran it (DATRIX_PACKAGES_ENSURED=1)` instead (these are
console lines relayed from the child's stdout; a child's `full.log` is written by the Python runner and
never carries `test.ps1`'s own output). A failing check launches no child: the gate exits 1 with `overall`
`INSTALL_CHECK_FAILED`.

**Completion row.** Every non-`-SelfTest` invocation appends exactly one row to
`D:\datrix\.tmp\full-suite-audit.jsonl` — the same log `guard-full-suite-runs.py` appends its allow/block
decision rows to — after aggregation (or on a usage error, a failed install check, a failed self-test, or
an interrupt):
`{"ts": <int epoch seconds>, "source": "affected-gate", "changed": [...], "consumers": [...], "excluded": [...], "ran": [...], "carried": [...], "wall_seconds": {"<pkg>": <s>}, "overall": "GREEN"|"RED"|"USAGE_ERROR"|"INSTALL_CHECK_FAILED"|"SELF_TEST_FAILED"|"ABORTED"}`.
`ts` has the guard rows' type (integer epoch seconds); `source` tells the two writers apart. The gate
prints `Completion row: overall=… ran=[…] carried=[…] excluded=[…] -> <path>` as its last line.
`affected-gate.json` carries the same `excluded` list at its top level.

**Self-test runs automatically, every invocation.** A plain-Python self-test suite (`--self-test`; no
pytest — real `tempfile.TemporaryDirectory()` fixtures, real git repositories, and `assert` statements)
covers the scheduler: on a fixed table of measured per-package CPU seconds, the simulated schedule never
has more allotted workers active than cores at any instant (for 1, 2, 8, 12 and 32 cores, and it fills all
12 on the table's own machine), the allotment matches concrete expected worker counts (including the
clamps and one `L` for every package), the simulated makespan lies between the CPU lower bound `Σc / n` and
1.25 × it, and no worse than the retired fixed-slot policy (4 slots × floor(n/4) workers) on the same
table, `-WorkersPerChild` is a uniform override refused outside `1..cores`, an allotment above the core
count is refused, `-MaxConcurrent 1` runs sequentially and `-MaxConcurrent 2`/`3` bound the number of
running children; longest-first ordering and the CPU demand read the newest full run (never a newer
targeted, selection-less or unreadable run) with the LOC fallback; then same-package double-request
rejection, consumer selection (a named consumer runs, every other importer is excluded, a consumer outside
the import closure is honoured, and neither/both of `-Consumers`/`-NoConsumers` or a changed package named
as a consumer is a usage error), a child that dies without producing an `index.json` forcing RED (never a
stale GREEN), and carry: every refusal above forces a run; identical inputs carry and launch no child;
`-NoCarry` runs a carriable package; newer targeted runs (RED or GREEN) never hide an older carriable full
run; a one-byte change in each of the seven fingerprint components (a cone tree file, an ignored-in-cone
file, a foreign tree, an observed executable, the installed set, the interpreter string, the algorithm)
runs the package with exactly that component in `diff_components`; `affected-gate.json` rows for a carried
and a ran package; `gate_verdict` rejecting a carry claim the run does not support; the completion row
sharing the guard's `ts` type (read from the guard's own source) while being told apart by `source`; and
install-once: every child's environment carries `DATRIX_PACKAGES_ENSURED=1`, `test.ps1`'s one install call
sits inside the guard reading that flag (proven on the real `test.ps1`, with the guard finder shown to
reject an unguarded call), `datrix_scripts.test_project` reads the same name, the install check is called
exactly once — from `_run`, after the in-progress refusal and before carry and scheduling, never on
`-SelfTest` — and real PowerShell processes over planted `venv.ps1` wrappers show a passing check is run
with `-Ensure -EnsurePackages -SkipIfInstalled` while a wrapper that exits 1, one that throws and a missing
wrapper each raise; the real `venv.ps1` declares every switch the gate passes (read with PowerShell's
parser). This suite runs, unconditionally, as step 1 of every invocation (self-test failure aborts before
real scheduling, exit 1); `-SelfTest` runs it in isolation and writes no completion row.

**Assertions:**
- At no point do concurrently-running children's declared `PYTEST_XDIST_AUTO_NUM_WORKERS` values sum above the logical core count.
- The scheduler never launches two live children for the same package.
- A package whose newest run directory has no/INCOMPLETE `index.json` (a run in progress) is refused unless `-Force`.
- A child that exits without naming a run directory of its own is reported RED with reason `CHILD_PRODUCED_NO_RUN`, never silently defaulting to whatever stale prior result exists.
- Every other package is judged on **the run directory its child attributed to itself** — the absolute `index.json` path in the `Details:` line `test.ps1` prints under its own `[PASSED]`/`[FAILED]` block, relayed through the child's stdout and pinned through `gate_verdict.evaluate_projects(pinned_runs=...)`. The newest run directory under `.test_results` is never consulted, neither at child exit nor at verdict time: `test.ps1` holds the workspace package lock only through its install phase, so a targeted `-Specific` run from another session can land a newer directory before **or** after the child exits, and a newest-run lookup then replaces a RED whole-suite result with an unrelated GREEN subset — a 59-test targeted run once stood in for a 5,950-test RED suite this way (the gate printed `OVERALL: GREEN` with exit 0), and later a 7-test targeted run landed mid-suite and stood in for a child that had exited 1 with two failures. A pinned run with no results file is RED with reason `PINNED_RUN_HAS_NO_RESULTS`; it never falls through to the newest run.
- A CARRIED package's `test.ps1` child is never launched (the decision is made before scheduling, not after), and its row is pinned to exactly the full run whose fingerprint matched.

Exit 1 also covers a failed install check or `-SelfTest` reporting a failing check. Exit 2 covers bad
`-MaxConcurrent`/`-WorkersPerChild`, an unknown or duplicate package name, both `-Projects` and `-All`
given, neither or both of `-Consumers`/`-NoConsumers` given without `-All`, either given with `-All`, and a
changed package named in `-Consumers`. The console output is also written to the gate log under
`.test-output\gates\affected\`.

Module: `datrix_scripts.test.affected_gate`; POSIX twin options `--projects`, `--consumers`,
`--no-consumers`, `--all`, `--max-concurrent`, `--workers-per-child`, `--mypy`, `--force`, `--no-carry`,
`--output`, `--self-test`, `--dbg`, classified by `guard-full-suite-runs.py` exactly as the wrapper.
`-SelfTest` adds the wrapper seam checks to the suite above.

## Test-Tooling Gates

Plain-Python gates over the test tooling and the scripts tree itself. Repo-level validation **scripts**, not
pytest suites (the datrix showcase repo hosts none).

### `shared-library-gate.ps1`

Behaviour checks for the shared scripts package (`common/lib/datrix_scripts/`) and the layout of the
scripts tree, as plain-Python checks (no pytest, no mocks/fakes, real `tempfile.TemporaryDirectory()`
fixtures). They cover:

- the structured-output writers (`structured_log_writer`, `generated_test_log_writer`, `deploy_test_log_writer`, `aggregate_test_writer`, `deploy_test_aggregate_writer`): JUnit XML / Jest JSON parsing and clustering by normalized error pattern, source-location fallback chains (project frame → test frame → conftest-as-test → stdlib-only/no-traceback → `unknown:0`), cross-project cluster correlation (representative-project count/alphabetical tie-breaking; suite-failure clusters as their own cluster type), deploy-test phase detection from human-readable and structured log markers (a Docker-unavailable-with-no-markers or fully empty deploy dir resolves to FAILED at docker-build with every phase SKIPPED, never PASSED; a lifecycle failure's message is the failed command's captured output), transient-vs-logic failure classification, `failures.json` read as the envelope the generated runners write, and per-service counts from each runner's own suite totals
- `codegen_hint_mapper` path mapping; `logging_utils`' log-content and cleanup functions (directory-claiming is covered more rigorously by `test-specific-selection-gate.ps1`)
- the test runner (`test_runner`, `selection_export`, `node_test_runner`, `suite_stamp`, `suite_inputs`): the `-Tag` pre-flight refusing an unknown or whole-tree tag selection before any phase, the selection export writing exactly the tagged items of a planted tree (with their `serial` marks, and changing nothing the session selects), a planted `-Tag` run splitting its selection into `parallel-args.txt` / `serial-args.txt`, skipping the serial phase when the serial file is empty, deselecting nothing, and running a selection no larger than the CPU count in one process, a preflight collection error failing the run closed with no phase run, the parallel phase's `-n auto --dist loadgroup` distribution (the only xdist mode that honours `xdist_group`), the selection classifier, the suite-input stamp over real git repositories, the serial-phase decision over real record files, and each stamp-path module importing first in a fresh interpreter (after proving on a planted cycle that the probe sees an order-dependent import cycle)
- `local_llm` (discovery, candidate order, request shapes, readiness, failover, a residency no request shortens, the no-server outcome) against real HTTP servers on loopback, and `llm_code_fix` (code-answer parsing; a ruff verification that cannot run fails closed)
- **the scripts tree** (`-Only check_scripts_tree`): no retired central `library` folder; every Python file in `<folder>/lib/`, `gates/<family>/lib/` or the shared package; no flat `lib/` module named like a stdlib or installed module (it would shadow it from `sys.path[0]`); every import resolvable (a shared module as `datrix_scripts.<name>`, a flat `lib/` file's siblings by bare name, never a bare sibling import from inside the shared package, which runs as `-m`); every third-party distribution an import reaches declared by a manifest the shared venv installs (a `datrix-*` package's dependencies or `[dev]` extra, or the `scripts` dependency group of `datrix/pyproject.toml`), so a tool installed by hand or pulled in by another tool's dependency is refused; no `except ImportError` around an import of such a declared distribution that carries on (it must raise, exit or return a nonzero status), since a missing declared tool means a broken venv, never a reason to measure less; every such refusal worded by `datrix_scripts.venv.missing_declared_tool`, which names the declaring manifest and the venv repair (never `pip install <tool>`, which patches one interpreter by hand); a declared tool run as a subprocess is held the same way: no text a script prints, writes, logs, raises or exits with advises `pip install` (any other repair is worded by `datrix_scripts.venv.venv_repair`), and no `subprocess` argv launches a declared distribution by its console-script name, which runs whatever copy PATH finds first (it runs as `sys.executable -m <module>`, refused up front with `missing_declared_tool` when `importlib.util.find_spec` finds no module); no `except ImportError` around an import of stdlib modules only (`requires-python` guarantees them: a newer module is chosen by `sys.version_info`, a platform-only one by `sys.platform`); every script a wrapper runs (`Join-Path $scriptDir|$commonDir "…"`, `-m datrix_scripts.<module>`) present; and every script path a doc, skill, hook, config or package file in any framework repo names present. Each check first proves on a planted fixture that it reports the defect it exists for, and the wrapper and reference scans also require a floor of matches, so a matcher that stopped matching fails rather than reporting clean.
- **the scripts-tree contracts**: `gate_harness` and `count_ratchet` behaviour; the one-home censuses (harness ownership, runner adoption, root resolvers, package discovery, `sys.path`, identical bodies, gate self-tests; see [../common/README.md](../common/README.md#one-home-per-fact)) and the unrolled-append census (no wrapper grows with `+=` a variable assigned from a bare `if`, `switch`, loop or `try` statement, which unrolls a one-element branch to a string), each proven on a planted copy and zero on the real tree; every shared module importing in a fresh interpreter; every hook-imported module exercised by a gate; `run_complete`'s project discovery by the emitted `tests/run-tests.ps1` (a `-Deploy` parameter selects deploy tests), and its running of every planted project through that entry point alone (the switch, the forwarded arguments, the project-root working directory, the activated workspace venv, a failing runner failing the project, a missing entry point failing rather than skipping); the gate verdict line `Invoke-DatrixPythonScript -Gate` prints, and the one a Python gate module prints in gate mode (`datrix_scripts.gate_log`, a crash included), being the line the red-run digest hook parses; and the held-clean modules (the `import_boundaries` scanner package, `run_complete.py`, and the `checklist.py` and `guard-predeploy-analysis.py` hooks) keeping every function at or under cognitive complexity 15, after proving the measurement reports a planted function over the limit.
- **`run_complete`** (`-Only check_run_complete`): the console parser over every test-summary format a runner prints, the step summary log, `run_command`'s exit and output in each output mode, the structured index of every service a run reported, steps 3 and 4 over planted generated projects (no container is started), and the workflow's step skipping and usage error.

`-HarnessSelfTest` proves the harness detects a forced failure (reports the planted `[FAIL]`, exits 0 when
it is caught). `-SelfTest` runs the harness self-test, each scripts-tree census over its planted copy, and
the wrapper seam checks. Exit 2 covers an `-Only` prefix naming no check.

Module: `datrix_scripts.test.shared_library_gate` (its checks also in
`datrix_scripts.test.scripts_contract_checks`, `scripts_tree_census` and `run_complete_checks`).

### `runner-plugin-gate.ps1`

Behaviour checks for the test runner's pytest plugin (`datrix_scripts.runner_plugin`). Every check spawns a
real, separate pytest process (`python -m pytest -p datrix_scripts.runner_plugin ...`) against a temporary
fixture suite and inspects the record files it writes: records never leak file contents, environment values
or CLI arguments; they hold exactly the observed/deselected/timings facts the session produced, with paths
confined to the workspace and transient paths excluded; a missing or malformed required environment
variable is a usage error that names it and leaves no record; records are named for their worker (`main`,
or the real `PYTEST_XDIST_WORKER` id under a distributed `-n` run, with the controller's
`observed-controller.json` / `workers-controller.json` naming every worker); an existing record file is
never overwritten. `-SelfTest` runs the harness self-test, then the wrapper seam checks (spawns no pytest).

Module: `datrix_scripts.test.runner_plugin_gate`.

### `test-tooling-parsing-gate.ps1`

Plain-Python checks (no pytest, no mocks/fakes) of how the test tooling reads run results:
`datrix_scripts.test.compare_tests`' `find_runs`/`build_service_comparisons`/`parse_unit_run`
(direct-child-only `unit-tests-*`/`deploy-test-*` run discovery excluding nested/archived dirs, service
change classification e.g. REGRESSED with OK/FAIL history, the flat-log fallback parser for
`unit-tests-summary.log`, and unit-vs-deploy runs discovered and compared as separate populations),
`datrix_scripts.status_tests`' `TestResult`/`_format_result_row`/`_read_index_json`/
`find_latest_log_file`/`parse_pytest_summary`/`parse_timestamp_from_log_file` (structured `index.json`
parsing including the INCOMPLETE-falls-back-to-`full.log` signal, `index.json`-preferred-over-`full.log`
discovery, directory-name timestamp parsing, and the in-progress xdist `[ NN%]` progress-percent extraction
case), `run_complete.py`'s summary-line statistics and generated-project metadata derivation, the
structured-output writers, and the Node test runner.

Module: `datrix_scripts.test.test_tooling_parsing_gate` (the `index.json` post-processing it checks is
`datrix_scripts.test.post_process_test_results`).

**Assertions:** several checks are inherently adversarial (nested/archived run dirs excluded from
discovery, corrupt JSON → `None`, INCOMPLETE result → `None`/fallback, missing `counts` → `None`), which
already demonstrates discriminating power; `-HarnessSelfTest` additionally proves the pass/fail harness
itself is not vacuous by registering one deliberately-failing dummy check and confirming it is reported
`[FAIL]` with a nonzero exit.

### `test-specific-selection-gate.ps1`

**The repo's proof that `test.ps1 <package> -Specific <file>` really runs THAT file.** A `-Specific` run
that prints `[PASSED]` while its own `index.json` / JUnit XML describe a **different** file's tests is a
silent false green — the caller "proves" a fix that never ran. That was a real, observed defect:
`TeeLogger` named its run directory `test-results-<YYYYMMDD-HHMMSS>` (second granularity) and created it
with `mkdir(exist_ok=True)`, so two `test.ps1` invocations against one package that started in the same
second **shared one run directory** and overwrote each other's `junit-*.xml` and `index.json` — each still
printing its own correct exit code.

`-Package` defaults to `datrix-codegen-python`; `-FileA` / `-FileB` are package-relative test files and must
be two *different* files (the default pair is the one from the original report). The default run takes
about 2 minutes. `-SelfTest` runs only the comparator's non-vacuity step over planted run directories and
the wrapper seam checks, and runs no test.

Module: `datrix_scripts.test.test_specific_selection_gate`.

**Assertions (4 steps):**
- **Non-vacuity (runs first).** The comparator is fed a deliberately **wrong-file** run directory — a synthetic JUnit XML naming another file's tests — and must reject it; it is also fed a correct run and a zero-testcase run, which it must accept and reject respectively. A comparator that cannot detect the forced mismatch fails the gate before any real result is trusted.
- **Positive.** A real `-Specific <FileA>` run's own artifacts (the run directory the runner *printed* — never the newest directory on disk) name tests from `FileA` and nothing else.
- **Run-directory exclusivity (deterministic).** `LogConfig.timestamp_format` is pinned to a literal so every racer computes the **same** preferred directory name — a guaranteed collision, not a hoped-for one. 8 sequential racers prove the name is never reused; 8 concurrent racers prove the claim is atomic. This is the root-cause invariant and it fails 8/8 against the old `mkdir(exist_ok=True)`.
- **Concurrency (end-to-end).** Two concurrent `-Specific` runs against the same package but different files must land in distinct run directories, each naming only its own file.

**The gate judges SELECTION, not test health:** a `-Specific` run of a file whose tests fail still passes
the gate, as long as the file that ran is the file that was asked for.

Exit 1 = wrong-file selection, shared run directory, or a vacuous comparator; exit 2 = `test.ps1` or the
named test files not found.

### `run-log-exclusivity-gate.ps1`

**The repo's proof that two concurrent runs never share one log file.** Same defect class as the gate
above, one surface over: `generate.ps1` named its log `generate-results-<YYYYMMDD-HHMMSS>-<language>.log`
and wrote the header with a truncating write, so two runs started together **for two different config
profiles** computed one name — the second truncated the first's log and both appended into it, each
pointing its caller at a log describing the other run's generation. Adding the profile as a third segment
would only move the collision to two runs of one profile, exactly as adding the language segment left the
profile case open, so uniqueness comes from *claiming* the name. Two claimers exist and the gate holds
both: `common/DatrixRunLog.psm1` (`FileMode.CreateNew`; the PowerShell gate mode) and its Python twin
`datrix_scripts.run_log` (`O_CREAT|O_EXCL`; `generate.ps1` and the Python gate mode), which must compose the
same names. The PowerShell claimer runs in real `powershell` processes (Windows PowerShell 5.1 suffices:
the concurrent racers are separate processes released together), the Python one in threads.

`-Racers` defaults to 8 (range 2–64) and widens the forced collision. `-SelfTest` runs only the gate's
non-vacuity proof over planted inputs, and the wrapper seam checks.

Module: `datrix_scripts.test.run_log_exclusivity_gate`.

**Assertions (5 steps):**
- **Non-vacuity (runs first).** The distinct-count comparator is fed names composed the way the defect composed them (one pinned timestamp, one label set) and must see **1** name; fed genuinely different label sets it must see all of them. A comparator that cannot see the forced collision fails the gate before any real result is trusted. The two claimers compose the same name for the same labels, hostile labels included.
- **Sequential exclusivity.** N claims on a **pinned** base name yield N distinct files that all exist — a name is never reused — through each claimer.
- **Concurrent exclusivity.** The same N claims made simultaneously yield N distinct files — the claim is atomic — through each claimer. This is the step that fails against any name-only scheme.
- **Label containment.** A label carrying `..`, a separator, a drive letter, or a wildcard cannot steer the log out of its results directory.
- **Wiring.** The **syntax tree** of `datrix_scripts.dev.generate`, the module behind `generate.ps1`, must call `claim_run_log_file` and must build no `generate-results-…` name inline (no string literal or f-string holding `generate-results-`; docstrings do not count), read through Python's `ast`, whose matcher is first proven on a planted module that does both. Without this the gate would prove a library nobody calls.

Exit 1 = a shared or reused log name, an escaped label, an unwired generate module, or a vacuous
comparator; exit 2 = `-Racers` outside 2–64, or `common/DatrixRunLog.psm1` or
`common/lib/datrix_scripts/dev/generate.py` not found.

### `toolchain-free-suites-gate.ps1`

**The repo's proof that no framework test suite compiles or executes generated output.** A
`datrix-*/tests/` suite exists to prove that DATRIX FUNCTIONALITY works — that the generator emits the
right thing. Whether the emitted output then compiles and runs in its target language belongs to the
generated tier: the generated project's own unit tests, and the deploy tests.

**Why it is a gate and not a convention:** a framework suite that shells out to a language toolchain has to
install one, so its result stops depending only on the code under test. That was real, not theoretical — a
cold Maven Central jar fetch with no timeout wedged one package's suite at 99% for an hour with no error
text, and the same suite runs in under a minute with the compile legs gone.

`-Suites` takes comma-separated `tests/` directories (each must be a directory). `-Shapes` takes kinds
(`toolchain-subprocess`, `in-process-execution`, `suite-in-suite-pytest`, `suite-in-suite-script`,
`unparseable`); for example `-Shapes suite-in-suite-pytest,suite-in-suite-script` enforces only the two
suite-in-suite shapes at hard zero, independent of the pre-existing `in-process-execution` /
`toolchain-subprocess` counts.

Module: `datrix_scripts.test.toolchain_free_suites`.

**Fails on:**
- A toolchain subprocess: `javac`, `java`, `mvn`/`mvnw`, `gradle`, `dotnet`, `tsc`/`tsx`, `npm`/`npx`, `node`, `docker`, `az`, `aws`, `gcloud`, `kubectl`, `terraform`, `bicep` — whether named as a literal or resolved through a helper.
- In-process execution of generated source: `exec(compile(...))`, `runpy.run_path`/`run_module`, `importlib`'s `spec_from_file_location`/`exec_module`.
- **`suite-in-suite-pytest`** — a `subprocess` call spawning a nested pytest session against a repo test path: `pytest`/`py.test` as argv[0], or the `[sys.executable, "-m", "pytest", ...]` module form.
- **`suite-in-suite-script`** — a `subprocess` call naming any script under `datrix/scripts/` (directly, or via `powershell -File`), whether the path is one joined literal or assembled from separate `Path(...) / "datrix" / "scripts" / ... / "x.ps1"` segments (still Call-node-local — no cross-statement variable tracing).

**Never fails on:**
- Linters over generated TEXT (`ruff`, `black`, `isort`, `mypy`) — reading is not executing.
- Subprocess runs of datrix itself (`sys.executable -m datrix_cli`, the import-boundary probes) — that is framework functionality, not generated output.
- Loading a sibling `test_*.py` for a shared harness — that is this suite's own code.
- A `pytester`-based synthetic suite (a test function taking a `pytester` fixture parameter, or a direct `pytester.runpytest*(...)` attribute call) — pytest's own plugin, launching a nested run against a SYNTHETIC tree in a tmp dir, never against this repo's own production tests. E.g. `datrix-common/tests/unit/testing/test_feature_tags.py`'s `runpytest_inprocess(...)` on a `pytester` tree.

**No baseline or exemption file for either new shape** — unlike the slow-test ratchet, both
`suite-in-suite-pytest` and `suite-in-suite-script` are hard zero; `-Shapes` scopes which kinds a run
enforces, it does not exempt individual sites.

**Assertions:** the non-vacuity self-test runs before every real scan (a planted `javac` call, a planted
`exec(compile(...))`, a planted nested-pytest subprocess, and a planted repo-script subprocess must all be
caught; an allowed `ruff` call, an allowed `sys.executable -m datrix_cli`, a `pytester`-fixture test, and a
`pytester.runpytest(...)` call must all pass), so a green result can never mean the detector was broken.

Exit 2 = a `-Suites` entry that is not a directory, or a `-Shapes` kind that does not exist — never a
narrower scan that passes.

## Structured Test Output

### Package-run `index.json` (schema version 2)

A package run's `index.json` carries `schema_version: 2`. Version 2 adds two fields; a version-1 file
predates both, and a reader treats it as a run whose selection is unknown.

- **`selection`** (every saved run) — what the run selected, recorded rather than inferred from a log. `{"kind": "full"}` for a bare `test.ps1 <package>`; otherwise `{"kind": "targeted", "specific": [...] | null, "keyword": str | null, "tier": str | null, "marker": str | null, "tags": [...] | null}`. Any of `-Specific`, `-Keyword`, `-Tag`, `-Unit`, `-Integration`, `-E2E`, `-Fast` or `-Slow` makes a run targeted — including `-Fast` on a Node suite, which has no markers and so runs whole. A pytest `-Tag` run also records what it ran from its exported selection: `selected_items` (the count), `serial_items` (the count carrying `serial`) and `execution` (`"single-process"` when the selection held no more items than CPUs or no worker pool was available, `"parallel+serial"` otherwise). An INCOMPLETE run records its selection too, and so does a run the runner refused before any phase (a failed `-Tag` preflight), whose `result` is `FAILED` with the reason under `runner_errors`.
- **`inputs`** (a full run only, and only when every phase completed) — the suite-input stamp: `{"algorithm": ..., "fingerprint": <blake2b hex>, "components": {...}}`, where `components` holds `trees` (one git-state digest per package in the run's cone — the package plus everything its suite reaches, cross-ecosystem edges included), `installed` (the installed Python distributions, plus — for every cone package carrying a `package.json` — its installed Node dependency state: npm's hidden lockfile `node_modules/.package-lock.json`, digested as `absent` when missing, and its own `package-lock.json` when git does not track it), `interpreter`, `foreign` (observed paths outside the cone), `in_cone_ignored` (observed cone paths git does not track) and `executables` (every executable started, content-digested; a Windows App Execution Alias such as `%LOCALAPPDATA%\Microsoft\WindowsApps\bash.exe`, which has no readable content, is digested by its reparse data — the package family, app id and versioned target path it launches — and an alias whose reparse data is unreadable or malformed refuses the stamp). A directory is a repository only when git itself confirms it as a work-tree top level; a path under a `.git` git rejects is digested as a path in no repository. A bytecode cache read — in `__pycache__` or under `PYTHONPYCACHEPREFIX` — is recorded as the source it caches, never as the cache. A targeted run never has an `inputs` key: its inputs are not the package's full suite, so a stamp would let a narrow run stand in for a full one. A full run is written **without** `inputs` — never with an empty or partial one — when a phase did not complete (its process could not start, or pytest exited interrupted, with an internal error or with a usage error), when any session's records are missing or unaccounted for, or when a cone tree or the installed set changed while the suite ran; `full.log` states the reason.

A full pytest run loads `test.runner_plugin` with `-p` in every phase; any other saved run except a `-Tag`
run loads it in its parallel phase only, for the serial-phase decision below, and is never stamped. A
`-Tag` run never loads it: its serial-phase decision reads the exported selection. The plugin writes its
records into the run directory:

```
    observed-<worker>.json      # paths opened/listed/loaded and executables started
    deselected-<worker>.json    # how many collected items the session deselected, in total and per test file
    timings-<worker>.json       # call-phase durations and module/package/session fixture setups
    workers-controller.json     # the xdist controller's list of the workers it ran
    timings.json                # the runner's merge of every timings-<worker>.json, each entry tagged "worker"
```

`<worker>` is the xdist worker id (`gw0`, `gw1`, ...) in the parallel phase, `main` in a phase that runs in
one process, and `controller` for the xdist controller, which writes only `observed-controller.json` and
`workers-controller.json`. The runner merges the records only when the set is exactly the one the phases
must have left — every listed worker's three records, the controller's two, and `main`'s three for a
single-process phase. A Node run has no records: its stamp's observed inputs are the `node` (and, when a
build ran, `npm`) executables the runner itself launched.

**The serial phase runs only when it has something to run.** The parallel phase selects `not serial`, so
each worker's `deselected-<worker>.json` counts its serial-marked items. When every worker the controller
lists recorded 0, no collected test is serial: the serial phase is skipped — no second collection —
`full.log` says `Phase 2: serial tests SKIPPED -- …`, there is no `junit-serial.xml`, and `index.json`
records `"phases": {"Parallel": {"status": 1}, "Serial": "skipped (0 serial items)"}`. Everything else runs
it: no records (`-NoSave`), a listed worker with no record, a parallel phase that did not complete, a
marker or keyword filter (`-Unit`, `-Fast`, `-Keyword`, …, whose own deselections hide whether serial items
exist — `-Specific` narrows collection and is not such a filter), or any worker that deselected items.
Workers disagreeing on the count, an unreadable record, or a record the controller did not list is a runner
error: the serial phase still runs, the run exits non-zero, and `index.json` is `FAILED` with the reason
under `runner_errors`. For disagreeing counts the reason names each test file whose per-file deselected
count differs and which workers saw which count, and lists the package files modified since the parallel
phase started: workers that start at different moments collect different trees when a test file is added
to, removed from or edited in the package mid-run.

### Generated-project `index.json` (per project)

```json
{
  "schema_version": 1,
  "project": "typescript/docker/03-domains/ecommerce",
  "project_path": "D:\\datrix\\.generated\\typescript\\docker\\03-domains\\ecommerce",
  "language": "typescript",
  "platform": "docker",
  "example": "03-domains/ecommerce",
  "dtrx_source": "datrix/examples/03-domains/ecommerce/system.dtrx",
  "timestamp": "2026-05-03T21:04:22",
  "duration_seconds": 12.3,
  "result": "FAILED",
  "counts": {"passed": 45, "failed": 0, "errors": 40, "skipped": 0, "suite_failures": 0},
  "services": [
    {"name": "ecommerce_user_service", "result": "FAILED",
     "counts": {"passed": 0, "failed": 0, "errors": 9, "skipped": 0, "suite_failures": 0},
     "log_file": "services/ecommerce_user_service/service.log"}
  ],
  "failures": [],
  "errors": [
    {"id": 1, "service": "ecommerce_user_service",
     "test_id": "tests/integration/repositories/test_user_repository.py",
     "error_type": "ImportError",
     "error_message": "cannot import name '_email_send_ses' from '..._email_helpers'",
     "import_chain": ["test_user_repository.py -> user_service", "user_service.py -> _email_send_ses"],
     "generated_file": "ecommerce_user_service/src/.../integrations/_email_helpers.py",
     "log_file": "errors/001-ecommerce_user_service-collection-test_user_repository.txt"}
  ],
  "failure_clusters": [],
  "error_clusters": [
    {"cluster_id": 1, "pattern": "ImportError: cannot import name * from *._email_helpers",
     "generated_file": "ecommerce_user_service/src/.../integrations/_email_helpers.py",
     "count": 6, "services_affected": ["ecommerce_user_service"], "error_ids": [1, 2, 3, 4, 5, 6],
     "representative_error_id": 1,
     "codegen_hint": {"probable_template": "integration_helpers.py.j2", "probable_generator": "IntegrationGenerator"}}
  ]
}
```

Key fields: **`dtrx_source`** (derived from the project path: the `.dtrx` to look up), **`import_chain`**
(for a collection error, the import chain from the test to the missing symbol), **`generated_file`** (the
generated file holding the bug, from the traceback), **`services_affected`** (which services hit the
cluster), **`codegen_hint`** (a best-effort guess at the template/generator; `null` when the mapping is
ambiguous — a starting point, not a verdict).

### Generated-project `aggregate-index.json` (across projects)

```json
{
  "schema_version": 1,
  "timestamp": "2026-05-03T21:08:12",
  "language": "typescript",
  "platform": "docker",
  "total_projects": 46,
  "projects_passed": 37,
  "projects_failed": 9,
  "total_counts": {"passed": 11661, "failed": 0, "errors": 52, "skipped": 0, "suite_failures": 7},
  "failed_projects": [
    {"project": "typescript/docker/03-domains/ecommerce", "example": "03-domains/ecommerce",
     "result_dir": ".../.test_results/unit-tests-20260503-210422",
     "counts": {"passed": 45, "failed": 0, "errors": 40, "suite_failures": 0},
     "top_cluster_pattern": "ImportError: cannot import name 'ContractViolationError' from *.errors"}
  ],
  "cross_project_clusters": [
    {"cluster_id": 1, "pattern": "ImportError: cannot import name 'ContractViolationError' from *.errors",
     "projects_affected": ["modules-imports", "ecommerce"], "total_errors": 46,
     "codegen_hint": {"probable_template": "error_classes.py.j2", "probable_generator": "ErrorGenerator"},
     "representative_project": "modules-imports"}
  ],
  "suite_failure_clusters": [
    {"cluster_id": 1, "pattern": "Cannot find module *", "projects_affected": ["advanced-cache", "batch-operations", "..."],
     "total_suite_failures": 7, "representative_project": "advanced-cache"}
  ]
}
```

Key fields: **`cross_project_clusters`** (identical error patterns grouped across projects: how many errors
share one root cause in the whole run), **`suite_failure_clusters`** (environment-level issues — missing
modules, config errors — that stop a whole suite; separate from test-level errors because their causes
differ), **`representative_project`** (the project to investigate first for a cluster),
**`top_cluster_pattern`** (per failed project, the most common error pattern; `null` for a project with
only suite failures — read `suite_failure_message`).

### Schema evolution policy

Both `index.json` and `aggregate-index.json` carry `schema_version` as their first field.

- **Additive changes** (new optional fields): no version bump; readers ignore unknown fields.
- **Breaking changes** (a field renamed, retyped, removed, or a required field added): bump `schema_version`.
- **Readers** read `schema_version` first; a version higher than the reader supports logs a warning and falls back to `summary.txt`. A file is never rejected.
- **Writers** always write the current version; no multi-version output.

### Agent workflow (generated-project tests)

1. Read `aggregate-index.json` — every failed project, cross-project clusters, codegen hints.
2. Read the representative project's `index.json` — per-service breakdown, error clusters with import chains.
3. Read `errors/001-....txt` (~30 lines) — one representative error per cluster.
4. Fix the root cause in the template/generator — re-run — read the new `aggregate-index.json`.

### Deploy test structured output

Deploy tests verify that generated projects build, deploy, and pass spec/integration tests against real
Docker containers. After each project's deploy tests, `run_complete.py` post-processes the raw data
(`failures.json`, JUnit XML, Jest JSON, Docker logs, `deploy-test-output.log`) into a result directory
under the project's `.test_results/`:

```
{project}/.test_results/
  deploy-test-20260503-210903/
    index.json                       # Machine-readable index (agent reads this FIRST)
    summary.txt                      # Human-readable summary (< 60 lines)
    full.log                         # Combined execution log
    environment.json                 # Toolchain metadata
    docker-logs/                     # Per-container logs
    services/<service>/
      spec/junit.xml | spec/jest-results.json
      integration/junit-project.xml, junit-service.xml | integration/jest-results.json
    failures/                        # One file per unique test failure (logic only)
    errors/                          # Infrastructure/lifecycle errors
```

`index.json` is always written (passing runs too); `failures/` and `errors/` only when there is something
to put there.

**Phases**, in order — a later phase is `SKIPPED` once an earlier one failed, and `index.json` names the
first failed phase (`failed_phase`), so a Docker lifecycle issue is told from a test failure at once:

| Phase | What happens | Failure output |
|-------|-------------|---------------|
| **docker-build** | `docker compose build` | Exit code + build output in `full.log` |
| **docker-up** | `docker compose up -d` + wait for healthy | Exit code + container logs in `docker-logs/` |
| **health-check** | HTTP health check per service | Timeout/error in `full.log` + container logs |
| **db-connectivity** | Database URL resolution + connection test | Error in `full.log` |
| **spec-tests** | pytest/Jest spec tests per service | `failures.json` + JUnit XML / Jest JSON |
| **integration-tests** | pytest/Jest integration tests | `failures.json` + JUnit XML / Jest JSON |

`summary.txt` lists the phases with their durations (`✓`/`✗`/`-` skipped), then `ERRORS:` (phase, error,
container log, probable template) or `FAILURE CLUSTERS:` (logic vs transient), then `SERVICE STATUS:` per
service (port, docker health, spec/integration result). An `errors/NNN-<phase>-<kind>.txt` file holds
`PHASE`, `ERROR`, `MESSAGE`, the relevant container, the last 50 lines of its log, the generated files
involved and the codegen hint (template, generator, `.dtrx` source); a
`failures/NNN-<service>-<phase>-<error>-<test>.txt` file holds `SERVICE`, `PHASE`, `TEST`, `FAILURE TYPE`,
`ERROR`, the traceback, the generated file and the codegen hint.

**Per-project deploy `index.json`** adds to the generated-project schema: `failed_phase`; `phases` (per
phase `result`, `duration_seconds`, and on failure `error_message` and `relevant_containers` — the only
docker logs to read); per service `port`, `docker_healthy`, `health_check_passed`,
`db_connectivity_passed`, `spec_result`, `integration_result`; per error `phase`, `container`,
`docker_log_file`; per failure `failure_type` (`"transient"` — connection resets, timeouts — or `"logic"`,
an actual bug; codegen fixes start from `"logic"`); and `phase` on each cluster.

**Cross-project deploy aggregate** (`.generated/.test_results/deploy-tests-<stamp>/`:
`aggregate-index.json`, `aggregate-summary.txt`, `full.log`) adds `total_counts.infrastructure_failures`
(projects that failed in a Docker lifecycle phase and never reached tests), `failed_phase` per failed
project, and per cross-project cluster `phase` and `failure_type` (`"infrastructure"`, `"logic"` or
`"transient"`; agents take `"logic"` first). `aggregate-summary.txt` groups the failed projects into
infrastructure, logic and transient failures, then lists the passed ones.

**Transient error patterns:** Python deploy tests classify a failure as transient or logic at runtime;
TypeScript failures are classified in post-processing. The patterns are `TRANSIENT_ERROR_PATTERNS` in
`common/lib/datrix_scripts/deploy_test_log_writer.py`: connection (`ConnectionResetError`,
`ConnectionDoesNotExistError`, `connection was closed in the middle of operation`), network/DNS
(`getaddrinfo failed`, `Name or service not known`, `Temporary failure in name resolution`), timeout
(`timeout`, `timed out`), database (`server closed the connection unexpectedly`,
`connection to server * closed unexpectedly`) and infrastructure (`Cannot connect to`,
`Connection refused`, `No route to host`). A transient failure is an environment issue, not a codegen bug.

**Agent workflow (deploy tests):** read `aggregate-index.json` (failed projects, phases, clusters, hints) →
the representative project's `index.json` (phase breakdown, service status, clusters) →
`errors/001-....txt` or `failures/001-....txt` (~30 lines, with the relevant container log excerpt) → fix
the root cause in the template/generator, re-run, read the new `aggregate-index.json`.
