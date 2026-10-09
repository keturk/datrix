# Quick Reference — Realization Gates

Gates that prove a declared capability or contract is actually realized: in generated output, in
every target's source, or by every spec in the standing conformance corpus. Repo-level validation
**scripts**, not pytest suites (the datrix showcase repo hosts none).

> **Bash invocation:** Prefix with `powershell -File`, use forward slashes, quote paths. See [../../quick-reference.md](../../quick-reference.md) for full details.
>
> **Base path:** `d:/datrix/datrix/scripts/`

---

## `gates\realization\conformance-gate.ps1`

Declarative design-acceptance assertion runner over a tree (generated output or package src) — the reusable backbone behind ad-hoc `prove_*`/`gate_*`/`*_conformance` scripts. Spec JSON: `{target, negative_control, assertions:[{id, type, pattern?, path?, glob?, expected_count?, description}]}` with types `must_contain`, `must_not_contain`, `file_exists`, `file_absent`, `count_equals` (regex patterns; binaries skipped). **Non-vacuity built in:** with `negative_control` set, a `must_not_contain` pattern must appear in the control tree or the assertion FAILS as vacuous. A self-test of every assertion type runs as step 1 of every invocation.

| Mode | Command | Description |
|------|---------|-------------|
| **Run a spec** | `.\gates\realization\conformance-gate.ps1 -Spec D:\datrix\.tmp\my-invariant.spec.json` | PASS/FAIL ledger per assertion |
| **Self-test only** | `.\gates\realization\conformance-gate.ps1 -SelfTest` | Prove every assertion type detects and passes |
| **Custom ledger path** | `.\gates\realization\conformance-gate.ps1 -Spec ... -Output D:\datrix\.test-output\my-ledger.json` | Override ledger location |

**Parameters:** `-Spec <path>` (required unless `-SelfTest`), `-SelfTest`, `-Output <path>`, `-Dbg`

**Output:** `D:\datrix\.test-output\conformance\<spec-stem>-ledger.json` (violating/matching paths per assertion, cap 100 + total). **Exit codes:** 0 = all assertions pass, 1 = any fail, 2 = usage / bad spec / self-test failure.

---

## `gates\realization\standing-conformance-gate.ps1`

Standing conformance-spec corpus gate: runs every committed `conformance_gate.py` spec under `scripts/config/conformance-specs/` (top-level `*.json` files only -- fixture subdirectories such as `_fixtures/` are never swept). Each spec's own self-test runs first, exactly as `conformance_gate.py`'s single-spec CLI already guarantees on every invocation.

**Policy this gate exists to serve:** a design-acceptance NEGATIVE check ("the old state is gone on every surface") that outlives its landing must either become a real test in the owning package (preferred, per the prefer-a-test-over-a-scratch-script rule), or a committed spec here -- never a one-off run nobody re-executes. When a change's acceptance proof is "the old construct no longer exists anywhere" and that proof cannot naturally live as a package test, add a spec JSON here.

