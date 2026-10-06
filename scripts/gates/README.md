# Gates

Repo-level validation gates: cross-cutting checks that no single package can own, so they live
as scripts here rather than as a pytest suite (the datrix showcase repo hosts no test suite).
Every gate derives its targets from what is installed or on disk, never from a hardcoded list,
and runs a non-vacuity self-test before it trusts a real result.

| Family | Holds | Reference |
|--------|-------|-----------|
| `parity/` | Every registered language or platform realizes the same thing the same way: domains, behaviour, headers, problem types, wire contracts, artifact roles, manifests and dependencies | [parity/quick-reference.md](parity/quick-reference.md) |
| `realization/` | A declared capability is actually realized: whole-system generation, determinism, shared-builder reachability, cache and RDBMS consumption, documentation, the standing conformance-spec corpus | [realization/quick-reference.md](realization/quick-reference.md) |
| `ratchet/` | Counts that may only move one way (or only with their pin): generated-file construction, out-of-table dependency decisions, capability gaps, slow tests | [ratchet/quick-reference.md](ratchet/quick-reference.md) |
| `repo-hygiene/` | What may be committed and what the repos and examples must satisfy: customer terms, design/task references, ignored sources, docs conformance, instruction surfaces, example registry and configs, hard-zero code shapes | [repo-hygiene/quick-reference.md](repo-hygiene/quick-reference.md) |

Each family keeps its Python beside its wrappers, in `<family>/lib/`; a detector shared with a
hook, the commit seam or another folder lives in `common/lib/datrix_scripts/` (see
[../common/README.md](../common/README.md#where-python-lives)).

Gates for one tool live with that tool, not here: the test-runner gates in `test/`, the code-index,
local-model and ineedtoknow gates in `dev/`, the review gate in `review/`, the task-orientation gate
in `tasks/`, the pre-review gate in `git/`.
