#!/usr/bin/env python3
"""
Ruff checker for Jinja2 templates.

Finds Jinja templates in subfolders, renders them with mock values,
runs ruff check on the generated files, and creates a report under
``<workspace>/.test-output/ruff-checker/`` -- never in the scanned folder.

The module behind ``scan/ruff-checker.ps1`` (and its ``.sh`` twin). Exit codes: 0 clean, 1 a render
error or a ruff finding, 2 ruff missing or a templates folder that is not a directory.

Usage:
    python -m datrix_scripts.scan.ruff_checker --templates-dir=<folder> [--dbg]
    python -m datrix_scripts.scan.ruff_checker --self-test
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Final, TypedDict

from datrix_scripts.venv import PACKAGE_DEPENDENCIES, PACKAGE_DEV_EXTRAS, missing_declared_tool

try:
    from jinja2 import (
        Environment,
        FileSystemLoader,
        TemplateSyntaxError,
        Undefined,
        UndefinedError,
    )
except ImportError as exc:
    raise SystemExit(missing_declared_tool("jinja2", PACKAGE_DEPENDENCIES)) from exc

from datrix_common.utils.text import to_camel_case, to_plural
from datrix_common.utils.identifier_case import to_pascal_case, to_snake_case

from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, print_command, write_files
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import SCAN_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.scan.ruff_checker"
WRAPPER: Final = "ruff-checker"

# The shared venv's ruff, run as a module of this interpreter so the venv's own copy checks the files.
_RUFF_MODULE = "ruff"


class TemplateResult(TypedDict):
    """What checking one template found."""

    template: Path
    rendered: bool
    render_error: str | None
    findings: list[str]


class SilentUndefined(Undefined):
    """Custom undefined that returns empty string instead of raising errors."""

    def _fail_with_undefined_error(self, *_args: object, **_kwargs: object) -> str:
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

    def __call__(self, *_args: object, **_kwargs: object) -> "SilentUndefined":
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
    return to_snake_case(entity_name)


def cdk_id(name: str) -> str:
    """Convert name to CDK construct ID (PascalCase without underscores)."""
    return to_pascal_case(name).replace("_", "")


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
        return f'"{str(value)}"'


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
            [sys.executable, "-m", _RUFF_MODULE, "check", "--output-format=concise", str(file_path)],
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
    except Exception as e:
        return [f"ERROR: Failed to run ruff: {e}"], 1


def generate_report(
    results: list[TemplateResult],
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


#: Where every report goes: outside every package repo, so a run never leaves a file to commit.
REPORT_DIR = WORKSPACE_DIR / ".test-output" / "ruff-checker"


#: Ruff output lines that summarise a run rather than report a finding.
_RUFF_SUMMARY_PREFIXES: Final = ("Found ", "All checks passed", "[*]")


def _template_findings(output_file: Path) -> list[str]:
    """The ruff findings on one rendered file, without ruff's summary lines."""
    findings, _ = run_ruff_check(output_file)
    return [
        finding for finding in findings
        if finding.strip() and not finding.startswith(_RUFF_SUMMARY_PREFIXES) and "fixable with" not in finding
    ]


def _check_template(template_path: Path, context: dict[str, object], temp_path: Path) -> TemplateResult:
    """Render one template into *temp_path* and run ruff on the output."""
    result = TemplateResult(template=template_path, rendered=False, render_error=None, findings=[])
    try:
        env = create_jinja_env(template_path)
        rendered, error = render_template(template_path, env, context)
        result["render_error"] = error
        result["rendered"] = error is None
        output_file = temp_path / get_output_filename(template_path)
        output_file.write_text(rendered, encoding="utf-8")
        result["findings"] = _template_findings(output_file)
    except Exception as e:
        result["render_error"] = f"Processing error: {type(e).__name__}: {e}"
    return result


