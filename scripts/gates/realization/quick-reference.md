# Quick Reference — Realization Gates

Bash: prefix `powershell -File`, forward slashes, quoted path ([../../quick-reference.md](../../quick-reference.md)). Base path `d:/datrix/datrix/scripts/`. What each gate proves, its assertions and how to write a standing spec: [README.md](README.md).

Gates that prove a declared capability or contract is actually realized. Each has a POSIX twin `gates/realization/<name>.sh` with `--kebab` flags and ends with `[GATE] <name> PASSED|FAILED exit=<n> log=<path>`. Every gate takes `-SelfTest` (non-vacuity proof, no real scan) and `-Dbg`.

## `gates\realization\conformance-gate.ps1`

Run a declarative design-acceptance assertion spec (`must_contain`, `must_not_contain`, `file_exists`, `file_absent`, `count_equals`) over a tree. Ledger: `D:\datrix\.test-output\conformance\<spec-stem>-ledger.json`.

| Form | Command |
|------|---------|
| Run a spec | `.\gates\realization\conformance-gate.ps1 -Spec D:\datrix\.tmp\my-invariant.spec.json` |
| Other ledger path | `.\gates\realization\conformance-gate.ps1 -Spec ... -Output D:\datrix\.test-output\my-ledger.json` |

Parameters: `-Spec <path>` (required unless `-SelfTest`), `-SelfTest`, `-Output <path>`, `-Dbg`. Exit: 0 all assertions pass, 1 any fail, 2 usage / bad spec / self-test failure.

## `gates\realization\standing-conformance-gate.ps1`

Run every committed spec under `scripts/config/conformance-specs/` (top-level `*.json` only).

| Form | Command |
|------|---------|
| Run | `.\gates\realization\standing-conformance-gate.ps1` |
| Debug, forwarded per spec | `.\gates\realization\standing-conformance-gate.ps1 -Dbg` |

Parameters: `-Dbg`, `-SelfTest`. Exit: 0 every spec passed, 1 a spec's assertions failed, 2 spec directory missing or empty / a committed spec uses an absolute path / a spec's own self-test failed.

## `gates\realization\typescript-whole-system-gate.ps1`

Generate `examples/01-foundation` twice with `-Language typescript`; assert real TypeScript output and byte-stability.

| Form | Command |
|------|---------|
| Run | `.\gates\realization\typescript-whole-system-gate.ps1` |
| Other output root | `.\gates\realization\typescript-whole-system-gate.ps1 -OutputRoot D:\datrix\.test-output\ts-gate` |

Parameters: `-OutputRoot` (default `d:/datrix/.test-output/ts-gate`), `-Dbg`/`-DebugLogging`, `-SelfTest`. Exit: 0 real and byte-stable, 1 generation failed / realness violated / byte drift / example missing, 2 usage error.

## `gates\realization\generation-determinism-gate.ps1`

Generate one example N times in separate processes for one language; every outcome must be identical.

| Form | Command |
|------|---------|
| Run (5 runs) | `.\gates\realization\generation-determinism-gate.ps1 -Language python` |
| Other run count (at least 2) | `.\gates\realization\generation-determinism-gate.ps1 -Language typescript -Runs 3` |
| Other output root | `.\gates\realization\generation-determinism-gate.ps1 -Language python -OutputRoot D:\datrix\.test-output\generation-determinism-gate\python` |

Parameters: `-Language` (required unless `-SelfTest`; a registered `datrix.languages` name), `-OutputRoot` (default `d:/datrix/.test-output/generation-determinism-gate/<Language>`), `-Runs` (default 5, at least 2), `-Dbg`/`-DebugLogging`, `-SelfTest` (alone). Exit: 0 identical outcomes, 1 mismatch / `-Runs` below 2 / example missing, 2 usage error.

## `gates\realization\ingress-migration-conformance-gate.ps1`

Regenerate representative examples and the full tree; prove only the four intended realized-exposure deltas occur.

| Form | Command |
|------|---------|
| Every registered language | `.\gates\realization\ingress-migration-conformance-gate.ps1` |
| One language | `.\gates\realization\ingress-migration-conformance-gate.ps1 -Languages python` |
| Other scratch root | `.\gates\realization\ingress-migration-conformance-gate.ps1 -OutputRoot D:\datrix\.test-output\ingress-gate` |

Parameters: `-OutputRoot` (default `D:\datrix\.test-output\ingress-gate`), `-Languages` (comma-separated; default every registered language), `-Dbg`/`-DebugLogging`, `-SelfTest`. Exit: 0 every delta accounted for, 1 a hard finding / no registered language, 2 usage error.

## `gates\realization\shared-builder-reachability-gate.ps1`

Every module-level `build_*` function in `datrix_codegen_common`'s `algorithms/` and `context_models/` must have a production caller. Hard zero, no exemption file.

