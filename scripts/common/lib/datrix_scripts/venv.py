"""The shared Datrix virtual environment: where it is, how it is built, and what is installed in it.

``common/venv.ps1`` and its POSIX twin ``common/venv.sh`` run this module; the wrapper's parameters
are its options. Every other Python script imports it to locate the venv's interpreter
(``get_venv_python``) and to word the refusal for a tool the venv should hold
(``missing_declared_tool``).

* **The venv** (``--ensure``, ``--recreate``): ``<workspace>/.venv``, created from a CPython built
  for the host CPU (``find_base_interpreter``; ``DATRIX_PYTHON`` names the only candidate). A venv
  built from an interpreter of another architecture runs emulated and builds native extensions
  (the Tree-sitter parser) for the wrong CPU, so it is refused (``check_venv_architecture``).
  ``--ensure`` first checks that the whole workspace is cloned. ``--recreate`` moves the old venv
  aside (a running interpreter cannot delete its own venv) and removes it once nothing uses it.
* **The installs** (``--ensure-packages``, ``--install-package``): every ``datrix-*`` package with a
  ``pyproject.toml`` installed editable (``--no-build-isolation``) in dependency order
  (``datrix_scripts.install_order``); then each package's ``[dev]`` extra
  (``datrix_scripts.dev_specs``), only once every package is installed, because a dev spec may
  name a sibling; then the ``scripts`` dependency group of ``datrix/pyproject.toml``. A package is
  reinstalled when it does not import, has no install marker, or its ``pyproject.toml`` or a
  ``src`` file is newer than the marker. Every install holds one workspace-wide lock
  (``<workspace>/.venv-package.lock``), so concurrent runs never write the venv at once.
* **Checks** (``--test-command``: ``datrix --version`` runs; ``--base-interpreter``;
  ``--list-packages``: the install order).

``DATRIX_OFFLINE`` set to 1, true or yes (or ``--offline``) runs no pip: the installs are verified
and anything missing or stale fails, naming the repair. ``DATRIX_VENV_VERBOSE`` set the same way
prints each step. Every pip call runs ``<venv python> -m pip`` by path, from the package's own
directory (relative ``file:`` specs resolve from the working directory), with the temp and cache
directories under ``<workspace>/.tmp``.

``--ensure`` also runs under the wrapper's bootstrap Python, before the venv exists, so this module
loads only the standard library and standard-library-only ``datrix_scripts`` modules; the install
steps run under the venv's interpreter and import the TOML readers where they are used.
"""

from __future__ import annotations

import argparse
import atexit
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from datrix_scripts.entrypoint import wrapper_command, wrapper_flag
from datrix_scripts.package_imports import FAILURE_PREFIX, SUMMARY_PREFIX
from datrix_scripts.paths import SCRIPTS_DIR, WORKSPACE_DIR, script_env

#: Where the shared venv's third-party tools are declared, for ``missing_declared_tool``.
SCRIPTS_DEPENDENCY_GROUP = "the `scripts` dependency group of datrix/pyproject.toml"
PACKAGE_DEV_EXTRAS = "the [dev] extras of the datrix-* packages"
PACKAGE_DEPENDENCIES = "the dependencies of the datrix-* packages"

WINDOWS: Final = os.name == "nt"
VENV_DIR_NAME: Final = ".venv"
VERBOSE_ENV: Final = "DATRIX_VENV_VERBOSE"
OFFLINE_ENV: Final = "DATRIX_OFFLINE"
PYTHON_ENV: Final = "DATRIX_PYTHON"
_TRUTHY: Final = frozenset({"1", "true", "yes"})
#: The wrapper that runs this module (under scripts/, without its suffix), named in every repair
#: this module prints through ``venv_command``.
WRAPPER: Final = "common/venv"
MODULE: Final = "datrix_scripts.venv"
EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
_BANNER: Final = "=" * 40

#: A complete clone contains these repositories. Deliberately a named list, not a scan, so it can
#: detect a repository that is MISSING; it must stay complete -- every shipped language and
#: platform package belongs here, so the parity and conformance gates that sweep the registered
#: target set are never vacuous against an incomplete workspace.
REQUIRED_REPOS: Final = (
    "datrix-cli",
    "datrix-common",
    "datrix-codegen-component",
    "datrix-codegen-common",
    "datrix-codegen-python",
    "datrix-codegen-typescript",
    "datrix-codegen-sql",
    "datrix-language",
    "datrix-codegen-aws",
    "datrix-codegen-azure",
    "datrix-codegen-angular",
    "datrix-codegen-flutter",
    "datrix-codegen-docker",
    "datrix-testing",
    "datrix-rdbms-schema",
    "datrix-semantic",
    "datrix-codegen-kernel",
    "datrix-codegen-typescript-core",
)

LOCK_TIMEOUT_SECONDS: Final = 120.0
LOCK_STALE_SECONDS: Final = 300.0
LOCK_POLL_SECONDS: Final = 2.0
_LOCK_RACE_RETRY_SECONDS: Final = 0.5
_LOCK_ERROR_RETRY_SECONDS: Final = 1.0
INSTALL_ATTEMPTS: Final = 2
_INSTALL_RETRY_DELAY_SECONDS: Final = 2.0
#: Editable installs write .pth files; the import check waits this long for the file system.
_EDITABLE_SETTLE_SECONDS: Final = 0.5
REPAIR_DELAY_SECONDS: Final = 2.0
_MARKER_TIME_FORMAT: Final = "%Y-%m-%d %H:%M:%S"
_MARKER_DIR: Final = ".datrix-markers"
_SCRIPTS_MARKER: Final = "datrix.scripts.marker"
_LOCK_FILE: Final = ".venv-package.lock"
_TEMP_DIR: Final = ".tmp"
_PIP_CACHE_DIR: Final = "pip-cache"
_SCRIPTS_PROJECT: Final = "datrix"
_PYPROJECT: Final = "pyproject.toml"
_PYVENV_CFG: Final = "pyvenv.cfg"
_RETIRED_VENV_PREFIX: Final = ".venv.retired-"
_CORRUPTED_PREFIX: Final = "~"
#: Paths under a package's ``src`` that are not package source: tools and test runs write there.
_NON_SOURCE_DIRS: Final = frozenset({"__pycache__", ".generated", ".pytest_cache", "tests"})
#: Build backends every editable install needs present, since ``--no-build-isolation`` never
#: installs a backend; and the extra ones one package's backend needs (hatchling builds its
#: editable wheel through the separate ``editables`` package).
_BASE_BUILD_BACKENDS: Final = ("setuptools", "wheel")
_PACKAGE_BUILD_BACKENDS: Final[Mapping[str, tuple[str, ...]]] = {"datrix-extensions": ("hatchling", "editables")}
_PERMISSION_ERROR: Final = re.compile(r"Permission denied|Errno 13|Access is denied")

# CPU architectures, named as Windows names PROCESSOR_ARCHITECTURE.
ARCH_AMD64: Final = "AMD64"
ARCH_ARM64: Final = "ARM64"
ARCH_X86: Final = "x86"
_PE_MACHINES: Final[Mapping[int, str]] = {0x8664: ARCH_AMD64, 0xAA64: ARCH_ARM64, 0x014C: ARCH_X86}
_ELF_MACHINES: Final[Mapping[int, str]] = {0x3E: ARCH_AMD64, 0xB7: ARCH_ARM64, 0x03: ARCH_X86}
_MACHO_CPU_TYPES: Final[Mapping[int, str]] = {0x01000007: ARCH_AMD64, 0x0100000C: ARCH_ARM64, 0x00000007: ARCH_X86}
_UNAME_MACHINES: Final[Mapping[str, str]] = {
    "x86_64": ARCH_AMD64, "amd64": ARCH_AMD64, "aarch64": ARCH_ARM64, "arm64": ARCH_ARM64,
    "i386": ARCH_X86, "i686": ARCH_X86, "x86": ARCH_X86,
}
#: uv's names for an architecture, for the install command a refusal suggests.
_UV_ARCH_NAMES: Final[Mapping[str, str]] = {ARCH_AMD64: "x86_64", ARCH_ARM64: "aarch64", ARCH_X86: "i686"}
#: Offset of e_lfanew (the PE header's file offset) inside the DOS header.
_PE_HEADER_POINTER_OFFSET: Final = 0x3C
#: Bytes read from the start of an executable: the DOS and PE headers of any linker's output.
_EXECUTABLE_PROBE_BYTES: Final = 4096
_ELF_MAGIC: Final = b"\x7fELF"
_ELF_DATA_OFFSET: Final = 5
_ELF_BIG_ENDIAN: Final = 2
_ELF_MACHINE_OFFSET: Final = 18
_MACHO_MAGICS: Final = frozenset({0xFEEDFACE, 0xFEEDFACF})
_MACHO_FAT_MAGIC: Final = b"\xca\xfe\xba\xbe"
_MACHO_FAT_ENTRY_BYTES: Final = 20
_HOST_ARCH_KEY: Final = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
_VERSION_PROBE: Final = "import sys; v = sys.version_info; print(f'{v.major}.{v.minor}.{v.micro} {v.releaselevel}')"
_VERSION_LINE: Final = re.compile(r"^(\d+)\.(\d+)\.(\d+) (\w+)$")
_FINAL_RELEASE: Final = "final"
_REQUIRES_PYTHON: Final = re.compile(r'^\s*requires-python\s*=\s*">=\s*(\d+)\.(\d+)"', re.MULTILINE)
_PY_LAUNCHER_PATH: Final = re.compile(r"([A-Za-z]:\\.+?\.exe)\s*$")
_STORE_ALIAS_DIR: Final = "windowsapps"
_CFG_LINE: Final = re.compile(r"^\s*([^=]+?)\s*=\s*(.*?)\s*$")
# Windows process liveness (OpenProcess / GetExitCodeProcess).
_PROCESS_QUERY_LIMITED_INFORMATION: Final = 0x1000
_STILL_ACTIVE: Final = 259
_ERROR_ACCESS_DENIED: Final = 5


