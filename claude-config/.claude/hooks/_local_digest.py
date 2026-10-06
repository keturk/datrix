"""A local model's digest of a log, for the hooks that hand an agent one instead of the log.

``digest-red-test-run.py`` (after a failed test run) and ``redirect-large-read.py`` (the first
whole read of a large log) both ask the local model servers for the distinct failures in a log
(``datrix_scripts.local_reading.digest_log``) and put the answer in front of the agent. This module is
their one implementation: the settings a hook can afford -- resident models only, short
timeouts, so a hook answers in a minute or not at all -- and the call, which never raises.

Every request is recorded in the local-model usage log under the calling hook's name.
"""

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

from _hook_log import add_scripts_lib_to_path

if TYPE_CHECKING:
    from datrix_scripts.local_llm import LocalLlmSettings

REACHABLE_TIMEOUT_MS: Final = 1500
GENERATE_TIMEOUT_MS: Final = 60000
MAX_DIGEST_CHARS: Final = 3500


def default_settings(caller: str) -> "LocalLlmSettings":
    """Resident models only, short timeouts, requests recorded under ``caller``."""
    add_scripts_lib_to_path()
    from datrix_scripts.local_llm import LocalLlmSettings

    return LocalLlmSettings(allow_load=False, reachable_timeout_ms=REACHABLE_TIMEOUT_MS,
                            generate_timeout_ms=GENERATE_TIMEOUT_MS, caller=caller)


def digest_of(log: Path, workspace: Path, settings: "LocalLlmSettings", writer: str) -> str:
    """The local model's list of the distinct failures in ``log``; empty when there is none.

    Empty, never an exception, when the log is missing or outside the read scope, or no model
    server answers: a hook adds nothing rather than failing the tool call it observed. The
    reason goes to stderr, named ``writer``.
    """
    add_scripts_lib_to_path()
    from datrix_scripts.local_llm import LocalLlmPool, LocalLlmUnavailable
    from datrix_scripts.local_reading import ReadScope, ReadScopeError, digest_log

    if not log.is_file():
        return ""
    scope = ReadScope(workspace)
    try:
        relative = log.resolve().relative_to(scope.workspace).as_posix()
        answer = digest_log(scope, LocalLlmPool(settings, report=lambda _line: None), relative, "")
    except (ValueError, ReadScopeError, LocalLlmUnavailable, OSError) as exc:
        sys.stderr.write(f"{writer}: no digest of {log}: {exc}\n")
        return ""
    return answer.render()[:MAX_DIGEST_CHARS]