def _print_summary(results: list[TemplateResult], templates: list[Path], report_path: Path) -> int:
    """Print the run summary; 1 when a template failed to render or ruff found anything, else 0."""
    rendered_count = sum(1 for r in results if r["rendered"])
    error_count = sum(1 for r in results if r["render_error"])
    with_issues = sum(1 for r in results if r["findings"])
    total_findings = sum(len(r["findings"]) for r in results)
    print()
    print("=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f" Python templates: {len(templates)}")
    print(f" Successfully rendered: {rendered_count}")
    print(f" Render errors: {error_count}")
    print(f" With ruff issues: {with_issues}")
    print(f" Total findings: {total_findings}")
    print()
    print(f"Report saved to: {report_path}")
    return 1 if error_count > 0 or total_findings > 0 else 0


def check_templates(base_path: Path, report_dir: Path) -> int:
    """Render every Python template under *base_path*, run ruff on each, and write the report into *report_dir*.

    0 clean, 1 a render error or a ruff finding, 2 ruff missing or *base_path* not a directory.
    """
    if importlib.util.find_spec(_RUFF_MODULE) is None:
        print(missing_declared_tool("ruff", PACKAGE_DEV_EXTRAS), file=sys.stderr)
        return 2
    base_path = base_path.resolve()
    if not base_path.is_dir():
        print(f"ERROR: --templates-dir {base_path} is not a directory. Pass a folder holding .j2 templates.",
              file=sys.stderr)
        return 2

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"ruff-report-{timestamp}.txt"

    print(f"Searching for templates in: {base_path}", flush=True)
    all_templates = find_templates(base_path)
    if not all_templates:
        print("No .j2 template files found.", flush=True)
        return 0
    templates = [t for t in all_templates if is_python_template(t)]
    print(f"Found {len(all_templates)} template(s), {len(templates)} Python template(s)", flush=True)
    if not templates:
        print("No Python templates to check.", flush=True)
        return 0
    print(flush=True)

    # The mock context is shared; each template gets its own environment so its includes resolve.
    context = create_mock_context()
    print("Processing templates...", flush=True)
    with tempfile.TemporaryDirectory(prefix="ruff_check_") as temp_dir:
        results = [_check_template(template_path, context, Path(temp_dir)) for template_path in templates]

    print(f"Processed {len(results)} templates", flush=True)
    generate_report(results, report_path, base_path, len(templates))
    return _print_summary(results, templates, report_path)


def build_parser() -> argparse.ArgumentParser:
    """The options of ``scan/ruff-checker.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--templates-dir", type=Path, default=None,
                        help="Directory searched for .j2 templates (default: the current directory).")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true",
                        help="Log at DEBUG level and print the python invocation before running.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: a planted template whose output ruff flags fails the "
                             "check, a clean one passes, a folder that is not a directory is refused, and the "
                             "wrapper seam holds.")
    return parser


def _checked_templates(files: dict[str, str]) -> tuple[int, str]:
    """``check_templates`` on a planted templates folder holding *files*: the exit code and its output."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_files(root / "templates", files)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = check_templates(root / "templates", root / "reports")
        reports = sorted((root / "reports").glob("ruff-report-*.txt"))
        report = reports[-1].read_text(encoding="utf-8") if reports else ""
        return code, out.getvalue() + _REPORT_MARKER + report


#: Separates a planted run's console output from its report text in what ``_checked_templates`` returns.
_REPORT_MARKER: Final = "\n--- report ---\n"


def _only_report(checked: str) -> str:
    """The report text of a ``_checked_templates`` result."""
    return checked.partition(_REPORT_MARKER)[2]


def _check_a_flagged_template_fails() -> None:
    code, out = _checked_templates({"api/flagged.py.j2": "import os\n\n\nVALUE = {{ 1 }}\n"})
    assert code == 1 and "With ruff issues: 1" in out and "F401" in _only_report(out), (
        f"the template's unused import (F401) must flag it (exit 1): {out!r}"
    )


def _check_a_clean_template_passes() -> None:
    code, out = _checked_templates({"api/clean.py.j2": "VALUE = {{ 1 }}\n", "api/readme.md.j2": "# {{ 1 }}\n"})
    assert code == 0 and "Python templates: 1" in out and "Total findings: 0" in out, (
        f"one clean Python template (the .md one is skipped) must pass: {out!r}"
    )


def _check_a_missing_folder_is_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(io.StringIO()) as err:
        code = check_templates(Path(tmp) / "no-such-folder", Path(tmp) / "reports")
    assert code == 2 and "is not a directory" in err.getvalue(), f"got {code}: {err.getvalue()!r}"


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_a_flagged_template_fails, _check_a_clean_template_passes, _check_a_missing_folder_is_refused]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=SCAN_SCRIPTS_DIR)
    searched = args.templates_dir or Path.cwd()
    print("Running ruff template checker...")
    print(f"Checking templates in: {searched}")
    print()
    if args.debug:
        print_command()
    return check_templates(searched, REPORT_DIR)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
