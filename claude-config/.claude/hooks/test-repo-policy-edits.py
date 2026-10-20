"""Exercise guard-repo-policy-edits.py with synthetic payloads and real directories.

A guard that misses the shape that caused the incident is decoration; one that blocks the
legitimate neighbour (editing a task's How-Solved, writing into an existing phase, a planning
skill opening a phase) blocks real work. Both directions are asserted.
"""
import json
import os
import subprocess
import sys
import tempfile

HOOK = os.path.join(r"d:\datrix\.claude\hooks", "guard-repo-policy-edits.py")
STATE_DIR = os.path.join(r"d:\datrix\.claude\hooks", ".state")
fails = []
BLOCK, ALLOW = 2, 0


def run(payload):
    p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload), capture_output=True, text=True)
    return p.returncode


def write(path, content="x", session="s-none"):
    return run({"tool_name": "Write", "session_id": session, "tool_input": {"file_path": path, "content": content}})


def edit(path, old, new):
    return run({"tool_name": "Edit", "tool_input": {"file_path": path, "old_string": old, "new_string": new}})


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: exit {got} want {want}")
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")


print("== GitHub Actions ==")
check("a new workflow", write(r"d:\datrix\datrix-cli\.github\workflows\ci.yml"), BLOCK)
check("an edit to a workflow", edit("D:/datrix/datrix/.github/workflows/test.yaml", "a", "b"), BLOCK)
check("a workflow in a generated example", write("d:/datrix/datrix/examples/x/generated/.github/workflows/b.yml"), BLOCK)
check("other .github files stay allowed", write("d:/datrix/datrix-cli/.github/CODEOWNERS"), ALLOW)
check("a doc that mentions workflows stays allowed", write("d:/datrix/datrix/docs/ci-notes.md"), ALLOW)
check("third-party source parked in .tmp stays allowed",
      write("d:/datrix/.tmp/garage-src/garage/.github/workflows/ci.yml"), ALLOW)

print("== completing a task by hand ==")
with tempfile.TemporaryDirectory(prefix="policy-gate-") as root:
    phase = os.path.join(root, "pkg", ".tasks", "phase-07")
    os.makedirs(phase)
    task = os.path.join(phase, "task-07-01-do-thing.md")
    done = os.path.join(phase, "task-07-02-already.md")
    with open(task, "w", encoding="utf-8") as handle:
        handle.write("# Task 07-01: Do thing\n\n## How Solved\n\nStatus: BLOCKED\n")
    with open(done, "w", encoding="utf-8") as handle:
        handle.write("# COMPLETED: Task 07-02: Already\n\n## How Solved\n\nDone.\n")

    check("edit adds the COMPLETED heading",
          edit(task, "# Task 07-01: Do thing", "# COMPLETED: Task 07-01: Do thing"), BLOCK)
    check("write adds the COMPLETED heading to a task that lacks it",
          write(task, "# COMPLETED: Task 07-01: Do thing\n\nbody"), BLOCK)
    check("write of a NEW task file already headed COMPLETED",
          write(os.path.join(phase, "task-07-09-new.md"), "# COMPLETED: Task 07-09: New\n"), BLOCK)
    check("forward slashes and upper case",
          edit(task.replace("\\", "/").upper().replace("PKG", "pkg"), "a", "# COMPLETED: Task 07-01: x"), BLOCK)
    check("editing How Solved stays allowed",
          edit(task, "Status: BLOCKED", "Status: fixed; see file:line"), ALLOW)
    check("editing a task that already carries the heading stays allowed",
          edit(done, "Done.", "Done, with notes."), ALLOW)
    check("rewriting a COMPLETED task keeps its heading: allowed",
          write(done, "# COMPLETED: Task 07-02: Already\n\nrewritten"), ALLOW)
    check("a non-task file mentioning COMPLETED stays allowed",
          write(os.path.join(root, "pkg", "docs", "notes.md"), "# COMPLETED: Task 1: demo"), ALLOW)
    check("a different status prefix stays allowed",
          edit(task, "# Task 07-01: Do thing", "# IN PROGRESS: Task 07-01: Do thing"), ALLOW)

    print("== creating a phase ==")
    new_task = os.path.join(root, "pkg", ".tasks", "phase-08", "task-08-01-new.md")
    existing = os.path.join(phase, "task-07-03-filed.md")
    check("a file in an EXISTING phase stays allowed", write(existing, "# Task 07-03: Filed\n"), ALLOW)
    check("a file in a NEW phase, no skill recorded", write(new_task, "# Task 08-01: New\n"), BLOCK)

    sid = f"policy-gate-{os.getpid()}"
    os.makedirs(STATE_DIR, exist_ok=True)
    state = os.path.join(STATE_DIR, f"skill-{sid}.json")

    def with_skill(skill):
        with open(state, "w", encoding="utf-8") as handle:
            json.dump({"skill": skill}, handle)
        try:
            return write(new_task, "# Task 08-01: New\n", session=sid)
        finally:
            os.remove(state)

    check("a new phase under /generate-tasks", with_skill("generate-tasks"), ALLOW)
    check("a new phase under /operationalize-design", with_skill("operationalize-design"), ALLOW)
    check("a new phase under /task-orchestrator", with_skill("task-orchestrator"), BLOCK)
    check("a new phase under a fix skill", with_skill("fix-codegen-azure"), BLOCK)
    check("a new phase when the record names no skill", with_skill(""), BLOCK)
    check("a new phase when the record is missing", write(new_task, "x", session=sid), BLOCK)

