#!/usr/bin/env python3
"""
Ruff checker for Jinja2 templates.

Finds Jinja templates in subfolders, renders them with mock values,
runs ruff check on the generated files, and creates a report.

Usage:
    python scripts/library/dev/ruff_checker.py

    Or use the PowerShell wrapper:
        .\\scripts\\dev\\ruff-checker.ps1
"""

import io
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

# Configure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    from jinja2 import Environment, FileSystemLoader, TemplateSyntaxError, UndefinedError, Undefined
except ImportError:
    print("ERROR: jinja2 is required. Install with: pip install jinja2", file=sys.stderr)
    sys.exit(1)

from datrix_common.errors import UnmappedTypeError, UnsupportedTypeError
from datrix_common.types import TypeRegistry
from datrix_common.utils.text import (
    to_camel_case,
    to_pascal_case,
    to_plural,
    to_snake_case,
)


class SilentUndefined(Undefined):
    """Custom undefined that returns empty string instead of raising errors."""

    def _fail_with_undefined_error(self, *args, **kwargs):
        return ""

    def __str__(self):
        return ""

    def __repr__(self):
        return ""

    def __iter__(self):
        return iter([])

    def __bool__(self):
        return False

    def __getattr__(self, name):
        return SilentUndefined()

    def __call__(self, *args, **kwargs):
        return SilentUndefined()

    def __json__(self):
        return "{}"

    def __int__(self):
        return 0

    def __float__(self):
        return 0.0


class MockObject:
    """Mock object that returns itself or a sensible default for any attribute access."""

    def __init__(self, name: str = "MockObject", value: Any = None):
        self._name = name
        self._value = value if value is not None else name

    def __getattr__(self, name: str) -> "MockObject":
        # Return common attribute values for known patterns
        known_attrs = {
            "name": MockObject("name", "MockEntity"),
            "lower": MockObject("lower", "mockentity"),
            "type_name": MockObject("type_name", "str"),
            "python_type": MockObject("python_type", "str"),
            "default_value": MockObject("default_value", '""'),
            "id": MockObject("id", "id"),
            "pk_type": MockObject("pk_type", "UUID"),
            "description": MockObject("description", "A mock description"),
        }
        return known_attrs.get(name, MockObject(name, name))

    def __str__(self) -> str:
        return str(self._value)

    def __repr__(self) -> str:
        return str(self._value)

    def __iter__(self):
        # Return empty iterator for loops
        return iter([])

    def __bool__(self) -> bool:
        return True

    def __len__(self) -> int:
        return 0

    def items(self):
        return []

    def keys(self):
        return []

    def values(self):
        return []

    def get(self, key: str, default: Any = None) -> Any:
        return default or MockObject(key)


class MockEntity(MockObject):
    """Mock entity with common entity attributes."""

    def __init__(self, name: str = "User"):
        super().__init__("entity", name)
        self.name = name

    def __getattr__(self, attr: str) -> Any:
        if attr == "name":
            return self._value
        if attr in ("fields", "all_fields", "relations", "indexes"):
            return {}
        return super().__getattr__(attr)


class MockField(MockObject):
    """Mock field with common field attributes."""

    def __init__(self, name: str = "field_name", python_type: str = "str"):
        super().__init__("field", name)
        self.name = name
        self.python_type = python_type
        self.type_name = python_type
        self.nullable = False
        self.default = None
        self.description = f"The {name} field"


def to_field_name(name: str, convention: str = "snake_case") -> str:
    """Convert field name to the specified naming convention."""
    if convention == "snake_case":
        return to_snake_case(name)
    return to_camel_case(name)


def to_test_class_name(entity_name: str) -> str:
    """Convert entity name to test class name."""
    return f"Test{entity_name}"


def to_test_method_name(method_name: str) -> str:
    """Convert method name to test method name."""
    if str(method_name).startswith("test_"):
        return str(method_name)
    return f"test_{method_name}"


def to_fixture_name(entity_name: str) -> str:
    """Convert entity name to fixture name."""
    return to_snake_case(str(entity_name))


class UnmappedSQLAlchemyTypeError(ValueError):
    """Raised when a SQLAlchemy type has no Python mapping in the registry."""

    def __init__(self, sa_type: str, available: list[str]) -> None:
        self.sa_type = sa_type
        self.available = available
        super().__init__(
        f"SQLAlchemy type {sa_type!r} has no Python mapping. Available: {sorted(available)}"
        )


def _build_sa_to_python_map() -> dict[str, str]:
    """Build SQLAlchemy base type name -> Python type map from TypeRegistry."""
    result: dict[str, str] = {}
    for type_name in TypeRegistry.get_available_types():
        try:
            sa_type = TypeRegistry.get_sqlalchemy_type(type_name)
            py_type = TypeRegistry.get_python_type(type_name)
            base_sa = sa_type.split("(")[0]
            result[base_sa] = py_type
        except (UnmappedTypeError, UnsupportedTypeError):
            continue
    return result


