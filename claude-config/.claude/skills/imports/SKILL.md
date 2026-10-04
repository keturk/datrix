---
description: Look up canonical Datrix module import paths
model: claude-sonnet-5-5
effort: medium
disable-model-invocation: true
---

# Canonical Module Paths

- `datrix_common.datrix_model.entity` → `Entity`, `Field`
- `datrix_common.datrix_model.containers` → `Service`, `Application`
- `datrix_common.datrix_model.blocks` → `RdbmsBlock`, `CacheBlock`
- `datrix_common.datrix_model.pubsub` → `PubsubBlock`, `Topic`, `Event`, `Subscription`
- `datrix_common.datrix_model.cqrs` → `CqrsBlock`, `View`
- `datrix_common.datrix_model.api` → `RestApi`, `GraphqlApi`
- `datrix_common.datrix_model.callables` → `Function`, `Endpoint`, `Command`, `Query`, `EventHandler`, `Parameter`, `AccessLevel`
- `datrix_common.types.registry` → `TypeRegistry`
- `datrix_common.types.base` → `ScalarType`, `DatrixType`
- `datrix_semantic` → `SemanticAnalyzer`, `AnalysisResult`
- `datrix_common.cross_service.contract` → `EndpointContract`, `get_cross_service_contract`
- `datrix_common.rendering.expressions` → `render_expression_source`; `datrix_language.formatting` → `FormatOptions`, `format_dtrx_source`, `verify_lossless`
- `datrix_common.config_resolution` → `resolve_service_configs`, `resolve_infrastructure_configs`
- `datrix_language.parser` → `TreeSitterParser`
- `datrix_codegen_kernel.generation.template_generator` → `TemplateGenerator`
- `datrix_codegen_kernel.generation.generator` → `Generator`, `GeneratedFile`
- `datrix_cli.pipeline.generation` → `GenerationPipeline`, `PipelineConfig`, `PipelineResult`
- `datrix_codegen_common.generation.type_resolver` → `TypeResolver`, `OrmTypeResolver`, `TypeMapping`
- `datrix_codegen_kernel.generation.plugin_helpers` → `detect_service_features`, `render_code_file`, `create_template_generator`
- `datrix_codegen_kernel.generation.discovery` → `discover_generators`, `discover_platforms`
- `datrix_codegen_common.generation.orchestrator` → `ServiceOrchestrator`
- `datrix_codegen_common.generation.language_generator` → `LanguageGenerator`
- `datrix_codegen_kernel.generation.type_mapping_registry` → `TypeMappingRegistry`, `global_registry`
- `datrix_codegen_common.transpiler.language_transpiler` → `LanguageTranspiler`, `LiteralKeywords`
- `datrix_codegen_common.transpiler.protocols` → `TranspilerStateProtocol`
- `datrix_codegen_kernel.generation.language_helpers` → `_derive_default_dialect`, `_build_service_map`, `_register_module_level_names`, `effective_observability_config`
- `datrix_codegen_common.generation.import_paths` → `build_entity_import_paths`
- `datrix_codegen_python.generation.sample_values` → `select_sample_index`
- `datrix_codegen_kernel.generation.registry` → `GeneratorDep`, `SubGeneratorSpec`
- `datrix_codegen_kernel.generation.validation` → `require_mapped_type`, `validate_template_dir`, `require_deployment_field`
- `datrix_codegen_kernel.generation.project_defaults` → `build_project_config`
- `datrix_cli.generation.file_writer` → `FileWriter`, `WriteResult`, `ConflictStrategy`
- `datrix_codegen_common.generation.language_hooks` → `LanguageHooks`
- `datrix_common.plugin.hook_outcome` → `HookOutcome`
- `datrix_codegen_kernel.generation.app_context` → `get_app_name`
- `datrix_migration.generator` → `MigrationGenerator`, `MigrationFormat`
- `datrix_migration.differ` → `SchemaDiffer`, `SchemaDiff`, `SchemaChange`, `ChangeKind`
- `datrix_migration.errors` → `DestructiveOperationError`, `NoSnapshotError`
- `datrix_common.fileops` → `read_text_utf8`, `write_text_utf8`, `load_json`, `save_json`
- `datrix_common.utils.text` → `to_snake_case`, `to_camel_case`, `to_pascal_case`, `to_kebab_case`, `to_screaming_snake_case`, `to_plural`, `to_singular`, `extract_simple_name`
- `datrix_common.paths` → `ServicePaths`
- `datrix_common.config.codegen_context` → `CodegenContext`
- `datrix_common.config.platform` → `BasePlatformConfig`, `DockerPlatformConfig`, `AwsPlatformConfig`, `AzurePlatformConfig`
- `datrix_common.config.project.models` → `ProjectConfig`, `EmptyProjectSettings`
- `datrix_common.config.project.catalog` → `get_dependency_version`, `CatalogLookupError`
- `datrix_common.config.datasource.broker_engine` → `BrokerEngine`, `get_broker_engine`, `KAFKA`, `all_broker_engines`
- `datrix_common.config.datasource.cache_engine` → `CacheEngine`, `get_cache_engine`, `REDIS`, `all_cache_engines` (plus `rdbms_engine`, `nosql_engine`, `models`)
- `datrix_codegen_docker.secrets` → `SecretStore`, `generate_password`, `generate_secret_key`
- `datrix_common.infra.registry` → `InfraRegistry`, `InfraGroup`, `InfraIdentity`
- `datrix_testing.infra_constants` (test/dev extra only) → `RDBMS_DEPLOYMENT_DEFAULTS`, `CACHE_DEPLOYMENT_DEFAULTS`, `PUBSUB_DEPLOYMENT_DEFAULTS`, `NOSQL_DEPLOYMENT_DEFAULTS`
- `datrix_common.config.datasource.rdbms_engine` → `RdbmsEngine`, `POSTGRES`, `MYSQL`, `MARIADB`, `get_rdbms_engine`, `get_rdbms_engine_by_sql_dialect`, `all_rdbms_engines`
- `datrix_common.errors.configuration` → `ConfigurationError`, `ConfigFileNotFoundError`, `ConfigParseError`, `ConfigValidationError`
- `datrix_common.utils.engine_helpers` → `engine_str`, `validate_engine`, `resolve_sql_dialect`
- `datrix_common.utils.job_helpers` → `job_timeout_seconds`, `job_retry_limit`, `get_job_render_context`
- `datrix_common.utils.resources` → `parse_cpu_millicores`, `parse_memory_mib`, `cpu_to_compose_str`, `memory_to_compose_str`
- `datrix_common.utils.provider_helpers` → `resolve_email_provider`, `resolve_sms_provider`, `get_provider_deps`, `get_provider_env_vars`
- `datrix_common.utils.json` → `canonical_json_string`, `parse_and_serialize_json`
- `datrix_common.directory_constants` → `SOURCE_DIR`, `SERVICES_DIR`, `ENUMS_DIR`, etc.
- `datrix_common.builtins.traits` → `BUILTIN_TRAIT_NAMES`
- `datrix_common.builtins.enums` → `BUILTIN_ENUM_NAMES`, `ENUM_REQUIRED_BY_TRAIT`
- `datrix_language.builtins.loader` → `get_builtin_traits`, `get_builtin_enums`