class VenvError(RuntimeError):
    """The venv or its installs are not in a state this module can act on; the message names the repair."""


class BaseInterpreterError(VenvError):
    """No interpreter on the machine may build the venv."""


class ArchitectureError(VenvError):
    """An executable's architecture cannot be read."""


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------


def venv_python(venv_root: Path) -> Path:
    """The interpreter inside the venv at *venv_root*."""
    if WINDOWS:
        return venv_root / "Scripts" / "python.exe"
    return venv_root / "bin" / "python"


@dataclass(frozen=True)
class VenvLayout:
    """Where the venv and its bookkeeping live for one workspace."""

    workspace: Path

    @property
    def root(self) -> Path:
        return self.workspace / VENV_DIR_NAME

    @property
    def python(self) -> Path:
        return venv_python(self.root)

    @property
    def datrix_cli(self) -> Path:
        return self.python.with_name("datrix.exe" if WINDOWS else "datrix")

    @property
    def markers(self) -> Path:
        return self.root / _MARKER_DIR

    @property
    def lock_path(self) -> Path:
        return self.workspace / _LOCK_FILE

    @property
    def temp_dir(self) -> Path:
        return self.workspace / _TEMP_DIR

    @property
    def scripts_project(self) -> Path:
        return self.workspace / _SCRIPTS_PROJECT

    @property
    def scripts_marker(self) -> Path:
        return self.markers / _SCRIPTS_MARKER

    def site_packages_dirs(self) -> list[Path]:
        """The venv's site-packages directories that exist."""
        if WINDOWS:
            candidates = [self.root / "Lib" / "site-packages"]
        else:
            candidates = sorted(self.root.glob("lib/python*/site-packages"))
        return [path for path in candidates if path.is_dir()]

    def package_dir(self, package: str) -> Path:
        return self.workspace / package

    def install_marker(self, package: str) -> Path:
        return self.markers / f"{package}.marker"

    def dev_marker(self, package: str) -> Path:
        return self.markers / f"{package}.dev.marker"


WORKSPACE_LAYOUT: Final = VenvLayout(WORKSPACE_DIR)


def venv_command(*parameters: str) -> str:
    """The wrapper command with *parameters* (its parameter names, e.g. ``Ensure``) as this platform
    types it: ``common\\venv.ps1 -Ensure`` on Windows, ``common/venv.sh --ensure`` elsewhere."""
    return wrapper_command(WRAPPER, *parameters)


def venv_repair() -> str:
    """The command that installs every declared package and tool into the shared venv from its manifests."""
    return wrapper_command(f"scripts/{WRAPPER}", "EnsurePackages")


def missing_declared_tool(distribution: str, declared_in: str) -> str:
    """The refusal for a tool the shared venv declares but this interpreter cannot import.

    A declared tool is installed with the venv, so its absence means the venv is incomplete or the
    script runs under another interpreter -- never a reason to carry on with less.
    """
    return (
        f"{distribution} cannot be imported by {sys.executable}. It is declared in {declared_in}, "
        "which the shared venv installs, so this venv is incomplete or this is not the shared venv's "
        f"interpreter. Repair the venv with {venv_repair()} (test.ps1 runs it), "
        f"or run the script with {get_venv_python()}."
    )


def get_venv_path() -> Path:
    """The shared venv's directory, ``<workspace>/.venv``."""
    return WORKSPACE_LAYOUT.root


def is_venv_active() -> bool:
    """True when a virtual environment is active (VIRTUAL_ENV set, or this interpreter is a venv's)."""
    if os.environ.get("VIRTUAL_ENV"):
        return True
    return sys.prefix != sys.base_prefix


def get_venv_python() -> Path:
    """The interpreter of the active venv when one is active, else the shared venv's interpreter."""
    active_venv = os.environ.get("VIRTUAL_ENV")
    if active_venv:
        return venv_python(Path(active_venv))
    if sys.prefix != sys.base_prefix:
        return Path(sys.executable)
    return WORKSPACE_LAYOUT.python


def module_name(package: str) -> str:
    """A package directory's import name: ``datrix-codegen-python`` -> ``datrix_codegen_python``.

    Derived, not tabulated, so a new ``datrix-codegen-<lang>`` package needs no edit here.
    """
    return package.replace("-", "_")


# ---------------------------------------------------------------------------
# Output and processes
# ---------------------------------------------------------------------------


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def is_verbose() -> bool:
    """True when ``DATRIX_VENV_VERBOSE`` asks for each step to be printed."""
    return _env_flag(VERBOSE_ENV)


def is_offline() -> bool:
    """True when ``DATRIX_OFFLINE`` forbids pip and every other network install."""
    return _env_flag(OFFLINE_ENV)


def _info(message: str = "") -> None:
    if is_verbose():
        print(message, flush=True)


def _warn(message: str) -> None:
    if is_verbose():
        print(f"WARNING: {message}", file=sys.stderr, flush=True)


def _error(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr, flush=True)


def _offline_refusal() -> str:
    return f"{OFFLINE_ENV} is set: pip installs are disabled. Unset {OFFLINE_ENV} and install packages while online."


def _stamp(marker: Path) -> None:
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(datetime.now().strftime(_MARKER_TIME_FORMAT) + "\n", encoding="utf-8")


def _newer(path: Path, than: Path) -> bool:
    return path.stat().st_mtime > than.stat().st_mtime


