# Datrix Documentation Index

Quick-reference index for AI agents. All paths relative to `D:/datrix/`.

## 🎯 Start Here (High Priority)

**When:** First time working with Datrix or need architectural overview
- [architecture-overview.md](datrix/docs/architecture/architecture-overview.md) → System architecture, pipeline, capabilities
- [design-principles.md](datrix/docs/architecture/design-principles.md) → Core philosophy, design patterns
- [ai-agent-rules.md](datrix-common/docs/contributing/ai-agent-rules.md) → **MANDATORY before any task**

**Quick refs:**
- [architecture-cheat-sheet.md](datrix/docs/architecture/architecture-cheat-sheet.md)
- [design-principles-cheat-sheet.md](datrix/docs/architecture/design-principles-cheat-sheet.md)

## 🏗️ Architecture Deep Dive

**When:** Understanding system internals, pipeline stages, or repository structure

**Core:**
- [pipeline-and-capabilities.md](datrix/docs/architecture/architecture/pipeline-and-capabilities.md) → `.dtrx → AST → generators` flow
- [repository-architecture.md](datrix/docs/architecture/architecture/repository-architecture.md) → Monorepo structure, plugin system
- [builtin-traits-enums.md](datrix/docs/architecture/architecture/builtin-traits-enums.md) → Standard library types

**Subsystems:**
- [code-generation.md](datrix-common/docs/architecture/code-generation.md) → Generator framework
- [codegen-design.md](datrix-common/docs/architecture/codegen-design.md) → Code generation design
- [codegen-consolidation.md](datrix-common/docs/architecture/codegen-consolidation.md) → Consolidation architecture
- [config-system.md](datrix-common/docs/architecture/config-system.md) → Configuration architecture
- [config-migration-rationale.md](datrix-common/docs/architecture/config-migration-rationale.md) → YAML → ConfigDSL migration
- [semantic-validators.md](datrix-common/docs/architecture/semantic-validators.md) → Validation system
- [ast-parent-containment.md](datrix-common/docs/architecture/ast-parent-containment.md) → AST design
- [import-boundaries.md](datrix-common/docs/architecture/import-boundaries.md) → Module dependency rules
- [output-path-contract.md](datrix-common/docs/architecture/output-path-contract.md) → Output file path conventions

**Migration:**
- [codegen-migration-strategy.md](datrix/docs/architecture/codegen-migration-strategy.md) → Generator consolidation strategy

## 📝 Language & DSL Reference

**When:** Writing `.dtrx` files, understanding syntax, or semantic model

### Datrix Language (datrix-language)

**Architecture:**
- [architecture.md](datrix-language/docs/architecture.md) → Language package overview
- [parser-overview.md](datrix-language/docs/architecture/parser-overview.md) → How Datrix parser works
- [parser-design.md](datrix-language/docs/architecture/parser-design.md) → Parser v2 design
- [semantic-design.md](datrix-language/docs/architecture/semantic-design.md) → Semantic analyzer design
- [model-metaprogramming.md](datrix-language/docs/architecture/model-metaprogramming.md) → Declarative model metaprogramming

**Reference:**
- [datrix-syntax-reference.md](datrix-language/docs/reference/datrix-syntax-reference.md) → Complete DSL syntax
- [datrix-grammar.md](datrix-language/docs/reference/datrix-grammar.md) → Parser grammar
- [datrix-model.md](datrix-language/docs/reference/datrix-model.md) → Semantic model (AST nodes)
- [datrix-ast-nodes.md](datrix-language/docs/reference/datrix-ast-nodes.md) → Node type reference
- [datrix-stdlib-reference.md](datrix-language/docs/reference/datrix-stdlib-reference.md) → Standard library
- [datrix-builtins.md](datrix-language/docs/reference/datrix-builtins.md) → Built-in types
- [datrix-decorators.md](datrix-language/docs/reference/datrix-decorators.md) → Modifiers (@unique, @index, etc.)
- [datrix-validators.md](datrix-language/docs/reference/datrix-validators.md) → Semantic validators
- [datrix-type-registry.md](datrix-language/docs/reference/datrix-type-registry.md) → Type registry system
- [datrix-service-blocks.md](datrix-language/docs/reference/datrix-service-blocks.md) → Service block types
- [datrix-rules.md](datrix-language/docs/reference/datrix-rules.md) → Rule DSL syntax

