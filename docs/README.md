# Datrix Documentation

Documentation for the Datrix code generation platform.

**Last updated:** April 13, 2026

---

## Why Datrix

- [Why Datrix](why-datrix.md) — Datrix vs vibe coding, the AI pairing, and what's under the hood

## Examples (repository)

Runnable specs live next to this tree under [`examples/`](../examples/):

- **[`examples/01-tutorial/`](../examples/01-tutorial/)** — 41 progressive lessons (Library Management System), from entities through GraphQL, jobs, and file operations. Start at [`01-basic-entity`](../examples/01-tutorial/01-basic-entity/).
- **[`examples/02-domains/`](../examples/02-domains/)** — Six full domains (blog-cms, ecommerce, healthcare, learning-management, social-platform, task-management) with `system.dtrx`, services, and `config/`.

See [`examples/README.md`](../examples/README.md) for structure, CLI usage, and patterns demonstrated in those trees.

## Architecture

- [Architecture Overview](architecture/architecture-overview.md) — System pipeline, repository structure, core principles
- [Design Principles](architecture/design-principles.md) — Fail-fast, exhaustive mappings, immutability, template-based generation

## Language Reference

- [Language Reference](reference/language-reference.md) — How to write `.dtrx` files: services, entities, APIs, events, caching, jobs, and more

## Getting Started

- [First Project](getting-started/first-project.md) — Build your first Datrix project (aligned with tutorial examples)

## Developer Guide

- [Guide index](guide/README.md) — Writing applications, configuration, patterns, and curated example links

---

## CLI

Install and usage details: [`datrix-cli/docs/commands.md`](../../datrix-cli/docs/commands.md). Typical commands:

```bash
datrix validate path/to/specs
datrix generate --source path/to/system.dtrx --output ./generated
datrix generate --source path/to/system.dtrx --output ./generated --profile production --language python --hosting docker
```

Short flags for overrides: `--language` / `-L`, `--hosting` / `-H`, `--platform` / `-P`.
