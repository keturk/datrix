"""Set up a stdio MCP server for the workspace on this machine (``code-index.ps1 -Setup``, ``local-llm.ps1 -Setup``).

Three steps, each one file or one registration:

* the server is written into ``<workspace>/.mcp.json`` with this machine's paths -- the venv's
  interpreter running the server module, with the shared scripts package on ``PYTHONPATH`` (Claude
  Code starts the server itself, not through a wrapper, so it inherits none). Claude Code reads that
  file from the folder it opens, for every installation and whatever the drive-letter case. It is
  written here, not checked in, because its paths are this machine's. Every other server already in
  the file is kept.
* the server is approved in ``<workspace>/.claude/settings.local.json`` (gitignored, per machine):
  current builds ignore an approval in the checked-in ``settings.json`` -- a repository must not
  approve its own servers -- so running the setup is the approval. Every other setting is kept.
* an older local-scope registration (``~/.claude.json``, keyed by the exact working-directory
  string, once per installation and drive-letter spelling) would shadow the project file, so each
  Claude Code installation removes it (``claude mcp remove --scope local``) from each spelling of the
  workspace, and a registration still reported afterwards fails the setup.

Nothing else is written. A file that is not valid JSON fails the setup with its repair
(``McpSetupError``); it is never overwritten.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.paths import PYTHONPATH_ROOT
from datrix_scripts.venv import get_venv_python

MCP_CONFIG_NAME: Final = ".mcp.json"
LOCAL_SETTINGS: Final = Path(".claude") / "settings.local.json"
SERVERS_KEY: Final = "mcpServers"
APPROVED_KEY: Final = "enabledMcpjsonServers"
_CLAUDE: Final = "claude"
_EXTENSIONS_DIR: Final = Path(".vscode") / "extensions"
_EXTENSION_PATTERN: Final = re.compile(r"^anthropic\.claude-code-(\d+)\.(\d+)\.(\d+)")
_BUNDLED_BINARY: Final = Path("resources") / "native-binary" / ("claude.exe" if os.name == "nt" else "claude")
_LOCAL_SCOPE: Final = re.compile(r"Scope:\s*Local")
_DRIVE: Final = re.compile(r"^[A-Za-z]:")
_JSON_INDENT: Final = 4
_SAMPLE_SERVER: Final = "datrix-sample"
_SAMPLE_MODULE: Final = "datrix_scripts.dev.sample_mcp"
_SAMPLE_SETUP: Final = "sample.ps1 -Setup"


class McpSetupError(Exception):
    """The setup cannot complete: a file is not valid JSON, or a stale registration survived removal."""


def claude_installations() -> list[str]:
    """Every Claude Code that can start a session on this machine: the CLI on ``PATH``, and the
    newest build the VS Code extension bundles.

    They are separate installations with different versions, and they key local scope differently
    (2.0 by ``D:\\datrix``, 2.1 by ``D:/datrix``), so a stale local-scope registration is looked for
    through each of them.
    """
    found: list[str] = []
    on_path = shutil.which(_CLAUDE)
    if on_path:
        found.append(on_path)
    extensions = Path.home() / _EXTENSIONS_DIR
    if not extensions.is_dir():
        return found
    versioned = [
        (tuple(int(part) for part in match.groups()), entry)
        for entry in extensions.iterdir()
        if entry.is_dir() and (match := _EXTENSION_PATTERN.match(entry.name))
    ]
    if versioned:
        bundled = max(versioned)[1] / _BUNDLED_BINARY
        if bundled.is_file():
            found.append(str(bundled))
    return found


def read_json_object(path: Path, setup_command: str) -> dict[str, object]:
    """The top-level object of *path*; empty when the file does not exist."""
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise McpSetupError(f"{path} is not valid JSON ({exc}); fix or delete it and re-run {setup_command}.") from exc
    if not isinstance(loaded, dict):
        raise McpSetupError(
            f"{path} holds a JSON {type(loaded).__name__}, expected an object; fix or delete it and re-run "
            f"{setup_command}."
        )
    return loaded


def write_json_object(path: Path, table: dict[str, object]) -> None:
    """Write *table* to *path* as UTF-8 JSON (no BOM), ending in a newline."""
    path.write_text(json.dumps(table, indent=_JSON_INDENT) + "\n", encoding="utf-8")


def server_entry(module: str) -> dict[str, object]:
    """The ``.mcp.json`` entry that starts *module* under this machine's venv interpreter."""
    return {
        "type": "stdio",
        "command": str(get_venv_python()),
        "args": ["-m", module],
        "env": {"PYTHONPATH": str(PYTHONPATH_ROOT)},
    }


def _workspace_spellings(text: str) -> list[str]:
    """Workspace path *text* with an upper-case and a lower-case drive letter (one spelling without a drive)."""
    if not _DRIVE.match(text):
        return [text]
    return list(dict.fromkeys([text[0].upper() + text[1:], text[0].lower() + text[1:]]))


def remove_local_registrations(name: str, workspace: Path, installations: Sequence[str]) -> None:
    """Remove every local-scope *name* registration each installation holds for each workspace spelling.

    Each ``claude`` call runs with that spelling as its working directory, so the key it looks up is
    the one an earlier setup wrote. ``claude mcp remove`` exits non-zero when there is nothing to
    remove, so success is read from ``claude mcp get`` afterwards, never from the exit code.
    """
    for claude in installations:
        for directory in _workspace_spellings(str(workspace)):
            subprocess.run(
                [claude, "mcp", "remove", "--scope", "local", name],
                cwd=directory, capture_output=True, check=False,
            )
            details = subprocess.run(
                [claude, "mcp", "get", name],
                cwd=directory, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
            )
            reported = details.stdout + details.stderr
            if _LOCAL_SCOPE.search(reported):
                raise McpSetupError(
                    f"A local-scope '{name}' registration ({claude}, {directory}) could not be removed: {reported}"
                )