_SA_TO_PYTHON_MAP = _build_sa_to_python_map()


def sqlalchemy_to_python_type(sa_type: str) -> str:
    """Convert SQLAlchemy type to Python type.

    Uses TypeRegistry-derived mapping. Raises if the SQLAlchemy type is not
    in the registry (fail fast).

    Args:
        sa_type: SQLAlchemy type string (e.g. "String(255)", "PGUUID(as_uuid=True)").

        Returns:
            Python type string for use in templates.

        Raises:
            UnmappedSQLAlchemyTypeError: If sa_type has no mapping in TypeRegistry.
    """
    base_sa = str(sa_type).strip().split("(")[0]
    if base_sa not in _SA_TO_PYTHON_MAP:
        raise UnmappedSQLAlchemyTypeError(base_sa, list(_SA_TO_PYTHON_MAP.keys()))
    return _SA_TO_PYTHON_MAP[base_sa]


def cdk_id(name: str) -> str:
    """Convert name to CDK construct ID (PascalCase without underscores)."""
    return to_pascal_case(str(name)).replace("_", "")


def tojson_filter(value: Any) -> str:
    """Convert value to JSON string, handling SilentUndefined."""
    import json

    def default_handler(obj):
        if isinstance(obj, Undefined):
            return None
        if hasattr(obj, "__dict__"):
            return str(obj)
        return str(obj)

    try:
        return json.dumps(value, default=default_handler)
    except (TypeError, ValueError):
        return '"{}"'.format(str(value))


def create_mock_context() -> dict[str, Any]:
    """Create a mock context for template rendering with common variables."""
    mock_entity = MockEntity("User")
    mock_field = MockField("username", "str")

    return {
    # Common entity variables
    "entity": mock_entity,
    "entity_name": "User",
    "model_name": "User",
    "service_name": "UserService",
    "table_name": "users",

    # Type variables
    "pk_type": "UUID",
    "pk_field": "id",

    # Boolean flags (common in templates)
    "needs_uuid": True,
    "needs_datetime": True,
    "needs_date": False,
    "needs_time": False,
    "needs_decimal": False,
    "needs_enum": False,
    "needs_field": False,
    "has_relations": False,
    "has_indexes": False,
    "is_async": True,
    "use_dataclass": False,

    # Collections (commonly iterated)
    "fields": [mock_field],
    "filter_fields": [],
    "relations": [],
    "indexes": [],
    "enum_types": [],
    "imports": [],
    "dependencies": [],
    "entities": [],
    "enums": [],
    "structs": [],
    "services": [],
    "routes": [],

    # Project-level variables
    "project": MockObject("project", "my_project"),
    "project_name": "my_project",
    "package_name": "my_package",
    "app_name": "app",
    "version": "0.1.0",
    "description": "A mock project description",
    "author": "Test Author",
    "python_version": "3.11",

    # Config and settings
    "config": MockObject("config"),
    "settings": MockObject("settings"),
    "database_url": "postgresql://localhost/db",

    # Common string placeholders
    "name": "MockName",
    "class_name": "MockClass",
    "module_name": "mock_module",
    "file_name": "mock_file",
    "path": "/mock/path",

    # Dev/deployment variables
    "workers": 4,
    "port": 8000,
    "host": "0.0.0.0",
    "reload": True,
    "debug": False,

    # Enum templates
    "enum_data": {
    "name": "Status",
    "values": [
    {"name": "ACTIVE", "value": "active"},
    {"name": "INACTIVE", "value": "inactive"},
    ],
    },
    "enum_name": "Status",
    "enum_values": ["ACTIVE", "INACTIVE"],

    # CDK/AWS variables
    "stack_name": "MockStack",
    "region": "us-east-1",
    "account": "123456789012",
    "environment": "dev",
    "resources": [],
    "lambdas": [],
    "tables": [],
    "queues": [],
    "buckets": [],

    # Discovery
    "service_discovery": MockObject("service_discovery"),
    "consul_host": "localhost",
    "etcd_host": "localhost",

    # Token/auth variables
    "include_refresh_token": True,
    "include_expires_in": True,
    "include_token_data": True,
    "include_token_request": True,
    "include_token_response": True,
    "include_grant_type": True,
    "include_user_info": True,
    "additional_claims": [],
    "token_data_fields": [],

    # Field naming convention
    "field_naming_convention": "snake_case",
    }