print("== a parity fact read through a probe is a row, never a new gate module ==")
PROBE_IMPORT = "from datrix_codegen_kernel.parity.conformance_probes import language_conformance_probes\n"
PACKAGE_IMPORT = "from datrix_codegen_kernel.parity import conformance_probes\n"
CENSUS_IMPORT = "from datrix_scripts.registered_targets import registered_language_names\n"
with tempfile.TemporaryDirectory(prefix="policy-gate-") as root:
    gates = os.path.join(root, "datrix", "scripts", "gates")
    lib = os.path.join(gates, "parity", "lib")
    os.makedirs(lib)
    with open(os.path.join(lib, "probe_reader.py"), "w", encoding="utf-8") as handle:
        handle.write(PROBE_IMPORT)
    with open(os.path.join(lib, "source_census.py"), "w", encoding="utf-8") as handle:
        handle.write(CENSUS_IMPORT)
    existing = os.path.join(lib, "existing_parity.py")
    with open(existing, "w", encoding="utf-8") as handle:
        handle.write(PROBE_IMPORT)

    check("a new lib module importing the probes", write(os.path.join(lib, "header_parity.py"), PROBE_IMPORT), BLOCK)
    check("a new lib module importing the probe module from its package",
          write(os.path.join(lib, "route_conformance.py"), PACKAGE_IMPORT), BLOCK)
    check("a probe-reading module in another gate family",
          write(os.path.join(gates, "realization", "lib", "doc_parity.py"), PROBE_IMPORT), BLOCK)
    check("a new wrapper running a probe-reading module",
          write(os.path.join(gates, "parity", "header-parity-gate.ps1"), '$x = Join-Path $scriptDir "lib\\probe_reader.py"\n'),
          BLOCK)
    check("a new source-census module", write(os.path.join(lib, "header_census.py"), CENSUS_IMPORT), ALLOW)
    check("a new wrapper running a census",
          write(os.path.join(gates, "parity", "census-gate.ps1"), '$x = Join-Path $scriptDir "lib\\source_census.py"\n'),
          ALLOW)
    check("rewriting an existing probe-reading module", write(existing, PROBE_IMPORT), ALLOW)
    check("a probe import outside the gates tree", write(os.path.join(root, "pkg", "src", "probes.py"), PROBE_IMPORT), ALLOW)

    # A family whose wrappers are rendered from the entrypoint template keeps its modules in
    # datrix_scripts.gates.<family>; the wrapper names the module, not a lib\ file.
    package = os.path.join(root, "datrix", "scripts", "common", "lib", "datrix_scripts", "gates", "parity")
    os.makedirs(package)
    with open(os.path.join(package, "probe_reader_gate.py"), "w", encoding="utf-8") as handle:
        handle.write(PROBE_IMPORT)
    with open(os.path.join(package, "source_census_gate.py"), "w", encoding="utf-8") as handle:
        handle.write(CENSUS_IMPORT)
    rendered = 'Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.parity.{0}" -Parameters $PSBoundParameters\n'
    twin = 'module="datrix_scripts.gates.parity.{0}"\n'
    check("a new package module importing the probes",
          write(os.path.join(package, "header_parity_gate.py"), PROBE_IMPORT), BLOCK)
    check("a probe-reading package module in another family",
          write(os.path.join(os.path.dirname(package), "realization", "doc_parity_gate.py"), PROBE_IMPORT), BLOCK)
    check("a new rendered wrapper running a probe-reading module",
          write(os.path.join(gates, "parity", "probe-reader-gate.ps1"), rendered.format("probe_reader_gate")), BLOCK)
    check("a new .sh twin running a probe-reading module",
          write(os.path.join(gates, "parity", "probe-reader-gate.sh"), twin.format("probe_reader_gate")), BLOCK)
    check("a new package module that is a census",
          write(os.path.join(package, "header_census_gate.py"), CENSUS_IMPORT), ALLOW)
    check("a new rendered wrapper running a census",
          write(os.path.join(gates, "parity", "source-census-gate.ps1"), rendered.format("source_census_gate")), ALLOW)
    for runner in ("parity_cases_gate.py", "parity_cases.py", "parity_cases_cli.py", "parity_observers.py"):
        check(f"the parity runner's own module {runner}", write(os.path.join(package, runner), PROBE_IMPORT), ALLOW)
    check("the parity runner's old lib path is no longer the runner",
          write(os.path.join(lib, "parity_observers.py"), PROBE_IMPORT), BLOCK)

print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("all checks passed")
