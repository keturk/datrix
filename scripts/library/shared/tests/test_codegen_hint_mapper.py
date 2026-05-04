"""Tests for codegen_hint_mapper.

Tests verify:
- Known path patterns return correct hints
- Unknown paths return None
- Most-specific pattern wins when multiple could match
- Both forward and back slashes work
"""

from __future__ import annotations

import pytest

from shared.codegen_hint_mapper import CodegenHint, get_codegen_hint


@pytest.mark.unit
class TestCodegenHintMapper:
    """Test codegen hint mapping from file paths."""

    def test_python_entity_model_returns_hint(self) -> None:
        """Python entity model path returns EntityGenerator hint."""
        hint = get_codegen_hint("user_service/src/user_service/models/main/user.py")
        assert hint is not None
        assert hint.probable_template == "entity_model.py.j2"
        assert hint.probable_generator == "EntityGenerator"

    def test_python_schema_returns_hint(self) -> None:
        """Python schema path returns SchemaGenerator hint."""
        hint = get_codegen_hint("svc/src/svc/schemas/main/user_schema.py")
        assert hint is not None
        assert hint.probable_template == "entity_schema.py.j2"
        assert hint.probable_generator == "SchemaGenerator"

    def test_python_service_returns_hint(self) -> None:
        """Python service path returns ServiceGenerator hint."""
        hint = get_codegen_hint("svc/src/svc/services/main/user_service.py")
        assert hint is not None
        assert hint.probable_template == "entity_service.py.j2"
        assert hint.probable_generator == "ServiceGenerator"

    def test_python_routes_returns_hint(self) -> None:
        """Python routes path returns EndpointGenerator hint."""
        hint = get_codegen_hint("svc/src/svc/routes/main/user_routes.py")
        assert hint is not None
        assert hint.probable_template == "api_routes.py.j2"
        assert hint.probable_generator == "EndpointGenerator"

    def test_python_integration_helpers_returns_hint(self) -> None:
        """Python integration helpers path returns IntegrationGenerator hint."""
        hint = get_codegen_hint("svc/src/svc/integrations/_email_helpers.py")
        assert hint is not None
        assert hint.probable_template == "integration_helpers.py.j2"
        assert hint.probable_generator == "IntegrationGenerator"

    def test_python_errors_init_returns_hint(self) -> None:
        """Python errors/__init__.py returns ErrorGenerator hint."""
        hint = get_codegen_hint("svc/src/svc/errors/__init__.py")
        assert hint is not None
        assert hint.probable_template == "error_classes.py.j2"
        assert hint.probable_generator == "ErrorGenerator"

    def test_typescript_entity_returns_hint(self) -> None:
        """TypeScript entity path returns EntityGenerator hint."""
        hint = get_codegen_hint("svc/src/entities/user.entity.ts")
        assert hint is not None
        assert hint.probable_template == "entity.ts.j2"
        assert hint.probable_generator == "EntityGenerator"

    def test_typescript_dto_returns_hint(self) -> None:
        """TypeScript DTO path returns DtoGenerator hint."""
        hint = get_codegen_hint("svc/src/dto/user.dto.ts")
        assert hint is not None
        assert hint.probable_template == "dto.ts.j2"
        assert hint.probable_generator == "DtoGenerator"

    def test_typescript_controller_returns_hint(self) -> None:
        """TypeScript controller path returns ControllerGenerator hint."""
        hint = get_codegen_hint("svc/src/controllers/user.controller.ts")
        assert hint is not None
        assert hint.probable_template == "controller.ts.j2"
        assert hint.probable_generator == "ControllerGenerator"

    def test_docker_compose_returns_hint(self) -> None:
        """docker-compose.yml returns DockerComposeGenerator hint."""
        hint = get_codegen_hint("project/docker-compose.yml")
        assert hint is not None
        assert hint.probable_template == "docker-compose.yml.j2"
        assert hint.probable_generator == "DockerComposeGenerator"

    def test_dockerfile_returns_hint(self) -> None:
        """Dockerfile returns DockerfileGenerator hint."""
        hint = get_codegen_hint("svc/Dockerfile")
        assert hint is not None
        assert hint.probable_template == "Dockerfile.j2"
        assert hint.probable_generator == "DockerfileGenerator"

    def test_unknown_pattern_returns_none(self) -> None:
        """Unknown file path returns None."""
        assert get_codegen_hint("some/random/file.py") is None
        assert get_codegen_hint("README.md") is None
        assert get_codegen_hint("") is None

    def test_backslash_paths_normalized(self) -> None:
        """Windows-style backslash paths are normalized and matched."""
        hint = get_codegen_hint("svc\\src\\svc\\models\\main\\user.py")
        assert hint is not None
        assert hint.probable_template == "entity_model.py.j2"

    def test_most_specific_pattern_wins(self) -> None:
        """Integration helpers pattern (more specific) wins over general models."""
        # _email_helpers.py matches integration_helpers pattern specifically
        hint = get_codegen_hint("svc/src/svc/integrations/_email_helpers.py")
        assert hint is not None
        assert hint.probable_generator == "IntegrationGenerator"

    def test_codegen_hint_is_frozen(self) -> None:
        """CodegenHint is a frozen dataclass."""
        hint = CodegenHint("template.j2", "Generator")
        with pytest.raises(AttributeError):
            hint.probable_template = "other.j2"  # type: ignore[misc]