**Features:**
- [field-attributes.md](datrix-language/docs/reference/field-attributes.md) → Field attribute reference
- [access-levels.md](datrix-language/docs/reference/access-levels.md) → Access control levels
- [cascade-behavior.md](datrix-language/docs/reference/cascade-behavior.md) → Relationship cascades
- [alert-syntax.md](datrix-language/docs/reference/alert-syntax.md) → Alert definitions
- [audit-syntax.md](datrix-language/docs/reference/audit-syntax.md) → Audit trail syntax

### Config DSL

**When:** Working with configuration files
- [config-dsl-reference.md](datrix/docs/reference/config-dsl-reference.md) → ConfigDSL syntax reference
- [config-dsl-reference.md](datrix-common/docs/config-dsl-reference.md) → ConfigDSL syntax reference (datrix-common)
- [config-dsl-guide.md](datrix-common/docs/config-dsl-guide.md) → Practical ConfigDSL guide
- [config-store.md](datrix-common/docs/config-store.md) → Runtime config store schema, enums, validation, and engine compatibility

### Seed DSL

**When:** Defining seed data
- [seed-dsl-syntax-reference.md](datrix-language/docs/reference/seed-dsl-syntax-reference.md) → SeedDSL syntax

## 🧪 Testing

**When:** Writing tests, understanding test strategy

### Test Guidelines (datrix-common)

- [unit-test-guidelines.md](datrix-common/docs/contributing/test-guidelines/unit-test-guidelines.md) → Unit test standards
- [integration-test-guidelines.md](datrix-common/docs/contributing/test-guidelines/integration-test-guidelines.md) → Integration test standards
- [e2e-test-guidelines.md](datrix-common/docs/contributing/test-guidelines/e2e-test-guidelines.md) → E2E test standards

**Shared guidelines:**
- [assertion-anti-patterns.md](datrix-common/docs/contributing/test-guidelines/shared/assertion-anti-patterns.md) → What NOT to do
- [test-utilities-and-fixtures.md](datrix-common/docs/contributing/test-guidelines/shared/test-utilities-and-fixtures.md) → Shared helpers
- [repo-specific-testing.md](datrix-common/docs/contributing/test-guidelines/shared/repo-specific-testing.md) → Per-repo testing guidance
- [repo-specific-integration.md](datrix-common/docs/contributing/test-guidelines/shared/repo-specific-integration.md) → Integration testing guidance

### Spec Testing

**When:** Testing at specification level
- [spec-testing.md](datrix/docs/guide/spec-testing.md) → Specification-level testing (DSL `test` blocks)

## 🛠️ Code Generation

**When:** Working with generators, templates, or code output

### GenDSL (datrix-codegen-common)

**When:** Defining or modifying generators
- [overview.md](datrix-codegen-common/docs/gendsl/overview.md) → Generator Definition DSL overview
- [syntax.md](datrix-codegen-common/docs/gendsl/syntax.md) → GenDSL syntax specification
- [context-models.md](datrix-codegen-common/docs/gendsl/context-models.md) → Template context models
- [iteration-model.md](datrix-codegen-common/docs/gendsl/iteration-model.md) → Multi-pass generation
- [python-interop.md](datrix-codegen-common/docs/gendsl/python-interop.md) → Python integration
- [runtime-ir.md](datrix-codegen-common/docs/gendsl/runtime-ir.md) → Runtime IR
- [semantic-requirements.md](datrix-codegen-common/docs/gendsl/semantic-requirements.md) → Semantic requirements
- [design-decisions.md](datrix-codegen-common/docs/gendsl/design-decisions.md) → GenDSL design decisions
- [migration-guide.md](datrix-codegen-common/docs/gendsl/migration-guide.md) → GenDSL migration guide
- [cross-domain-contributions.md](datrix-codegen-common/docs/gendsl/cross-domain-contributions.md) → Cross-domain file contributions
- [generated-tests.md](datrix-codegen-common/docs/gendsl/generated-tests.md) → Generated test structure
- [examples.md](datrix-codegen-common/docs/gendsl/examples.md) → Complete GenDSL examples