def install_project_mcp_server(
    *,
    name: str,
    module: str,
    workspace: Path,
    setup_command: str,
    installations: Sequence[str] | None = None,
) -> None:
    """Write server *name* (running *module*) into the workspace ``.mcp.json``, approve it for this
    machine and remove its stale local-scope registrations (*installations*, every Claude Code here
    when None). Raises ``McpSetupError`` with the repair, naming *setup_command*."""
    config_path = workspace / MCP_CONFIG_NAME
    config = read_json_object(config_path, setup_command)
    existing = config.get(SERVERS_KEY) or {}
    if not isinstance(existing, dict):
        raise McpSetupError(
            f"{config_path}'s {SERVERS_KEY!r} is a JSON {type(existing).__name__}, expected an object; fix or delete "
            f"it and re-run {setup_command}."
        )
    config[SERVERS_KEY] = {**existing, name: server_entry(module)}
    write_json_object(config_path, config)
    print(f"Wrote '{name}' into {config_path}.")

    settings_path = workspace / LOCAL_SETTINGS
    settings = read_json_object(settings_path, setup_command)
    approved_value = settings.get(APPROVED_KEY) or []
    if not isinstance(approved_value, list):
        raise McpSetupError(
            f"{settings_path}'s {APPROVED_KEY!r} is a JSON {type(approved_value).__name__}, expected a list; fix "
            f"or delete it and re-run {setup_command}."
        )
    approved = [entry for entry in approved_value if entry]
    if name not in approved:
        approved.append(name)
    settings[APPROVED_KEY] = approved
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_object(settings_path, settings)

    remove_local_registrations(name, workspace, claude_installations() if installations is None else installations)
    print(
        f"Approved '{name}' for this machine in {settings_path}. Restart Claude Code (in VS Code: "
        "Developer: Reload Window) to load its tools."
    )


def run_setup(*, name: str, module: str, workspace: Path, setup_command: str) -> int:
    """``install_project_mcp_server`` as a wrapper action: 0 when set up, 1 with the reason on stderr."""
    try:
        install_project_mcp_server(name=name, module=module, workspace=workspace, setup_command=setup_command)
    except McpSetupError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


def _check_setup_keeps_other_entries_and_writes_only_two_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        other_server = {"type": "stdio", "command": "node", "args": ["server.js"]}
        write_json_object(workspace / MCP_CONFIG_NAME, {SERVERS_KEY: {"other": other_server}, "extra": 1})
        (workspace / LOCAL_SETTINGS).parent.mkdir()
        write_json_object(workspace / LOCAL_SETTINGS, {APPROVED_KEY: ["other"], "permissions": {"allow": ["x"]}})
        before = sorted(path.relative_to(workspace) for path in workspace.rglob("*"))
        for _ in range(2):  # A second run must neither duplicate the approval nor drop anything.
            with contextlib.redirect_stdout(io.StringIO()):  # The setup's own messages, for the real run.
                install_project_mcp_server(
                    name=_SAMPLE_SERVER, module=_SAMPLE_MODULE, workspace=workspace, setup_command=_SAMPLE_SETUP,
                    installations=(),
                )
        after = sorted(path.relative_to(workspace) for path in workspace.rglob("*"))
        assert after == before, f"the setup must write only its two files; before {before}, after {after}"
        config = read_json_object(workspace / MCP_CONFIG_NAME, _SAMPLE_SETUP)
        assert config["extra"] == 1, config
        assert config[SERVERS_KEY] == {"other": other_server, _SAMPLE_SERVER: server_entry(_SAMPLE_MODULE)}, config
        assert server_entry(_SAMPLE_MODULE)["args"] == ["-m", _SAMPLE_MODULE]
        settings = read_json_object(workspace / LOCAL_SETTINGS, _SAMPLE_SETUP)
        assert settings == {APPROVED_KEY: ["other", _SAMPLE_SERVER], "permissions": {"allow": ["x"]}}, settings


def _check_setup_refuses_invalid_json_and_leaves_it() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        broken = "{ not json"
        (workspace / MCP_CONFIG_NAME).write_text(broken, encoding="utf-8")
        try:
            install_project_mcp_server(
                name=_SAMPLE_SERVER, module=_SAMPLE_MODULE, workspace=workspace, setup_command=_SAMPLE_SETUP,
                installations=(),
            )
        except McpSetupError as exc:
            assert "is not valid JSON" in str(exc) and _SAMPLE_SETUP in str(exc), str(exc)
        else:
            raise AssertionError("an invalid .mcp.json must fail the setup")
        assert (workspace / MCP_CONFIG_NAME).read_text(encoding="utf-8") == broken, "an invalid file must not be rewritten"
        assert not (workspace / LOCAL_SETTINGS).exists(), "nothing is approved when the config could not be written"


def _check_workspace_spellings() -> None:
    cases = {
        "D:\\datrix": ["D:\\datrix", "d:\\datrix"],
        "d:\\datrix": ["D:\\datrix", "d:\\datrix"],
        "/srv/datrix": ["/srv/datrix"],
    }
    for text, expected in cases.items():
        assert _workspace_spellings(text) == expected, f"{text!r} -> {_workspace_spellings(text)}, expected {expected}"


SELF_TEST_CHECKS: Final = (
    _check_setup_keeps_other_entries_and_writes_only_two_files,
    _check_setup_refuses_invalid_json_and_leaves_it,
    _check_workspace_spellings,
)