def _run(
    command: Sequence[str | Path], *, cwd: Path | None = None, env: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run *command* (an argument vector, never a shell string); stdout and stderr merged, in order."""
    return subprocess.run(
        [str(part) for part in command],
        cwd=cwd,
        env=None if env is None else dict(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


# ---------------------------------------------------------------------------
# Architectures and the base interpreter
# ---------------------------------------------------------------------------


def _pe_architecture(data: bytes, path: Path) -> str:
    header = int.from_bytes(data[_PE_HEADER_POINTER_OFFSET:_PE_HEADER_POINTER_OFFSET + 4], "little", signed=True)
    if header <= 0 or header + 6 > len(data) or data[header:header + 2] != b"PE":
        raise ArchitectureError(f"Not a Windows PE executable: {path}. Expected an MZ/PE image (python.exe of a CPython install).")
    machine = int.from_bytes(data[header + 4:header + 6], "little")
    if machine not in _PE_MACHINES:
        raise ArchitectureError(
            f"Unrecognised PE machine type 0x{machine:04X} in {path}. Known types: AMD64 (0x8664), ARM64 (0xAA64), x86 (0x014C)."
        )
    return _PE_MACHINES[machine]


def _elf_architecture(data: bytes, path: Path) -> str:
    order = "big" if data[_ELF_DATA_OFFSET] == _ELF_BIG_ENDIAN else "little"
    machine = int.from_bytes(data[_ELF_MACHINE_OFFSET:_ELF_MACHINE_OFFSET + 2], order)
    if machine not in _ELF_MACHINES:
        raise ArchitectureError(
            f"Unrecognised ELF machine type 0x{machine:04X} in {path}. Known types: x86-64 (0x3E), AArch64 (0xB7), i386 (0x03)."
        )
    return _ELF_MACHINES[machine]


def _macho_architectures(data: bytes, path: Path) -> frozenset[str]:
    if data[:4] == _MACHO_FAT_MAGIC:
        count = int.from_bytes(data[4:8], "big")
        offsets = [8 + index * _MACHO_FAT_ENTRY_BYTES for index in range(count)]
        cpu_types = [int.from_bytes(data[offset:offset + 4], "big") for offset in offsets]
    else:
        cpu_types = [int.from_bytes(data[4:8], "little")]
    known = frozenset(_MACHO_CPU_TYPES[cpu] for cpu in cpu_types if cpu in _MACHO_CPU_TYPES)
    if not known:
        raise ArchitectureError(f"No known CPU type in the Mach-O image {path}. Known types: x86-64, arm64, i386.")
    return known


def executable_architectures(data: bytes, path: Path) -> frozenset[str]:
    """The architectures the executable whose first bytes are *data* runs natively on.

    A PE or ELF image has one; a universal (fat) Mach-O image may have several.
    """
    if data[:2] == b"MZ":
        return frozenset({_pe_architecture(data, path)})
    if data[:4] == _ELF_MAGIC:
        return frozenset({_elf_architecture(data, path)})
    if data[:4] == _MACHO_FAT_MAGIC or int.from_bytes(data[:4], "little") in _MACHO_MAGICS:
        return _macho_architectures(data, path)
    raise ArchitectureError(f"Not a PE, ELF or Mach-O executable: {path}. Expected the python executable of a CPython install.")


def executable_architectures_of(path: Path) -> frozenset[str]:
    """The architectures of the executable at *path* (``executable_architectures``)."""
    with open(path, "rb") as stream:
        return executable_architectures(stream.read(_EXECUTABLE_PROBE_BYTES), path)


def host_architecture() -> str:
    """The machine's CPU architecture, independent of emulation.

    Windows: read from the system environment in the registry, never this process's
    PROCESSOR_ARCHITECTURE (an x64 process emulated on ARM64 sees AMD64). macOS: arm64 hardware
    answers ``hw.optional.arm64``. Elsewhere: the kernel's machine name.
    """
    if WINDOWS:
        import winreg  # Windows-only standard module.

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _HOST_ARCH_KEY) as key:
            value = str(winreg.QueryValueEx(key, "PROCESSOR_ARCHITECTURE")[0]).strip()
        if not value:
            raise ArchitectureError(
                f"Cannot determine the host CPU architecture: PROCESSOR_ARCHITECTURE is empty under HKLM\\{_HOST_ARCH_KEY}. "
                "Expected AMD64, ARM64 or x86."
            )
        return value
    if sys.platform == "darwin":
        answer = _run(["sysctl", "-n", "hw.optional.arm64"]).stdout.strip()
        return ARCH_ARM64 if answer == "1" else ARCH_AMD64
    machine = os.uname().machine.lower()
    if machine not in _UNAME_MACHINES:
        raise ArchitectureError(f"Unrecognised machine type {machine!r}. Known types: {', '.join(sorted(_UNAME_MACHINES))}.")
    return _UNAME_MACHINES[machine]


def required_python_version(workspace: Path) -> tuple[int, int]:
    """The minimum Python the Datrix packages declare (``requires-python`` of datrix-common)."""
    pyproject = workspace / "datrix-common" / _PYPROJECT
    text = pyproject.read_text(encoding="utf-8") if pyproject.is_file() else ""
    match = _REQUIRES_PYTHON.search(text)
    if match is None:
        raise BaseInterpreterError(
            f'Cannot read the minimum Python version from {pyproject}. Expected a line like: requires-python = ">=3.11".'
        )
    return int(match.group(1)), int(match.group(2))


def _path_interpreters() -> list[str]:
    names = ("python.exe",) if WINDOWS else ("python3", "python")
    found: list[str] = []
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if directory:
            found.extend(str(Path(directory) / name) for name in names if (Path(directory) / name).is_file())
    return found


def _py_launcher_interpreters() -> list[str]:
    launcher = shutil.which("py") if WINDOWS else None
    if launcher is None:
        return []
    listed = _run([launcher, "-0p"]).stdout.splitlines()
    return [match.group(1) for match in (_PY_LAUNCHER_PATH.search(line) for line in listed) if match]


def _uv_interpreters() -> list[str]:
    uv = shutil.which("uv")
    if uv is None:
        return []
    listed = subprocess.run(
        [uv, "python", "list", "--only-installed", "--output-format", "json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if listed.returncode != 0 or not listed.stdout.strip():
        return []
    try:
        entries = json.loads(listed.stdout)
    except ValueError as exc:
        raise BaseInterpreterError(
            f"'uv python list --output-format json' printed output that is not JSON ({exc}). "
            f"Update uv, or set {PYTHON_ENV} to an interpreter, then retry."
        ) from exc
    return [
        str(entry["path"]) for entry in entries
        if isinstance(entry, dict) and entry.get("implementation") == "cpython" and entry.get("path")
    ]


def _is_venv_interpreter(path: Path) -> bool:
    return (path.parent.parent / _PYVENV_CFG).is_file()


def filter_candidates(raw: Iterable[str]) -> list[Path]:
    """Existing interpreters from *raw*, resolved and de-duplicated, minus Store aliases (stubs that
    open the Microsoft Store) and venv interpreters (not a base to build a venv from)."""
    seen: set[str] = set()
    kept: list[Path] = []
    for entry in raw:
        given = Path(entry)
        if not given.is_file() or _is_venv_interpreter(given):
            continue
        resolved = given.resolve()
        key = str(resolved).casefold() if WINDOWS else str(resolved)
        store_alias = _STORE_ALIAS_DIR in (part.casefold() for part in resolved.parts)
        if store_alias or _is_venv_interpreter(resolved) or key in seen:
            continue
        seen.add(key)
        kept.append(resolved)
    return kept


def interpreter_candidates() -> list[Path]:
    """Every CPython the machine offers: DATRIX_PYTHON, python on PATH, the py launcher's list and
    uv-managed interpreters, filtered by ``filter_candidates``."""
    chosen = os.environ.get(PYTHON_ENV, "").strip()
    raw = ([chosen] if chosen else []) + _path_interpreters() + _py_launcher_interpreters() + _uv_interpreters()
    return filter_candidates(raw)


@dataclass(frozen=True)
class InterpreterProbe:
    """What one candidate interpreter is: its architectures and version, or why they are unknown."""

    path: Path
    architectures: frozenset[str]
    version: tuple[int, int, int]
    release_level: str
    problem: str

    def describe(self) -> str:
        arch = ", ".join(sorted(self.architectures)) or "unknown architecture"
        version = ".".join(str(part) for part in self.version) + f" {self.release_level}" if self.release_level else "version unknown"
        detail = f"; {self.problem}" if self.problem else ""
        return f"  {self.path} ({arch}, {version}{detail})"


def probe_interpreter(path: Path) -> InterpreterProbe:
    """Read *path*'s architectures from its header and its version by running it."""
    unknown = (0, 0, 0)
    try:
        architectures = executable_architectures_of(path)
    except (ArchitectureError, OSError) as exc:
        return InterpreterProbe(path, frozenset(), unknown, "", str(exc))
    try:
        answer = _run([path, "-c", _VERSION_PROBE])
    except OSError as exc:
        return InterpreterProbe(path, architectures, unknown, "", f"it could not be run: {exc}")
    match = _VERSION_LINE.match(answer.stdout.strip())
    if answer.returncode != 0 or match is None:
        return InterpreterProbe(path, architectures, unknown, "", f"the version probe exited {answer.returncode}")
    version = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return InterpreterProbe(path, architectures, version, match.group(4), "")


def choose_base_interpreter(probes: Sequence[InterpreterProbe], host: str, required: tuple[int, int]) -> Path:
    """The interpreter to build the venv from: built for *host*, a final release of at least
    *required*, the highest version first. An interpreter of another architecture runs emulated and
    builds native extensions for the wrong CPU, so it is never chosen."""
    eligible = [
        probe for probe in probes
        if host in probe.architectures and probe.release_level == _FINAL_RELEASE and probe.version[:2] >= required
    ]
    if eligible:
        return max(eligible, key=lambda probe: probe.version).path
    found = "\n".join(probe.describe() for probe in probes) or "  (none)"
    minimum = f"{required[0]}.{required[1]}"
    platform_suffix = f"-windows-{_UV_ARCH_NAMES[host]}" if WINDOWS and host in _UV_ARCH_NAMES else ""
    raise BaseInterpreterError(
        f"No CPython >= {minimum} built for this machine's CPU ({host}) was found. Interpreters found:\n{found}\n"
        "An interpreter of another architecture runs emulated and builds native extensions for the wrong CPU, so it is not used.\n"
        f"Fix: install a native {host} CPython (for example: uv python install cpython-{minimum}{platform_suffix}), "
        f"or set {PYTHON_ENV} to the path of one, then retry."
    )


def _same_file(left: Path, right: Path) -> bool:
    if WINDOWS:
        return str(left.resolve()).casefold() == str(right.resolve()).casefold()
    return left.resolve() == right.resolve()


def find_base_interpreter(workspace: Path) -> Path:
    """The CPython to build the venv from (``choose_base_interpreter`` over ``interpreter_candidates``).

    ``DATRIX_PYTHON``, when set, is the only candidate.
    """
    host = host_architecture()
    required = required_python_version(workspace)
    candidates = interpreter_candidates()
    chosen = os.environ.get(PYTHON_ENV, "").strip()
    if chosen:
        candidates = [candidate for candidate in candidates if _same_file(candidate, Path(chosen))]
    return choose_base_interpreter([probe_interpreter(candidate) for candidate in candidates], host, required)


def venv_base_interpreter(venv_root: Path) -> Path:
    """The interpreter a venv was created from, read from its pyvenv.cfg (executable, else home)."""
    cfg = venv_root / _PYVENV_CFG
    if not cfg.is_file():
        raise VenvError(f"Not a virtual environment: {cfg} is missing. Recreate it with {venv_command('Recreate')}.")
    values: dict[str, str] = {}
    for line in cfg.read_text(encoding="utf-8").splitlines():
        match = _CFG_LINE.match(line)
        if match:
            values[match.group(1).lower()] = match.group(2)
    if "executable" in values and Path(values["executable"]).is_file():
        return Path(values["executable"])
    if "home" in values:
        from_home = Path(values["home"]) / ("python.exe" if WINDOWS else "python3")
        if from_home.is_file():
            return from_home
    raise VenvError(
        f"Cannot find the base interpreter of the venv at {venv_root}: pyvenv.cfg names neither an existing "
        f"'executable' nor a 'home' holding the interpreter. Recreate it with {venv_command('Recreate')}."
    )


# ---------------------------------------------------------------------------
# The venv
# ---------------------------------------------------------------------------


def workspace_missing_repos(workspace: Path) -> list[str]:
    """The ``REQUIRED_REPOS`` with no directory in *workspace*."""
    return [repo for repo in REQUIRED_REPOS if not (workspace / repo).exists()]


def check_workspace_present(layout: VenvLayout) -> bool:
    """True when every required repository is cloned; otherwise prints which are missing."""
    missing = workspace_missing_repos(layout.workspace)
    if not missing:
        return True
    lines = [
        "", _BANNER, " DATRIX WORKSPACE NOT FOUND", _BANNER, "",
        "This is the Datrix showcase repository containing documentation,",
        "examples, and development scripts.", "",
        "The scripts require the full Datrix workspace to function.",
        "The following repositories are missing:", "",
        *(f"  - {repo}" for repo in missing), "",
        "To explore what Datrix generates, browse the examples/ directory",
        "and the generated output in examples/02-domains/*/generated/.", "",
        "For access to the full platform, visit:", "  https://github.com/keturk", "", _BANNER, "",
    ]
    print("\n".join(lines), flush=True)
    return False


def remove_retired_venvs(layout: VenvLayout) -> None:
    """Delete the venvs ``--recreate`` moved aside. One still in use (the interpreter that moved it
    is running) stays, named, until a later run removes it."""
    for retired in sorted(layout.workspace.glob(f"{_RETIRED_VENV_PREFIX}*")):
        try:
            shutil.rmtree(retired)
        except OSError as exc:
            print(f"The retired venv {retired} is still in use ({exc}); the next {venv_command('Ensure')} removes it.", flush=True)


def _retire_venv(layout: VenvLayout) -> bool:
    retired = layout.workspace / f"{_RETIRED_VENV_PREFIX}{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    _info(f"Moving the existing virtual environment aside to {retired}...")
    try:
        layout.root.rename(retired)
    except OSError as exc:
        _error(f"Cannot move the venv at {layout.root} aside ({exc}). Stop every process using it, then retry.")
        return False
    return True


def create_venv(layout: VenvLayout, *, force: bool) -> bool:
    """Create the venv from ``find_base_interpreter``'s choice. With *force*, an existing venv is
    moved aside first (and deleted once nothing runs from it)."""
    if layout.python.is_file() and not force:
        _info(f"Virtual environment already exists at: {layout.root}")
        return True
    try:
        base = find_base_interpreter(layout.workspace)
    except VenvError as exc:
        _error(str(exc))
        return False
    if force and layout.root.exists() and not _retire_venv(layout):
        return False
    _info(f"Creating virtual environment at: {layout.root} from {base}")
    _info()
    result = _run([base, "-m", "venv", layout.root])
    if result.returncode != 0:
        _error(
            f"Failed to create virtual environment at {layout.root} from {base} "
            f"(exit code {result.returncode}): {result.stdout.strip()}"
        )
        return False
    remove_retired_venvs(layout)
    _info("Virtual environment created successfully")
    return True


def check_venv_architecture(layout: VenvLayout) -> bool:
    """False, naming both architectures and the repair, when the venv's interpreter is not built for this CPU."""
    host = host_architecture()
    base = venv_base_interpreter(layout.root)
    architectures = executable_architectures_of(base)
    if host in architectures:
        return True
    _error(
        f"The Datrix venv at {layout.root} runs an interpreter built for {', '.join(sorted(architectures))} ({base}) "
        f"on a machine whose CPU is {host}. It runs emulated and builds native extensions (the Tree-sitter parser) "
        "for the wrong CPU.\n"
        f"Fix: stop every process using the venv, then run {venv_command('Recreate', 'EnsurePackages')} (or delete "
        f"{layout.root} and run {venv_command('Ensure', 'EnsurePackages')}); a native {host} CPython is picked, or set "
        f"{PYTHON_ENV} to one."
    )
    return False


def ensure_venv(layout: VenvLayout) -> bool:
    """The workspace is complete, the venv exists (created if not) and is built for this CPU."""
    if not check_workspace_present(layout):
        return False
    remove_retired_venvs(layout)
    if not layout.python.is_file():
        _info(f"Virtual environment not found at: {layout.root}")
        _info("Creating virtual environment...")
        _info()
        if not create_venv(layout, force=False):
            return False
        _info()
    return check_venv_architecture(layout)


# ---------------------------------------------------------------------------
# The package lock
# ---------------------------------------------------------------------------


def _windows_process_alive(pid: int) -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ctypes.get_last_error() == _ERROR_ACCESS_DENIED
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == _STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def process_alive(pid: int) -> bool:
    """True when a process with *pid* is running (one this user may not inspect counts as running)."""
    if pid <= 0:
        return False
    if WINDOWS:
        return _windows_process_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class PackageLock:
    """The workspace-wide exclusive lock every install holds, so concurrent pip runs never corrupt
    the one shared venv. A JSON file (pid, timestamp, script) created atomically; one older than the
    stale age, one whose process is gone, or one that cannot be read is removed. Re-entrant within a
    process, and released at exit if a run ends holding it."""

    def __init__(
        self,
        path: Path,
        *,
        timeout_seconds: float = LOCK_TIMEOUT_SECONDS,
        stale_seconds: float = LOCK_STALE_SECONDS,
        poll_seconds: float = LOCK_POLL_SECONDS,
    ) -> None:
        self.path = path
        self.timeout_seconds = timeout_seconds
        self.stale_seconds = stale_seconds
        self.poll_seconds = poll_seconds
        self._depth = 0
        self._exit_release_registered = False

    @property
    def held(self) -> bool:
        return self._depth > 0

    def _must_wait(self, waited: float) -> bool:
        """Inspect an existing lock file: remove it when stale, orphaned or unreadable (False), or
        report that a live process holds it (True)."""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            pid = int(data["pid"])
            stamp = datetime.fromisoformat(str(data["timestamp"]))
            age = (datetime.now().astimezone() - stamp.astimezone()).total_seconds()
        except FileNotFoundError:
            return False
        except (OSError, ValueError, KeyError, TypeError):
            _info("Removing corrupted package lock file")
            self.path.unlink(missing_ok=True)
            return False
        if age > self.stale_seconds:
            _info(f"Removing stale package lock (age: {int(age)}s, pid: {pid})")
        elif not process_alive(pid):
            _info(f"Removing orphaned package lock (pid {pid} no longer running)")
        else:
            _info(f"Waiting for package lock (held by pid {pid} for {int(age)}s, waited {int(waited)}s)...")
            return True
        self.path.unlink(missing_ok=True)
        return False

    def _create(self) -> None:
        """Create the lock file atomically; FileExistsError when another process won the race."""
        record = json.dumps({"pid": os.getpid(), "timestamp": datetime.now().astimezone().isoformat(), "script": sys.argv[0]})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(record)

    def _took(self) -> bool:
        """One attempt to create the lock file; False after the retry pause when it failed."""
        try:
            self._create()
        except FileExistsError:
            time.sleep(_LOCK_RACE_RETRY_SECONDS)
            return False
        except OSError as exc:
            _warn(f"Error acquiring package lock: {exc}")
            time.sleep(_LOCK_ERROR_RETRY_SECONDS)
            return False
        return True

    def acquire(self) -> bool:
        """Take the lock, waiting up to the timeout; True when held (already held counts)."""
        if self._depth:
            self._depth += 1
            return True
        started = time.monotonic()
        while time.monotonic() - started <= self.timeout_seconds:
            if self.path.exists() and self._must_wait(time.monotonic() - started):
                time.sleep(self.poll_seconds)
                continue
            if not self._took():
                continue
            self._depth = 1
            if not self._exit_release_registered:
                atexit.register(self._release_at_exit)
                self._exit_release_registered = True
            _info(f"Package lock acquired (pid: {os.getpid()})")
            return True
        _warn(f"Timeout waiting for package lock after {self.timeout_seconds:g} seconds")
        return False

    def release(self) -> None:
        """Release one hold; the file is removed when the last hold ends, and only if this process wrote it."""
        if not self._depth:
            return
        self._depth -= 1
        if self._depth:
            return
        try:
            owner = int(json.loads(self.path.read_text(encoding="utf-8"))["pid"])
        except FileNotFoundError:
            return
        except (OSError, ValueError, KeyError, TypeError):
            self.path.unlink(missing_ok=True)
            return
        if owner == os.getpid():
            self.path.unlink(missing_ok=True)
            _info(f"Package lock released (pid: {os.getpid()})")

    def _release_at_exit(self) -> None:
        if self._depth:
            self._depth = 1
            self.release()

    @contextmanager
    def holding(self) -> Iterator[bool]:
        """Hold the lock for a block; yields whether it was acquired."""
        acquired = self.acquire()
        try:
            yield acquired
        finally:
            if acquired:
                self.release()


_LOCKS: dict[Path, PackageLock] = {}


def package_lock(layout: VenvLayout) -> PackageLock:
    """This process's one lock object for *layout*'s lock file, so nested installs re-enter it."""
    return _LOCKS.setdefault(layout.lock_path, PackageLock(layout.lock_path))


# ---------------------------------------------------------------------------
# Install state
# ---------------------------------------------------------------------------


def install_order_packages(layout: VenvLayout) -> list[str]:
    """The installable ``datrix-*`` packages (a directory with a pyproject.toml), in dependency order.

    The order is derived (``datrix_scripts.install_order``); a cycle or a declared datrix-*
    dependency missing from disk raises naming every package involved, never an alphabetical fallback.
    """
    # Imported here: the TOML readers need Python 3.11, and --ensure runs under any bootstrap Python.
    from datrix_scripts.install_order import InstallOrderError, topological_install_order
    from datrix_scripts.pyproject_deps import discover_packages

    try:
        return topological_install_order(discover_packages(layout.workspace))
    except InstallOrderError as exc:
        raise VenvError(f"Failed to compute the Datrix package install order: {exc}") from exc


def import_verdict(lines: Sequence[str], exit_code: int, packages: Sequence[str]) -> list[str]:
    """The packages ``python -m datrix_scripts.package_imports`` reported as not importing.

    Fails closed: an exit code other than the one its failures imply, or a summary line that does
    not account for every module named, raises -- the import state is then unknown, never "all importable".
    """
    package_by_module = {module_name(package): package for package in packages}
    failed_line = re.compile(rf"^{FAILURE_PREFIX} (?P<module>[^:\s]+): ")
    unimportable: list[str] = []
    for line in lines:
        match = failed_line.match(line)
        if match is None:
            continue
        _info(line)
        if match.group("module") in package_by_module:
            unimportable.append(package_by_module[match.group("module")])
    summaries = [line for line in lines if re.fullmatch(rf"{SUMMARY_PREFIX} \d+/\d+", line)]
    summary = summaries[-1] if summaries else ""
    expected_summary = f"{SUMMARY_PREFIX} {len(packages) - len(unimportable)}/{len(packages)}"
    expected_exit = EXIT_FAILED if unimportable else EXIT_OK
    if exit_code != expected_exit or summary != expected_summary:
        output = "\n".join(lines)
        raise VenvError(
            "The package import checker (python -m datrix_scripts.package_imports) gave no usable verdict: "
            f"exit code {exit_code} and summary '{summary}', expected exit code {expected_exit} and "
            f"'{expected_summary}' for the {len(packages)} module(s) named. The packages' import state is unknown; "
            f"fix the checker (run it with --self-test) and retry. Checker output:\n{output}"
        )
    return unimportable


def unimportable_packages(layout: VenvLayout, packages: Sequence[str]) -> list[str]:
    """The *packages* whose module does not import in the venv, each checked once, all in one process."""
    if not layout.python.is_file():
        raise VenvError(
            f"Cannot import-check the Datrix packages: Python not found in the venv at {layout.python}. "
            f"Run {venv_command('Ensure')} first, then retry."
        )
    modules = [module_name(package) for package in packages]
    result = _run([layout.python, "-m", "datrix_scripts.package_imports", *modules], env=script_env())
    return import_verdict(result.stdout.splitlines(), result.returncode, packages)


def _newest_source_mtime(src: Path) -> float:
    newest = 0.0
    for directory, subdirectories, files in os.walk(src):
        subdirectories[:] = [name for name in subdirectories if name not in _NON_SOURCE_DIRS]
        times = [(Path(directory) / name).stat().st_mtime for name in files if name.endswith(".py")]
        newest = max([newest, *times])
    return newest


def package_needs_reinstall(layout: VenvLayout, package: str, *, importable: bool) -> bool:
    """True when *package* is not *importable*, has no install marker, or its pyproject.toml or a
    ``src`` source file is newer than the marker. Starts no process."""
    pyproject = layout.package_dir(package) / _PYPROJECT
    if not pyproject.is_file():
        return False
    marker = layout.install_marker(package)
    if not marker.is_file() or not importable:
        return True
    if _newer(pyproject, marker):
        return True
    src = layout.package_dir(package) / "src"
    return src.is_dir() and _newest_source_mtime(src) > marker.stat().st_mtime


def package_dev_specs(layout: VenvLayout, package: str) -> list[str]:
    """*package*'s ``[dev]`` specs as the venv installs them (a sibling named by bare name)."""
    from datrix_scripts.dev_specs import installable_dev_specs  # 3.11's tomllib; see install_order_packages.

    return installable_dev_specs(layout.package_dir(package))


def dev_extras_need_install(layout: VenvLayout, package: str) -> bool:
    """True when *package* declares ``[dev]`` specs and they were never installed or its
    pyproject.toml changed since. A marker no older than pyproject.toml answers without reading it."""
    pyproject = layout.package_dir(package) / _PYPROJECT
    if not pyproject.is_file():
        return False
    marker = layout.dev_marker(package)
    if marker.is_file() and not _newer(pyproject, marker):
        return False
    return bool(package_dev_specs(layout, package))


def scripts_requirement_specs(layout: VenvLayout) -> list[str]:
    """The ``scripts`` dependency group of datrix/pyproject.toml: the third-party tools the scripts
    tree imports or runs that no datrix-* package declares. A group that cannot be read raises."""
    from datrix_scripts import dev_specs  # 3.11's tomllib; see install_order_packages.

    try:
        return dev_specs.read_dependency_group(layout.scripts_project, dev_specs.SCRIPTS_DEPENDENCY_GROUP)
    except ValueError as exc:
        raise VenvError(f"Cannot read the scripts dependency group of {layout.scripts_project / _PYPROJECT}: {exc}") from exc


def scripts_requirements_need_install(layout: VenvLayout) -> bool:
    """True when the scripts dependency group was never installed or datrix/pyproject.toml changed since."""
    marker = layout.scripts_marker
    return not marker.is_file() or _newer(layout.scripts_project / _PYPROJECT, marker)


def remove_corrupted_packages(layout: VenvLayout) -> None:
    """Delete ``~``-prefixed directories in site-packages: leftovers of interrupted pip runs that
    make pip warn "Ignoring invalid distribution"."""
    leftovers = [
        path for site_packages in layout.site_packages_dirs()
        for path in sorted(site_packages.glob(f"{_CORRUPTED_PREFIX}*")) if path.is_dir()
    ]
    for leftover in leftovers:
        try:
            shutil.rmtree(leftover)
        except OSError:
            _warn(f"Could not remove corrupted directory: {leftover}")
            continue
        _info(f"Removed corrupted package directory: {leftover.name}")


def _pth_names_datrix(path: Path) -> bool:
    try:
        return "datrix" in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def editable_installs_intact(layout: VenvLayout) -> bool:
    """True when site-packages holds a datrix editable install (a .pth naming datrix, an
    ``__editable__*datrix*`` directory or a ``datrix*.egg-link``)."""
    for site_packages in layout.site_packages_dirs():
        found = (
            any(_pth_names_datrix(path) for path in site_packages.glob("*.pth") if path.is_file())
            or any(path.is_dir() for path in site_packages.glob("__editable__*datrix*"))
            or any(path.is_file() for path in site_packages.glob("datrix*.egg-link"))
        )
        if found:
            return True
    return False


def repair_broken_editable_installs(layout: VenvLayout, *, delay_seconds: float = REPAIR_DELAY_SECONDS) -> bool:
    """When install markers exist but no editable install does (an interrupted pip run), remove the
    markers so every package reinstalls. True when nothing needed repair or the repair succeeded."""
    markers = sorted(layout.markers.glob("*.marker")) if layout.markers.is_dir() else []
    if not markers or editable_installs_intact(layout):
        return True
    for line in ("", _BANNER, "DETECTED: Broken editable installs", _BANNER, "Markers exist but .pth files are missing.",
                 "This can happen due to interrupted pip operations.", "", "Initiating automatic repair...",
                 f"Waiting {delay_seconds:g} seconds before repair..."):
        _info(line)
    time.sleep(delay_seconds)
    _info("Removing stale marker files...")
    try:
        for marker in markers:
            marker.unlink(missing_ok=True)
    except OSError as exc:
        _error(f"Failed to remove the install markers in {layout.markers}: {exc}. Delete that directory, then retry.")
        return False
    remove_corrupted_packages(layout)
    for line in ("Marker files removed successfully.", "", "Repair preparation complete. Packages will be reinstalled.", _BANNER, ""):
        _info(line)
    return True


@dataclass(frozen=True)
class CommandCheck:
    """Whether ``datrix --version`` runs, and why not: its output and exit code, or the missing executable."""

    ok: bool
    detail: str


def check_datrix_command(layout: VenvLayout) -> CommandCheck:
    """Run ``datrix --version`` from the venv: the console-script entry point works."""
    executable = layout.datrix_cli
    if not executable.is_file():
        return CommandCheck(False, f"{executable.name} not found at {executable}")
    try:
        result = _run([executable, "--version"])
    except OSError as exc:
        return CommandCheck(False, f"'{executable} --version' could not be run: {exc}")
    if result.returncode == 0:
        return CommandCheck(True, "")
    return CommandCheck(False, f"'{executable} --version' exited {result.returncode}\n{result.stdout.rstrip()}")


# ---------------------------------------------------------------------------
# pip
# ---------------------------------------------------------------------------


def _pip_environment(layout: VenvLayout) -> dict[str, str]:
    """This process's environment with pip's temp directories under the workspace's .tmp folder."""
    layout.temp_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    for name in ("TMP", "TEMP", "TMPDIR"):
        env[name] = str(layout.temp_dir)
    return env


def _pip(layout: VenvLayout, arguments: Sequence[str | Path], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return _run([layout.python, "-m", "pip", *arguments], cwd=cwd, env=_pip_environment(layout))


def _pip_cache(layout: VenvLayout) -> Path:
    cache = layout.temp_dir / _PIP_CACHE_DIR
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _pip_has(layout: VenvLayout, distribution: str) -> bool:
    # One "pip show" per distribution: "pip show a b" exits 0 when only one of them is installed.
    return _pip(layout, ["show", distribution]).returncode == 0


def _print_pip_failure(label: str, output: str, extra: Sequence[str]) -> None:
    lines = ["", _BANNER, label, _BANNER, *extra, *output.splitlines()]
    print("\n".join(lines), flush=True)


def pip_install_specs(layout: VenvLayout, specs: Sequence[str], *, cwd: Path, label: str) -> bool:
    """pip-install requirement *specs* from *cwd*; on failure print *label* and pip's output."""
    result = _pip(layout, ["install", "--cache-dir", _pip_cache(layout), *specs], cwd=cwd)
    if result.returncode == 0:
        return True
    _print_pip_failure(label, result.stdout, [f"Specs: {', '.join(specs)}"])
    _error(f"{label} (pip exit code: {result.returncode})")
    return False


def _ensure_build_backends(layout: VenvLayout, package: str) -> bool:
    """Every editable install runs with --no-build-isolation, so pip never installs a build backend:
    the base backends, and the extra ones *package*'s backend needs, are installed here first."""
    if not all(_pip_has(layout, backend) for backend in _BASE_BUILD_BACKENDS):
        _info("Installing build dependencies (setuptools, wheel)...")
        if _pip(layout, ["install", "--upgrade", *_BASE_BUILD_BACKENDS]).returncode != 0:
            _error("Failed to install build dependencies (setuptools, wheel)")
            return False
    extra = _PACKAGE_BUILD_BACKENDS[package] if package in _PACKAGE_BUILD_BACKENDS else ()
    if extra and not all(_pip_has(layout, backend) for backend in extra):
        _info(f"Installing {package} build prerequisite ({', '.join(extra)})...")
        if _pip(layout, ["install", *extra]).returncode != 0:
            _error(f"Failed to install {package} build prerequisite ({', '.join(extra)})")
            return False
    return True


def _installed_after(layout: VenvLayout, package: str, pip_output: str) -> bool:
    """Whether *package* is installed after its pip run: it imports, or pip reported installing it
    (pip's exit code is unreliable on Windows when temp cleanup fails)."""
    time.sleep(_EDITABLE_SETTLE_SECONDS)
    if not layout.python.is_file():
        return False
    pip_succeeded = re.search(rf"Successfully installed.*{re.escape(package)}", pip_output) is not None
    imported = _run([layout.python, "-c", f"import {module_name(package)}"])
    if imported.returncode == 0:
        return True
    if pip_succeeded:
        _info(f"Note: pip installed {package} but import test failed:")
        _info(imported.stdout.rstrip())
        _info("Continuing since pip reported success.")
    return pip_succeeded


def _report_install_failure(layout: VenvLayout, package: str, result: subprocess.CompletedProcess[str]) -> None:
    _print_pip_failure(
        f"PIP INSTALLATION FAILED for {package}", result.stdout,
        [f"Exit code: {result.returncode}", "", "Pip output:"],
    )
    hints = ["", f"Package path: {layout.package_dir(package)}", _BANNER, ""]
    if _PERMISSION_ERROR.search(result.stdout):
        hints += [
            "This appears to be a permission error with temporary directories.",
            "Suggestions:",
            " 1. Remove the pip-* directories under your temp directory, then retry",
            " 2. Run the shell as Administrator and try again",
            f" 3. The script uses a custom temp directory at: {layout.temp_dir}",
            " Ensure this directory is writable",
        ]
    print("\n".join(hints), flush=True)
    _error(f"Failed to install {package} (exit code: {result.returncode})")


def _install_refusal(layout: VenvLayout, package: str) -> str:
    """Why *package* cannot be installed now; empty when it can."""
    package_dir = layout.package_dir(package)
    if not package_dir.is_dir():
        return f"Package not found: {package_dir}"
    if not (package_dir / _PYPROJECT).is_file():
        return f"pyproject.toml not found in: {package_dir}"
    if is_offline():
        return _offline_refusal()
    if not layout.python.is_file():
        return f"Python not found in the venv at {layout.python}. Run {venv_command('Ensure')} first, then retry."
    return ""


def install_package(layout: VenvLayout, package: str, *, no_dev: bool) -> bool:
    """Install *package* editable (with its ``[dev]`` extra unless *no_dev*), holding the package
    lock, and stamp its install marker."""
    refusal = _install_refusal(layout, package)
    if refusal:
        _error(refusal)
        return False
    package_dir = layout.package_dir(package)
    with package_lock(layout).holding() as acquired:
        if not acquired:
            _error(f"Could not acquire package lock for installing {package}")
            return False
        remove_corrupted_packages(layout)
        if not _ensure_build_backends(layout, package):
            return False
        _info(f"Installing {package} in editable mode...")
        target = str(package_dir) if no_dev else f"{package_dir}[dev]"
        result = _pip(layout, ["install", "--cache-dir", _pip_cache(layout), "--no-build-isolation", "-e", target], cwd=package_dir)
        if not _installed_after(layout, package, result.stdout):
            _report_install_failure(layout, package, result)
            return False
        _info(f"{package} installed successfully")
        _stamp(layout.install_marker(package))
        return True


def install_dev_extras(layout: VenvLayout, package: str) -> bool:
    """Install *package*'s declared ``[dev]`` specs (not the package, already editable) from its
    own directory, and stamp its dev marker."""
    if is_offline():
        _error(_offline_refusal())
        return False
    specs = package_dev_specs(layout, package)
    if specs:
        _info(f"Installing dev extras for {package} ({len(specs)} spec(s))...")
        label = f"DEV-EXTRAS INSTALL FAILED for {package}"
        if not pip_install_specs(layout, specs, cwd=layout.package_dir(package), label=label):
            return False
        _info(f"{package} dev extras installed successfully")
    _stamp(layout.dev_marker(package))
    return True


def install_scripts_requirements(layout: VenvLayout) -> bool:
    """Install the scripts dependency group (the datrix repo is never installed itself, so this is
    the only step that brings in the scripts tree's tools) and stamp its marker."""
    if is_offline():
        _error(_offline_refusal())
        return False
    specs = scripts_requirement_specs(layout)
    if specs:
        _info(f"Installing the scripts dependency group ({len(specs)} spec(s))...")
        label = "SCRIPTS DEPENDENCY-GROUP INSTALL FAILED"
        if not pip_install_specs(layout, specs, cwd=layout.scripts_project, label=label):
            return False
    _stamp(layout.scripts_marker)
    _info("Scripts dependency group installed successfully")
    return True


# ---------------------------------------------------------------------------
# Ensuring the installs
# ---------------------------------------------------------------------------


def _verify_offline(layout: VenvLayout) -> bool:
    """Offline: verify the installs and the CLI without pip."""
    remove_corrupted_packages(layout)
    packages = install_order_packages(layout)
    if not layout.python.is_file():
        _error(f"{OFFLINE_ENV}: Python not found in venv at {layout.python}")
        return False
    unimportable = unimportable_packages(layout, packages)
    if unimportable:
        names = ", ".join(f"'{package}'" for package in unimportable)
        _error(f"{OFFLINE_ENV}: package(s) {names} not importable. Install editable packages while online, then retry.")
        return False
    stale = [package for package in packages if package_needs_reinstall(layout, package, importable=True)]
    if stale:
        _error(f"{OFFLINE_ENV}: package '{stale[0]}' is out of date (pyproject.toml or sources changed). Reinstall while online, then retry.")
        return False
    command = check_datrix_command(layout)
    if not command.ok:
        _error(f"{OFFLINE_ENV}: 'datrix --version' failed. Fix the CLI while online ({venv_command('InstallPackage')} datrix-cli).\n{command.detail}")
        return False
    _info("Offline mode: Datrix packages and CLI verified (no pip).")
    return True


def _outstanding_installs(layout: VenvLayout, packages: Sequence[str]) -> bool:
    """True when a package, a ``[dev]`` extra or the scripts group changed since it was installed."""
    outstanding = False
    for package in packages:
        if package_needs_reinstall(layout, package, importable=True):
            outstanding = True
            _info(f"Package '{package}' has changed pyproject.toml or source files")
        if dev_extras_need_install(layout, package):
            outstanding = True
            _info(f"Package '{package}' has outstanding [dev] extras to install")
    if scripts_requirements_need_install(layout):
        outstanding = True
        _info("The scripts dependency group of datrix/pyproject.toml is outstanding")
    return outstanding


def _installs_current(layout: VenvLayout) -> bool:
    """True when every package imports and nothing is outstanding (``_outstanding_installs``)."""
    if not layout.python.is_file():
        _info("Some packages are not importable, proceeding with installation...")
        return False
    packages = install_order_packages(layout)
    unimportable = unimportable_packages(layout, packages)
    if unimportable:
        _info(f"Package(s) not importable: {', '.join(unimportable)}")
        _info("Some packages are not importable, proceeding with installation...")
        return False
    if _outstanding_installs(layout, packages):
        _info("Some packages have changed, proceeding with installation...")
        return False
    return True


def _install_with_retry(layout: VenvLayout, package: str) -> bool:
    for attempt in range(1, INSTALL_ATTEMPTS + 1):
        if attempt > 1:
            _info(f"Retrying installation of '{package}' (attempt {attempt}/{INSTALL_ATTEMPTS})...")
            time.sleep(_INSTALL_RETRY_DELAY_SECONDS)
        if install_package(layout, package, no_dev=True):
            return True
    return False


def _install_stale_packages(layout: VenvLayout, packages: Sequence[str], *, force: bool, reinstalled: list[str]) -> bool:
    """Pass 1: reinstall every stale package (all with *force*), appending each to *reinstalled*;
    False when one could not be installed."""
    unimportable = [] if force else unimportable_packages(layout, packages)
    for package in packages:
        if not (force or package_needs_reinstall(layout, package, importable=package not in unimportable)):
            continue
        _info(f"Package '{package}' needs reinstallation (source files changed)")
        if not _install_with_retry(layout, package):
            _error(f"Failed to reinstall package: {package} after {INSTALL_ATTEMPTS} attempts")
            return False
        reinstalled.append(package)
    return True


def _install_all(layout: VenvLayout, *, force: bool) -> bool:
    """Under the lock: every stale package (all with *force*), then every ``[dev]`` extra, then the
    scripts group. Dev extras wait for every base install: a dev spec may name a sibling, which
    would otherwise resolve against PyPI on a rebuild from scratch."""
    if not repair_broken_editable_installs(layout):
        _error("Failed to repair broken editable installs")
        return False
    remove_corrupted_packages(layout)
    packages = install_order_packages(layout)
    reinstalled: list[str] = []
    if not _install_stale_packages(layout, packages, force=force, reinstalled=reinstalled):
        return False
    for package in packages:
        if dev_extras_need_install(layout, package) and not install_dev_extras(layout, package):
            _error(f"Failed to install dev extras for package: {package}")
            return False
    if scripts_requirements_need_install(layout) and not install_scripts_requirements(layout):
        _error("Failed to install the scripts dependency group of datrix/pyproject.toml")
        return False
    if reinstalled:
        _info()
        _info(f"Reinstalled {len(reinstalled)} package(s): {', '.join(reinstalled)}")
    return True


def ensure_packages_installed(layout: VenvLayout, *, force: bool, skip_if_installed: bool, offline: bool) -> bool:
    """Every package installed and current, its dev extras and the scripts group installed.

    *skip_if_installed* returns at once when nothing is outstanding (for runs that must not
    reinstall mid-flight); *force* reinstalls every package; offline (*offline* or
    ``DATRIX_OFFLINE``) verifies without pip.
    """
    offline_mode = offline or is_offline()
    if offline_mode and force:
        _error(
            f"Cannot use {wrapper_flag('Force')} with offline mode ({OFFLINE_ENV} environment variable or "
            f"{wrapper_flag('Offline')} switch): offline mode runs no pip, so nothing can be reinstalled. "
            f"Drop {wrapper_flag('Force')}, or unset {OFFLINE_ENV} and drop {wrapper_flag('Offline')}."
        )
        return False
    if offline_mode:
        return _verify_offline(layout)
    if skip_if_installed and not force:
        remove_corrupted_packages(layout)
        if _installs_current(layout):
            _info("All packages are importable and up-to-date, skipping reinstall (SkipIfInstalled mode)")
            return True
    with package_lock(layout).holding() as acquired:
        if not acquired:
            _error("Could not acquire package lock - another process may be installing packages")
            return False
        return _install_all(layout, force=force)


def require_packages(layout: VenvLayout = WORKSPACE_LAYOUT) -> bool:
    """The check a run that imports the datrix-* packages makes first: the venv is sound and every
    package is installed and current (``ensure_packages_installed`` in its skip-if-installed mode,
    as ``common/venv.ps1 -Ensure -EnsurePackages -SkipIfInstalled`` runs it). On failure prints why
    and returns False."""
    try:
        passed = ensure_venv(layout) and ensure_packages_installed(
            layout, force=False, skip_if_installed=True, offline=False)
    except VenvError as exc:
        _error(str(exc))
        passed = False
    if not passed:
        _error(
            f"the shared venv at {layout.root} and its package installs failed the check above. "
            f"Fix what it names, then re-run (set {VERBOSE_ENV}=1 to see each step of "
            f"{venv_command('Ensure', 'EnsurePackages', 'SkipIfInstalled')})."
        )
    return passed


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


_QUERIES: Final = ("base_interpreter", "list_packages", "self_test")
_ACTIONS: Final = ("recreate", "ensure", "install_package", "ensure_packages", "test_command")
_MODIFIERS: Final = ("skip_if_installed", "force", "offline")


def build_parser() -> argparse.ArgumentParser:
    """The options ``common/venv.ps1`` passes (each wrapper parameter as ``--kebab-name``)."""
    parser = argparse.ArgumentParser(
        prog="venv",
        description=(
            "Create, check and install the shared Datrix venv. Actions run in the order "
            "--recreate, --ensure, --install-package, --ensure-packages, --test-command; "
            "a query (--base-interpreter, --list-packages, --self-test) runs alone."
        ),
    )
    parser.add_argument("--ensure", action="store_true",
                        help="the workspace is complete and the venv exists (created if not) and is built for this CPU")
    parser.add_argument("--recreate", action="store_true", help="build the venv afresh from a native base interpreter")
    parser.add_argument("--ensure-packages", action="store_true",
                        help="install every stale package, then the [dev] extras and the scripts group")
    parser.add_argument("--skip-if-installed", action="store_true",
                        help="with --ensure-packages: return at once when nothing is outstanding")
    parser.add_argument("--force", action="store_true", help="with --ensure-packages: reinstall every package")
    parser.add_argument("--offline", action="store_true", help=f"with --ensure-packages: verify without pip (as {OFFLINE_ENV} does)")
    parser.add_argument("--install-package", metavar="PACKAGE", help="install one package editable, e.g. datrix-cli")
    parser.add_argument("--no-dev", action="store_true", help="with --install-package: without its [dev] extra")
    parser.add_argument("--test-command", action="store_true", help="'datrix --version' runs; on failure print why")
    parser.add_argument("--base-interpreter", action="store_true", help="print the interpreter a new venv would be built from")
    parser.add_argument("--list-packages", action="store_true", help="print the installable packages in install order")
    parser.add_argument("--self-test", action="store_true", help="run this module's self-test")
    return parser


def _usage_problem(args: argparse.Namespace) -> str:
    """Why *args* cannot run together; empty when they can."""
    queries = [name for name in _QUERIES if getattr(args, name)]
    actions = [name for name in _ACTIONS if getattr(args, name)]
    if len(queries) > 1 or (queries and actions):
        return "a query (--base-interpreter, --list-packages, --self-test) runs alone"
    if any(getattr(args, name) for name in _MODIFIERS) and not args.ensure_packages:
        return "--skip-if-installed, --force and --offline modify --ensure-packages"
    if args.no_dev and not args.install_package:
        return "--no-dev modifies --install-package"
    return ""


def _run_query(args: argparse.Namespace, layout: VenvLayout) -> int:
    if args.self_test:
        return EXIT_OK if run_self_test() else EXIT_FAILED
    if args.base_interpreter:
        print(find_base_interpreter(layout.workspace))
        return EXIT_OK
    for package in install_order_packages(layout):
        print(package)
    return EXIT_OK


def _report_command(layout: VenvLayout) -> bool:
    command = check_datrix_command(layout)
    if not command.ok:
        print(command.detail, file=sys.stderr, flush=True)
    return command.ok


def _run_actions(args: argparse.Namespace, layout: VenvLayout) -> int:
    steps: list[tuple[bool, Callable[[], bool]]] = [
        (args.recreate, lambda: create_venv(layout, force=True) and check_venv_architecture(layout)),
        (args.ensure, lambda: ensure_venv(layout)),
        (bool(args.install_package), lambda: install_package(layout, args.install_package, no_dev=args.no_dev)),
        (args.ensure_packages, lambda: ensure_packages_installed(
            layout, force=args.force, skip_if_installed=args.skip_if_installed, offline=args.offline)),
        (args.test_command, lambda: _report_command(layout)),
    ]
    for requested, step in steps:
        if requested and not step():
            return EXIT_FAILED
    return EXIT_OK


def main(argv: Sequence[str] | None = None, layout: VenvLayout = WORKSPACE_LAYOUT) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    problem = _usage_problem(args)
    if problem:
        parser.error(problem)
    if not any(getattr(args, name) for name in (*_QUERIES, *_ACTIONS)):
        parser.print_usage(sys.stderr)
        help_command = f"Get-Help {venv_command()}" if WINDOWS else venv_command("Help")
        print(f"Error: pass an action or a query (see {help_command}).", file=sys.stderr)
        return EXIT_FAILED
    try:
        if any(getattr(args, name) for name in _QUERIES):
            return _run_query(args, layout)
        return _run_actions(args, layout)
    except VenvError as exc:
        _error(str(exc))
        return EXIT_FAILED


# ---------------------------------------------------------------------------
# Self-test (--self-test): planted workspaces, venvs and executables; no pip, no network.
# ---------------------------------------------------------------------------


def _pe_image(machine: int) -> bytes:
    data = bytearray(512)
    data[0:2] = b"MZ"
    data[_PE_HEADER_POINTER_OFFSET:_PE_HEADER_POINTER_OFFSET + 4] = (0x80).to_bytes(4, "little")
    data[0x80:0x82] = b"PE"
    data[0x84:0x86] = machine.to_bytes(2, "little")
    return bytes(data)


def _elf_image(machine: int) -> bytes:
    data = bytearray(64)
    data[0:4] = _ELF_MAGIC
    data[_ELF_DATA_OFFSET] = 1
    data[_ELF_MACHINE_OFFSET:_ELF_MACHINE_OFFSET + 2] = machine.to_bytes(2, "little")
    return bytes(data)


def _fat_macho_image(cpu_types: Sequence[int]) -> bytes:
    data = bytearray(_MACHO_FAT_MAGIC + len(cpu_types).to_bytes(4, "big"))
    for cpu in cpu_types:
        data += cpu.to_bytes(4, "big") + bytes(_MACHO_FAT_ENTRY_BYTES - 4)
    return bytes(data)


def _raises(error: type[Exception], action: Callable[[], object]) -> str:
    try:
        action()
    except error as exc:
        return str(exc)
    raise AssertionError(f"expected {error.__name__}, nothing was raised")


def _check_module_names() -> None:
    assert module_name("datrix-codegen-python") == "datrix_codegen_python", module_name("datrix-codegen-python")


def _check_executable_architectures() -> None:
    planted = Path("planted.exe")
    cases = (
        (_pe_image(0xAA64), {ARCH_ARM64}), (_pe_image(0x8664), {ARCH_AMD64}), (_elf_image(0xB7), {ARCH_ARM64}),
        (_fat_macho_image([0x01000007, 0x0100000C]), {ARCH_AMD64, ARCH_ARM64}),
    )
    for data, expected in cases:
        assert executable_architectures(data, planted) == expected, (expected, executable_architectures(data, planted))
    assert "Unrecognised PE machine" in _raises(ArchitectureError, lambda: executable_architectures(_pe_image(0x1234), planted))
    assert "Not a PE, ELF or Mach-O" in _raises(ArchitectureError, lambda: executable_architectures(b"#!/bin/sh\n", planted))
    assert host_architecture() in {ARCH_AMD64, ARCH_ARM64, ARCH_X86}, host_architecture()
    assert executable_architectures_of(Path(sys.executable)), sys.executable


def _check_required_python_version() -> None:
    with tempfile.TemporaryDirectory(prefix="venv-selftest-") as tmp:
        workspace = Path(tmp)
        assert "Cannot read the minimum Python version" in _raises(BaseInterpreterError, lambda: required_python_version(workspace))
        (workspace / "datrix-common").mkdir()
        (workspace / "datrix-common" / _PYPROJECT).write_text('[project]\nrequires-python = ">=3.11"\n', encoding="utf-8")
        assert required_python_version(workspace) == (3, 11), required_python_version(workspace)


def _check_candidates_are_filtered() -> None:
    with tempfile.TemporaryDirectory(prefix="venv-selftest-") as tmp:
        root = Path(tmp)
        base = root / "cpython" / "python.exe"
        alias = root / "WindowsApps" / "python.exe"
        in_venv = root / "somevenv" / "Scripts" / "python.exe"
        for path in (base, alias, in_venv):
            path.parent.mkdir(parents=True)
            path.write_bytes(b"MZ")
        (root / "somevenv" / _PYVENV_CFG).write_text("home = x\n", encoding="utf-8")
        duplicate = str(base).upper() if WINDOWS else str(base)
        kept = filter_candidates([str(base), duplicate, str(alias), str(in_venv), str(root / "absent.exe")])
        assert kept == [base.resolve()], kept


def _check_base_interpreter_choice() -> None:
    def probe(name: str, arch: str, version: tuple[int, int, int], level: str = _FINAL_RELEASE) -> InterpreterProbe:
        return InterpreterProbe(Path(name), frozenset({arch}), version, level, "")

    probes = [
        probe("emulated", ARCH_AMD64, (3, 14, 0)), probe("old", ARCH_ARM64, (3, 10, 9)),
        probe("beta", ARCH_ARM64, (3, 15, 0), "beta"), probe("native-313", ARCH_ARM64, (3, 13, 2)),
        probe("native-314", ARCH_ARM64, (3, 14, 6)),
    ]
    assert choose_base_interpreter(probes, ARCH_ARM64, (3, 11)) == Path("native-314")
    refusal = _raises(BaseInterpreterError, lambda: choose_base_interpreter(probes[:3], ARCH_ARM64, (3, 11)))
    assert "built for this machine's CPU (ARM64)" in refusal and "emulated" in refusal and PYTHON_ENV in refusal, refusal


def _check_venv_base_interpreter() -> None:
    with tempfile.TemporaryDirectory(prefix="venv-selftest-") as tmp:
        venv_root = Path(tmp) / "venv"
        venv_root.mkdir()
        assert "Not a virtual environment" in _raises(VenvError, lambda: venv_base_interpreter(venv_root))
        home = Path(tmp) / "home"
        home.mkdir()
        interpreter = home / ("python.exe" if WINDOWS else "python3")
        interpreter.write_bytes(b"")
        cfg = venv_root / _PYVENV_CFG
        cfg.write_text(f"home = {home}\nexecutable = {Path(tmp) / 'gone.exe'}\n", encoding="utf-8")
        assert venv_base_interpreter(venv_root) == interpreter, venv_base_interpreter(venv_root)
        cfg.write_text(f"executable = {interpreter}\n", encoding="utf-8")
        assert venv_base_interpreter(venv_root) == interpreter
        cfg.write_text("version = 3.14.6\n", encoding="utf-8")
        assert "Cannot find the base interpreter" in _raises(VenvError, lambda: venv_base_interpreter(venv_root))


def _dead_pid() -> int:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def _plant_lock(path: Path, pid: int, age_seconds: float) -> None:
    stamp = datetime.fromtimestamp(time.time() - age_seconds).astimezone().isoformat()
    path.write_text(json.dumps({"pid": pid, "timestamp": stamp, "script": "planted"}), encoding="utf-8")


def _check_package_lock() -> None:
    with tempfile.TemporaryDirectory(prefix="venv-selftest-") as tmp:
        path = Path(tmp) / _LOCK_FILE
        lock = PackageLock(path, timeout_seconds=0.2, poll_seconds=0.01)
        assert lock.acquire() and lock.acquire() and path.is_file(), "a free lock was not taken, or not re-entered"
        lock.release()
        assert path.is_file(), "releasing one of two holds removed the lock file"
        lock.release()
        assert not path.exists(), "the last release left the lock file"
        plants: list[tuple[str, Callable[[], object]]] = [
            ("stale", lambda: _plant_lock(path, os.getpid(), LOCK_STALE_SECONDS + 60)),
            ("orphaned", lambda: _plant_lock(path, _dead_pid(), 0)),
            ("corrupted", lambda: path.write_text("{not json", encoding="utf-8")),
        ]
        for label, plant in plants:
            plant()
            assert lock.acquire(), f"a {label} lock was not replaced"
            lock.release()
        _plant_lock(path, os.getppid(), 0)
        assert process_alive(os.getppid()), "this process's parent was reported as not running"
        assert not PackageLock(path, timeout_seconds=0.05, poll_seconds=0.01).acquire(), "a lock held by a live process was taken"
        other = PackageLock(path)
        other._depth = 1
        other.release()
        assert path.is_file(), "a release removed a lock file another holder wrote"
        path.unlink()


def _plant_package(workspace: Path, name: str, dev_specs: Sequence[str] = ()) -> Path:
    package = workspace / name
    (package / "src" / module_name(name)).mkdir(parents=True)
    dev = ", ".join(json.dumps(spec) for spec in dev_specs)
    (package / _PYPROJECT).write_text(
        f'[project]\nname = "{name}"\nversion = "0"\n[project.optional-dependencies]\ndev = [{dev}]\n', encoding="utf-8"
    )
    (package / "src" / module_name(name) / "__init__.py").write_text("", encoding="utf-8")
    return package


def _age(path: Path, seconds_ago: float) -> None:
    moment = time.time() - seconds_ago
    os.utime(path, (moment, moment))


def _check_reinstall_decisions() -> None:
    with tempfile.TemporaryDirectory(prefix="venv-selftest-") as tmp:
        layout = VenvLayout(Path(tmp))
        package = _plant_package(layout.workspace, "datrix-planted", ["pytest"])
        source = package / "src" / "datrix_planted" / "__init__.py"
        cached = package / "src" / "datrix_planted" / "__pycache__" / "x.py"
        cached.parent.mkdir()
        cached.write_text("", encoding="utf-8")
        for path in (package / _PYPROJECT, source):
            _age(path, 100)
        assert package_needs_reinstall(layout, "datrix-planted", importable=True), "no marker must mean reinstall"
        _stamp(layout.install_marker("datrix-planted"))
        _age(layout.install_marker("datrix-planted"), 50)
        assert not package_needs_reinstall(layout, "datrix-planted", importable=True), "a newer __pycache__ file triggered a reinstall"
        assert package_needs_reinstall(layout, "datrix-planted", importable=False), "an unimportable package must reinstall"
        _age(source, 10)
        assert package_needs_reinstall(layout, "datrix-planted", importable=True), "a newer source file did not trigger a reinstall"
        assert dev_extras_need_install(layout, "datrix-planted"), "declared [dev] specs with no marker must install"
        _stamp(layout.dev_marker("datrix-planted"))
        assert not dev_extras_need_install(layout, "datrix-planted"), "a dev marker newer than pyproject.toml must answer False"
        _plant_package(layout.workspace, "datrix-bare")
        assert not dev_extras_need_install(layout, "datrix-bare"), "a package with no [dev] specs has nothing to install"
        layout.scripts_project.mkdir()
        (layout.scripts_project / _PYPROJECT).write_text("[dependency-groups]\nscripts = []\n", encoding="utf-8")
        assert scripts_requirements_need_install(layout), "no scripts marker must mean install"
        _age(layout.scripts_project / _PYPROJECT, 100)
        _stamp(layout.scripts_marker)
        assert not scripts_requirements_need_install(layout) and scripts_requirement_specs(layout) == []
        assert install_order_packages(layout) == ["datrix-bare", "datrix-planted"], install_order_packages(layout)


def _check_import_verdict() -> None:
    packages = ["datrix-common", "datrix-cli"]
    assert import_verdict([f"{SUMMARY_PREFIX} 2/2"], EXIT_OK, packages) == []
    failing = [f"{FAILURE_PREFIX} datrix_cli: ModuleNotFoundError: x", f"{SUMMARY_PREFIX} 1/2"]
    assert import_verdict(failing, EXIT_FAILED, packages) == ["datrix-cli"]
    unusable: list[tuple[list[str], int]] = [(["no summary"], EXIT_OK), ([f"{SUMMARY_PREFIX} 2/2"], EXIT_FAILED), (failing, EXIT_OK)]
    for lines, code in unusable:
        refusal = _raises(VenvError, lambda lines=lines, code=code: import_verdict(lines, code, packages))
        assert "gave no usable verdict" in refusal, refusal


def _check_site_packages_upkeep() -> None:
    with tempfile.TemporaryDirectory(prefix="venv-selftest-") as tmp:
        layout = VenvLayout(Path(tmp))
        site = layout.root / ("Lib/site-packages" if WINDOWS else "lib/python3.99/site-packages")
        (site / "~orrupted").mkdir(parents=True)
        remove_corrupted_packages(layout)
        assert not (site / "~orrupted").exists(), "a ~ leftover directory was not removed"
        _stamp(layout.install_marker("datrix-planted"))
        assert not editable_installs_intact(layout)
        assert repair_broken_editable_installs(layout, delay_seconds=0), "the repair reported failure"
        assert not layout.install_marker("datrix-planted").exists(), "the repair left the stale install marker"
        (site / "__editable__.datrix_planted-0.pth").write_text("import __editable___datrix_planted_finder\n", encoding="utf-8")
        assert editable_installs_intact(layout), "an editable .pth naming datrix was not found"


def _check_venv_bookkeeping() -> None:
    with tempfile.TemporaryDirectory(prefix="venv-selftest-") as tmp:
        layout = VenvLayout(Path(tmp))
        assert workspace_missing_repos(layout.workspace) == list(REQUIRED_REPOS)
        for repo in REQUIRED_REPOS:
            (layout.workspace / repo).mkdir()
        assert workspace_missing_repos(layout.workspace) == []
        missing = check_datrix_command(layout)
        assert not missing.ok and str(layout.datrix_cli) in missing.detail, missing
        retired = layout.workspace / f"{_RETIRED_VENV_PREFIX}planted"
        (retired / "Lib").mkdir(parents=True)
        remove_retired_venvs(layout)
        assert not retired.exists(), "a retired venv was not removed"


def _check_command_line() -> None:
    parser = build_parser()
    refused = (["--skip-if-installed"], ["--no-dev"], ["--self-test", "--ensure"], ["--list-packages", "--base-interpreter"])
    for argv in refused:
        assert _usage_problem(parser.parse_args(argv)), f"{argv} was accepted"
    accepted = (["--ensure", "--ensure-packages", "--skip-if-installed"], ["--install-package=datrix-cli", "--no-dev"],
                ["--recreate", "--ensure-packages"])
    for argv in accepted:
        assert not _usage_problem(parser.parse_args(argv)), f"{argv} was refused: {_usage_problem(parser.parse_args(argv))}"


def _check_wrapper_seam() -> None:
    from datrix_scripts import entrypoint  # The seam check runs PowerShell's parser; only the self-test needs it.

    failures = entrypoint.self_test_problems()
    failures += entrypoint.wrapper_problems(SCRIPTS_DIR / "common" / "venv.ps1", MODULE, build_parser())
    assert not failures, "\n".join(failures)


def run_self_test() -> bool:
    """Run every check; print ``[OK]``/``[FAIL]`` per check; True when all pass."""
    from datrix_scripts.gate_harness import named_checks, run_checks

    checks = named_checks([
        _check_module_names, _check_executable_architectures, _check_required_python_version,
        _check_candidates_are_filtered, _check_base_interpreter_choice, _check_venv_base_interpreter,
        _check_package_lock, _check_reinstall_decisions, _check_import_verdict, _check_site_packages_upkeep,
        _check_venv_bookkeeping, _check_command_line, _check_wrapper_seam,
    ])
    passed = run_checks(checks, also_failing=(VenvError,))
    print()
    print("SELF-TEST PASSED" if passed else "SELF-TEST FAILED: see failures above.")
    return passed


if __name__ == "__main__":
    sys.exit(main())
