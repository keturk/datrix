"""NEGATIVE CONTROL FIXTURE for the standing conformance spec
'dgen-corpus-no-hand-authored-module-tuple'.

Never imported or executed by anything -- it exists purely so the spec's
must_not_contain assertion has a live, textual proof that its regex CAN
match (conformance_gate.py's non-vacuity rule: a pattern absent from BOTH
the target and the negative control proves nothing and fails as vacuous).
This is a frozen textual snapshot of the retired hand-authored DAL generator
module tuple the seed spec asserts is gone from the real
scripts/gates/realization/lib/dgen_corpus_resolution.py.

Do not delete, rename, or "fix" this file to match the derived
implementation -- its entire purpose is to keep containing the OLD literal
shape forever, as the spec's vacuity check. If this file is ever deleted,
the spec's must_not_contain assertion silently degrades to "always passes,
proves nothing" -- exactly the failure mode this fixture exists to prevent.
"""

DGEN_DEFINITION_MODULES = (
    "datrix_codegen_python.dgen.definitions",
    "datrix_codegen_typescript.dgen_definitions",
    "datrix_codegen_sql.dgen.sql_definitions",
    "datrix_codegen_docker.dgen_definitions",
    "datrix_codegen_aws.dgen.aws_definitions",
    "datrix_codegen_azure.dgen.azure_definitions",
    "datrix_codegen_component.dgen_definitions",
)