### Codegen Common

- [architecture.md](datrix-codegen-common/docs/architecture.md) → datrix-codegen-common overview
- [dashboards-api.md](datrix-codegen-common/docs/dashboards-api.md) → Dashboard generation API
- [test-artifacts.md](datrix-codegen-common/docs/test-artifacts.md) → Test artifact generation

### Language Generators

**Python (datrix-codegen-python):**
- [architecture.md](datrix-codegen-python/docs/architecture.md) → Python generator architecture
- [generators.md](datrix-codegen-python/docs/generators.md) → Python generator catalog
- [type-mappings-extensions.md](datrix-codegen-python/docs/type-mappings-extensions.md) → Python type mappings
- [exceptions-and-custom-scalars.md](datrix-codegen-python/docs/exceptions-and-custom-scalars.md) → Exception & scalar handling
- [observability-codegen.md](datrix-codegen-python/docs/observability-codegen.md) → Python observability generation
- [tenancy-codegen.md](datrix-codegen-python/docs/tenancy-codegen.md) → Python multi-tenancy generation
- [seed-generation.md](datrix-codegen-python/docs/seed-generation.md) → Python seed data generation
- [runtime-config-client.md](datrix-codegen-python/docs/runtime-config-client.md) → Python runtime config store client

**TypeScript (datrix-codegen-typescript):**
- [architecture.md](datrix-codegen-typescript/docs/architecture.md) → TypeScript generator architecture
- [generators.md](datrix-codegen-typescript/docs/generators.md) → TypeScript generator catalog
- [extension-type-mappings.md](datrix-codegen-typescript/docs/extension-type-mappings.md) → TypeScript type mappings
- [observability-codegen.md](datrix-codegen-typescript/docs/observability-codegen.md) → TypeScript observability generation
- [tenancy-codegen.md](datrix-codegen-typescript/docs/tenancy-codegen.md) → TypeScript multi-tenancy generation
- [seed-generation.md](datrix-codegen-typescript/docs/seed-generation.md) → TypeScript seed data generation
- [runtime-config-client.md](datrix-codegen-typescript/docs/runtime-config-client.md) → TypeScript runtime config store client

**SQL (datrix-codegen-sql):**
- [architecture.md](datrix-codegen-sql/docs/architecture.md) → SQL generator architecture
- [type-mappings-extensions.md](datrix-codegen-sql/docs/type-mappings-extensions.md) → SQL type mappings
- [seed-dialect-extensions.md](datrix-codegen-sql/docs/seed-dialect-extensions.md) → SQL dialect extensions

### Platform Generators

**Component (datrix-codegen-component):**
- [architecture.md](datrix-codegen-component/docs/architecture.md) → Component generator architecture
- [extensions.md](datrix-codegen-component/docs/extensions.md) → Component generator extensions

**Docker (datrix-codegen-docker):**
- [README.md](datrix-codegen-docker/docs/README.md) → Docker generator documentation
- [architecture.md](datrix-codegen-docker/docs/architecture.md) → Docker generator architecture
- [docker-generator-api.md](datrix-codegen-docker/docs/docker-generator-api.md) → Docker generator API
- [docker-compose.md](datrix-codegen-docker/docs/docker-compose.md) → Docker Compose generation
- [multi-service.md](datrix-codegen-docker/docs/multi-service.md) → Multi-service applications
- [observability-stack.md](datrix-codegen-docker/docs/observability-stack.md) → Observability stack generation
- [seed-services.md](datrix-codegen-docker/docs/seed-services.md) → Seed service Docker generation
- [config-store.md](datrix-codegen-docker/docs/config-store.md) → Consul config store generation (Docker)

**AWS (datrix-codegen-aws):**
- [architecture.md](datrix-codegen-aws/docs/architecture.md) → AWS generator architecture
- [aws-generator-api.md](datrix-codegen-aws/docs/aws-generator-api.md) → AWS generator API
- [config-store.md](datrix-codegen-aws/docs/config-store.md) → AWS AppConfig config store generation

