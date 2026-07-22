"""
Test project configuration loader for Datrix scripts.

Loads and processes test project definitions from test-projects.json.
"""

import json
import logging
import sys
from pathlib import Path

from shared.venv import get_datrix_root

# Add datrix-common to path for DATRIX_FILE_EXTENSION
_datrix_root = get_datrix_root()
_datrix_common_src = _datrix_root / "datrix-common" / "src"
if _datrix_common_src.exists() and str(_datrix_common_src) not in sys.path:
    sys.path.insert(0, str(_datrix_common_src))
from datrix_common import DATRIX_FILE_EXTENSION  # noqa: E402

logger = logging.getLogger(__name__)

FOUNDATION_EXAMPLES_PREFIX = "examples/01-foundation/"
ALL_TEST_SET = "all"

# Output paths are organized as {language}/{runtime}/{provider}/{project}. The
# runtime segment is supplied by the caller (CLI flag); the provider segment is
# read from each project's config/system.dcfg so generation and downstream
# tooling always agree on where a project's output lives.
DEFAULT_RUNTIME = "docker-compose"
DEFAULT_PROVIDER = "local"
DEFAULT_PROFILE = "test"

# Cache resolved providers per (project_dir, profile) so a single run does not
# re-parse the same system.dcfg for every helper call.
_provider_cache: dict[tuple[str, str], str] = {}


def resolve_provider(project_dir: Path, profile: str = DEFAULT_PROFILE) -> str:
    """Resolve the deployment provider path segment for a project.

    Reads ``<project_dir>/config/system.dcfg`` and returns the resolved
    ``deployment.provider`` of the active *profile* (profiles extend ``base``).
    This is the same value generation uses, so output paths always match the
    project's configured provider instead of a separate CLI flag.

    Args:
        project_dir: Project directory containing ``config/system.dcfg``.
        profile: Config profile to resolve (datrix's default is ``test``).

    Returns:
        Provider segment string (e.g. ``"local"``, ``"aws"``, ``"azure"``).
        Falls back to ``"local"`` when the project has no system.dcfg. A config
        that exists but fails to load is reported and also falls back to
        ``"local"`` so path-deriving tooling never crashes on one bad project.
    """
    cache_key = (str(project_dir), profile)
    cached = _provider_cache.get(cache_key)
    if cached is not None:
        return cached

    config_path = project_dir / "config" / "system.dcfg"
    if not config_path.exists():
        provider = DEFAULT_PROVIDER
    else:
        from datrix_common.config.unified_loader import load_system_config
        from datrix_common.errors.base import DatrixError

        try:
            unified = load_system_config(
                config_path=config_path,
                project_root=project_dir,
                profile=profile,
            )
            provider = str(unified.system.deployment.provider)
        except DatrixError as exc:
            logger.warning(
                "Could not resolve provider from %s (profile=%s): %s; using '%s'",
                config_path,
                profile,
                exc,
                DEFAULT_PROVIDER,
            )
            provider = DEFAULT_PROVIDER

    _provider_cache[cache_key] = provider
    return provider


def normalize_path(path: str) -> str:
 """
 Normalize path separators for current platform.

 Args:
  path: Path string (may use / or \\)

 Returns:
  Normalized path string
 """
 return path.replace("\\", "/")


def build_output_path(source_path: str, language: str, platform: str) -> str:
 """
 Build output path from source path, organized by language and platform.

 Supports two input patterns:
 1. **Directory-based**: Project in subdirectory with system.dtrx
    - Input: "examples/02-features/01-core-data-modeling/entities/system.dtrx"
    - Output: "python/docker/02-features/01-core-data-modeling/entities"

 2. **File-based**: Standalone .dtrx file
    - Input: "examples/02-domains/ecommerce/system.dtrx"
    - Output: "python/docker/02-domains/ecommerce"

 Args:
  source_path: Source file path from project config
  language: Target language (python, typescript)
  platform: Target platform (docker, aws, azure)

 Returns:
  Relative output path without .generated prefix
 """
 # Remove 'examples/' prefix (handle both / and \ separators)
 relative = source_path.replace("examples/", "").replace("examples\\", "")

 # Handle two patterns:
 # 1. Directory-based: "XX/YY/system.dtrx" -> "{language}/{platform}/XX/YY"
 # 2. File-based: "XX/YY.dtrx" -> "{language}/{platform}/XX/YY"

 if relative.endswith("/system.dtrx") or relative.endswith("\\system.dtrx"):
  # Pattern 1: Directory-based
  # Remove /system.dtrx, prepend language/platform
  base = relative.replace("/system.dtrx", "").replace("\\system.dtrx", "")
  return f"{language}/{platform}/{base}"

 elif relative.endswith(DATRIX_FILE_EXTENSION):
  # Pattern 2: File-based
  # Remove extension, prepend language/platform
  base = relative[: -len(DATRIX_FILE_EXTENSION)]
  return f"{language}/{platform}/{base}"

 else:
  # Fallback: No .dtrx extension
  return f"{language}/{platform}/{relative}"


def load_config() -> dict:
 """
 Load the test-projects.json configuration file from datrix/scripts/config.

 Returns:
 Dictionary containing the configuration

 Raises:
 FileNotFoundError: If the config file doesn't exist
 """
 # Find datrix root
 datrix_root = get_datrix_root()
 # Config is in datrix/scripts/config
 config_path = datrix_root / "datrix" / "scripts" / "config" / "test-projects.json"

 if not config_path.exists():
  raise FileNotFoundError(f"Configuration file not found: {config_path}")

 with open(config_path, encoding="utf-8") as f:
  return json.load(f)


