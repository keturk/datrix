"""
Test project configuration loader for Datrix scripts.

Loads and processes test project definitions from test-projects.json.
"""

import json
import sys
from pathlib import Path
from typing import List, Optional

from shared.venv import get_datrix_root

# Add datrix-common to path for DATRIX_FILE_EXTENSION
_datrix_root = get_datrix_root()
_datrix_common_src = _datrix_root / "datrix-common" / "src"
if _datrix_common_src.exists() and str(_datrix_common_src) not in sys.path:
    sys.path.insert(0, str(_datrix_common_src))
from datrix_common import DATRIX_FILE_EXTENSION


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
    - Input: "examples/01-tutorial/01-basic-entity/system.dtrx"
    - Output: "python/docker/01-tutorial/01-basic-entity"

 2. **File-based**: Standalone .dtrx file
    - Input: "examples/02-domains/ecommerce/system.dtrx"
    - Output: "python/docker/02-domains/ecommerce"

 Args:
  source_path: Source file path from project config
  language: Target language (python, typescript)
  platform: Target platform (docker, k8s, aws, azure)

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


def get_default_output_path(example_path: str) -> Path:
 """
 Derive the default output path for a single example from test-projects.json.

 Uses defaultLanguage and defaultPlatform from the config so callers do not
 need to compute the path when running a single example without -OutputPath.

 Args:
  example_path: Path to the .dtrx file (absolute or relative, must be under examples/).

 Returns:
  Absolute path under datrix_root/.generated/ for the default language/platform.

 Raises:
  FileNotFoundError: If the config file does not exist.
  ValueError: If config lacks defaultLanguage/defaultPlatform or example_path is not under examples/.
 """
 config = load_config()
 default_language = config.get("defaultLanguage")
 default_platform = config.get("defaultPlatform")
 if not default_language or not default_platform:
  available = [k for k in ("defaultLanguage", "defaultPlatform") if config.get(k)]
  raise ValueError(
   "test-projects.json must define defaultLanguage and defaultPlatform. "
   f"Present: {available}"
  )
 normalized = normalize_path(example_path)
 examples_marker = "examples/"
 idx = normalized.lower().find(examples_marker)
 if idx < 0:
  raise ValueError(
   f"example_path must be under examples/. Got: {example_path}"
  )
 source_path = normalized[idx:]  # "examples/..." (with or without leading path)
 output_relative = build_output_path(
  source_path, default_language, default_platform
 )
 datrix_root = get_datrix_root()
 return datrix_root / ".generated" / output_relative


def get_test_projects(
 test_set: str | None = None,
 all_projects: bool = False,
 language: str = "python",
 platform: str = "docker",
) -> List[dict]:
 """
 Get project definitions for a test set.

 Args:
 test_set: Name of the test set (e.g., "default", "all", "quick", "domains", "generate-all")
 all_projects: If True, use "all" test set
 language: Target language (default: "python")
 platform: Target platform (default: "docker")

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
 if test_set_name == "non-tutorial":
  # All examples except those in tutorial-all (generate-all minus tutorial-all), preserve order
  all_ordered = test_sets.get("generate-all", [])
  tutorial_names = set(test_sets.get("tutorial-all", []))
  project_names = [name for name in all_ordered if name not in tutorial_names]
 elif test_set_name not in test_sets:
  raise ValueError(f"Test set '{test_set_name}' not found in configuration. Available: {list(test_sets.keys())}")
 else:
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
  # So examples/01-tutorial/... becomes datrix/examples/01-tutorial/...
  full_path = datrix_root / "datrix" / project_path

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


def get_project_by_name(name: str) -> Optional[dict]:
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


def list_test_sets() -> List[str]:
 """
 Get a list of all available test set names.

 Returns:
 List of test set names (includes derived sets like "non-tutorial")
 """
 config = load_config()
 keys = list(config.get("testSets", {}).keys())
 if "non-tutorial" not in keys:
  keys.append("non-tutorial")
  keys.sort()
 return keys


def list_projects() -> List[str]:
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
