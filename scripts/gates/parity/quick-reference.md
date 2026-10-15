# Quick Reference — Parity Gates

Cross-target gates: every registered language (or platform) must realize the same thing the same
way. Each derives its target set from the installed entry points, never a hardcoded list, and runs a
non-vacuity self-test before trusting a real result. Repo-level validation **scripts**, not pytest
suites (the datrix showcase repo hosts none).

> **Bash invocation:** Prefix with `powershell -File`, use forward slashes, quote paths. See [../../quick-reference.md](../../quick-reference.md) for full details.
>
> **Base path:** `d:/datrix/datrix/scripts/`

**A parity fact over generated artifacts is a row, never a new gate module.** A fact read through
a conformance probe ("every language answers this route with this contract") is one row of
`gates\parity\cases\<area>.parity.yaml`, read on every registered target by
`parity-cases-gate.ps1`. A new gate module under this family is reserved for a source census (a
check that reads package source or declarations, and imports no probe).

---

## `gates\parity\parity-cases-gate.ps1`

Reads every parity row on every registered target of its axis and compares each reading with the
row's authored expectation. A **parity row** is a case row (`datrix_testing.cases.model.Case`,
the row kind `datrix_testing.cases.parity`): `stage: parity`, `observer` a method of
`LanguageConformanceProbes` (read on every registered language) or `PlatformConformanceProbes`
(read on every registered platform), `input` the fixture, `selector` the facet of the probe's
return and its keys, `expectation` the authored value, `tags` (`parity` plus the behaviour tag),
`reason`. The rows live in `gates\parity\cases\*.parity.yaml`; the probes a row may name, their
facets and the reading of each are `gates\parity\lib\parity_observers.py` (`PROBE_READINGS`).

