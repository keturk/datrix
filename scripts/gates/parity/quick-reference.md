# Quick Reference — Parity Gates

Bash: prefix `powershell -File`, forward slashes, quoted path ([../../quick-reference.md](../../quick-reference.md)). Base path `d:/datrix/datrix/scripts/`. What each gate proves, the probe/facet table, baselines and self-tests: [README.md](README.md).

Cross-target gates: every registered language (or platform) must realize the same thing the same way. Each has a POSIX twin `gates/parity/<name>.sh` with `--kebab` flags and ends with `[GATE] <name> PASSED|FAILED exit=<n> log=<path>`. Every gate takes `-SelfTest` (non-vacuity proof, no real scan) and `-Dbg`.

**A parity fact over generated artifacts is a row, never a new gate module.** A fact read through a conformance probe is one row of `gates\parity\cases\<area>.parity.yaml`, read on every registered target by `parity-cases-gate.ps1`; author rows with `parity-cases.ps1`. A new gate module here is reserved for a source census.

## `gates\parity\parity-cases-gate.ps1`

Read every parity row on every registered target of its axis and compare each reading with the row's authored expectation (verdicts `DIVERGENCE`, `UNREADABLE`, `DRIFT`, `GAP`, `N/A`). Fixtures under `D:\datrix\.tmp\parity-cases\`.

