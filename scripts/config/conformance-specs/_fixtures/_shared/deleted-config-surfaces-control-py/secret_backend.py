# SYNTHETIC NON-VACUITY CONTROL FIXTURE -- never imported, never real source.
# Exists only so the SecretBackend.AWS_SSM conformance spec's must_not_contain
# assertion can prove its pattern is not vacuous.
#
# Kept as a separate control root from deleted-config-surfaces-control/ because
# the runner scans a control tree with the assertion's own glob, and that spec
# globs 'secret_backend.py' rather than '**/system.dcfg'.
AWS_SSM_CONTROL_TOKEN = "aws-ssm"