**Writing a spec:**
- **Paths are relative to the spec file.** `conformance_gate.py` accepts absolute paths too (fine for a one-off hand-run spec), but a *committed* spec bakes one machine's checkout location into the repo, and the runner hard-fails exit 2 on a missing directory -- so an absolute path does not degrade elsewhere, it simply cannot run. This gate checks the whole corpus for rooted paths **before running any spec** and aborts with exit 2 naming the offenders. From `scripts/config/conformance-specs/`: `../../../examples` (datrix examples), `../../gates/realization/lib` (a scripts `lib/` folder), `../../../../<package>/src` (a sibling package).
- **Negative-control fixtures live under `_fixtures/`** -- per-spec in `_fixtures/<spec-stem>/negative-control/`, or `_fixtures/_shared/<name>/` when several specs police the same retired surface (the four config-block dead-surface specs share one `system.dcfg` control this way). A `must_not_contain` whose pattern is absent from the control tree too fails as VACUOUS, so the fixture must keep containing the forbidden pattern forever -- never "fix" it to match the real code. A control tree is scanned with the **assertion's own glob**, so the fixture's filenames must satisfy that glob (a spec globbing `secret_backend.py` needs a control root holding a file by that name).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\realization\standing-conformance-gate.ps1` | Run every committed spec |
| **Debug** | `.\gates\realization\standing-conformance-gate.ps1 -Dbg` | Debug logging, forwarded per-spec |

**Parameters:** `-Dbg`

**Assertions:**
- Every `*.json` file directly under `scripts/config/conformance-specs/` is a spec, run via `conformance_gate.py --spec <file>` (its own built-in self-test runs first, per-spec, aborting that spec with exit 2 before any real result is trusted).
- Seed spec `gendsl-corpus-no-hand-authored-module-tuple.json`: `gendsl_corpus_resolution.py` contains none of the seven retired hand-authored genDSL definitions-module literal strings, proven non-vacuous by a dedicated negative-control fixture under `scripts/config/conformance-specs/_fixtures/` that intentionally still contains them.

**Exit codes:** 0 = every spec passed, 1 = at least one spec's assertions failed, 2 = the spec directory is missing/empty, a committed spec addresses its trees by absolute path, or any individual spec's own self-test failed (that spec's run aborts before its real assertions are evaluated).

---

## `gates\realization\typescript-whole-system-gate.ps1`

Whole-system **TypeScript** generation gate: proves the whole-system generate path emits real TypeScript (not a hollow/failed run) and is byte-deterministic. Generates the language-neutral `examples/01-foundation` twice with `-Language typescript`, into two explicit `--output` dirs, and asserts realness + byte-stability. The target comes solely from the flag — Datrix has no language-specific examples, and a `language` key in a system `.dcfg` is rejected at load time.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\realization\typescript-whole-system-gate.ps1` | Generate twice, assert realness + byte-stability |
| **Custom output root** | `.\gates\realization\typescript-whole-system-gate.ps1 -OutputRoot D:\datrix\.test-output\ts-gate` | Override run1/run2 location |
| **Debug** | `.\gates\realization\typescript-whole-system-gate.ps1 -Dbg` | Forward `-Dbg` to generate.ps1 |

**Parameters:** `-OutputRoot` (default: `d:/datrix/.test-output/ts-gate`), `-Dbg`/`-DebugLogging`

