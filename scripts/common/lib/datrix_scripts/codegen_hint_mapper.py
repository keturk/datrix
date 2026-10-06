"""Maps generated file paths to probable codegen templates and generators.

Best-effort mapping — returns None when the path pattern is ambiguous.
Based on the /troubleshoot-generated skill's mapping table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class CodegenHint:
    """Best-effort identification of which template/generator produced a file."""

    probable_template: str
    probable_generator: str


#: The compose file's "template" is the YAML-builder module, not a Jinja file;
#: shared with the deploy-test log writer's lifecycle-phase hint so both name
#: the same place.
COMPOSE_BUILDER_HINT_TEMPLATE: Final[str] = (
    "generators/compose/compose_builder.py (YAML builders; no Jinja template)"
)
COMPOSE_BUILDER_HINT_GENERATOR: Final[str] = "ComposeBuilder"

# Pattern → hint mapping (most specific first).
# Each entry is (compiled regex, CodegenHint).
# Patterns match against forward-slash-normalized paths.
_PATH_PATTERNS: Final[list[tuple[re.Pattern[str], CodegenHint]]] = [
    # ── Python targets ──
    (
        re.compile(r".*/models/[^/]+/[^/]+\.py$"),
        CodegenHint("entity_model.py.j2", "EntityGenerator"),
    ),
    (
        re.compile(r".*/schemas/[^/]+/[^/]+_schema\.py$"),
        CodegenHint("entity_schema.py.j2", "SchemaGenerator"),
    ),
    (
        re.compile(r".*/services/[^/]+/[^/]+_service\.py$"),
        CodegenHint("entity_service.py.j2", "ServiceGenerator"),
    ),
    (
        re.compile(r".*/routes/[^/]+/[^/]+_routes\.py$"),
        CodegenHint("api_routes.py.j2", "EndpointGenerator"),
    ),
    (
        re.compile(r".*/integrations/_[^/]+_helpers\.py$"),
        CodegenHint("integration_helpers.py.j2", "IntegrationGenerator"),
    ),
    (
        re.compile(r".*/errors/__init__\.py$"),
        CodegenHint("error_classes.py.j2", "ErrorGenerator"),
    ),
    (
        re.compile(r".*/config/settings\.py$"),
        CodegenHint("settings.py.j2", "ConfigGenerator"),
    ),
    (
        re.compile(r".*/events/[^/]+\.py$"),
        CodegenHint("event_handler.py.j2", "EventGenerator"),
    ),
    (
        re.compile(r".*/cqrs/[^/]+\.py$"),
        CodegenHint("cqrs_component.py.j2", "CqrsGenerator"),
    ),
    (
        re.compile(r".*/cache/[^/]+\.py$"),
        CodegenHint("cache_config.py.j2", "CacheGenerator"),
    ),
    # ── TypeScript targets ──
    (
        re.compile(r".*/entities/[^/]+\.entity\.ts$"),
        CodegenHint("entity.ts.j2", "EntityGenerator"),
    ),
    (
        re.compile(r".*/dto/[^/]+\.dto\.ts$"),
        CodegenHint("dto.ts.j2", "DtoGenerator"),
    ),
    (
        re.compile(r".*/controllers/[^/]+\.controller\.ts$"),
        CodegenHint("controller.ts.j2", "ControllerGenerator"),
    ),
    (
        re.compile(r".*/services/[^/]+\.service\.ts$"),
        CodegenHint("service.ts.j2", "ServiceGenerator"),
    ),
    (
        re.compile(r".*/modules/[^/]+\.module\.ts$"),
        CodegenHint("module.ts.j2", "ModuleGenerator"),
    ),
    (
        re.compile(r".*/app\.module\.ts$"),
        CodegenHint("app_module.ts.j2", "AppModuleGenerator"),
    ),
    (
        re.compile(r".*/database/[^/]+\.ts$"),
        CodegenHint("database_config.ts.j2", "DatabaseGenerator"),
    ),
    (
        re.compile(r".*/config/[^/]+\.ts$"),
        CodegenHint("config.ts.j2", "ConfigGenerator"),
    ),
    # ── Docker/Compose targets ──
    # The compose file has no Jinja template: it is assembled by the YAML
    # builders under generators/compose/ and serialized by ComposeBuilder. A
    # hint naming a .j2 that does not exist sends triage to a file nobody can
    # open; name the builder module instead.
    (
        re.compile(r".*/docker-compose\.ya?ml$"),
        CodegenHint(COMPOSE_BUILDER_HINT_TEMPLATE, COMPOSE_BUILDER_HINT_GENERATOR),
    ),
    (
        re.compile(r".*/Dockerfile$"),
        CodegenHint("Dockerfile.j2", "DockerfileGenerator"),
    ),
]


def get_codegen_hint(generated_file_path: str) -> CodegenHint | None:
    """Map a generated file path to its probable template and generator.

    Args:
        generated_file_path: Path to the generated file (forward or
            back slashes accepted).

    Returns:
        A CodegenHint if a known pattern matches, None if the mapping
        is ambiguous or no pattern matches.
    """
    normalized = generated_file_path.replace("\\", "/")
    for pattern, hint in _PATH_PATTERNS:
        if pattern.search(normalized):
            return hint
    return None
