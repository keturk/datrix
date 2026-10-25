# Gates

Repo-level validation gates: cross-cutting checks that no single package can own, so they live
as scripts here rather than as a pytest suite (the datrix showcase repo hosts no test suite).
Every gate derives its targets from what is installed or on disk, never from a hardcoded list,
and runs a non-vacuity self-test before it trusts a real result.

| Family | Holds | Reference (run it · understand it) |
|--------|-------|-----------|
| `parity/` | Every registered language or platform realizes the same thing the same way: domains, behaviour, headers, problem types, wire contracts, artifact roles, manifests and dependencies. A fact read off generated artifacts through a conformance probe is a row of `parity/cases/*.parity.yaml`, read on every target by `parity-cases-gate.ps1`; a new gate module here is a source census | [parity/quick-reference.md](parity/quick-reference.md) · [parity/README.md](parity/README.md) |
| `realization/` | A declared capability is actually realized: whole-system generation, determinism, shared-builder reachability, cache and RDBMS consumption, documentation, the standing conformance-spec corpus | [realization/quick-reference.md](realization/quick-reference.md) · [realization/README.md](realization/README.md) |
| `ratchet/` | Counts that may only move one way (or only with their pin): generated-file construction, out-of-table dependency decisions, capability gaps, slow tests | [ratchet/quick-reference.md](ratchet/quick-reference.md) · [ratchet/README.md](ratchet/README.md) |
| `repo-hygiene/` | What may be committed and what the repos and examples must satisfy: customer terms, design/task references, ignored sources, docs conformance, instruction surfaces, example registry and configs, hard-zero code shapes, the scripts tree's own catalogue | [repo-hygiene/quick-reference.md](repo-hygiene/quick-reference.md) · [repo-hygiene/README.md](repo-hygiene/README.md) |

Each family keeps its Python beside its wrappers, in `<family>/lib/`, except a family whose wrappers
are rendered from `common/templates/entrypoint.ps1` (`realization/`, `ratchet/`, `parity/`): its modules are
`common/lib/datrix_scripts/gates/<family>/<wrapper stem>.py`. A detector shared with a
hook, the commit seam or another folder lives in `common/lib/datrix_scripts/` (see
[../common/README.md](../common/README.md#where-python-lives)).

## How a gate is built

Every gate, here or beside its tool, is built on the same shared parts:

- **One check loop.** `datrix_scripts.gate_harness` is the only home of check running
  (`run_checks` over plain callables or `NamedCheck`s; a check raises `AssertionError` to fail, and
  only that is caught), the harness non-vacuity proof (`harness_self_test`: a deliberately failing
  check must be reported), `[OK]`/`[FAIL]` printing, logging setup, the shared CLI flags
  (`gate_argument_parser`: `--debug`, `--self-test`, `--harness-self-test`, optional
  `--update-baseline`), the Ctrl-C handler and the planted-fixture writer (`write_file`,
  `write_files`). A gate keeps its own data shapes (`Violation`, `Finding`, …) and message text;
  it never defines its own `run_checks`, `_ok`/`_fail` or logging setup. Exit codes: 0 pass,
  1 violation, 2 usage (`UsageError`), 130 interrupt.
- **One runner and one verdict line.** The wrapper is rendered from the template and runs the gate
  module, whose `main` is `datrix_scripts.gate_log.run_as_gate`: it tees the output to a claimed log
  under `<workspace>\.test-output\gates\<name>\` (outside every repository) and prints
  `[GATE] <name> PASSED|FAILED exit=<n> log=<path>` last; the red-run digest hook reads that line.
- **`-SelfTest` on every gate.** Every `*-gate.ps1`, `*ratchet*.ps1` and
  `type-mapping-completeness.ps1` declares `-SelfTest`, which runs only the gate's non-vacuity
  proof (a planted violation is reported, its clean twin passes) and reads nothing of the real
  workspace.
- **One count ratchet.** A gate that compares counts against a baseline uses
  `datrix_scripts.count_ratchet`: `compare(current, baseline, mode)` returns the failing deltas in
  one of two semantics, `TIGHTEN_ONLY` (an increase fails, a decrease passes, a missing key is 0)
  or `EXACT_PIN` (an increase and an unbanked decrease both fail); `read_counts` refuses a
  non-dict, a bool, a non-int or a negative value, naming the file and key. A baseline file that
  does not exist is an error, never an empty table: a first run is an explicit `--update-baseline`.
  Structured baselines that are not count maps keep their own loaders.

Gates for one tool live with that tool, not here: the test-runner gates in `test/`, the code-index,
local-model and ineedtoknow gates in `dev/`, the review gate in `review/`, the task-orientation gate
in `tasks/`, the pre-review gate in `git/`.