| Probe | Fixture (`input`) | Facets (selector keys) |
|---|---|---|
| `route_wire_contracts` | a registered example, generated per language | `route` (`verb`, `path`): `{status, body, media-type}`; `routes`: every `VERB /path/{}`; `duplicate-routes`; `query-keys` (`verb`, `path`): the query keys the route binds, each read as its camelCase words (a backend's own casing is proven by that backend's list-query seam test against `route_query_wire_keys`) |
| `response_body_wire_fields` | a registered example, generated per language | `wire-name` (`field`, `excluding`: schema kinds outside the population): the wire keys the field emits, whatever each language calls it; `nonconformant-fields` (`excluding`): fields whose wire key is not `body_wire_name`'s. A row never selects by schema kind: how a probe classifies a response class differs per language |
| `event_envelopes` | a registered example, generated per language | `envelope-keys` (`event`), `payload-keys` (`event`), `published-events`, `unwritten-consumed-keys` |
| `render_enum_classifier` | a registered example; the `enum` key names one of its enums, rendered by each language | `classifiers` (`enum`): the keyword classifiers defined; `no-match-raise` (`enum`): `{exception: declared or the name raised, message}` |
| `realized_web_security_headers` | a header-set fixture: `web-security-domain` or `web-security-loopback` (the shared builder's set for neutral origins), rendered by each platform | `header` (`name`): the emitted value; `headers`: every emitted name |

A registered example is a project name of `scripts\config\test-projects.json`. The web-security
probe takes a header set rather than a generated tree, so its rows name one of the two header-set
fixtures; every platform renders both topologies. Any row may carry `capability: <kind>:<id>`, the
`capability_gaps` surface the fact belongs to.

**Security posture.** A row is a case, so the strict schema, the raw-secret refusal on its values
and the tag vocabulary apply at load. A row that guards a security control (web-security headers,
framework headers, CORS, identity) carries a tag of `datrix_testing.cases.security.SECURITY_TAGS`
(the `web-security-headers` rows do), which makes it a security case, and the test-rebuild approval
gate covers `*.parity.yaml` exactly as it covers `*.cases.yaml`. Fixtures are committed examples
generated under the test profile; every probe reads generated output only, contained under the
generated root.

**Two verdicts.** The authored one decides: a reading that differs from the expectation is a
`DIVERGENCE` (every target agreeing on a wrong value fails); a selector that resolves on nothing
(an unregistered route, an unpublished event) is `UNREADABLE`. The mutual one informs: a `DRIFT`
line names every target's reading when the targets differ from each other, which says which
target moved when the expectation is the stale side. A target whose capability declaration
carries the row's `capability` surface is a `GAP`, which fails like a divergence. A target the
probe does not apply to (a platform hosting no static site, a language registering no `enum`
sub-generator) is `N/A`. Fixtures are generated once per (input, target) under
`D:\datrix\.tmp\parity-cases\`, and each probe is called once per (target, fixture). A report line
carries row ids, targets, readings and expectations only, never a fixture path or a fixture's or
probe's error text (`-Dbg` shows that text).

**Self-test, every invocation, before any row.** The three gate modules name no target
(`self_test_gate_names_no_target`); two planted languages give two readings per row; one divergent
planted language is exactly one failure, plus a `DRIFT` line; two planted languages agreeing on a
wrong value both fail; a row selecting an unregistered route is unreadable on both; a planted gap
fails as a `GAP`; a planted language whose probes lack the row's method stops the run (exit 2)
naming the language and the method; a planted probe returning another type than its Protocol's
stops the run naming the language; a single target is refused; a planted fixture path and a
planted probe error carrying a canary never reach the report; and the tag selection refuses four
tags and an unknown tag.

| Mode | Command | Description |
|------|---------|-------------|
| **Run tagged rows** | `.\gates\parity\parity-cases-gate.ps1 -Tag rest-api` | Read the rows carrying any of the tags (at most three, each carried by some row, never a selection keeping every row) |
| **Run every row** | `.\gates\parity\parity-cases-gate.ps1` | The whole corpus; Jon's run (refused for agents by `guard-untargeted-scans.py`) |
| **Self-test only** | `.\gates\parity\parity-cases-gate.ps1 -SelfTest` | Run only the self-test; read no row |
| **Debug** | `.\gates\parity\parity-cases-gate.ps1 -Tag pubsub -Dbg` | Debug logging, including fixture and probe error text |

**Parameters:** `-Tag <tag,...>`, `-SelfTest`, `-Dbg`

**Exit codes:** 0 = every selected row holds on every target (or a successful `-SelfTest`), 1 = a
divergence, an unreadable row or a gap, 2 = the self-test failed, a row file or row is malformed,
a tag selection is refused, fewer than two targets can read a row, a target's probes are missing
or incomplete, a fixture fails to build, a probe raised, or a probe returned another type than its
Protocol's.

---

## `gates\parity\parity-cases.ps1`

The parity rows' authoring tool.

| Mode | Command | Description |
|------|---------|-------------|
| **Observe** | `.\gates\parity\parity-cases.ps1 observe rest-api route_wire_contracts "{facet: route, verb: get, path: /api/v1/books}"` | Build the fixture for every target and print each reading, with the expectation's form. Writes nothing |
| **New** | `.\gates\parity\parity-cases.ps1 new routes -Id routes.rest-api.list-books -Tags parity,rest-api -Input rest-api -Probe route_wire_contracts -Selector "{facet: route, verb: get, path: /api/v1/books}" -Expectation "{status: '200', body: page, media-type: application/json}" -Reason "..."` | Validate one authored row against the checks and every committed row, read it on every target, append it to `cases\<area>.parity.yaml`. Refused while the approval gate is armed for the cases directory |
| **Migrate** | `.\gates\parity\parity-cases.ps1 migrate pubsub event_envelopes -Area events -Tags pubsub` | Propose one row per selector the probe's return offers on any target, each with every target's reading and no expectation, under `D:\datrix\.tmp\case-proposals\`. `-Replaces <gate>` names the probe-backed gate the rows replace |
| **Accept** | `.\gates\parity\parity-cases.ps1 accept D:\datrix\.tmp\case-proposals\parity-events-event-envelopes.proposal.json` | Move an approved proposal's rows in; refuses a proposal no `.cases.approved` covers at its current hash, and a row without an expectation. With `replaces`, also deletes that gate's wrapper, its `lib\` module and its section here |
| **Check** | `.\gates\parity\parity-cases.ps1 check` | Every committed row parses, names a probe with readings, a fixture that probe accepts, a facet with exactly its keys and an expectation of its shape, carries documented tags; no id or (input, probe, selector) twice |

**Parameters:** `-Id`, `-Tags`, `-Input`, `-Probe`, `-Selector`, `-Expectation`, `-Reason` (new);
`-Area`, `-Tags`, `-Replaces` (migrate); `-Dbg`

**Every expectation is authored.** `observe` and `migrate` print and propose readings and never
write an expectation; `accept` refuses a row without one. A proposal is approved exactly as a case
proposal (`<name>.cases.approved` in the approval-gate directory, from Jon's terminal), and while
the gate is armed for `gates\parity\cases` a row reaches it only through `accept`.

**Exit codes:** 0 = done and clean, 1 = refused or problems found, 2 = usage error.

---

## `gates\parity\response-body-transform-census-gate.ps1`

The response-bodies parity rows (`cases\response-bodies.parity.yaml`) read each language's emitted
response classes, so a transform applied after serialization (a global interceptor, a
response-model setting that changes field names) is invisible to them. Each registered language
declares the regular expressions that spell such a transform in its framework
(`LanguageCapabilityDeclaration.response_body_transform_idioms`, required and non-empty); this gate
generates the CQRS example (`datrix/examples/02-features/03-infrastructure-blocks/cqrs/`, profile
`test`) once per registered language and greps the generated tree for them. Every hit must be a
typed `transform_exemptions` entry in `scripts/config/response-body-transform-exemptions.json`
(`{language, path_suffix, matched_text, reason}`) -- the TypeScript `MetricsInterceptor`
registration (`APP_INTERCEPTOR` in `src/app.module.ts`), which never touches the body, is the one
entry. An unexempted hit, an exemption that matches nothing, an exemption naming an unregistered
language, and a language with no declaration each fail by name. The review file is refused if it
carries any key other than `_comment` and `transform_exemptions`: a response-body field that
diverges from the camelCase rule has no review shape. A census over generated text; it imports no
conformance probe. Language set from the installed `datrix.languages` entry points.

**Self-test, every invocation.** The gate names no target; a planted `useGlobalInterceptors(` line
is reported at `src/main.ts:2` while a clean `useGlobalPipes(` line is not; an exemption covers the
hit, an exemption covering nothing is stale, and one covering a hit is not; a language with no
capability declaration is refused by name; the review file parses its real shape and refuses a
per-schema-kind `exemptions` list, a non-object entry and a blank reason; fewer than two languages
refuse the run.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\parity\response-body-transform-census-gate.ps1` | Generate the CQRS example for every registered language and census its tree |
| **Debug** | `.\gates\parity\response-body-transform-census-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\gates\parity\response-body-transform-census-gate.ps1 -SelfTest` | Run only the self-test; skip generation |

**Parameters:** `-Dbg`, `-SelfTest`

**Exit codes:** 0 = every hit is reviewed and no entry is stale (or a successful `-SelfTest`), 1 = an
unreviewed hit, a stale entry or a language with no declaration, 2 = the self-test failed, fewer than
two languages are registered, or the review file is missing or malformed.

---

## `gates\parity\type-mapping-completeness.ps1`

Two independent checks over the language type-mapping surfaces, both run on every invocation:

1. **Canonical-type completeness** — every canonical type in `TypeRegistry` has a mapping in
   each requested language's `TYPE_MAP` (`global_registry.unmapped_types`). Restricted by
   `-Languages` when given; defaults to every registered `datrix.languages` target (derived at
   runtime from the installed entry points — never a hardcoded literal). **SQL is not covered by
   this leg** — it is not a `datrix.languages` plugin and its `type_mappings` module does not
   register with `global_registry`.
2. **Extension-map completeness** — for every installed `datrix.extensions` pack, every
   registered language's `*_EXTENSION_MAPS` dict (`PYTHON_EXTENSION_MAPS`, `TS_EXTENSION_MAPS`,
   ...) **and SQL's** (`SQL_EXTENSION_MAPS`) must carry a
   key for that pack's name — an entry present but empty is correct for a pack contributing zero
   scalars. This leg is unconditional: `-Languages` never narrows it. SQL's map is a shared SQL
   fact in the codegen kernel (`datrix_codegen_kernel.sql_facts.type_mappings`), read directly,
   not via `datrix.languages`.

**Built-in non-vacuity self-test, every invocation.** Before any real check is trusted, the script
feeds the extension-map comparator a synthetic surface that DOES carry a synthetic pack's key
(must report zero missing) and a synthetic surface that does NOT (must report exactly that pack
missing); a comparator that cannot detect the forced gap aborts (exit 2) before either real check
runs.

| Mode | Command | Description |
|------|---------|-------------|
| **Both checks, every registered language** | `.\gates\parity\type-mapping-completeness.ps1` | Canonical-type check over every registered language + extension-map check over every registered language and sql |
| **Restrict canonical-type check** | `.\gates\parity\type-mapping-completeness.ps1 -Languages python,typescript` | Canonical-type check limited to the named languages; extension-map check still covers everyone |
| **Debug** | `.\gates\parity\type-mapping-completeness.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\gates\parity\type-mapping-completeness.ps1 -SelfTest` | Run only the extension-map comparator's non-vacuity self-test; skip both real checks |

**Parameters:** `-Languages` (comma-separated subset of the REGISTERED `datrix.languages` set;
optional — omit for every registered language; restricts the canonical-type leg only), `-SelfTest`,
`-Dbg`

**Assertions:** canonical-type leg — `global_registry.unmapped_types(language)` is empty for every
requested language. Extension-map leg — `compare_extension_map_completeness` reports zero missing
packs for every surface (every registered language + sql).

**Exit codes:** 0 = both checks pass (or a successful `-SelfTest` run), 1 = either check found a
gap, 2 = the non-vacuity self-test failed, no languages are registered/requested, or a
discovery/import error occurred.

---

## `gates\parity\supported-domain-parity-gate.ps1`

Two checks, in order, both against a live-computed universe never a fixed count quoted here (the universe grows as domains are added — run the gate for its live output):

1. **Domain-universe closure.** Before checking declarations, computes the union of every registered language's COMPILED DAL generator IR domain ids (`get_definitions(<lang>)`, read directly — independent of any declaration a plugin later commits) and asserts it equals `datrix_codegen_common.parity.domain_registry.SHARED_CONTEXT_TYPES.keys()` exactly. A domain id some language's compiled IR declares but the registry omits fails naming the declaring language(s); a registry id no registered language's compiled IR declares fails as a dead entry (dead surfaces are deleted, never deprecated in place). Zero tolerance, no exemption file — this check short-circuits the gate (exit 1) before the declaration-presence check runs, since a wrong universe makes that check meaningless.
2. **Per-language declaration presence.** EVERY registered `datrix.languages` plugin must declare every STRUCTURAL domain id (`datrix_codegen_kernel.parity.domain_ids.STRUCTURAL_DOMAIN_IDS`) and nothing outside the full registration universe (`SHARED_CONTEXT_TYPES`). `discovery` and `resilience` keep their DAL generator registration but carry no structural-pattern obligation: no language is required to declare either, and a language that does is not reported out-of-universe. The gate reads only membership (`domain_id in plugin.domain_declarations`) and a declaration's `structural_pattern`. A structural id a language does not declare, or an out-of-universe declaration, is a fail-loud `DECLARATION PRESENCE VIOLATION` naming the language and the id; a domain a language does not realize is accounted for only by that language's own `domain:<id>` gap row (logged as a `TRACKED GAP` line; a row for a declared domain (stale) or for a non-structural id (unknown) fails the gate). Derives its target LANGUAGE set from `importlib.metadata.entry_points(group="datrix.languages")` at runtime — never a hardcoded language literal — so a future `datrix-codegen-<lang>` package is covered automatically with no edit to this gate. This is a presence check, never an agreement check: languages may emit a domain to different globs.

On success, the gate prints, for every STRUCTURAL domain id, each registered language's declared `structural_pattern` (or `no structural pattern`) as `DECLARATION: <lang>.<id> = ...`, then a divergence block listing the languages that declare a structural id with no structural pattern or do not declare it. `discovery`/`resilience` appear nowhere in the report. The report is diagnostic and never itself a failure condition.

**The MariaDB engine boundary needs no special-case code** — it is an engine choice inside the `rdbms`/migration domains, not a withheld domain, so it never shows up as a domain-id-level diff at all (this script compares at `domain_id` grain, coarser than per-engine).

**Built-in non-vacuity self-test, every invocation.** Before any real comparison is trusted, the script runs two self-tests: one feeds the domain-universe closure comparator a synthetic matching registry/compiled-IR pair (must report zero divergence), a synthetic compiled id absent from the registry (must be reported, naming the declaring language), and a synthetic registry id no synthetic language declares (must be reported as a dead entry); the other feeds the declaration-presence comparator a complete synthetic declaration table over the structural ids (must report zero findings), a synthetic language omitting one structural id (must be reported, naming that language and id), a synthetic language declaring an out-of-universe id (must be reported, naming that language and id), and a synthetic language declaring the non-structural id (must be neither reported nor required). Either self-test failing aborts the gate (exit 2) before any real comparison runs. Fails loud (exit 2) if fewer than 2 languages are registered — a cross-language comparison over 0 or 1 language is vacuous.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\gates\parity\supported-domain-parity-gate.ps1` | Check domain-universe closure and every registered language's declaration presence |
| **Debug** | `.\gates\parity\supported-domain-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\gates\parity\supported-domain-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Exit codes:** 0 = the domain-universe closure holds and every registered language declares every structural domain id, 1 = a domain-universe closure violation was found (checked first) or a declaration-presence violation was found for at least one language, 2 = a non-vacuity self-test failed or fewer than 2 languages are registered.

---

## `gates\parity\behaviour-parity-gate.ps1`

**Replaces the retired name-keyed drift report on the language axis.** AST-walks the `src/`
tree of every package implementing each registered target -- the package registering its
entry point plus every `<backend>-core` distribution it requires, derived from the installed
requirements (`datrix_testing.target_distributions`), never a hand list -- and groups functions into **roles** — a *signature
role* (shared-typed parameter/return annotations from `datrix_common`/`datrix_codegen_common`)
or, for functions with no shared-typed parameter, a *normalized-name role* (bare name with each
language's own declared `name_tokens` stripped) — so a language token inside a name can never
hide a parallel implementation. Each role's members are compared by **behaviour skeleton**
(`if`/`for`/`while`/comprehension/`return`/`raise` structure, `try`/`except`/`with` structure,
and parameter arity, model-rooted predicates and calls preserved, every other literal collapsed)
rather than by verbatim text, and classified `identical`, `same-behaviour` (skeletons and arity
equal, bodies differ), or `divergent`. A per-target difference in behaviour is a defect with N
copies, never a choice; only rendering differs per target. **Arity is role-level:** a parameter
name ANY member of a role drops as language-private plumbing is dropped for every member sharing
that name, so a language whose own file-scope subclass happens to live inside the shared layer
does not count a parameter its sibling languages drop.

**Two buckets that fail by shape, one that fails by skeleton groups:**
- `identical` / `same-behaviour` fail unless every member is a **pre-binding adapter** (a single
  `return` of a call into the shared codegen layer — `datrix_codegen_common` or
  `datrix_codegen_kernel`, never a language package or a language core such as
  `datrix_codegen_typescript_core` — recognized by AST shape only; no written exemption list).
- `divergent` is judged **without a reference language**: the role's member packages are
  partitioned into **skeleton groups** (packages whose contributed skeleton sets are equal share
  a group); the role passes iff there is at most one group, and otherwise fails with one reason
  naming every group (e.g. `members split into 2 skeleton groups: {python} vs {typescript}`) —
  the gate cannot know which group is right, so it names all of them. No package is ever set
  aside: no domain stance, builtin-group stance, emission-trigger declaration, capability
  declaration or `capability_gaps` row is an input to the verdict, so a capability a target does
  not realize, or realizes under a different trigger, leaves its roles failing and counted. A
  role the gate cannot classify (unparseable member, unresolvable annotation) is
  reported as a **failure naming the member** — never skipped.
- The `identical`/`same-behaviour` shape exemption also covers a **rendering leaf**: a body with
  no branch/loop/`try`/`with`/comprehension/`raise`, no attribute chain rooted at `self`, a
  shared-typed or unannotated parameter, or a derived root sourced from one of those (a chain
  rooted at a language-private parameter, or at a derived root sourced only from such reads, is
  exempt — it is never a model root by the same rule the arity count already applies), and every
  call resolving to the shared codegen layer or the standard library — reported
  `rendering-leaf-exempt` beside `adapter-exempt`.

**Every role is in scope; the verdict is a pinned, two-directional failing-role count.** No
file, flag or domain id narrows the measured population: every bucket, every domain, and every
role the domain ladder resolves to `undomained` is evaluated and counted. The gate compares the
number of failing roles with `[languages].failing_roles` in
`datrix/scripts/config/behaviour-parity-baseline.toml` and exits 0 only on an exact match. More
failing roles than the pin fails (a regression); FEWER failing roles than the pin fails too,
unless the pin is lowered in the same change (an improvement must be banked — no other ratchet in
this repo fails on an unpinned decrease). The failure message names the direction, the delta and
the live split. The `[languages.buckets]` counts split the failing roles by verdict
(`identical`/`same_behaviour`/`divergent`); they are diagnostic — a stale split logs a WARNING and
never moves the exit code. The loader refuses a missing, unreadable or malformed file, an
unrecognized top-level section or key (naming the file and the key), and a non-integer or
negative count. Seed or lower a pin from the gate's own `BEHAVIOUR-PARITY GATE: N role(s) FAIL
(...)` line (`-Dbg` also lists every role), never from a document. The platform axis has no
section.

**`-Scope` / `-Buckets` are report filters only.** They choose which role lines the report
prints (a role prints when its domain and its verdict satisfy every filter given), print a
`BEHAVIOUR-PARITY REPORT FILTER` line, and never change the failing-role count, the ratchet
comparison or the exit code. An unknown id is a usage error naming the valid options, and both
are refused on a `--report-only` run.

**Non-vacuity is enforced on every run.** A synthetic five-bucket tree (one identical role, one
same-behaviour role, one divergent role, one role split only by a language token, one role
unified only by shared-typed signature) must land in exactly its bucket, a single-target tree
must be refused, a two-group divergent role must fail naming both groups, a divergent role whose
package would once have been declared unsupported or on-demand (or whose member is an
`@emit_adapter` over an unsupported builtin group) must still fail, the module's own AST must
import, name and read none of the retired declaration types or the on-demand table, an `undomained` failing role must be counted by the failing-role count
and the ratchet, a live count above the pin and a live count below it must each fail while an
exact match passes, the baseline loader must refuse an unrecognized key naming the file, a report
filter must change the printed lines and not the verdict, and the bucket labels printed must be
exactly `identical` / `same-behaviour` / `divergent`. A fixture language split into a backend
and a core must resolve both packages under one label, a function planted only in the core must
be compared as that language's member, and the core must never land in the "other package" set
whose bare names exclude name roles (fed as one, the role is excluded). The fingerprint pass's own non-vacuity is
checked the same way: a renamed cross-language pair must be reported, and a covered pair (same
name in both packages), an under-size pair, a no-model-attribute-read pair, and a pair of renamed
copies inside one package must not.

**The platform axis (`-Axis platforms`) gates against its own `[platforms]` pin** in
`behaviour-parity-baseline.toml`, exactly like the language axis. Before the signature and
normalized-name keys it tries COORDINATE role keys: every cell of a platform's own
`RealizationTable`s (loaded from its `realization.dal` by `load_realization_tables`, whose result
the package binds to a module-level name) binds a `plan_builder` and its `emitters` (the
functions that emit the cell's IaC); those seed the key, and every function of the same package a
seed statically reaches (calls and function values resolved through imports, `self`/`super()`,
instance attributes and annotated receivers -- never text) joins the seed's block-type role. Flavors
of one block type fold into one role; a function reached from several block types (a uniform
builder, a shared helper) is a member of each; a bound method or one-delegate closure adapter
resolves to the function holding the behaviour. A cell bound to `ScaffoldRuntimeRealization` (its
artifact is emitted by the docker-compose scaffold platform, e.g. azure-vm's self-hosted cells)
seeds only its plan builder. Before scanning, every declared emitter must be reached from its
platform's generator (the `datrix.platforms` entry-point class's methods plus every function its
compiled DAL generator definitions reference) and every scaffold delegation must land on a scaffold
cell that binds emitters; a platform whose tables cannot be located or imported, a seed outside
its package, an unreached emitter or an unrealized delegation fails the run (exit 2) rather than
falling back to name keys. The self-test asserts a floor of live coordinate roles spanning at
least two platform packages.

**Fingerprint pass (report-only, `-Fingerprint`).** The role/name grouping above only compares
functions that already share a signature or normalized-name role; a parallel implementation each
language wrote under an unrelated name, with no shared return type, lands in a single-package
role and is never compared. `-Fingerprint` adds a second, independent pass over exactly those
uncovered functions — members of a role with fewer than 2 distinct member packages, minus
pre-binding adapters and rendering leaves — grouping them across packages by a **behaviour
fingerprint**: the function's control shape (the ordered statement heads a skeleton renders —
`if`/`for`/`return`/… — with every predicate, chain and operand dropped) paired with the set of
model attribute names it reads (every `.attr` access rooted at a parameter or a derived root,
never through `self` and never through a plain local). A skeleton under
`FINGERPRINT_MIN_SKELETON_LINES` (6) lines, or a function reading no model attribute, is never a
candidate. A surviving cross-package group is judged by the same `identical` / `same-behaviour` /
`divergent` verdict rules a name/signature role uses — no second classifier — and labelled
`match` (every member's skeleton text equal) or `near-match` (same shape and attributes, at least
one member's skeleton text differs). The pass never reaches the exit code, the baseline, or the
report filters; it becomes gated only once its first measurement is worked down.

**The language axis also covers every `transpiler_profile`-bearing frontend-client renderer.**
Beside every `datrix.languages` package, the language axis compares every registered
`datrix.generators` package whose native generator class declares a non-`None`
`transpiler_profile` on its `PluginDescriptor` (angular/flutter once their own tasks land
— none do yet, so today's scan is unaffected). Its name-token vocabulary comes from its
`ClientTargetCapabilityDeclaration.name_tokens`, resolved only after no `datrix.languages`
plugin answers to the same name — never guessed from the bare registered name alone. The
`.ps1` wrapper and its flags are unchanged; only the underlying `--axis languages` scan widens.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\gates\parity\behaviour-parity-gate.ps1` | Language axis: the failing-role count against its pinned baseline, in both directions |
| **List every role** | `.\gates\parity\behaviour-parity-gate.ps1 -Dbg` | Debug logging; also prints every passing role (failing roles always print) |
| **Filter by domain** | `.\gates\parity\behaviour-parity-gate.ps1 -Dbg -Scope queue,cache` | Print only these domains' role lines (add `undomained` to see those); never changes the exit code |
| **Filter by bucket** | `.\gates\parity\behaviour-parity-gate.ps1 -Dbg -Buckets identical` | Print only these verdict buckets' role lines (identical, same-behaviour, divergent); never changes the exit code |
| **Platform axis** | `.\gates\parity\behaviour-parity-gate.ps1 -Axis platforms` | Failing-role count against the `[platforms]` pin, both directions; exit 0 on exact match, 1 otherwise |
| **Fingerprint pass** | `.\gates\parity\behaviour-parity-gate.ps1 -Fingerprint` | Also report cross-package skeleton-fingerprint groups among functions no role covers (report-only; exit code unchanged) |
| **Self-test only** | `.\gates\parity\behaviour-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test |

**Parameters:** `-Axis <languages|platforms>` (default: languages), `-Scope <id,...>`, `-Buckets <id,...>`, `-Dbg`, `-SelfTest`, `-Fingerprint`

**Exit codes:** 0 = the failing-role count equals its pin (or a successful `-SelfTest`),
1 = the count differs from its pin (above it: a regression; below it: an improvement whose pin was not lowered in the same change),
2 = usage/discovery/parse error, an unreadable or malformed baseline, or the self-test failed.

---

## `gates\parity\shared-home-body-gate.ps1`

A function with a shared home has exactly one definition. The homes are `datrix-common`,
`datrix-codegen-kernel` and `datrix-codegen-common`; a private copy elsewhere is usually a renamed
one, so this gate compares **normalized bodies**, not names or text (the sibling hoist tests prove a
copy is gone by name; Pylint's similar-lines check is textual and misses a renamed copy).
The walker (`datrix_scripts.function_sources`) and the normalization (`datrix_scripts.body_digest`)
are shared with `scan\find-duplicate-bodies.ps1`, which reports every duplicate group anywhere. That
includes copies the gate does not pin, such as two private copies in two target packages, or a copy
of a private home helper.

**What a hit is.** The gate AST-walks every public function of the three homes (no segment of the
qualified name starts with `_`) and every function, public or private, of every discovered
`datrix-*` package's `src/` tree. A function qualifies at **8 lines and 40 AST nodes** (measured on
the docstring-free body; the floor removes Protocol `...` stubs and one-line accessors). Its body is
normalized: the function's own name, decorators, annotations and docstring are dropped; every
parameter and locally bound name becomes a positional token; every constant collapses to its type
name; **attribute names, keyword-argument names and non-local call targets are kept**, so two
functions that read different attributes or call different functions never compare equal. A function
in package P is a hit when its normalized body equals a public home function's in a package other
than P. The rule is symmetric across homes: when two public home functions in different home
packages are duplicates, both are hits (deleting one clears both); equal bodies inside the same
package are not hits.

**The verdict is a decrease-only per-package count** pinned in
`datrix/scripts/config/shared-home-body-baseline.toml`: `[[baseline]]` entries with exactly the keys
`package` (import name), `count`, `seed` and `reason`. A live count above its `count` fails; a
decrease passes and logs the command to lower the pin. A package with no entry is pinned at 0.
`seed` is the first measurement and never changes (the closing check proves each package's count
strictly below its seed). The loader refuses a missing or malformed file, an unrecognized key, a
duplicate package, a negative or non-integer count, `count > seed` and an empty `reason`.

**Self-test, run first on every invocation.** On a fixture tree under `D:\datrix\.tmp`: a planted
renamed copy raises its package's count by exactly 1 and the ratchet message names the package, the
live count and the pin; reverting clears it; docstring-only and constant-only differences are hits;
attribute-name and call-target differences are not; a below-floor pair and a copy of a private home
function are not; same-package equal bodies are not hits and a cross-home pair counts symmetrically;
the ratchet verdicts (above, below, no entry, unknown package); the baseline round trip (seed,
load, lower, refuse a rise, refuse each malformed form); and an unparseable source file fails the
scan naming the file. Run `-Symbol <name>` over the real tree to confirm a known real renamed copy is
found.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\gates\parity\shared-home-body-gate.ps1` | Per-package duplicate count against the decrease-only pin; exit 0 when no package exceeds its pin |
| **List every hit** | `.\gates\parity\shared-home-body-gate.ps1 -Hits` | Print every `SHARED-HOME BODY HIT:` line (copy location and name == home location and name) |
| **Check named copies** | `.\gates\parity\shared-home-body-gate.ps1 -Symbol event_for_replay_plan,_iter_calls` | Print only the hit lines whose copy has one of these bare names; `0 hit line(s) shown` proves a removed copy is gone. A report filter only |
| **Seed / lower the pin** | `.\gates\parity\shared-home-body-gate.ps1 -UpdateBaseline` | Seed the baseline when the file does not exist (`count = seed = measured`); otherwise lower every `count` to the live value, keeping `seed` and `reason`. Refuses (exit 1, file untouched) when any count would rise |
| **Debug logging** | `.\gates\parity\shared-home-body-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\gates\parity\shared-home-body-gate.ps1 -SelfTest` | Run only the plant / observe / revert self-test |

**Parameters:** `-Hits`, `-Symbol <name,...>`, `-UpdateBaseline`, `-Dbg`, `-SelfTest`

**Exit codes:** 0 = no package exceeds its pin (or a successful `-SelfTest` / `-UpdateBaseline`),
1 = a package's count is above its pin, or `-UpdateBaseline` was refused because a count would rise,
2 = the self-test failed, the baseline is unreadable or malformed, a source file cannot be parsed,
or a home package is missing from disk.

---

## `gates\parity\observability-axis-parity-gate.ps1`

Cross-target observability-AXIS parity gate: proves every registered language agrees with the platform axis about which observability categories a language may realize. Exists because two generation-breaking defects shipped with every per-package conformance suite green — a language declaring it realized providers in a category only the PLATFORM provisions (so the same config generated on one language and failed generation on another), and the language-axis validator policing a platform-only category (so a provider the resolved platform natively realizes and actually provisions was rejected for every project on that language). Both are **cross-target** consistency defects, which per-package conformance cannot detect by construction: each package validates its own declaration in isolation, so all of them stay internally green while disagreeing about the same portable field. Target sets come from the installed `datrix.languages` / `datrix.platforms` entry points at runtime — never a hardcoded language or provider literal — so a new package is covered with no edit here.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\gates\parity\observability-axis-parity-gate.ps1` | Both legs, every registered language × platform |
| **Debug** | `.\gates\parity\observability-axis-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\gates\parity\observability-axis-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- **Leg 1 (declaration identity).** Every registered language declares exactly the empty set for every category in `PLATFORM_ONLY_OBSERVABILITY_CATEGORIES` — a non-empty claim is how the same config generates on one language and fails generation on another.
- **Leg 2 (validator agreement).** For each in-scope category, **every** provider at least one registered platform declares native must validate cleanly against **every** registered language. All providers are checked, not a representative: the original defect was one specific provider being rejected, which a single-representative check misses whenever another sorts first.

**Leg 2's scope is derived from the declarations, never from `PLATFORM_ONLY_OBSERVABILITY_CATEGORIES`** — it is the set of categories some platform realizes and **no** language realizes. Scoping it by that constant would make the gate blind to the exact defect the constant can have: dropping a category from it would silently drop the category from the check too, so reintroducing the original rejection defect passes unnoticed. This was not theoretical — the first revision of this gate did scope leg 2 by the constant, and a mutation test proved it passed green with the real defect planted.

**Non-vacuity self-test runs as step 1 of every invocation** (self-test failure aborts before any real comparison, exit 2). Leg 1's comparator must detect a synthetic language claiming a platform-only provider and must not fire on a clean one. Leg 2's check must still observe the validator **reject** an unrealized provider in a language-realizable category — otherwise a neutered validator would make leg 2's clean result vacuous.

**Exit codes:** 0 = both legs hold, 1 = an axis violation was found, 2 = the non-vacuity self-test failed, or too few registered targets (no language, no platform, or no category in leg 2's derived scope) for a non-vacuous comparison.

---

## `gates\parity\manifest-import-parity-gate.ps1`

Manifest / import parity gate: for every `datrix-*` package at the workspace root carrying a `pyproject.toml`, the `datrix-*` distributions its `[project] dependencies` declare must equal the `datrix_*` import roots its `src/` tree actually imports (mapped by the `_` → `-` spelling every package uses). `imported − declared` is an undeclared dependency; `declared − imported` is a dead declaration; a runtime requirement carrying a test-only extra (`[testkit]`, `[dev]`, `[testing]`) drags a test surface into production. All three are violations, and the gate is a **hard zero** with no baseline — there is no legitimate steady state in which a manifest disagrees with the import set. Exists because the shared editable venv makes every package importable from every other, so a manifest can lie in either direction with every suite green (a package documented as fenced out of `datrix-codegen-common` imported it from twelve production modules; a platform package ran on an undeclared dependency; three language packages carried a dead dependency; one pulled `[testkit]` into production). `TYPE_CHECKING`-only imports count: a type-checking install needs the package too. The package set is discovered from disk, never a hardcoded list.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\parity\manifest-import-parity-gate.ps1` | Compare every `datrix-*` package's manifest against its `src/` imports |
| **Debug** | `.\gates\parity\manifest-import-parity-gate.ps1 -Dbg` | Debug logging (prints each package's declared and imported sets) |
| **Self-test only** | `.\gates\parity\manifest-import-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- For every discovered package, `imported − declared = ∅` and `declared − imported = ∅` over Datrix distributions, and no `[project] dependencies` entry naming a Datrix distribution carries a test-only extra. An import satisfied only by one of the package's **own** non-dev extras (for example `datrix-codegen-common`'s `testkit/` subtree importing `datrix-language`, declared by its `[testkit]` extra) is a declared optional dependency: logged, never a violation. A `dev`/`testing` extra never satisfies a `src/` import.
- Non-vacuity self-test (every invocation): a synthetic dirty package yields exactly its five planted violations (one plain undeclared import, one `TYPE_CHECKING`-only undeclared import, one import declared only by a `dev` extra, one dead declaration, one test-only extra) while its import declared by a non-dev extra is not reported; a synthetic clean package yields none; a workspace with fewer than two packages is refused; and the **live** scan sees every package registering `datrix.languages` import `datrix-codegen-common` — a real edge, so the scanner is proven against the tree it guards, not only against fixtures.

**Exit codes:** 0 = every manifest agrees with its imports (or a successful `-SelfTest`), 1 = a violation was found, 2 = the self-test failed, fewer than two packages were discovered, or a manifest/module could not be parsed.

---

## `gates\parity\third-party-dependency-parity-gate.ps1`

Third-party dependency parity gate: for every `datrix-*` package with a `src/` tree, the **third-party** distributions its `[project] dependencies` declare must equal the third-party distributions its `src/` tree imports (`ast`, nested imports included, mapped to distributions through the installed metadata via `importlib.metadata.packages_distributions`). `imported − declared` is an undeclared dependency that works here only because something else installed it into the shared venv; `declared − imported` is a dead declaration. Extras other than `dev` are optional runtime surfaces (a shipped `testing` helper subpackage, an `lsp` server) that may satisfy a `src/` import; the `dev` extra never does. A root several distributions provide (`ruamel`) is satisfied by any declared candidate; a root no installed distribution provides is itself a violation. A distribution the package **invokes as a subprocess** rather than imports is a reviewed executable exemption in `datrix/scripts/config/third-party-dependency-exemptions.json` (package + distribution + reason; a stale entry fails the gate) — a distribution merely used by the projects the package generates is never exempted. The sibling `manifest-import-parity-gate.ps1` holds the same invariant for the Datrix distributions. Exists because four packages imported a password hasher no framework manifest declared (present only because generated customer projects installed into the venv required it), five packages declared a template engine only a sixth (undeclared) imported, and one generator declared the web framework and ORM of the projects it generates.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\parity\third-party-dependency-parity-gate.ps1` | Compare every `datrix-*` manifest's third-party dependencies against its `src/` imports |
| **Self-test only** | `.\gates\parity\third-party-dependency-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |
| **Show files** | `.\gates\parity\third-party-dependency-parity-gate.ps1 -ShowFiles` | Print each package's declared set as it is scanned |
| **Debug** | `.\gates\parity\third-party-dependency-parity-gate.ps1 -Dbg` | Print the python invocation |

**Parameters:** `-BaseDir <path>`, `-SelfTest`, `-ShowFiles`, `-Dbg`

**Assertions:**
- For every discovered package, `imported − declared = ∅` and `declared − imported = ∅` over third-party distributions, where `declared` is `[project] dependencies` plus every non-`dev` extra and a dead declaration is excused only by a reviewed executable exemption.
- Non-vacuity self-test (every invocation): a planted dirty package yields exactly its four violations (an undeclared import, a `dev`-extra-only import, an import no distribution provides, a dead declaration) while its non-`dev`-extra import, its ambiguous root satisfied by one declared candidate, and its exempted executable are accepted and its stale exemption is left unused; a planted clean package yields none; a workspace with fewer than two packages is refused; and the **live** scan sees at least one real package both declare and import the same distribution.

**Exit codes:** 0 = every manifest agrees with its imports (or a successful `-SelfTest`), 1 = a violation or a stale exemption was found, 2 = the self-test failed, fewer than two packages were discovered, or a manifest/exemption file could not be parsed.

---

## `gates\parity\framework-header-parity-gate.ps1`

Framework header parity gate: every registered language spells the framework-minted HTTP headers from datrix-codegen-common's one registry (`datrix_codegen_common.generation.http_headers` — the trusted-caller token, the three rate-limit response headers, the inbound webhook secret, the outbound webhook delivery headers) and realizes every header family. The gate censuses every `.py` and `.j2` source under the `src/` tree of every package implementing each registered language (its backend plus each language core the backend requires) for `X-`-prefixed header tokens and registry-constant references; a spelling records the package it lives in, which is what an exemption keys on. **Spelling:** a header under a framework prefix (`X-Datrix-`, `X-RateLimit-`, `X-Webhook-`) is an exact registered name (case-insensitively — Node lowercases header names) or a reviewed, counted entry in `scripts/config/framework-header-exemptions.json`; a retired name (`X-Internal-Token`, `X-Datrix-Delegated-User`) is a violation with no exemption path. **Realization:** every registered language realizes every registered family (the exact name spelled, or its registry constant referenced from python); a family a language does not realize fails naming the language and the family, and no declaration can excuse it; a family no language realizes is a dead registry entry and fails; an unused exemption is stale and fails. Hard zero: any problem exits non-zero and there is no baseline file. Language set from the installed `datrix.languages` entry points; registry read from the packages — never a table in the script.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\parity\framework-header-parity-gate.ps1` | Census every registered language against the registry and the exemption file; prints the family × language realized/MISSING table |
| **Debug** | `.\gates\parity\framework-header-parity-gate.ps1 -Dbg` | Debug logging (per-language spelling and constant-reference counts) |
| **Self-test only** | `.\gates\parity\framework-header-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real census |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- Spelling: `framework-prefixed spellings − registered names − exemptions = ∅`; `retired spellings = ∅`; `exemptions − live spellings = ∅` (no stale entry); every entry carries package, header, a registered family and a non-empty reason.
- Realization, per language: `registered families − realized families = ∅`.
- Registry: every family is realized by at least one language.
- Non-vacuity self-test (every invocation): a planted source tree yields exactly its two template spellings plus one python constant reference (a Markdown file and a `__pycache__` entry are not counted); the comparator reports exactly one problem for a retired spelling, an unregistered framework-prefixed spelling, a stale exemption and an unrealized family (it takes no declaration input that could excuse one), one dead-contract problem for a family nobody realizes, and none for a clean pair, an exempted spelling, a non-framework `X-` header, or a constant-realized family; the exemption parser rejects a miscount, an unknown family, a non-framework header and a reasonless entry; a fixture language split into a backend and a core has a header and a registry constant planted only in the core realized for the language and keyed on the core package; the **live** census finds the caller-token header on at least two languages; a single-language set is refused.

**Exit codes:** 0 = every language passes both rules (or a successful `-SelfTest`), 1 = a violation was found, 2 = the self-test failed, fewer than two languages are registered, or the exemption file is missing/malformed/miscounted.

---

## `gates\parity\problem-type-parity-gate.ps1`

Problem-type parity gate: every registered language answers errors with RFC 7807 `type` URNs from datrix-common's one registry (`datrix_common.datrix_model.problem_types` — `urn:datrix:error:<slug>`; a declared DSL exception derives its slug from its class name through the shared exception-declaration algorithm, a framework error uses a registered family) and is obligated to every framework family. The gate censuses every `.py` and `.j2` source under the `src/` tree of every package implementing each registered language (its backend plus each language core the backend requires) for **registry references**, never URN literals: `PROBLEM_<FAMILY>` in a template, `problem_type_for("<family>")` in Python, or a template naming `GENERIC_PROBLEM_FAMILY_BY_STATUS` (which realizes every generic family it carries). **Spelling:** any `urn:datrix:error:<slug>` literal in a language package is a hard problem with no exemption path — the registry renders every URN, and a literal is a second vocabulary. **Realization:** every registered language is obligated to reference every registered family. A (language, family) cell a language does not reference is an *unspelled cell*, printed on every run as `PINNED GAP language=<l> family=<f>` and counted against that language's pin in `scripts/config/problem-type-parity-baseline.toml` (`[languages]` table, `<language> = <count>`; a language absent from the table is pinned at zero; the loader refuses an unrecognized key, a negative count or a bool). A count above the pin fails (`EXCEED`: spell the family, never raise the pin); a count below the pin fails (`BELOW`: lower the pin in the same change); a pin naming an unregistered language is stale. The pin is seeded from a live run and lowered by hand; no script writes it. A family no language spells is a dead registry entry and fails outright, and is never pinned. Language set from the installed `datrix.languages` entry points; registry read from the packages — never a table in the script.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\parity\problem-type-parity-gate.ps1` | Census every registered language against the registry and its pin; prints the family × language realized/MISSING table and every `PINNED GAP` cell |
| **Debug** | `.\gates\parity\problem-type-parity-gate.ps1 -Dbg` | Debug logging (per-language spelling counts) |
| **Self-test only** | `.\gates\parity\problem-type-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real census |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- Spelling: `literal slugs − registered families = ∅`.
- Realization, per language: `len(unspelled families) == pin` (exact match; the pin defaults to zero for a language absent from the baseline).
- Registry: every family is spelled by at least one language.
- Non-vacuity self-test (every invocation): a planted source tree yields exactly its two literal slugs (the bare prefix, a Markdown file and a `__pycache__` entry are not counted); the comparator reports a language spelling only some families as exactly one unspelled cell and zero hard problems, and exactly one hard problem for a private slug and for a family nobody spells; the pin check is clean on an exact match, one `EXCEED` above the pin, one `BELOW` (saying to lower the pin) under it, `EXCEED` against the implicit zero for an unpinned language with one unspelled family, and one stale-pin problem for a pin naming an unregistered language; the baseline loader accepts a well-formed file and rejects an unrecognized key, a missing `[languages]` table, a negative count, a bool, a non-integer, invalid TOML and a missing file; a fixture language split into a backend and a core has a URN planted only in the core censused against the core package (a backend-only census misses it); the **live** census finds the `internal` type on at least two languages; a single-language set is refused.

**Exit codes:** 0 = every language's unspelled-cell count equals its pin and no hard problem was found (or a successful `-SelfTest`), 1 = a violation was found, 2 = the self-test failed, fewer than two languages are registered, or the baseline is missing/malformed.

---

## `gates\parity\field-error-path-parity-gate.ps1`

Field-error-path parity gate: every registered language spells a `request-validation` problem body's `errors[].field` with the ONE shape `datrix_common.datrix_model.problem_types.FIELD_ERROR_PATH_RULE` defines (a dot-separated wire-name path relative to the request body root, no leading `body` segment, `[n]` for array elements). Hard zero: every registered language is obligated to realize the rule and no declaration excuses one. Unlike the problem-type/framework-header registries this is not a family table — there is exactly one rule. Realization is a runtime BEHAVIOUR rather than a literal wire string, so there is no single cross-language regex: each language declares how it realizes the rule on its own `LanguageCapabilityDeclaration.field_error_path_realization`, and the gate dispatches on the declaration TYPE (a closed set of two techniques in `datrix_common.plugin.language_capability`, never a language name), across every package implementing the language (its backend plus each language core the backend requires). An `ExecutedFieldErrorPathFormatter` names a module and function inside the language's own distribution (a module outside its src dirs is a violation, never executed) that the gate imports and EXECUTES against the rule's own canonical worked example, so the produced string is real, not guessed; its optional `located_classifier` is executed too, against a located fixture (a missing path parameter, a wrongly typed query value, an unknown body field), and a path or query entry landing in the wrong `location`, `field` or `code` is a violation. A `TemplateFieldErrorPathConstruction` names a template (relative to the package's import root, in exactly one of the language's packages), the builder's anchor and every construction regex that must be present (bracket-indexed, dot-joined); an anchor present with a construction missing is a divergence naming the missing regex. Both techniques also prove the declared `call_site` matches in the language's `.j2`/`.py` sources — a realization nothing calls is not on the emission path. **Realization:** the declared realization produces the canonical path for the shared fixture with no defect; a language that declares `None` fails naming the language (no declaration says "does not realize" — a language that does not realize the rule fails until it does); a found but divergent construction (a literal `body` prefix, or an index not spelled `[n]`) fails naming the found and expected spelling. Language set from the installed `datrix.languages` entry points — never a table in the script.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\parity\field-error-path-parity-gate.ps1` | Census every registered language's construction technique against the canonical rule; prints the language realized/MISSING table |
| **Debug** | `.\gates\parity\field-error-path-parity-gate.ps1 -Dbg` | Debug logging (per-language site counts) |
| **Self-test only** | `.\gates\parity\field-error-path-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real census |

**Parameters:** `-Dbg`, `-SelfTest`

**Assertions:**
- Realization, per language: the census produces the canonical path; an empty census is a failure.
- Non-vacuity self-test (every invocation): the gate names no registered target (`datrix_scripts.registered_targets.self_test_gate_names_no_target`); a planted correct executed formatter's real execution produces the canonical path, a planted divergent one surfaces its actual wrong output; a planted correct template-constructed builder censuses as canonical, one missing the `[n]`-index construction censuses as divergent; a language with no known detector censuses to zero sites; a fixture language split into a backend and a core has a realization planted only in the core censused against the core package; the comparator reports exactly one problem for a divergent spelling and for a language that realizes nothing (it takes no declaration input that could excuse one), and none for two languages spelling the canonical path; the **live** census finds at least one registered language realizing the rule; a single-language set is refused.

**Exit codes:** 0 = every language realizes the rule (or a successful `-SelfTest`), 1 = a violation was found, 2 = the self-test failed or fewer than two languages are registered.

---

## `gates\parity\artifact-role-parity-gate.ps1`

Artifact-role parity gate, cross-language and cross-provider: detects a language (or a provider) silently emitting nothing for a construct another language (or provider) realizes, without generating anything and without storing anything. It reads the generation pipeline's own per-target manifests (`.datrix/manifests/<target>.json`: the files each target wrote, plus a `generated_at` stamp) from the example trees `generate.ps1` writes under `<workspace>/.generated/<language>/<runtime>/<provider>/<example>/`. **There is no committed baseline and no bless step** -- see `datrix/docs/architecture/generated-output-stability.md`.

**Language axis.** For every `(example, runtime, provider)` generated in >= 2 registered languages, each language's paths are classified by domain role via that language's own derived `DomainDeclaration.structural_pattern` set (a domain is realized exactly when its declaration carries a pattern), and the role set must be identical across those languages. A missing role is a failure. EXACTLY ONE skip exists, and it reads no declaration and no committed exemption: the domain's own pattern matches nothing anywhere in that language's ENTIRE generated footprint (corpus-vacuous). It is never silent: every corpus-vacuous `(language, domain)` must carry a typed, counted record in `scripts/config/corpus-vacuity-records.json` saying why nothing exercises it. A language that emits a domain under a narrower DSL trigger than another language (for example, a service-level `fn` file only for the service's own `fn` declarations, where another language also folds `rest_api`-scoped `fn`s into it) is reported: the same source produced a different artifact set. A language that realizes a domain by NO structural pattern is never excused either: the gap is tracked once, as a `capability_gaps` row on its own capability declaration and counted by the capability-gap ledger gate, and this gate reports the missing role regardless of whether a row exists. Paths matching no pattern are reported in an "unclassified" bucket but never compared -- template-level naming legitimately differs by language; the role SET is the contract.

**Provider axis.** The same comparison then runs for a fixed language: for every `(language, example, runtime)` generated under >= 2 providers, each provider's role set must be identical. A role present under one provider and absent under another is reported as `ARTIFACT-ROLE CROSS-PROVIDER DRIFT`, naming the language, example, runtime, the provider missing the role and the providers that have it. The same corpus-vacuity skip applies, plus one skip the provider axis alone has, read from the platforms' own capability declarations: a **platform-gated** domain -- one `datrix_codegen_kernel.parity.platform_gated_domains.PLATFORM_GATED_DOMAINS` links to the capability predicate its emission path calls (`cdn` → `provides_cdn_cache_invalidation`) -- is not drift when the lacking provider's platform answers False for that capability and every provider carrying the role answers True. Each such skip is logged (`artifact_role_platform_withheld`). The provider segment is resolved through `declaration_for_provider`, the same key generation resolved the platform by; a segment no registered platform answers to stops the gate (exit 2). A `capability_gaps` row never stands in for that answer: a platform that does not offer the capability is declaring its topology, not a hole, and a gap row suppresses nothing here. Below two providers there is nothing to compare, so a single-provider corpus yields no provider-axis comparison (a no-op, not an error); the self-test is what proves the axis live.

**Platform-gate seam check.** The skip is held to the output it excuses: every tree carrying a role its own provider's platform withholds fails as `ARTIFACT-ROLE PLATFORM-WITHHELD ROLE EMITTED`, naming the tree, the domain and the capability -- the platform declaration, the domain's table entry or the emitting generator is wrong. This runs over every tree, so it is live on a single-provider corpus.

**The gate is exactly as current as the local corpus, and refuses an incomplete one.** It prints every language's oldest and newest `generated_at` stamp, and exits 2 before comparing anything when any registered language has a registered example with no generated tree and no entry in `scripts/config/parity-known-nongenerating.json` -- naming every missing pair and the command that fills it (`generate.ps1 -All -L <language>`, once per registered language; Jon runs this, it is blocked for agents). A parked pair that DOES have a generated tree is a stale park entry and also fails: the recorded defect is fixed, delete the entry.

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\parity\artifact-role-parity-gate.ps1` | Compare role sets for every `(example, runtime, provider)` generated in >= 2 languages, and for every `(language, example, runtime)` generated under >= 2 providers, under `<workspace>/.generated` |
| **Explicit output base** | `.\gates\parity\artifact-role-parity-gate.ps1 -GeneratedRoot D:\datrix\.generated` | Same, reading a named `generate.ps1` output base |
| **Debug** | `.\gates\parity\artifact-role-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\gates\parity\artifact-role-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test (one `[OK]` line per proven case); skip the real comparison |
| **Corpus-vacuity census** | `.\gates\parity\artifact-role-parity-gate.ps1 -Census` | Print every `(language, domain)` the generated corpus exercises nowhere, with its reviewed status; exit 0 (exit 2 on an incomplete corpus) |

**Parameters:** `-GeneratedRoot` (default: `<workspace>/.generated`), `-Dbg`, `-SelfTest`, `-Census`

**Assertions:**
- Every registered language's corpus is complete: each `system.dtrx` under `datrix/examples/` has a generated tree (a directory carrying `.datrix/manifests/*.json`) or a park entry; no parked pair has a tree.
- Every `(example, runtime, provider)` generated in >= 2 registered languages is compared, and every `(language, example, runtime)` generated under >= 2 providers is compared.
- A domain role present (>= 1 matching path) in one language's generated tree for an example and absent from another language's tree for the SAME `(example, runtime, provider)` is a violation, UNLESS the domain's pattern matches nothing across that language's entire generated footprint (`_is_corpus_vacuous_for_language`). No declaration and no committed per-example file excuses a missing role; a language holding no declaration for the domain is not excused.
- A role present under one provider and absent under another, for the same language, example and runtime, is a violation under the same corpus-vacuity skip, unless the role is platform-gated, the lacking provider's platform withholds its capability and every carrying provider's platform realizes it.
- No generated tree carries a platform-gated role its own provider's platform withholds.
- A structural domain a language neither realizes nor tracks with a `domain:<id>` `capability_gaps` row makes the declaration derivation raise (exit 2), naming the fix.
- **Corpus vacuity is skipped but never silent.** `check_corpus_vacuity_records` censuses EVERY registered language against EVERY domain it realizes by a pattern (not just the pairs the multi-language groups happen to exercise) and holds each corpus-vacuous `(language, domain)` to a reviewed record in `scripts/config/corpus-vacuity-records.json`. The comparison runs in both directions: a censused pair with no record fails (exit 1), and a record whose pair is no longer vacuous fails as stale (exit 1). Each record carries one of three statuses, which are never interchangeable because each carries a different remedy -- `unreachable-by-design` (no example can produce a matching file at all, whatever it declares or targets), `cloud-platform-only` (only an example resolving `deployment.provider` to a cloud provider could, and the corpus has none), `unexercised` (an ordinary local/docker example could and none declares the construct). `load_corpus_vacuity_records` refuses (exit 2) a missing/malformed file, a status outside those three, or a duplicated `(language, domain)`.
- Non-vacuity self-test (every invocation, one `[OK]` line per case): the language-axis comparator detects a forced mismatch and reports nothing for a matching pair; `classify_paths` buckets matched vs. unclassified paths, ignores a package-init marker and credits the most specific pattern; `unexcused_missing_domains` fails a missing role for a language with no declaration, fails one in a domain the language realizes elsewhere in its footprint, and excuses it only through a zero-match footprint; `_is_corpus_vacuous_for_language` is proven against a synthetic footprint (never touching a real generated tree); the corpus reader and the provider axis are proven against synthetic `.generated` layouts under a PID-scoped scratch root (corpus reader: two targets' manifests union into one sorted path list with the newest stamp, a directory without pipeline manifests is not a tree, a single-language tree forms no comparison group, and the completeness check names a missing pair and a stale park entry; provider axis: only >= 2-provider groups compared, other languages/examples/runtimes ignored, a planted role reported against exactly the provider lacking it on a line naming both providers, identical sets and a single provider report nothing, the vacuity excuse honored, a role withheld by the lacking provider's platform and realized by the carrying one excused, the same role still reported when the carrying provider's platform withholds it too or alone, a tree carrying a role its platform withholds reported by name and nothing reported when no platform withholds anything); the provider resolver answers for every registered platform and refuses a provider directory no platform registers; and `compare_vacuity_records` reports nothing for an agreeing census/record pair, reports a censused pair carrying no record, and reports a record whose pair is no longer censused -- with `_parse_vacuity_record` accepting each declared status and refusing an undeclared one.

**Exit codes:** 0 = every comparable group's role sets agree on both axes modulo recorded corpus-vacuous skips and platform-withheld roles, and no tree carries a role its platform withholds (or a successful `-SelfTest` / `-Census`), 1 = an un-excused role difference on the language or provider axis, a tree carrying a platform-withheld role, or a corpus-vacuous `(language, domain)` carries no reviewed record (or a record carries no corpus-vacuous pair), 2 = the self-test failed, the generated corpus is incomplete for some registered language (or a park entry is stale), a provider directory names no registered platform, zero groups are generated in >= 2 languages, a declaration could not be derived (a structural domain neither realized nor tracked by a `capability_gaps` row), or the corpus-vacuity-record / park file is missing/malformed.

---

## `gates\parity\generated-suite-parity-gate.ps1`

Cross-language generated-suite parity gate: every registered language's generated project carries its own emitted test suite, and the suites must agree. For every `(example, runtime, provider)` unit-tested in >= 2 registered languages under `<workspace>/.generated/<language>/<runtime>/<provider>/<example>/`, it compares the structured result index `run-complete.ps1` already wrote for each language's latest unit-test run (`<project>/.test_results/unit-tests-<stamp>/index.json`, written by `datrix_scripts.generated_test_log_writer`, whose `tests` list names every executed test as `{service, test, case, outcome}`). **Generates NOTHING and runs NOTHING** -- it reads existing index files only; there is no committed baseline. A test is identified by its service and its language-neutral **case id** (`datrix_codegen_common.algorithms.test_case_identity`), which the writer reads from the JUnit `<property name="datrix_case">` a generated pytest suite records, or from a Jest test's own title when that title is a case id; the framework-reported full name (pytest `classname::name`, Jest `fullName`) is kept for the report but never decides identity, so module paths, `describe` titles and test wording cannot make two languages' identical tests look different. Four divergences are reported, each its own category: a **role gap** (a test present in one language's suite and absent from another's), a **behaviour gap** (a test present in several languages' suites that passes in one and fails or errors in another), a **skip gap** (a test one language skips and another runs -- a skip is neither a pass nor a fail, so it is never folded into the other two; a test every language skips is no divergence), and an **unidentified test** (a test carrying no case id, which can match nothing -- never counted as a role gap and never dropped). The pass/fail comparison runs over the languages a test is present in, so a role gap never hides a behaviour gap. Only unit-test runs are compared: a deploy-test index records the docker lifecycle phases of a live stack, not a flat per-test suite.

**The gate is exactly as current as the local corpus, and refuses incomplete evidence.** It prints every language's oldest and newest index timestamp and exits 2 before comparing anything when: fewer than two languages are registered; a registered language has no unit-tests index for an example another language has one for and the pair has no entry in `scripts/config/parity-known-nongenerating.json` (naming every missing pair and the command that fills it, `run-complete.ps1 -All -L <language> -Skip4`; Jon runs this, the gate never runs a suite itself); an index predates per-test records (no `tests` list) or per-test case ids (a record with no `case` key); a service's per-test records do not equal its `passed + failed + errors + skipped` counts (it reported totals only, or no test report at all); a service reports a spec file that never ran (`suite_failures > 0`); two tests of one service carry one case id (a template rendered a case twice); an outcome falls outside `passed/failed/error/skipped`; an index belongs to another language or example than the tree it sits in; or the newest `unit-tests-*` run directory holds no `index.json` (an older run is never substituted for it). A missing index is never read as "zero tests, therefore zero gap".

| Mode | Command | Description |
|------|---------|-------------|
| **Run gate** | `.\gates\parity\generated-suite-parity-gate.ps1` | Compare the unit-test suites of every `(example, runtime, provider)` unit-tested in >= 2 languages under `<workspace>/.generated` |
| **Explicit output base** | `.\gates\parity\generated-suite-parity-gate.ps1 -GeneratedRoot D:\datrix\.generated` | Same, reading a named `generate.ps1` output base |
| **Longer listing** | `.\gates\parity\generated-suite-parity-gate.ps1 -ListLimit 50` | List up to 50 gaps per (example group, kind) before summarizing the rest (default 10) |
| **Debug** | `.\gates\parity\generated-suite-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\gates\parity\generated-suite-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-GeneratedRoot` (default: `<workspace>/.generated`), `-ListLimit` (default: 10), `-Dbg`, `-SelfTest`

**Assertions:**
- Every `(example, runtime, provider)` unit-tested in >= 2 registered languages is compared; the language set comes from the installed `datrix.languages` entry points, never a list in the script.
- A test present in one language's index and absent from another's is a role gap; present in several with a pass in one and a fail/error in another is a behaviour gap; skipped in one and run in another is a skip gap.
- Non-vacuity self-test (every invocation, 11 `[OK]` lines): a planted role gap, a planted behaviour gap and a planted skip divergence are each reported as exactly that gap; a matching pair reports none; a fail against an error is no gap; fewer than two registered languages is refused (the real entry point and the comparator); every outcome the index writer records is classified; indices written by the real writer (pytest JUnit and Jest JSON) are read, grouped and compared; an incomplete corpus is refused naming the pair while a parked pair is not missing; each unusable-index shape above is refused with its reason; the newest run is read and a newest run with no index is refused; and the entry point exits 0 for agreeing suites, 1 for each gap kind (named in the report, bounded by `-ListLimit`) and 2 over an empty corpus.

**Exit codes:** 0 = every comparable group's suites agree (or a successful `-SelfTest`), 1 = a role, behaviour or skip gap was found, 2 = the self-test failed, fewer than two languages are registered, the corpus is incomplete, an index is unusable, or no group is unit-tested in >= 2 languages.

---

## `gates\parity\block-realization-parity-gate.ps1`

Cross-platform capability parity gate: the platform-axis counterpart of
`supported-domain-parity-gate.ps1`. It compares CAPABILITIES, never implementations. A platform that
lacks one flavor, vendor product or provider another platform has is not a gap; a capability a platform
realizes by no implementation is recorded as a `<kind>:<id>` row in that platform's own
`capability_gaps`. A row accounts for the violation here and suppresses nothing in any other gate.
There is no exemption file.

Declarations are read through one extractor (presence only) and compared as plain facts. Seven surfaces:
1. block types: every block type any platform realizes by at least one flavor is realized by at least one
   flavor on every platform (`block_type:<id>` row).
2. observability categories: at least one native provider per category any platform realizes
   (`observability_category:<id>` row).
3. supported runtimes: a floor of at least one runtime (no row kind).
4. identity features: offered through at least one provider on every platform (`identity_feature:<id>` row).
5. static web hosting: each platform's origin equals its OWN edge (`domain` when the edge binds custom
   domains, `loopback_port` otherwise).
6. custom-domain surfaces: an edge-binding platform carries both `gateway` and `web`, any other carries neither.
7. model realizations: at least one provider with a flavor cell.

Retired surfaces: secret backends and deployable constructs (construction-time floors, product vocabulary),
the set-shaped optional fields (each platform's own vocabulary) and the presence-shaped optional fields
(per-platform topology facts). A field partition guard still forces every declaration field, required or
optional, into a named bucket. Derives platforms from
`importlib.metadata.entry_points(group="datrix.platforms")`; the self-test plants facts every run; exit 2 if
fewer than 2 platforms are registered or a live surface unions over nothing.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\gates\parity\block-realization-parity-gate.ps1` | Compare every registered platform's capabilities |
| **Debug** | `.\gates\parity\block-realization-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\gates\parity\block-realization-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test |

**Parameters:** `-Dbg`, `-SelfTest`

**Exit codes:** 0 = every capability realized or accounted for, 1 = at least one violation, 2 = self-test or
partition guard failed, fewer than 2 platforms, or a vacuous live surface.

---

## `gates\parity\builtin-claims-parity-gate.ps1`

Cross-language builtin-claims parity gate. Reads every registered `datrix.languages` plugin's
`LanguageCapabilityDeclaration.realized_builtin_groups` and `capability_gaps` and checks two surfaces,
neither with a reviewed-gap path (a divergence is always a real defect):

1. **Claim accounting** — a language's realized set names only real `BuiltinGroup` members; every group it is
   obligated to realize (derived from the group's own axis through `obligated_groups`) is realized or carried
   as a `builtin_group:<id>` gap row; a group both realized and rowed is a stale row. Each tracked gap row is
   logged on a live run.
2. **Realized-group mapping coherence** — every `BUILTIN_REGISTRY` row whose group the language realizes is
   mapped by its profile, whether or not the language carries a gap row. Re-derives, as an independent
   backstop, the judgment `register_builtin_capability` enforces at plugin import.

Language set from the installed `datrix.languages` entry points. Built-in non-vacuity self-test every
invocation: planted frozensets (a clean language, an unknown realized name, an unaccounted obligated group, a
rowed obligated group, a stale row, an unmapped key of a realized group, an extra client-axis group). Exit 2
if fewer than 2 languages are registered.

| Mode | Command | Description |
|------|---------|--------------|
| **Run gate** | `.\gates\parity\builtin-claims-parity-gate.ps1` | Compare every registered language's stance key sets and stance-vs-mapper coherence |
| **Debug** | `.\gates\parity\builtin-claims-parity-gate.ps1 -Dbg` | Debug logging |
| **Self-test only** | `.\gates\parity\builtin-claims-parity-gate.ps1 -SelfTest` | Run only the non-vacuity self-test; skip the real comparison |

**Parameters:** `-Dbg`, `-SelfTest`

**Exit codes:** 0 = stance key sets identical and every `supported` group is fully mapped, 1 = a
stance key-set divergence or an unmapped row in a `supported` group was found, 2 = the
non-vacuity self-test failed or fewer than 2 languages are registered.