| Form | Command |
|------|---------|
| Run | `.\gates\realization\shared-builder-reachability-gate.ps1` |
| Print the census, exit 0 | `.\gates\realization\shared-builder-reachability-gate.ps1 -Census` |

Parameters: `-Dbg`, `-SelfTest`, `-Census`. Exit: 0 every builder reachable and every floor holds, 1 a dead builder or violated floor, 2 self-test failed / package not located / fewer than 2 languages.

## `gates\realization\zero-environment-runtime-gate.ps1`

Generate the `serverless` example per language and census environment reads in the emitted code against `scripts/config/zero-environment-runtime-baseline.json`.

| Form | Command |
|------|---------|
| Run | `.\gates\realization\zero-environment-runtime-gate.ps1` |
| List every environment read | `.\gates\realization\zero-environment-runtime-gate.ps1 -Dbg` |
| Lower the `pinned_count` pins | `.\gates\realization\zero-environment-runtime-gate.ps1 -UpdateBaseline` |

Parameters: `-Dbg`, `-SelfTest`, `-UpdateBaseline` (refuses to raise a pin; exemptions are hand-authored). Exit: 0 every language matches its entry, 1 a violation, 2 self-test failed / fewer than 2 languages / malformed baseline.

## `gates\realization\model-realization-parity-gate.ps1`

Every registered platform declares a well-formed `model_realizations` mapping.

| Form | Command |
|------|---------|
| Run | `.\gates\realization\model-realization-parity-gate.ps1` |

Parameters: `-Dbg`, `-SelfTest`. Exit: 0 all well formed, 1 a violation, 2 self-test failed / fewer than 2 platforms.

## `gates\realization\pooled-cache-realization-gate.ps1`

A pooled cache member's declared slice reaches each target's emitted-output-facing source (static); exemptions in `scripts/config/pooled-cache-realization-exemptions.json`.

| Form | Command |
|------|---------|
| Both axes | `.\gates\realization\pooled-cache-realization-gate.ps1` |
| One axis | `.\gates\realization\pooled-cache-realization-gate.ps1 -Axis platforms` (`-Axis languages`) |

Parameters: `-Axis <languages|platforms>` (default both), `-Dbg`, `-SelfTest`. Exit: 0 every target realizes the slice or carries a reviewed exemption, 1 an unexempted gap or stale exemption, 2 self-test failed / fewer than 2 targets on an axis.

## `gates\realization\shared-cache-realization-gate.ps1`

A service that `uses` a shared cache container realizes its cache block (`realized_cache_blocks`); platforms also call `require_cache_keys_supplied` (static).

| Form | Command |
|------|---------|
| Both axes | `.\gates\realization\shared-cache-realization-gate.ps1` |
| One axis | `.\gates\realization\shared-cache-realization-gate.ps1 -Axis platforms` (`-Axis languages`) |

Parameters: `-Axis <languages|platforms>` (default both), `-Dbg`, `-SelfTest`. Exit: 0 every target walks the realized blocks, 1 a consumer-blind target, 2 self-test failed / fewer than 2 targets on an axis.

## `gates\realization\shared-rdbms-realization-gate.ps1`

Generate the shared-rdbms fixture per language and assert consumers realize the shared block (entity modules, canonical migration chain, seed in the writer only).

| Form | Command |
|------|---------|
| Run | `.\gates\realization\shared-rdbms-realization-gate.ps1` |

Parameters: `-Dbg`, `-SelfTest`. Exit: 0 every language realizes shared consumption, 1 a gap, 2 self-test failed / fewer than 2 languages.

## `gates\realization\documentation-realization-parity-gate.ps1`

Generate one documented fixture per language; published (`///`) comments must reach the published surface and source (`//`) comments the source surface, in every (construct kind, surface) cell. Hard zero, plus a decrease-only coverage-hole baseline (`scripts/config/documentation-coverage-baseline.json`). Report: `D:\datrix\.tmp\documentation-realization-parity-gate-report.json`.

| Form | Command |
|------|---------|
| Run | `.\gates\realization\documentation-realization-parity-gate.ps1` |
| Re-pin coverage | `.\gates\realization\documentation-realization-parity-gate.ps1 -UpdateCoverageBaseline` |

Parameters: `-Dbg`, `-SelfTest`, `-UpdateCoverageBaseline` (refuses when a target failed generation). Exit: 0 every cell populated and no coverage regression, 1 a hole / coverage regression / generation failure, 2 self-test failed / fewer than 2 languages.

## `gates\realization\dgen-corpus-resolution-gate.ps1`

Compile every target's DAL generator definitions (one subprocess per target); a bad reference raises `DalReferenceError`.

| Form | Command |
|------|---------|
| Run | `.\gates\realization\dgen-corpus-resolution-gate.ps1` |
| Print the discovered module list | `.\gates\realization\dgen-corpus-resolution-gate.ps1 -Dbg` |

Parameters: `-Dbg`, `-SelfTest`. Exit: 0 every corpus resolved, 1 a target failed to resolve or import.