def create_jinja_env(template_path: Path) -> Environment:
    """Create Jinja2 environment with FileSystemLoader for the template's directory tree."""
    # Build search paths: template dir, parent dirs up to 'templates' folder
    search_paths = []
    current = template_path.parent

    # Walk up to find 'templates' directory and include all paths
    while current.name and current != current.parent:
        search_paths.append(str(current))
        if current.name == "templates":
            break
        current = current.parent

    # If no templates dir found, just use the template's directory
    if not search_paths:
        search_paths = [str(template_path.parent)]

    env = Environment(
        loader=FileSystemLoader(search_paths),
        autoescape=False,
        undefined=SilentUndefined,
    )

    # Add custom filters (matching real codegen filters)
    env.filters["pluralize"] = to_plural
    env.filters["snake_case"] = to_snake_case
    env.filters["pascal_case"] = to_pascal_case
    env.filters["camel_case"] = to_camel_case
    env.filters["to_field_name"] = to_field_name
    env.filters["test_class_name"] = to_test_class_name
    env.filters["test_method_name"] = to_test_method_name
    env.filters["fixture_name"] = to_fixture_name
    env.filters["sqlalchemy_to_python_type"] = sqlalchemy_to_python_type
    env.filters["cdk_id"] = cdk_id
    env.filters["tojson"] = tojson_filter

    # Add common built-in filters
    env.filters["default"] = lambda value, default="": value if value else default
    env.filters["capitalize"] = lambda s: str(s).capitalize() if s else ""
    env.filters["title"] = lambda s: str(s).title() if s else ""
    env.filters["upper"] = lambda s: str(s).upper() if s else ""
    env.filters["lower"] = lambda s: str(s).lower() if s else ""

    return env


def find_templates(base_path: Path) -> list[Path]:
    """Find all .j2 template files in subfolders."""
    templates = []
    for root, _dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith(".j2"):
                templates.append(Path(root) / file)
    return sorted(templates)


def render_template(template_path: Path, env: Environment, context: dict) -> tuple[str, str | None]:
    """
    Render a template with mock context.

    Returns:
        Tuple of (rendered_content, error_message)
    """
    try:
        template_content = template_path.read_text(encoding="utf-8")
        template = env.from_string(template_content)
        rendered = template.render(**context)
        return rendered, None
    except TemplateSyntaxError as e:
        return "", f"Template syntax error at line {e.lineno}: {e.message}"
    except UndefinedError as e:
        return "", f"Undefined variable: {e.message}"
    except Exception as e:
        return "", f"Render error: {type(e).__name__}: {e}"


def get_output_filename(template_path: Path) -> str:
    """Get the output filename by removing .j2 extension."""
    name = template_path.name
    if name.endswith(".j2"):
        name = name[:-3]
    return name


def is_python_template(template_path: Path) -> bool:
    """Check if a template generates a Python file."""
    name = get_output_filename(template_path)
    return name.endswith(".py")