def get_default_output_path(
 example_path: str,
 language: str | None = None,
 runtime: str | None = None,
 profile: str = DEFAULT_PROFILE,
) -> Path:
 """
 Derive the default output path for a single example.

 The path is ``{language}/{runtime}/{provider}/{project}``. The provider
 segment is read from the example's ``config/system.dcfg`` (active *profile*),
 not supplied by the caller. When *language* or *runtime* are provided they
 override the defaults, so ``-L typescript`` produces an output path under
 ``.generated/typescript/…`` instead of ``.generated/python/…``.

 Args:
  example_path: Path to the .dtrx file (absolute or relative, must be under examples/).
  language: Override target language (e.g. "typescript").  Falls back to
            ``defaultLanguage`` in test-projects.json when *None*.
  runtime: Override target runtime (e.g. "docker-compose").  Falls back to
            ``DEFAULT_RUNTIME`` when *None*.
  profile: Config profile used to resolve the provider (default ``test``).

 Returns:
  Absolute path under datrix_root/.generated/ for the resolved language/runtime/provider.

 Raises:
  FileNotFoundError: If the config file does not exist.
  ValueError: If config lacks defaultLanguage or example_path is not under examples/.
 """
 config = load_config()
 resolved_language = language or config.get("defaultLanguage")
 if not resolved_language:
  raise ValueError(
   "test-projects.json must define defaultLanguage."
  )
 resolved_runtime = runtime or DEFAULT_RUNTIME
 provider = resolve_provider(Path(example_path).resolve().parent, profile)
 normalized = normalize_path(example_path)
 examples_marker = "examples/"
 idx = normalized.lower().find(examples_marker)
 if idx < 0:
  raise ValueError(
   f"example_path must be under examples/. Got: {example_path}"
  )
 source_path = normalized[idx:]  # "examples/..." (with or without leading path)
 output_relative = build_output_path(
  source_path, resolved_language, f"{resolved_runtime}/{provider}"
 )
 datrix_root = get_datrix_root()
 return datrix_root / ".generated" / output_relative


def get_test_projects(
 test_set: str | None = None,
 all_projects: bool = False,
 language: str = "python",
 runtime: str = DEFAULT_RUNTIME,
 profile: str = DEFAULT_PROFILE,
) -> list[dict]:
 """
 Get project definitions for a test set.

 Output paths are ``{language}/{runtime}/{provider}/{project}``. The provider
 segment is resolved per project from its ``config/system.dcfg`` (active
 *profile*), so the path always matches the project's configured provider.

 Args:
 test_set: Name of the test set (e.g., "default", "all", "quick", "domains")
 all_projects: If True, use "all" test set
 language: Target language (default: "python")
 runtime: Target runtime segment (default: "docker-compose")
 profile: Config profile used to resolve each project's provider (default: "test")

 Returns:
 List of project dictionaries with keys: name, path, language, platform, output, description
 """
 config = load_config()

 # Determine which test set to use
 if test_set:
  test_set_name = test_set
 elif all_projects:
  test_set_name = "all"
 else:
  test_set_name = "default"

 # Get project names from the test set
 test_sets = config.get("testSets", {})
 if test_set_name not in test_sets:
  available = list_test_sets()
  raise ValueError(f"Test set '{test_set_name}' not found in configuration. Available: {available}")
 project_names = test_sets[test_set_name]

 # Build flat list of all projects
 all_projects_dict = {}
 for category in config.get("projects", {}).values():
  for project in category:
   all_projects_dict[project["name"]] = project

 # Build result list
 projects = []

 # Find datrix root
 datrix_root = get_datrix_root()

 for project_name in project_names:
  if project_name not in all_projects_dict:
   # Project name not found, skip it
   continue

  project = all_projects_dict[project_name]

  # Normalize path for current platform
  project_path = normalize_path(project["path"])
  # Examples are in datrix/examples, paths in JSON are relative to examples/
  # So examples/02-features/... becomes datrix/examples/02-features/...
  full_path = datrix_root / "datrix" / project_path

  # Resolve the provider segment from the project's own config/system.dcfg.
  provider = resolve_provider(full_path.parent, profile)
  platform = f"{runtime}/{provider}"

  # Build output path - handle both system.dtrx and standalone .dtrx files
  output_relative = build_output_path(project["path"], language, platform)
  # Generated output is in datrix root
  output_path = datrix_root / ".generated" / output_relative

  projects.append(
   {
    "name": project["name"],
    "path": str(full_path),
    "language": language,
    "platform": platform,
    "output": str(output_path),
    "description": project.get("description", ""),
   }
  )

 return projects


def get_project_by_name(name: str) -> dict | None:
 """
 Get a single project definition by name.

 Args:
 name: Project name

 Returns:
 Project dictionary or None if not found
 """
 config = load_config()

 # Search all categories
 for category in config.get("projects", {}).values():
  for project in category:
   if project["name"] == name:
    return project

 return None


def list_test_sets() -> list[str]:
 """
 Get a list of all available test set names.

 Returns:
 List of test set names
 """
 config = load_config()
 return list(config.get("testSets", {}).keys())


def list_projects() -> list[str]:
 """
 Get a list of all available project names.

 Returns:
 List of project names
 """
 config = load_config()
 projects = []

 for category in config.get("projects", {}).values():
  for project in category:
   projects.append(project["name"])

 return sorted(projects)