**Azure (datrix-codegen-azure):**
- [architecture.md](datrix-codegen-azure/docs/architecture.md) → Azure generator architecture
- [azure-generator-api.md](datrix-codegen-azure/docs/azure-generator-api.md) → Azure generator API
- [extensions.md](datrix-codegen-azure/docs/extensions.md) → Azure infrastructure generation extensions
- [config-store.md](datrix-codegen-azure/docs/config-store.md) → Azure App Configuration config store generation

## 🔌 Extensions

**When:** Adding custom types, integrations, or domain-specific functionality

### datrix-extensions

- [extensions-guide.md](datrix-extensions/docs/extensions-guide.md) → Extension user guide
- [creating-extensions.md](datrix-extensions/docs/creating-extensions.md) → Building extension packs
- [postgis-extension.md](datrix-extensions/docs/postgis-extension.md) → PostGIS geospatial extension
- [geo-raster-extension.md](datrix-extensions/docs/geo-raster-extension.md) → Raster data extension

### datrix-common

- [extensions.md](datrix-common/docs/extensions.md) → Domain extensions overview

### datrix-cli

- [extensions.md](datrix-cli/docs/extensions.md) → CLI domain extensions

## 📚 Contributing & Standards

**When:** Making changes to the codebase

### MANDATORY Reading

- [ai-agent-rules.md](datrix-common/docs/contributing/ai-agent-rules.md) → **Read before ANY task**
  - [prohibited-patterns.md](datrix-common/docs/contributing/ai-agent-rules/prohibited-patterns.md) → 8 absolute prohibitions
  - [code-quality-standards.md](datrix-common/docs/contributing/ai-agent-rules/code-quality-standards.md) → Type hints, docstrings, testing
  - [repo-specific-rules.md](datrix-common/docs/contributing/ai-agent-rules/repo-specific-rules.md) → Per-repo rules
  - [canonical-imports.md](datrix-common/docs/contributing/ai-agent-rules/canonical-imports.md) → Import path standards

### Contributing Guides

- [README.md](datrix-common/docs/contributing/README.md) → Start here for contributing
- [configuration-standards.md](datrix-common/docs/contributing/configuration-standards.md) → Configuration standards
- [error-handling-policy.md](datrix-common/docs/error-handling-policy.md) → Error handling policy
- [pycharm-monorepo-setup.md](datrix-common/docs/contributing/pycharm-monorepo-setup.md) → PyCharm setup for monorepo
- [releases.md](datrix-common/docs/contributing/releases.md) → Release process
- [task-template.md](datrix-common/docs/contributing/task-template.md) → Task documentation template
- [pyproject.toml.template](datrix-common/docs/contributing/pyproject.toml.template) → pyproject.toml template

### Agent Skills

- [execute_tasks.md](datrix-common/docs/contributing/agent_skills/execute_tasks.md) → Task execution AI prompts

## 📖 User Guides

**When:** Learning how to use Datrix

### Getting Started

- [README.md](datrix/docs/README.md) → Documentation home
- [first-project.md](datrix/docs/getting-started/first-project.md) → Your first Datrix project
- [quick-start.md](datrix-common/docs/getting-started/quick-start.md) → Quick start guide
- [installation.md](datrix-common/docs/getting-started/installation.md) → Installation instructions

### Guides (datrix/docs/guide)

- [README.md](datrix/docs/guide/README.md) → Datrix developer guide
- [writing-datrix-applications.md](datrix/docs/guide/writing-datrix-applications.md) → Writing Datrix applications
- [patterns-and-best-practices.md](datrix/docs/guide/patterns-and-best-practices.md) → Patterns and best practices
- [complete-examples.md](datrix/docs/guide/complete-examples.md) → Complete example applications
- [configuration-guide.md](datrix/docs/guide/configuration-guide.md) → Configuration guide
- [seed-data-guidelines.md](datrix/docs/guide/seed-data-guidelines.md) → Seed data guidelines
- [event-contracts.md](datrix/docs/guide/event-contracts.md) → Event contract validation

### Why Datrix

- [why-datrix.md](datrix/docs/why-datrix.md) → Why use Datrix