def run_ruff_check(file_path: Path) -> tuple[list[str], int]:
    """
    Run ruff check on a file.

    Returns:
        Tuple of (list of findings, exit_code)
    """
    try:
        result = subprocess.run(
            ["ruff", "check", "--output-format=concise", str(file_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        findings = []
        output = result.stdout + result.stderr
        # Pattern to extract line:col and message from ruff output
        # Input: C:\...\file.py:3:22: F401 message
        # Output: Line 3:22: F401 message
        # Use regex to handle Windows paths with drive letters (C:)
        pattern = re.compile(r":(\d+):(\d+): (.+)$")
        for line in output.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            match = pattern.search(line)
            if match:
                line_num = match.group(1)
                col_num = match.group(2)
                message = match.group(3)
                findings.append(f"Line {line_num}:{col_num}: {message}")
            else:
                findings.append(line)
        return findings, result.returncode
    except FileNotFoundError:
        return ["ERROR: ruff not found. Install with: pip install ruff"], 1
    except Exception as e:
        return [f"ERROR: Failed to run ruff: {e}"], 1


def generate_report(
    results: list[dict],
    report_path: Path,
    base_path: Path,
    total_templates: int,
) -> None:
    """Generate a report of all findings."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("RUFF TEMPLATE CHECK REPORT\n")
        f.write("=" * 80 + "\n")
        f.write(f"Timestamp: {timestamp}\n")
        f.write(f"Base path: {base_path}\n")
        f.write(f"Total templates found: {total_templates}\n")
        f.write("\n")

        # Summary
        rendered_count = sum(1 for r in results if r["rendered"])
        error_count = sum(1 for r in results if r["render_error"])
        with_issues = sum(1 for r in results if r["findings"])
        clean = sum(1 for r in results if r["rendered"] and not r["findings"])
        total_findings = sum(len(r["findings"]) for r in results)

        f.write("-" * 40 + "\n")
        f.write("SUMMARY\n")
        f.write("-" * 40 + "\n")
        f.write(f" Successfully rendered: {rendered_count}\n")
        f.write(f" Render errors: {error_count}\n")
        f.write(f" Templates with issues: {with_issues}\n")
        f.write(f" Clean templates: {clean}\n")
        f.write(f" Total ruff findings: {total_findings}\n")
        f.write("\n")

        # Render errors section
        render_errors = [r for r in results if r["render_error"]]
        if render_errors:
            f.write("-" * 40 + "\n")
            f.write("TEMPLATE RENDER ERRORS\n")
            f.write("-" * 40 + "\n")
            for r in render_errors:
                rel_path = r["template"].relative_to(base_path) if base_path in r["template"].parents else r["template"]
                f.write(f"\n{rel_path}:\n")
                f.write(f"  {r['render_error']}\n")
            f.write("\n")

        # Ruff findings section
        templates_with_issues = [r for r in results if r["findings"]]
        if templates_with_issues:
            f.write("-" * 40 + "\n")
            f.write("RUFF FINDINGS BY TEMPLATE\n")
            f.write("-" * 40 + "\n")
            for r in templates_with_issues:
                rel_path = r["template"].relative_to(base_path) if base_path in r["template"].parents else r["template"]
                f.write(f"\n{rel_path}:\n")
                for finding in r["findings"]:
                    f.write(f"  {finding}\n")
                f.write("\n")

        if clean > 0:
            f.write("-" * 40 + "\n")
            f.write("CLEAN TEMPLATES (no issues)\n")
            f.write("-" * 40 + "\n")
            for r in results:
                if r["rendered"] and not r["findings"]:
                    rel_path = r["template"].relative_to(base_path) if base_path in r["template"].parents else r["template"]
                    f.write(f"  {rel_path}\n")
            f.write("\n")

        f.write("=" * 80 + "\n")
        f.write("END OF REPORT\n")
        f.write("=" * 80 + "\n")


def main() -> int:
    """Main entry point."""
    # Always search from current directory
    base_path = Path.cwd()

    # Generate output path with timestamp
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = Path.cwd() / f"ruff-report-{timestamp}.txt"

    print(f"Searching for templates in: {base_path}", flush=True)

    # Find templates
    all_templates = find_templates(base_path)
    if not all_templates:
        print("No .j2 template files found.", flush=True)
        return 0

    # Filter to only Python templates
    templates = [t for t in all_templates if is_python_template(t)]
    print(f"Found {len(all_templates)} template(s), {len(templates)} Python template(s)", flush=True)

    if not templates:
        print("No Python templates to check.", flush=True)
        return 0
    print(flush=True)

    # Create mock context (environment created per-template for proper includes)
    context = create_mock_context()
    print("Processing templates...", flush=True)

    results = []
    total_findings = 0

    # Process templates
    try:
        with tempfile.TemporaryDirectory(prefix="ruff_check_") as temp_dir:
            temp_path = Path(temp_dir)

            for template_path in templates:
                result = {
                    "template": template_path,
                    "rendered": False,
                    "render_error": None,
                    "findings": [],
                }

                try:
                    env = create_jinja_env(template_path)
                    rendered, error = render_template(template_path, env, context)

                    if error:
                        result["render_error"] = error
                    else:
                        result["rendered"] = True

                    output_name = get_output_filename(template_path)
                    output_file = temp_path / output_name
                    output_file.write_text(rendered, encoding="utf-8")

                    findings, _ = run_ruff_check(output_file)
                    findings = [
                        f for f in findings
                        if f.strip()
                        and not f.startswith("Found ")
                        and not f.startswith("All checks passed")
                        and not f.startswith("[*]")
                        and "fixable with" not in f
                    ]

                    if findings:
                        result["findings"] = findings
                    total_findings += len(findings)
                except Exception as e:
                    result["render_error"] = f"Processing error: {type(e).__name__}: {e}"

                results.append(result)
    except Exception as e:
        print(f"ERROR: Failed to process templates: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc()
        sys.stderr.flush()
        return 1

    print(f"Processed {len(results)} templates", flush=True)
    generate_report(results, report_path, base_path, len(templates))

    print()
    print("=" * 50)
    print("SUMMARY")
    print("=" * 50)
    rendered_count = sum(1 for r in results if r["rendered"])
    error_count = sum(1 for r in results if r["render_error"])
    with_issues = sum(1 for r in results if r["findings"])

    print(f" Python templates: {len(templates)}")
    print(f" Successfully rendered: {rendered_count}")
    print(f" Render errors: {error_count}")
    print(f" With ruff issues: {with_issues}")
    print(f" Total findings: {total_findings}")
    print()
    print(f"Report saved to: {report_path}")

    if error_count > 0 or total_findings > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
