# Quick Reference — Ratchet Gates

Bash: prefix `powershell -File`, forward slashes, quoted path ([../../quick-reference.md](../../quick-reference.md)). Base path `d:/datrix/datrix/scripts/`. What each gate pins and how it decides: [README.md](README.md).

Gates that pin a count and let it only move one way. Each has a POSIX twin `gates/ratchet/<name>.sh` with `--kebab` flags and ends with `[GATE] <name> PASSED|FAILED exit=<n> log=<path>`. Every gate takes `-SelfTest` (its non-vacuity self-test, no real scan) and `-Dbg`.

## `gates\ratchet\check-generated-file-ratchet.ps1`

Count direct `GeneratedFile(...)` constructor calls per `datrix-*` package against `scripts/config/generated-file-ratchet.json`; a count may only shrink.

| Form | Command |
|------|---------|
| Run | `.\gates\ratchet\check-generated-file-ratchet.ps1` |
| Report regressions, exit 0 | `.\gates\ratchet\check-generated-file-ratchet.ps1 -Warn` |
| Print each file scanned | `.\gates\ratchet\check-generated-file-ratchet.ps1 -ShowFiles` |
| Freeze or tighten the baseline | `.\gates\ratchet\check-generated-file-ratchet.ps1 -UpdateBaseline` |
| Other monorepo root | `.\gates\ratchet\check-generated-file-ratchet.ps1 -BaseDir D:\datrix` |

Parameters: `-Warn`, `-ShowFiles`, `-BaseDir`, `-UpdateBaseline`, `-SelfTest`, `-Dbg`. Exit: 0 at or below baseline, 1 a count exceeds it, 2 usage error / missing baseline / attempted baseline increase / self-test step failed.

## `gates\ratchet\dependency-declaration-ratchet-gate.ps1`

Per-language census of dependency-set decision sites outside the language's declared table; decrease-only baseline `scripts/config/dependency-declaration-ratchet-baseline.json`.

| Form | Command |
|------|---------|
| Run the report | `.\gates\ratchet\dependency-declaration-ratchet-gate.ps1` |
| List every out-of-table site | `.\gates\ratchet\dependency-declaration-ratchet-gate.ps1 -Dbg` |
| Freeze or tighten the baseline | `.\gates\ratchet\dependency-declaration-ratchet-gate.ps1 -UpdateBaseline` |

Parameters: `-Dbg`, `-SelfTest`, `-UpdateBaseline` (the only writer of the baseline). Exit: 0 at or below baseline, 1 above it, 2 self-test failed / fewer than 2 languages registered / discovery or parse error.

## `gates\ratchet\migration-upgrade-op-family-gate.ps1`

Pins the target-specific `_build_upgrade_op_for_*` family and the one shared `INDEX_ADDED` parser call counts per language (`scripts/config/migration-upgrade-op-family-baseline.json`).

| Form | Command |
|------|---------|
| Run | `.\gates\ratchet\migration-upgrade-op-family-gate.ps1` |
| Debug | `.\gates\ratchet\migration-upgrade-op-family-gate.ps1 -Dbg` |

Parameters: `-Dbg`, `-SelfTest`. Exit: 0 all hold, 1 a violation, 2 self-test failed / language package unresolved / baseline missing or malformed.

## `gates\ratchet\capability-gap-ledger-gate.ps1`

Census of every target's `capability_gaps` rows against a two-directional pin (`scripts/config/capability-gap-baseline.toml`); fails a surface every implementation of an axis carries a row for.

| Form | Command |
|------|---------|
| Run | `.\gates\ratchet\capability-gap-ledger-gate.ps1` |
| Print every censused row | `.\gates\ratchet\capability-gap-ledger-gate.ps1 -Dbg` |
| Alternate pin | `.\gates\ratchet\capability-gap-ledger-gate.ps1 -BaselinePath <file.toml>` |

Parameters: `-Dbg`, `-SelfTest`, `-BaselinePath`. Exit: 0 ledger equals the pin, 1 a ratchet violation (either direction) or shared-layer defect, 2 self-test failed / fewer than 2 implementations on an axis / baseline unreadable.

## `gates\ratchet\slow-test-ratchet-gate.ps1`

Decrease-only ceiling on test wall time from the newest full run's `timings.json` (call > 30.0s; fixture replicated across workers with setup > 5.0s), against `scripts/config/slow-test-baseline.json`.

| Form | Command |
|------|---------|
| Run | `.\gates\ratchet\slow-test-ratchet-gate.ps1` |
| Seed the baseline from current offenders (hand-edit every `class` and `reason` before commit) | `.\gates\ratchet\slow-test-ratchet-gate.ps1 -Seed` |

Parameters: `-SelfTest`, `-Seed`, `-Dbg`. Exit: 0 no un-baselined offender and no stale entry, 1 an offender / stale entry / missing full run / baseline grew relative to HEAD, 2 invalid baseline / untrusted git read / `-Seed` would grow the committed baseline.