**Assertions:**
- **Realness (positive):** generated `*.ts` source count > 0 (the TypeScript language generator ran).
- **Realness (leak guard):** no `*.py` under any generated `src/` tree, and every `*.py` in the output lives only under `tests/` or `migration-tools/` — the two **language-agnostic** Python artifact classes emitted for every target (httpx HTTP-contract integration tests regenerated by datrix-codegen-python's `python_http_contract_overlay`; the live-schema exporter rendered by datrix-codegen-sql). Any other `*.py` is a language leak and fails the gate.
- **Byte-stability:** recursive sha256 diff of run1 vs run2, excluding non-source build/install artifacts `.datrix/`, `.ruff_cache/`, `.tsc_cache/`, `node_modules/`. Any content or file-set difference fails.

**Exit codes:** 0 = real + byte-stable TypeScript whole-system output, 1 = generation failed, realness violated, or byte drift detected.

---

## `gates\realization\generation-determinism-gate.ps1`

Generation-pipeline determinism gate for one registered language: the SAME source tree, generated N times in a row via the documented single-project `generate.ps1` path, must never produce two different outcomes (same failure mode every time, or a byte-identical success manifest every time). Each run is its own `generate.ps1` process (fresh `python.exe`, fresh `PYTHONHASHSEED`), so this also exercises hash-seed-driven set-iteration-order bugs a single long-lived process would never surface. Targets `examples/02-features/03-infrastructure-blocks/nosql/system.dtrx` — the example a corpus generation sweep once found producing three different outcomes (a struct-test planning failure, then two different compile failures) from the identical, unchanged-tree invocation. No before/after comparison of two code states can catch this class of bug, because it never runs the same code twice; this gate runs the SAME code N times and compares outcomes to each other. `-Language` is required — the gate never assumes which languages are installed.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate (5 runs)** | `.\gates\realization\generation-determinism-gate.ps1 -Language python` | Generate 5 times for one language, assert identical outcomes |
| **Custom run count** | `.\gates\realization\generation-determinism-gate.ps1 -Language typescript -Runs 3` | Fewer/more repeated generations (must be >= 2) |
| **Custom output root** | `.\gates\realization\generation-determinism-gate.ps1 -Language python -OutputRoot D:\datrix\.test-output\generation-determinism-gate\python` | Override run1..runN location |
| **Debug** | `.\gates\realization\generation-determinism-gate.ps1 -Language python -Dbg` | Forward `-Dbg` to generate.ps1 |

**Parameters:** `-Language` (required; a registered `datrix.languages` name), `-OutputRoot` (default: `d:/datrix/.test-output/generation-determinism-gate/<Language>`), `-Runs` (default: 5, must be >= 2), `-Dbg`/`-DebugLogging`

**Assertions:**
- Every run's classification (SUCCESS vs FAILED) matches run 1's.
- A SUCCESS run's per-relative-path sha256 manifest of the generated source tree (excluding `.datrix/`, whose audit log / snapshot / manifest `generated_at` timestamp are expected to differ every invocation by design) matches run 1's manifest exactly.
- A FAILED run's generation-results log, normalized (run-specific `--output` directory replaced with a fixed placeholder; timestamp/log-path preamble lines stripped) and hashed, matches run 1's normalized fingerprint exactly.

**Exit codes:** 0 = all N runs produced the identical outcome, 1 = a classification or fingerprint mismatch was found (non-deterministic generation), non-zero PowerShell error = usage/environment error (e.g. venv activation failure, missing example).

---

## `gates\realization\ingress-migration-conformance-gate.ps1`

Declaration-driven service ingress migration conformance gate. Repo-level, independent proof that regenerating the framework's own showcase examples produces only the four intended DI-6 realized-exposure deltas. Regenerates three representative registered examples individually (`identity` for delta d, `shared-block` for delta a, `authentication` + `01-foundation` for delta c) via single-project explicit-output `generate.ps1` calls, separately runs the existing full-tree example generation gate (`test\run-complete.ps1 -All -Skip3 -Skip4`) over every registered example, proves at the source level that the webhook verification prelude is independent of `AuthMode`, and greps for the removed config keys.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate (both languages)** | `.\gates\realization\ingress-migration-conformance-gate.ps1` | Full DI-6 conformance sweep, python + typescript |
| **Single language** | `.\gates\realization\ingress-migration-conformance-gate.ps1 -Languages python` | Faster iteration while debugging |
| **Custom output root** | `.\gates\realization\ingress-migration-conformance-gate.ps1 -OutputRoot D:\datrix\.test-output\ingress-gate` | Override scratch generation root |
| **Debug** | `.\gates\realization\ingress-migration-conformance-gate.ps1 -Dbg` | Forward `-Dbg` to generate.ps1/run-complete.ps1 |

**Parameters:** `-OutputRoot` (default: `D:\datrix\.test-output\ingress-gate`), `-Languages` (comma-separated, default: `python,typescript`), `-Dbg`/`-DebugLogging`

**Assertions:**
- **Step 0 (live counts):** re-verifies `rest_api` file count, `system.dcfg` gateway-declaration count, `auth(service` occurrence count, and that the sole `verify(` usage is paired with `auth(webhook)` (the webhook migration's precondition).
- **Delta (a):** shared-block's `publisher-service.dtrx` (all-`auth(service)` surface) derives `INTERNAL` — no gateway route, no bare all-interfaces port publish.
- **Delta (b):** documented, verified absence — no registered example reproduces the name-suppression fixture (owned by the docker/azure/aws package suites).
- **Delta (c):** a single-service example with a declared `gateway {}` (`authentication`) emits a non-empty `config/nginx/nginx.conf`; a single-service example with NO declared gateway (`01-foundation`) emits none.
- **Delta (d):** the shared webhook context builder, the python prelude builder and the typescript guard template each dispatch only on their verify-mode field and carry no `AuthMode` / `auth_contract.mode` / `access_level` reference, so the generated prelude is a pure function of the unchanged `verify(...)` contract; `identity` is also regenerated per language so the live tree is on disk for inspection (the repo keeps no stored output snapshot to diff against).
- **Step 3:** zero ING001/ING002/ING003 and webhook-invariant errors across the full-tree generation gate, both languages (known, tracked, out-of-scope failures — e.g. shared-block's pre-existing API003/XSV017 defect — are reported but not conflated with an ingress regression).
- **Step 4:** zero `publicIngress`/`platforms.azure.services` matches under `datrix/examples`.

**Exit codes:** 0 = every DI-6 delta class accounted for and the negative acceptance property holds, 1 = any finding (including known, out-of-scope pre-existing defects, reported distinctly) causes a non-zero ledger.

---

## `gates\realization\shared-builder-reachability-gate.ps1`

Shared-builder reachability gate: every module-level `build_*` function declared in `datrix_codegen_common`'s `algorithms/` and `context_models/` modules must have at least one production caller outside its own defining module, across the defining package itself, every registered language package, and `datrix-cli`. A shared context builder that is written, exported and unit-tested but never called looks complete by every signal except the one that matters — it never executes on a real generation run — and that shape recurs as machinery gets hoisted into the shared layer for several languages to share, because every other gate asks whether the code is CORRECT, never whether it RUNS. Whole-tree AST import/call-graph resolution, never text matching: it follows aliased imports (`import X as Y`, `from X import Y as Z`), attribute calls (`module.build_x(...)`), and package `__init__` re-exports (bounded chase, so a cyclic re-export cannot loop). It also counts a **thin delegation** as live — a wrapper whose entire body is one context construction delegating to a callee some module OUTSIDE the defining package binds, and whose constructed type another production module builds — which is what keeps the registered test-axis domains' `build_<kind>_test_context` wrappers from reading as dead when the production path builds the identical value generically inside `TestGeneratorOrchestrator`. A builder that branches, walks the model, logs, or returns `None` has more than one statement and is never a thin delegation, whatever types it touches. **Hard zero: no exemption file, no pinned baseline** — a baseline on a gate whose entire job is "notice code nobody wired in" would exempt exactly the defect class it exists to catch. Language package set from the installed `datrix.languages` entry points at runtime, never a literal list; the gate refuses to run against fewer than two languages rather than passing vacuously. A unit test importing several generator packages would be the cross-package coupling `scan\check-import-boundaries.ps1` forbids, so this proof lives here.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\realization\shared-builder-reachability-gate.ps1` | Census the real installed package tree |
| **Debug** | `.\gates\realization\shared-builder-reachability-gate.ps1 -Dbg` | Debug logging (names each self-test check as it passes) |
| **Self-test only** | `.\gates\realization\shared-builder-reachability-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real census |
| **Census** | `.\gates\realization\shared-builder-reachability-gate.ps1 -Census` | Print every builder with its calling packages, every live thin delegation with the delegate and context type it resolved through, and every dead builder; exit 0 |

**Parameters:** `-Dbg`, `-SelfTest`, `-Census`

**Assertions:**
- Zero `build_*` definitions under the scanned subpackages have neither a resolved external caller nor a live thin delegation.
- **Correctness floors (over-reporting is as much a failure as under-reporting):** five named genuinely-wired builders are never flagged dead; `build_api_context`'s resolved callers span several language packages (cross-package resolution); `extract_max_length` resolves through its aliased same-named private wrappers (alias resolution); and every registered test-axis wrapper is live through its OWN `plan_<kind>_tests` delegate and constructs `TestPlanContext` — a rule folding every wrapper onto one delegate would pass a bare "something was rescued" check while proving nothing. A floor whose expected caller package is not installed is a loud configuration error (exit 2), never a silent skip.
- Non-vacuity self-test (every invocation, before any real census): a planted orphan `build_*` is flagged by name and clears once a real cross-module caller is wired; a caller reached ONLY through an aliased private wrapper is still resolved (the shape no text search can see); a thin wrapper over a production-bound plan is recognized as live with its delegate and context type recorded; a **multi-statement** builder touching the same production-bound plan and constructing the same production-built context type is STILL dead (the half that matters most — a delegation rule that rescued it would have quietly disabled the whole gate); and a thin wrapper whose delegate nothing outside the defining package binds is still dead.

**Exit codes:** 0 = every shared builder is reachable and every floor holds (or a successful `-SelfTest` / `-Census`), 1 = a dead builder or a violated correctness floor, 2 = the self-test failed, a scanned package could not be located, or fewer than two languages are registered.

---

## `gates\realization\zero-environment-runtime-gate.ps1`

Zero-environment runtime census gate: every registered language is obligated to bake deployment-static values at generation time (the running service consults no environment variable). Each language plugin states, on its `LanguageCapabilityDeclaration.zero_environment_runtime`, the regular expressions that spell an environment read in its own templates. The gate censuses every `.j2` template under the `src/` tree of every package implementing each registered language (its backend plus each language core the backend requires) against those idioms, and holds each language to the rule the KIND of its entry in `scripts/config/zero-environment-runtime-baseline.json` selects — never a field on the declaration, a reason or a gap row:
- `reviewed_exemptions`: every template that reads the environment is listed with a written reason, as a justification of that specific read (python's reads are per-read reviewed exemptions). An unlisted read and a stale entry are both violations. A language with NO entry is held to this kind with an empty list, so adding a language needs no edit here.
- `pinned_count`: a decrease-only count of environment-reading templates, for a language that delivers runtime facts through the environment by design (typescript). It may fall and may never rise.

A registered language that states no idioms fails, named; a baseline entry naming an unregistered language is stale and fails. Language set from the installed `datrix.languages` entry points; idioms from each language's declaration — never a table in the script. Test-harness templates count too (a harness that reads the environment is still emitted into the generated project).

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\realization\zero-environment-runtime-gate.ps1` | Census every registered language against its baseline entry |
| **Debug** | `.\gates\realization\zero-environment-runtime-gate.ps1 -Dbg` | Debug logging (lists every environment-reading template) |
| **Self-test only** | `.\gates\realization\zero-environment-runtime-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real census |
| **Lower pins** | `.\gates\realization\zero-environment-runtime-gate.ps1 -UpdateBaseline` | Lower every `pinned_count` entry to its live census (the only writer of `pinned_count`; it refuses to raise one; `reviewed_exemptions` entries are hand-authored and untouched) |

**Parameters:** `-Dbg`, `-SelfTest`, `-UpdateBaseline`

**Assertions:**
- `reviewed_exemptions` kind (or no entry): `reads − exemptions = ∅` and `exemptions − reads = ∅`; every exemption carries a non-empty reason.
- `pinned_count` kind: `len(reads) ≤ pinned_count`; a count below the pin is logged with the lower-the-pin hint, never silently accepted as the new floor.
- Every entry's `kind` is one of the two values and carries exactly its own payload key; a missing or unknown kind, a `pinned_count` entry carrying `exemptions` (or the reverse), an entry lacking its payload, or an extra key is rejected.
- Non-vacuity self-test (every invocation): the gate names no registered target (`datrix_scripts.registered_targets.self_test_gate_names_no_target`); a synthetic template tree yields exactly the planted read (the clean template and a non-`.j2` file are not counted); the comparator reports exactly one problem for a missing exemption, a stale exemption, a count above the pin, and no entry with a read, and none for an exact match, a count at/below the pin, or no entry with no read; the same one-read census passes against a `pinned_count` entry of 1 and fails against an empty `reviewed_exemptions` entry (the entry kind alone selects the branch); a reasonless exemption is rejected; every `entry_kind` rejection above; `-UpdateBaseline`'s writer lowers a pin, refuses to raise one and carries exemption entries through unchanged; a baseline entry naming an unregistered language is one stale-entry problem; a fixture language split into a backend and a core has a read planted in the core censused (a backend-only census misses it) and one relative template path carried by both packages refused; the **live** census finds at least one read the committed baseline lists as a reviewed exemption (derived from the baseline, never a language or path pinned in the gate); a single-language set is refused.

**Exit codes:** 0 = every language matches its baseline entry (or a successful `-SelfTest` / `-UpdateBaseline`), 1 = a violation was found, 2 = the self-test failed, fewer than two languages are registered, or the baseline is malformed.

---

## `gates\realization\model-realization-parity-gate.ps1`

Model-realization capability-declaration parity gate: every installed
`datrix.platforms` plugin declares a well-formed `model_realizations` mapping on its
`PlatformCapabilityDeclaration` — one `ModelRealization` per model provider (API family) the
platform realizes, each cell's `flavors` drawn from the closed placement domain
`container | external | managed | direct`. The field is REQUIRED with no default: a platform
realizing zero providers must still declare an explicit empty mapping, so a missing declaration
is a construction error (reported naming the platform, never a raw traceback), not a silently
absent capability. Scoped to that single field — it never compares provider sets across
platforms (a platform realizing zero providers is conforming); the cross-platform union
comparison over every OTHER capability surface is `gates\parity\block-realization-parity-gate.ps1`'s job.

Derives its target platform set from `importlib.metadata.entry_points(group="datrix.platforms")`
at runtime — never a hardcoded platform literal.

**Built-in non-vacuity self-test, every invocation.** Feeds the comparator a synthetic matching
declaration pair (must report zero violations) and a synthetic pair with one planted
out-of-domain flavor cell (must report exactly one violation, naming the offending platform and
flavor). Fails loud (exit 2) if fewer than 2 platforms are registered.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\gates\realization\model-realization-parity-gate.ps1` | Check every registered platform's `model_realizations` declaration |
| **Debug** | `.\gates\realization\model-realization-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\gates\realization\model-realization-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Exit codes:** 0 = every registered platform declares a well-formed `model_realizations`
mapping, 1 = at least one violation (an unconstructible declaration or an out-of-domain
flavor), 2 = the non-vacuity self-test failed or fewer than 2 platforms are registered.

---

## `gates\realization\pooled-cache-realization-gate.ps1`

Pooled-cache member-slice realization gate: for every registered `datrix.languages` /
`datrix.platforms` target, asserts that a pooled cache member's declared slice
(`PooledMember.slice_index`, `datrix_codegen_kernel.pooling.contract`) actually reaches that
target's own emitted-output-facing source — not merely that the shared pooling pre-pass computed
it. **Detection is STATIC**: the gate AST-parses each target package's own `src/` tree (never a
substring/regex scan, never `generate.ps1`) for a function that both reads a `.slice_index`
attribute AND is call-reachable from elsewhere in that same tree — declared AND consumed, not dead
code. A target that does not yet realize the slice must carry a typed exemption (axis + target +
reason) in `datrix/scripts/config/pooled-cache-realization-exemptions.json` — a target quietly losing its realization
(a regression) fails the gate the same way a target that never had one does; a target that starts
realizing while its exemption is still present (a stale exemption) also fails.

Derives its target sets from
`importlib.metadata.entry_points(group="datrix.languages" | "datrix.platforms")` at runtime —
never a hardcoded language-name or platform literal — so a
future `datrix-codegen-<x>` package is covered automatically with no edit here. Every registered
entry-point name is checked independently (a platform name backed by a shared package, e.g.
`local` with `docker` or `azure-vm` with `azure`, still gets its own exemption entry).

**Built-in non-vacuity self-test, every invocation.** Proves, against synthetic source trees it
has never seen, that a declared-and-reachable `.slice_index` consumer classifies realized and a
declared-but-dead (never called) one classifies NOT realized — the exact regression shape a
realization task could introduce. Also exercises the gate's own vacuity guard for real (via a
`target_names` override, the same code path a live run takes) against a synthetic single-target
axis. Fails loud (exit 2) if fewer than 2 targets are registered on an axis being checked.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate (both axes)** | `.\gates\realization\pooled-cache-realization-gate.ps1` | Check every registered language AND platform target |
| **Single axis** | `.\gates\realization\pooled-cache-realization-gate.ps1 -Axis platforms` | Check only the platforms axis (or `-Axis languages`) |
| **Debug** | `.\gates\realization\pooled-cache-realization-gate.ps1 -Dbg` | Debug logging (also lists each target's declared-and-reachable consumer sites) |
| **Self-test only** | `.\gates\realization\pooled-cache-realization-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real check |

**Parameters:** `-Axis <languages\|platforms>` (default: both axes), `-Dbg`, `-SelfTest`

**Exemptions:** `scripts/config/pooled-cache-realization-exemptions.json` — one entry per
currently-unrealized target (`{axis, target, reason}`). There is no `-UpdateBaseline`: a
realization change removes its own entry, never a generic freeze command.

**Exit codes:** 0 = every registered target realizes the slice or carries a reviewed exemption
(and no exemption is stale), 1 = at least one unexempted gap or stale exemption was found, 2 = the
non-vacuity self-test failed or fewer than 2 targets are registered on an axis being checked.

---

## `gates\realization\shared-cache-realization-gate.ps1`

Shared-cache realization gate: a service that `uses` a shared cache container realizes that
container's cache block next to its own (`realized_cache_blocks`). For every registered
`datrix.languages` target the gate asserts the target's source walks `realized_cache_blocks`; for
every registered `datrix.platforms` target it asserts the source walks the same set AND calls
`require_cache_keys_supplied` (every connection key the surface declares is supplied). **Detection
is STATIC**: the gate AST-parses each target's own `src/` trees (the backend package plus every
language core it requires), never generating a project. The behavioural assertions per language and
platform live in each package's own tests.

Derives both target sets from `importlib.metadata.entry_points` at runtime — never a hardcoded
language or platform list — and refuses to pass (exit 2) with fewer than two targets on an axis.

**Built-in non-vacuity self-test, every invocation.** A planted consumer-blind source tree (it reads
only the service's own cache block) must be detected, a tree that walks the realized blocks must
classify realized, and a single-target axis must be refused as vacuous.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate (both axes)** | `.\gates\realization\shared-cache-realization-gate.ps1` | Check every registered language AND platform target |
| **Single axis** | `.\gates\realization\shared-cache-realization-gate.ps1 -Axis platforms` | Check only the platforms axis (or `-Axis languages`) |
| **Debug** | `.\gates\realization\shared-cache-realization-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\gates\realization\shared-cache-realization-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real check |

**Parameters:** `-Axis <languages\|platforms>` (default: both axes), `-Dbg`, `-SelfTest`

**Exit codes:** 0 = every registered target walks the realized cache blocks (and every platform
proves the keys supplied), 1 = at least one target is consumer-blind, 2 = the non-vacuity self-test
failed or fewer than 2 targets are registered on an axis being checked.

---

## `gates\realization\shared-rdbms-realization-gate.ps1`

Shared-RDBMS realization gate: a service that `uses` a shared container's RDBMS block realizes that
block next to its own (`realized_rdbms_blocks`). For every registered `datrix.languages` target the
gate **generates** the shared-rdbms fixture (a shared container's block, a `readwrite` consumer that
holds a seed, a `readonly` consumer) and applies language-neutral file-set assertions to the emitted
tree: every consumer emits an entity module for the consumed block, every file of the owner's
canonical migration chain appears byte for byte in every consumer, and the block's seed is emitted
in the writer and in no reader. The behavioural assertions per language (typed access, read-only
repositories, the chain lock key) live in each package's own tests.

Derives the language set from `importlib.metadata.entry_points(group="datrix.languages")` at runtime
— never a hardcoded language list — and refuses to pass (exit 2) with fewer than two registered
languages.

**Built-in non-vacuity self-test, every invocation.** A planted language whose consumer emits no
entity module, one whose carried chain differs from the canonical one, and one that seeds a reader
must each be reported; a faithful planted language must report nothing; a single-language run must
be refused as vacuous.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\gates\realization\shared-rdbms-realization-gate.ps1` | Generate the fixture for every registered language and check the emitted trees |
| **Debug** | `.\gates\realization\shared-rdbms-realization-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\gates\realization\shared-rdbms-realization-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; generate nothing |

**Parameters:** `-Dbg`, `-SelfTest`

**Exit codes:** 0 = every registered language realizes shared consumption, 1 = at least one language
has a gap, 2 = the non-vacuity self-test failed or fewer than 2 languages are registered.

---

## `gates\realization\documentation-realization-parity-gate.ps1`

Documentation-realization parity gate. For every registered `datrix.languages`
target, generates one small fixture project — via the real
`datrix_cli.pipeline.generation.GenerationPipeline` (the exact code path `datrix generate`/
`generate.ps1` runs, `ValidationLevel.FAST` so each language's post-generation toolchain build is
skipped — see below), never a hand-built test context — whose DSL documents an endpoint, an entity,
a field, an enum value, a struct field and a function, each with a published (`///`) comment and an
adjacent source-channel (`//`) comment. Asserts, by reading the generated artifacts through each
language's own conformance probes (`LanguagePlugin.conformance_probes`,
`LanguageConformanceProbes.documentation_surfaces`) which parse them **structurally** — a language
with a native AST uses it (Python: the real `ast` + `tokenize`), a C-family language such as
TypeScript uses the shared lexer `datrix_codegen_kernel.parity.c_family_source_scan` (decorator
anchors outside any string/comment span, bracket-depth-tracked to the matching close, plus
`/** ... */` doc blocks distinguished from plain `/* ... */` block comments by their `/**` opener —
never a line-oriented regex over a whole file) — that the published text reaches that target's
declared published surface and the source text reaches its source surface and never the published
one. The gate names no target and carries no per-target table; a probe that finds no documentation
surface at all fails the run. The gate is a hard zero: every registered target realizes every
(construct kind, surface) cell, and an unpopulated cell is a hole that fails the gate naming the
target, construct kind and surface. There is no exemption mechanism of any kind.

**Asserts over generated artifacts, not a running/building service.** Generation runs with
`ValidationLevel.FAST` — `fix_imports` + `format_files` run, but `validate_files` (where a language's
toolchain build would otherwise be invoked) is skipped, because the property under test is where the
text lands, not whether the toolchain builds. Each language package proves a real end-to-end
document in its own suite: python against a real FastAPI router's `.openapi()`, and typescript
against a real `tsc` + `SwaggerModule.createDocument()` run over an npm-installed dependency set.
This gate is the repo-level cross-target census.

Derives its target set from `importlib.metadata.entry_points(group="datrix.languages")` at
runtime — never a hardcoded language-name literal.

**Built-in non-vacuity self-test, every invocation.** First scans the gate's own source with
`datrix_scripts.registered_targets.target_references_in_module` (any import of a target package or
target-name literal in a target-identity position fails it), confirms every marker text is
actually present in the fixture DSL itself, then drives the gate's real surface reading with
in-process fixture probes whose language name is not registered (a fully documented fixture has no
hole; a missing published text is exactly one hole; a source note leaked into the published set is
exactly one hole; an empty probe result and a plugin with no probe member are each refused). The
per-language extractors are proven by the owning packages' own tests
(`datrix-codegen-{python,typescript}/tests/unit/conformance/`, the kernel's
`tests/unit/parity/test_c_family_source_scan.py`). A planted unpopulated cell is proven to fail the
gate, with no input that excuses it. Fails loud (exit 2) if fewer than 2 languages are registered.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\gates\realization\documentation-realization-parity-gate.ps1` | Check every registered language target |
| **Debug** | `.\gates\realization\documentation-realization-parity-gate.ps1 -Dbg` | Debug logging (also logs each target's discovered published-string set and the fixture's `files_written` count) |
| **Self-test only** | `.\gates\realization\documentation-realization-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skips fixture generation entirely |
| **Re-pin coverage** | `.\gates\realization\documentation-realization-parity-gate.ps1 -UpdateCoverageBaseline` | Re-freeze the decrease-only coverage-hole baseline to this run's measured counts (the only writer; refuses to write when any target failed generation) |

**Parameters:** `-Dbg`, `-SelfTest`, `-UpdateCoverageBaseline`

**Coverage census:** the same run re-parses the fixture with the shipped
capture pipeline, collects every comment run ATTACHED to a node, and counts how many reach no
generated artifact at all on each target. Comparison is marker- and whitespace-normalized (a
formatter rewrapping a comment across lines is not lost documentation) and paragraph-by-paragraph
(the summary/description split puts one run's paragraphs in two different fields). Counts are held
by `scripts/config/documentation-coverage-baseline.json`; a target whose hole count rises above its
pinned value fails the gate. Attachment itself is policed separately, and at zero, by
`datrix-language`'s own produced-minus-consumed census.

**Output:** `D:\datrix\.tmp\documentation-realization-parity-gate-report.json` (per-target census:
checked/populated/holes, the list of holes, the coverage block with each target's attached/reached/
hole counts and the anchors of any holes, plus generation failures if any) on every run, pass or
fail. The fixture project and its per-target generated output tree live under
`D:\datrix\.tmp\documentation-realization-parity-gate\` (fixture/, generated/&lt;target&gt;/).

**Exit codes:** 0 = every registered target's every `(construct_kind, surface)` cell is populated
AND no target's coverage holes exceed its pinned baseline, 1 = at least one hole, a coverage
regression or a generation failure, 2 = the non-vacuity self-test failed or fewer than 2 languages
are registered.

---

## `gates\realization\gendsl-corpus-resolution-gate.ps1`

GenDSL corpus proof: eager builder/call-expression reference resolution runs when each target's
`.gendsl` resource is registered (`datrix_codegen_kernel.gendsl.resolver`). Importing
each discovered target's genDSL definitions module IS the assertion: a bad reference raises
`GenDSLReferenceResolutionError` at import time.

**Target set is derived, never hardcoded.** The module list comes from
`datrix_codegen_kernel.gendsl.target_registry.target_kind_map()` +
`definition_modules_for()`, folded from `datrix.gendsl_generator_targets` entry-point discovery --
every target, platforms included, self-registers its definition modules there (platform
KIND classification separately derives from `datrix.platforms` membership). A future
`datrix-codegen-<x>` package that registers either entry-point group is swept automatically, with
no edit to this gate.

The proof is inherently repo-level: it imports every concrete target package, which a
`datrix-codegen-common` test may not do (the shared layer must not import a concrete target, and a
cross-package test is prohibited everywhere), so it lives here rather than allowlisting a boundary
violation.

**Each target's module is imported in its own dedicated subprocess** — never in this process — so
no single process ever holds more than one generator package's genDSL modules loaded at once (a
registration from one package's earlier import could otherwise silently satisfy a reference the
next package's own corpus does not actually resolve on its own).

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\gates\realization\gendsl-corpus-resolution-gate.ps1` | Import every discovered target's genDSL definitions, fail on any unresolved reference |
| **Debug** | `.\gates\realization\gendsl-corpus-resolution-gate.ps1 -Dbg` | Debug logging (also prints the discovered module list and count) |

**Parameters:** `-Dbg`

**Exit codes:** 0 = every discovered target's genDSL corpus resolved at import, 1 = at least one
target failed to resolve or import.
