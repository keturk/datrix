"""Exercise guard-approved-test-plan.py with synthetic payloads against a throwaway gate directory.

The gate is worthless if an unapproved module slips through, if another session is blocked,
or if the agent can approve itself. All three directions are asserted below.

Run: python .claude/hooks/test-approved-test-plan.py
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HOOK = os.path.join(os.path.dirname(os.path.realpath(__file__)), "guard-approved-test-plan.py")
BLOCK, ALLOW = 2, 0
SESSION = "session-under-test"
OTHER_SESSION = "another-session"
fails: list[str] = []

workspace = tempfile.mkdtemp(prefix="approval-gate-selftest-")
gate_dir = os.path.join(workspace, "gate")
tests_root = os.path.join(workspace, "pkg", "tests")
os.makedirs(gate_dir)
os.makedirs(os.path.join(tests_root, "unit", "auth"))
existing_module = os.path.join(tests_root, "unit", "auth", "test_existing.py")
with open(existing_module, "w", encoding="utf-8") as handle:
    handle.write("")
proposals_dir = os.path.join(workspace, "proposals")
os.makedirs(proposals_dir)
env = dict(os.environ, DATRIX_APPROVAL_GATE_DIR=gate_dir, DATRIX_CASE_PROPOSALS_DIR=proposals_dir)


def run(payload: dict[str, object]) -> int:
    process = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                             capture_output=True, text=True, env=env)
    return process.returncode


def write(path: str, session: str = SESSION, tool: str = "Write") -> int:
    return run({"tool_name": tool, "session_id": session, "tool_input": {"file_path": path}})


def case_write(path: str, content: str, session: str = SESSION) -> int:
    return run({"tool_name": "Write", "session_id": session, "tool_input": {"file_path": path, "content": content}})


def case_edit(path: str, old: str, new: str) -> int:
    return run({"tool_name": "Edit", "session_id": SESSION,
                "tool_input": {"file_path": path, "old_string": old, "new_string": new}})


def row(case_id: str) -> str:
    return f"- id: {case_id}\n  tags: [identity]\n  input: shop\n  stage: generate\n"


def shell(command: str) -> int:
    return run({"tool_name": "PowerShell", "session_id": SESSION, "tool_input": {"command": command}})


def check(label: str, got: int, want: int) -> None:
    ok = got == want
    if not ok:
        fails.append(f"{label}: exit {got} want {want}")
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")


def tests_path(relative: str) -> str:
    return os.path.join(tests_root, *relative.split("/"))


try:
    new_module = tests_path("unit/auth/test_new_table.py")

    print("== not armed: nothing is gated ==")
    check("a new test module", write(new_module), ALLOW)

    print("== arming ==")
    armed_path = os.path.join(gate_dir, "armed.json")
    check("creating the arming file", write(armed_path), ALLOW)
    with open(armed_path, "w", encoding="utf-8") as handle:
        json.dump({"session_id": SESSION, "tests_root": tests_root}, handle)
    check("overwriting the arming file", write(armed_path), BLOCK)
    check("editing the arming file", write(armed_path, tool="Edit"), BLOCK)

    print("== armed, nothing approved ==")
    check("a new test module", write(new_module), BLOCK)
    check("the same module from another session", write(new_module, session=OTHER_SESSION), ALLOW)
    check("an existing test module", write(existing_module), ALLOW)
    check("a non-test module under tests", write(tests_path("unit/auth/helpers.py")), ALLOW)
    check("a test module outside the tests root",
          write(os.path.join(workspace, "other", "tests", "test_x.py")), ALLOW)

    print("== the agent cannot approve itself ==")
    approval = os.path.join(gate_dir, "identity.approved")
    check("writing an approval", write(approval), BLOCK)
    check("a shell copy into the gate", shell(f"Copy-Item plan.txt {approval}"), BLOCK)
    check("a shell removal of the arming file", shell(f"Remove-Item {armed_path}"), BLOCK)
    check("an unrelated shell command", shell("git status --short"), ALLOW)

    print("== armed, approved ==")
    with open(approval, "w", encoding="utf-8") as handle:
        handle.write("# identity cluster\nunit/auth/test_new_table.py  # the decision table\n")
    check("the approved module", write(new_module), ALLOW)
    check("an unlisted module", write(tests_path("unit/auth/test_unlisted.py")), BLOCK)

    print("== armed: a case id reaches a case file only through an approved proposal ==")
    case_file = tests_path("cases/identity.cases.yaml")
    approved_id = "identity.shop.context.tenant-name"
    check("a case id no proposal holds", case_write(case_file, row("identity.shop.unapproved")), BLOCK)
    check("the same from another session", case_write(case_file, row("identity.shop.unapproved"),
                                                      session=OTHER_SESSION), ALLOW)
    proposal = os.path.join(proposals_dir, "pkg-substring.proposal.json")
    with open(proposal, "w", encoding="utf-8") as handle:
        json.dump({"records": [{"disposition": "case", "case": {"id": approved_id}},
                               {"disposition": "case", "existing": "identity.shop.kept"},
                               {"disposition": "unplaced", "reason": "a fragment"}]}, handle)
    with open(proposal, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    check("before the proposal is approved", case_write(case_file, row(approved_id)), BLOCK)
    with open(os.path.join(gate_dir, "pkg-substring.cases.approved"), "w", encoding="utf-8") as handle:
        handle.write(f"proposal: pkg-substring.proposal.json\nsha256: {digest}\n{approved_id}\n")
    check("an id of the approved proposal", case_write(case_file, row(approved_id)), ALLOW)
    check("an id the proposal covers by an existing case", case_write(case_file, row("identity.shop.kept")), ALLOW)
    check("an approved id beside an unapproved one",
          case_write(case_file, row(approved_id) + row("identity.shop.unapproved")), BLOCK)
    check("a flow-style row with an unapproved id", case_write(case_file, "- {id: 'identity.shop.flow', tags: []}\n"),
          BLOCK)
    check("a block-scalar id no proposal holds",
          case_write(case_file, "- id: >-\n    identity.shop.folded\n  tags: [identity]\n"), BLOCK)
    parity_file = tests_path("cases/identity.parity.yaml")
    check("a parity row id no proposal holds", case_write(parity_file, row("identity.shop.parity-unapproved")), BLOCK)
    check("a parity row id of the approved proposal", case_write(parity_file, row(approved_id)), ALLOW)
    check("a parity row id from another session",
          case_write(parity_file, row("identity.shop.parity-unapproved"), session=OTHER_SESSION), ALLOW)

    print("== armed: an approval approves nothing until it names every security and `not in` row ==")
    guarded_id, absent_id = "identity.shop.guard.statements", "identity.shop.guard.absent-bypass"
    protected_proposal = os.path.join(proposals_dir, "pkg-modules-abc.proposal.json")
    with open(protected_proposal, "w", encoding="utf-8") as handle:
        json.dump({"records": [
            {"disposition": "case", "security": False, "not_in": False,
             "case": {"id": guarded_id, "tags": ["tenancy"]}},
            {"disposition": "case", "security": False, "not_in": True,
             "case": {"id": absent_id, "tags": ["compose"]}},
        ]}, handle)
    with open(protected_proposal, "rb") as handle:
        protected_digest = hashlib.sha256(handle.read()).hexdigest()
    protected_approval = os.path.join(gate_dir, "pkg-modules-abc.cases.approved")
    with open(protected_approval, "w", encoding="utf-8") as handle:
        handle.write(f"proposal: pkg-modules-abc.proposal.json\nsha256: {protected_digest}\n{guarded_id}\n")
    check("a row of a proposal whose approval omits its `not in` row", case_write(case_file, row(guarded_id)), BLOCK)
    with open(protected_approval, "w", encoding="utf-8") as handle:
        handle.write(f"proposal: pkg-modules-abc.proposal.json\nsha256: {protected_digest}\n{absent_id}\n")
    check("a row of a proposal whose approval omits its security-tagged row", case_write(case_file, row(absent_id)),
          BLOCK)
    with open(protected_approval, "w", encoding="utf-8") as handle:
        handle.write(f"proposal: pkg-modules-abc.proposal.json\nsha256: {protected_digest}\n{guarded_id}\n{absent_id}\n")
    check("a row of a proposal whose approval names every protected row",
          case_write(case_file, row(guarded_id) + row(absent_id)), ALLOW)
    os.makedirs(os.path.dirname(case_file), exist_ok=True)
    with open(case_file, "w", encoding="utf-8") as handle:
        handle.write(row("identity.shop.legacy"))
    check("an edit that changes a field, adding no id",
          case_edit(case_file, "input: shop", "input: storefront"), ALLOW)
    check("an edit that renames an id to an unapproved one",
          case_edit(case_file, "identity.shop.legacy", "identity.shop.renamed"), BLOCK)
    with open(proposal, "a", encoding="utf-8") as handle:
        handle.write("\n")
    check("an approved proposal changed after approval approves nothing",
          case_write(case_file, row(approved_id)), BLOCK)

    print("== armed: an annotation reaches a fixture only through an approved annotation proposal ==")
    fixture = tests_path("fixtures/billing/system.dtrx")
    os.makedirs(os.path.dirname(fixture), exist_ok=True)
    service = "service shop.InvoiceService('config/i.dcfg') : version('banana') {\n}\n"
    with open(fixture, "w", encoding="utf-8") as handle:
        handle.write(service)
    expect_block = ["// @expect SVC002", "// @tags semantic-analysis", "// @reason A version is semver."]
    annotated = "\n".join(expect_block) + "\n" + service
    per_code = tests_path("fixtures/diagnostics/SVC002.invalid_version.dtrx")
    per_code_text = "// @tags semantic-analysis\n// @reason A version is semver.\n// @expect SVC002.invalid_version\n" + service
    check("an annotation no proposal writes", case_write(fixture, annotated), BLOCK)
    check("the same from another session", case_write(fixture, annotated, session=OTHER_SESSION), ALLOW)
    check("an edit adding no annotation line", case_edit(fixture, "version('banana')", "version('1.0.0')"), ALLOW)
    check("a per-code fixture no proposal writes", case_write(per_code, per_code_text), BLOCK)
    annotation_proposal = os.path.join(proposals_dir, "pkg-annotations-abc.proposal.json")

    def propose(security: bool) -> str:
        with open(annotation_proposal, "w", encoding="utf-8") as handle:
            json.dump({"mode": "annotations", "records": [
                {"disposition": "annotate", "id": "versions.test-svc002", "security": security, "edits": [
                    {"edit": "annotation", "path": "fixtures/billing/system.dtrx", "line": 1, "lines": expect_block},
                    {"edit": "fixture", "path": "fixtures/diagnostics/SVC002.invalid_version.dtrx",
                     "text": per_code_text},
                ]},
                {"disposition": "unplaced", "reason": "its input is built at run time"},
            ]}, handle)
        with open(annotation_proposal, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()

    annotation_approval = os.path.join(gate_dir, "pkg-annotations-abc.cases.approved")
    with open(annotation_approval, "w", encoding="utf-8") as handle:
        handle.write(f"proposal: pkg-annotations-abc.proposal.json\nsha256: {propose(security=False)}\n")
    check("the annotation the approved proposal writes", case_write(fixture, annotated), ALLOW)
    check("the per-code fixture the approved proposal writes", case_write(per_code, per_code_text), ALLOW)
    check("an extra annotation beside the approved one",
          case_write(fixture, annotated.replace("{\n}", "{ // @expect SVC003\n}")), BLOCK)
    check("the approved annotation in another fixture",
          case_write(tests_path("fixtures/other/system.dtrx"), annotated), BLOCK)
    with open(annotation_approval, "w", encoding="utf-8") as handle:
        handle.write(f"proposal: pkg-annotations-abc.proposal.json\nsha256: {propose(security=True)}\n")
    check("a proposal whose approval omits its security record approves nothing",
          case_write(fixture, annotated), BLOCK)
    with open(annotation_approval, "w", encoding="utf-8") as handle:
        handle.write(f"proposal: pkg-annotations-abc.proposal.json\nsha256: {propose(security=True)}\n"
                     "versions.test-svc002\n")
    check("a proposal whose approval names its security record", case_write(fixture, annotated), ALLOW)
finally:
    shutil.rmtree(workspace, ignore_errors=True)

if fails:
    print(f"\n{len(fails)} FAILED:")
    for failure in fails:
        print(f"  {failure}")
    sys.exit(1)
print("\nall passed")