| Form | Command |
|------|---------|
| Tagged rows (at most three tags, each carried by some row) | `.\gates\parity\parity-cases-gate.ps1 -Tag rest-api` |
| Every row (Jon's run; refused for agents by `guard-untargeted-scans.py`) | `.\gates\parity\parity-cases-gate.ps1` |
| Include fixture and probe error text | `.\gates\parity\parity-cases-gate.ps1 -Tag pubsub -Dbg` |

Parameters: `-Tag <tag,...>`, `-SelfTest`, `-Dbg`. Exit: 0 every selected row holds on every target, 1 divergence / unreadable row / gap, 2 self-test failed / malformed row or row file / refused tag selection / fewer than two targets can read a row / missing or incomplete probes / fixture failed to build / probe raised.

## `gates\parity\parity-cases.ps1`

The parity rows' authoring tool: `observe`, `new`, `migrate`, `accept`, `check`. Every expectation is authored; the tool never writes one.

| Form | Command |
|------|---------|
| Observe a probe on every target (writes nothing) | `.\gates\parity\parity-cases.ps1 observe rest-api route_wire_contracts "{facet: route, verb: get, path: /api/v1/books}"` |
| Add one authored row | `.\gates\parity\parity-cases.ps1 new routes -Id routes.rest-api.list-books -Tags parity,rest-api -Input rest-api -Probe route_wire_contracts -Selector "{facet: route, verb: get, path: /api/v1/books}" -Expectation "{status: '200', body: page, media-type: application/json}" -Reason "..."` |
| Propose rows for a probe | `.\gates\parity\parity-cases.ps1 migrate pubsub event_envelopes -Area events -Tags pubsub` |
| Accept an approved proposal | `.\gates\parity\parity-cases.ps1 accept D:\datrix\.tmp\case-proposals\parity-events-event-envelopes.proposal.json` |
| Check every committed row | `.\gates\parity\parity-cases.ps1 check` |

Parameters: `-Id`, `-Tags`, `-Input`, `-Probe`, `-Selector`, `-Expectation`, `-Reason` (new); `-Area`, `-Tags`, `-Replaces <gate>` (migrate); `-Dbg`; `-SelfTest` (alone). POSIX flags: `--id`, `--tags`, `--case-input`, `--probe`, `--selector`, `--expectation`, `--reason`, `--area`, `--replaces`. Exit: 0 done and clean, 1 refused or problems found, 2 usage error.

## `gates\parity\response-body-transform-census-gate.ps1`

Generate the CQRS example per language and census response-body transform idioms; every hit must be a reviewed entry in `scripts/config/response-body-transform-exemptions.json`.

| Form | Command |
|------|---------|
| Run | `.\gates\parity\response-body-transform-census-gate.ps1` |

Parameters: `-Dbg`, `-SelfTest`. Exit: 0 every hit reviewed and no stale entry, 1 an unreviewed hit / stale entry / language with no declaration, 2 self-test failed / fewer than two languages / review file missing or malformed.

## `gates\parity\type-mapping-completeness.ps1`

Every canonical type has a mapping in each language's `static_type_map`, and every installed `datrix.extensions` pack has a key in every language's (and SQL's) extension maps.

| Form | Command |
|------|---------|
| Both checks, every registered language | `.\gates\parity\type-mapping-completeness.ps1` |
| Restrict the canonical-type check | `.\gates\parity\type-mapping-completeness.ps1 -Languages python,typescript` |

Parameters: `-Languages` (comma-separated subset of the registered set; restricts the canonical-type leg only), `-SelfTest`, `-Dbg`. Exit: 0 both pass, 1 a gap, 2 self-test failed / no languages / discovery or import error.

## `gates\parity\supported-domain-parity-gate.ps1`

Domain-universe closure (compiled DAL generator domain ids equal the registry) and per-language declaration presence for every structural domain id.

| Form | Command |
|------|---------|
| Run | `.\gates\parity\supported-domain-parity-gate.ps1` |

Parameters: `-Dbg`, `-SelfTest`. Exit: 0 closure holds and every language declares every structural id, 1 a closure or declaration-presence violation, 2 self-test failed / fewer than 2 languages.

## `gates\parity\behaviour-parity-gate.ps1`

Group functions across targets into roles, compare by behaviour skeleton, and hold the failing-role count to its two-directional pin in `scripts/config/behaviour-parity-baseline.toml`.

| Form | Command |
|------|---------|
| Language axis | `.\gates\parity\behaviour-parity-gate.ps1` |
| List every role | `.\gates\parity\behaviour-parity-gate.ps1 -Dbg` |
| Report filter by domain | `.\gates\parity\behaviour-parity-gate.ps1 -Dbg -Scope queue,cache` |
| Report filter by bucket | `.\gates\parity\behaviour-parity-gate.ps1 -Dbg -Buckets identical` |
| Platform axis | `.\gates\parity\behaviour-parity-gate.ps1 -Axis platforms` |
| Fingerprint pass (report only) | `.\gates\parity\behaviour-parity-gate.ps1 -Fingerprint` |

Parameters: `-Axis <languages|platforms>` (default languages), `-Scope <id,...>`, `-Buckets <id,...>` (both report filters only; buckets `identical`, `same-behaviour`, `divergent`), `-Dbg`, `-SelfTest`, `-Fingerprint`. Exit: 0 count equals its pin, 1 count differs (above: regression; below: lower the pin in the same change), 2 usage / discovery / parse error / malformed baseline / self-test failed.

## `gates\parity\shared-home-body-gate.ps1`

Functions of `datrix-common`, `datrix-codegen-kernel`, `datrix-codegen-common` must not be copied (normalized body, 8 lines / 40 AST nodes) into another package; per-package decrease-only pin in `scripts/config/shared-home-body-baseline.toml`.

| Form | Command |
|------|---------|
| Run | `.\gates\parity\shared-home-body-gate.ps1` |
| List every hit | `.\gates\parity\shared-home-body-gate.ps1 -Hits` |
| Check named copies are gone | `.\gates\parity\shared-home-body-gate.ps1 -Symbol event_for_replay_plan,_iter_calls` |
| Seed or lower the pin | `.\gates\parity\shared-home-body-gate.ps1 -UpdateBaseline` |

Parameters: `-Hits`, `-Symbol <name,...>` (report filter), `-UpdateBaseline`, `-Dbg`, `-SelfTest`. Exit: 0 no package exceeds its pin, 1 a count above its pin or `-UpdateBaseline` refused because a count would rise, 2 self-test failed / baseline unreadable / unparseable source / home package missing.

## `gates\parity\observability-axis-parity-gate.ps1`

Every registered language agrees with the platform axis about which observability categories it may realize (declaration identity, validator agreement).

| Form | Command |
|------|---------|
| Run | `.\gates\parity\observability-axis-parity-gate.ps1` |

Parameters: `-Dbg`, `-SelfTest`. Exit: 0 both legs hold, 1 an axis violation, 2 self-test failed / too few registered targets.

## `gates\parity\manifest-import-parity-gate.ps1`

Each `datrix-*` package's declared `datrix-*` dependencies equal the `datrix_*` roots its `src/` imports; no test-only extra in a runtime requirement. Hard zero.

| Form | Command |
|------|---------|
| Run | `.\gates\parity\manifest-import-parity-gate.ps1` |
| Print declared and imported sets | `.\gates\parity\manifest-import-parity-gate.ps1 -Dbg` |

Parameters: `-Dbg`, `-SelfTest`. Exit: 0 every manifest agrees, 1 a violation, 2 self-test failed / fewer than two packages / unparseable manifest or module.

## `gates\parity\third-party-dependency-parity-gate.ps1`

Each package's declared third-party distributions equal those its `src/` imports; reviewed executable exemptions in `scripts/config/third-party-dependency-exemptions.json`.

| Form | Command |
|------|---------|
| Run | `.\gates\parity\third-party-dependency-parity-gate.ps1` |
| Print each package's declared set | `.\gates\parity\third-party-dependency-parity-gate.ps1 -ShowFiles` |

Parameters: `-BaseDir <path>`, `-SelfTest`, `-ShowFiles`, `-Dbg`. Exit: 0 every manifest agrees, 1 a violation or stale exemption, 2 self-test failed / fewer than two packages / unparseable manifest or exemption file.

## `gates\parity\framework-header-parity-gate.ps1`

Every language spells framework-minted HTTP headers from the one registry and realizes every header family; exemptions in `scripts/config/framework-header-exemptions.json`. Hard zero.

| Form | Command |
|------|---------|
| Run (prints the family × language table) | `.\gates\parity\framework-header-parity-gate.ps1` |

Parameters: `-Dbg`, `-SelfTest`. Exit: 0 every language passes both rules, 1 a violation, 2 self-test failed / fewer than two languages / exemption file missing, malformed or miscounted.

## `gates\parity\problem-type-parity-gate.ps1`

Every language answers errors with RFC 7807 `type` URNs from the one registry and references every framework family; unspelled cells pinned per language in `scripts/config/problem-type-parity-baseline.toml`.

| Form | Command |
|------|---------|
| Run (prints the table and every `PINNED GAP` cell) | `.\gates\parity\problem-type-parity-gate.ps1` |

Parameters: `-Dbg`, `-SelfTest`. Exit: 0 every unspelled-cell count equals its pin and no hard problem, 1 a violation, 2 self-test failed / fewer than two languages / baseline missing or malformed.

## `gates\parity\field-error-path-parity-gate.ps1`

Every language spells a `request-validation` problem body's `errors[].field` with the one shape of `FIELD_ERROR_PATH_RULE`, by the realization it declares. Hard zero.

| Form | Command |
|------|---------|
| Run (prints the realized/MISSING table) | `.\gates\parity\field-error-path-parity-gate.ps1` |
| Per-language site counts | `.\gates\parity\field-error-path-parity-gate.ps1 -Dbg` |

Parameters: `-Dbg`, `-SelfTest`. Exit: 0 every language realizes the rule, 1 a violation, 2 self-test failed / fewer than two languages.

## `gates\parity\artifact-role-parity-gate.ps1`

Reads the generation manifests under `.generated` and compares each domain role set across languages (same example, runtime, provider) and across providers (same language). Reads only; Jon fills a missing corpus with `generate.ps1 -All -L <language>`.

| Form | Command |
|------|---------|
| Run | `.\gates\parity\artifact-role-parity-gate.ps1` |
| Other generated base | `.\gates\parity\artifact-role-parity-gate.ps1 -GeneratedRoot D:\datrix\.generated` |
| Corpus-vacuity census | `.\gates\parity\artifact-role-parity-gate.ps1 -Census` |

Parameters: `-GeneratedRoot` (default `<workspace>/.generated`), `-Dbg`, `-SelfTest`, `-Census`. Exit: 0 role sets agree on both axes (or `-SelfTest` / `-Census`), 1 an un-excused role difference / platform-withheld role emitted / corpus-vacuity record missing or stale, 2 self-test failed / incomplete corpus or stale park entry / unregistered provider directory / no multi-language group / underivable declaration / missing or malformed record file.

## `gates\parity\generated-suite-parity-gate.ps1`

Compares the emitted unit-test suites (the `unit-tests-*` `index.json` `run-complete.ps1` wrote) of every example tested in two or more languages: role, behaviour and skip gaps, unidentified tests, and contract-tier tests (a case id of a `CONTRACT_TIER_FAMILIES` family, which no language suite may carry). Reads only.

| Form | Command |
|------|---------|
| Run | `.\gates\parity\generated-suite-parity-gate.ps1` |
| Other generated base | `.\gates\parity\generated-suite-parity-gate.ps1 -GeneratedRoot D:\datrix\.generated` |
| List more gaps per group | `.\gates\parity\generated-suite-parity-gate.ps1 -ListLimit 50` |

Parameters: `-GeneratedRoot` (default `<workspace>/.generated`), `-ListLimit` (default 10), `-Dbg`, `-SelfTest`. Exit: 0 suites agree, 1 a role, behaviour or skip gap, an unidentified test or a contract-tier test, 2 self-test failed / fewer than two languages / incomplete corpus / unusable index / no multi-language group.

## `gates\parity\block-realization-parity-gate.ps1`

Every registered platform realizes every capability another does, or carries it as a `capability_gaps` row. No exemption file.

| Form | Command |
|------|---------|
| Run | `.\gates\parity\block-realization-parity-gate.ps1` |

Parameters: `-Dbg`, `-SelfTest`. Exit: 0 every capability realized or accounted for, 1 a violation, 2 self-test or partition guard failed / fewer than two platforms / a vacuous live surface.

## `gates\parity\builtin-claims-parity-gate.ps1`

Every language's realized builtin groups are accounted for (realized or a `builtin_group:<id>` gap row) and fully mapped by its profile. No reviewed-gap path.

| Form | Command |
|------|---------|
| Run | `.\gates\parity\builtin-claims-parity-gate.ps1` |

Parameters: `-Dbg`, `-SelfTest`. Exit: 0 stance key sets identical and every `supported` group fully mapped, 1 a divergence or unmapped row, 2 self-test failed / fewer than two languages.