## 🖥️ CLI (datrix-cli)

**When:** Using the Datrix CLI tool

- [architecture.md](datrix-cli/docs/architecture.md) → CLI architecture
- [commands.md](datrix-cli/docs/commands.md) → Command reference
- [getting-started.md](datrix-cli/docs/getting-started.md) → Getting started with CLI
- [examples.md](datrix-cli/docs/examples.md) → CLI examples

**Commands:**
- [generate.md](datrix-cli/docs/commands/generate.md) → `generate` command
- [seed.md](datrix-cli/docs/commands/seed.md) → `seed` command

## 🔍 Generated Reference

**When:** Understanding auto-generated documentation

- [cli-generate-help.md](datrix/docs/generated/cli-generate-help.md) → CLI generate command help output
- [semantic-pipeline-stages.md](datrix/docs/generated/semantic-pipeline-stages.md) → Semantic pipeline stages

## 🌐 Integrations

**When:** Integrating with external services

- [arcgis-feature-layer.md](datrix-common/docs/integrations/arcgis-feature-layer.md) → ArcGIS FeatureLayer integration
- [payment-gateways.md](datrix-common/docs/integrations/payment-gateways.md) → Payment gateway integration

## 📦 API Documentation

**When:** Using Datrix programmatically

- [datrix-common-api.md](datrix-common/docs/datrix-common-api.md) → datrix-common API
- [datrix-codegen-api.md](datrix-common/docs/datrix-codegen-api.md) → Code generation API (quick ref)
- [datrix-codegen.md](datrix-common/docs/reference/datrix-codegen.md) → Code generation system reference
- [datrix-language-api.md](datrix-language/docs/datrix-language-api.md) → datrix-language API
- [generators-api.md](datrix-common/docs/generators-api.md) → Generator APIs reference

## 🗂️ Project Structure

**When:** Understanding repository organization

- [meta-project-structure.md](datrix-common/docs/meta-project-structure.md) → Datrix monorepo structure
- [output-directory-layout.md](datrix-common/docs/output-directory-layout.md) → Generated code directory layout

## 🔍 Special Topics

**When:** Working with specific cross-cutting concerns

| Topic | Documentation |
|-------|--------------|
| **Observability** | [observability.md](datrix-common/docs/observability.md), Python: [observability-codegen.md](datrix-codegen-python/docs/observability-codegen.md), TypeScript: [observability-codegen.md](datrix-codegen-typescript/docs/observability-codegen.md), Docker: [observability-stack.md](datrix-codegen-docker/docs/observability-stack.md) |
| **Multi-tenancy** | Python: [tenancy-codegen.md](datrix-codegen-python/docs/tenancy-codegen.md), TypeScript: [tenancy-codegen.md](datrix-codegen-typescript/docs/tenancy-codegen.md) |
| **Runtime Config Store** | Schema: [config-store.md](datrix-common/docs/config-store.md), Python client: [runtime-config-client.md](datrix-codegen-python/docs/runtime-config-client.md), TypeScript client: [runtime-config-client.md](datrix-codegen-typescript/docs/runtime-config-client.md), Docker/Consul: [config-store.md](datrix-codegen-docker/docs/config-store.md), AWS AppConfig: [config-store.md](datrix-codegen-aws/docs/config-store.md), Azure App Configuration: [config-store.md](datrix-codegen-azure/docs/config-store.md) |
| **Seed data** | [seed-data-guidelines.md](datrix/docs/guide/seed-data-guidelines.md), Python: [seed-generation.md](datrix-codegen-python/docs/seed-generation.md), TypeScript: [seed-generation.md](datrix-codegen-typescript/docs/seed-generation.md), SQL: [seed-dialect-extensions.md](datrix-codegen-sql/docs/seed-dialect-extensions.md), Docker: [seed-services.md](datrix-codegen-docker/docs/seed-services.md) |
| **Entity identity** | [entity-identity.md](datrix-common/docs/generation/entity-identity.md) |
| **Code generation** | [README.md](datrix-common/docs/generation/README.md) |

---

**Index last updated:** 2026-05-31
**Total indexed documents:** 151
