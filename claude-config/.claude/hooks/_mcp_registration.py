"""Whether a Datrix MCP server is registered for the directory a session runs in.

The code index's and the local models' tools reach an agent only through an MCP registration
on the machine, made by ``code-index.ps1 -Setup`` and ``local-llm.ps1 -Setup``. Nothing in any
repository carries it, so a machine that never ran a setup -- or a session started in a
directory the registration does not cover -- has none of that server's ``mcp__<server>__*``
tools. Hooks that point an agent at those tools ask this module first, so they never send an
agent to look for a tool its session does not have.

Claude Code finds a server in three places, and so does this module:
  * user scope    -- ``mcpServers`` at the top of ``~/.claude.json``, every directory;
  * local scope   -- ``projects[<directory>].mcpServers`` in ``~/.claude.json``, keyed by the
                     exact directory the session started in (drive-letter case included;
                     separators differ between builds, so they are normalised);
  * project scope -- ``mcpServers`` in ``<directory>/.mcp.json`` -- which the setups write --
                     loaded only once approved on the machine: named in
                     ``enabledMcpjsonServers`` (or ``enableAllProjectMcpServers`` set) in
                     ``<directory>/.claude/settings.local.json`` or in the project's entry of
                     ``~/.claude.json``, and not named in ``disabledMcpjsonServers``. An
                     unapproved entry has no tools, so it does not count.

A config that cannot be read or parsed counts as no registration: the caller then names the
setup command, which is right either way.

The directory that matters is the one the session STARTED in, which Claude Code hands every
hook as ``CLAUDE_PROJECT_DIR``. A hook payload's ``cwd`` is the shell's current directory,
which moves whenever the agent changes directory; it stands in only when the variable is
absent (at SessionStart the two are the same directory).
"""

import json
import os
from typing import Final

CODE_INDEX_SERVER: Final = "datrix-code-index"
LOCAL_LLM_SERVER: Final = "datrix-local-llm"
_USER_CONFIG_NAME: Final = ".claude.json"
_PROJECT_CONFIG_NAME: Final = ".mcp.json"
_PROJECT_DIR_VARIABLE: Final = "CLAUDE_PROJECT_DIR"
_LOCAL_SETTINGS_PATH: Final = (".claude", "settings.local.json")
_ENABLED_KEY: Final = "enabledMcpjsonServers"
_DISABLED_KEY: Final = "disabledMcpjsonServers"
_ENABLE_ALL_KEY: Final = "enableAllProjectMcpServers"


def session_directory(payload_cwd: str) -> str:
    """The directory the session started in: ``CLAUDE_PROJECT_DIR``, else the payload's ``cwd``."""
    return os.environ.get(_PROJECT_DIR_VARIABLE) or payload_cwd


def _load_json_object(path: str) -> dict[str, object]:
    try:
        with open(path, encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _names_server(config: object, server: str) -> bool:
    if not isinstance(config, dict):
        return False
    servers = config.get("mcpServers")
    return isinstance(servers, dict) and server in servers


def _normalised_directory(directory: str) -> str:
    return directory.replace("\\", "/").rstrip("/")


def _user_project_entries(user_config: dict[str, object], directory: str) -> list[dict[str, object]]:
    """The ``~/.claude.json`` project entries keyed by ``directory``, in any separator spelling."""
    projects = user_config.get("projects")
    if not isinstance(projects, dict):
        return []
    wanted = _normalised_directory(directory)
    return [project for key, project in projects.items()
            if _normalised_directory(str(key)) == wanted and isinstance(project, dict)]


def _lists(config: dict[str, object], key: str, server: str) -> bool:
    values = config.get(key)
    return isinstance(values, list) and server in values


def _project_server_approved(approvals: list[dict[str, object]], server: str) -> bool:
    if any(_lists(config, _DISABLED_KEY, server) for config in approvals):
        return False
    return any(_lists(config, _ENABLED_KEY, server) or config.get(_ENABLE_ALL_KEY) is True
               for config in approvals)


def is_registered(directory: str, server: str) -> bool:
    """True when a Claude Code session started in ``directory`` loads ``server``."""
    if not directory:
        return False
    user_config = _load_json_object(os.path.join(os.path.expanduser("~"), _USER_CONFIG_NAME))
    if _names_server(user_config, server):
        return True
    entries = _user_project_entries(user_config, directory)
    if any(_names_server(entry, server) for entry in entries):
        return True
    if not _names_server(_load_json_object(os.path.join(directory, _PROJECT_CONFIG_NAME)), server):
        return False
    local_settings = _load_json_object(os.path.join(directory, *_LOCAL_SETTINGS_PATH))
    return _project_server_approved([local_settings, *entries], server)
