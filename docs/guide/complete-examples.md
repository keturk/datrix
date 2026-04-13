# Complete Examples

**Last updated:** April 13, 2026

The **canonical, maintained examples** live under [`examples/`](../../examples/) in this repository. They are validated against the current DSL and generators. Use them as copy-paste starting points and as the ground truth for syntax.

This page **indexes** those trees. Older narrative “synthetic” multi-page specs were removed so the docs do not drift from what actually parses and generates.

---

## 1. Tutorial series (`examples/01-tutorial/`)

Forty-one progressive steps built around a **Library Management System** (Book / Member / Loan services as tutorials advance).

| Area | Tutorial folders (examples) |
|------|------------------------------|
| Entities, enums, APIs | [`01-basic-entity`](../../examples/01-tutorial/01-basic-entity/) → [`03-basic-api`](../../examples/01-tutorial/03-basic-api/) |
| Computed fields, relationships | [`04-computed-fields`](../../examples/01-tutorial/04-computed-fields/) → [`05-relationships`](../../examples/01-tutorial/05-relationships/) → [`16-advanced-relationships`](../../examples/01-tutorial/16-advanced-relationships/) |
| Validation & hooks | [`06-validation`](../../examples/01-tutorial/06-validation/) → [`07-lifecycle-hooks`](../../examples/01-tutorial/07-lifecycle-hooks/) |
| Auth & events | [`08-authentication`](../../examples/01-tutorial/08-authentication/) → [`09-events`](../../examples/01-tutorial/09-events/) |
| Multi-service | [`10-multiple-services`](../../examples/01-tutorial/10-multiple-services/) → [`11-service-dependencies`](../../examples/01-tutorial/11-service-dependencies/) → [`12-internal-endpoints`](../../examples/01-tutorial/12-internal-endpoints/) |
| Integrations, cache, CQRS, jobs | [`14-integrations`](../../examples/01-tutorial/14-integrations/) → [`15-cache`](../../examples/01-tutorial/15-cache/) → [`20-cqrs`](../../examples/01-tutorial/20-cqrs/) → [`21-background-jobs`](../../examples/01-tutorial/21-background-jobs/) |
| Resilience & gateway | [`22-resilience`](../../examples/01-tutorial/22-resilience/) → [`23-api-gateway`](../../examples/01-tutorial/23-api-gateway/) |
| NoSQL, storage | [`24-nosql`](../../examples/01-tutorial/24-nosql/) → [`25-storage`](../../examples/01-tutorial/25-storage/) |
| Modules & GraphQL | [`29-modules`](../../examples/01-tutorial/29-modules/) → [`30-graphql`](../../examples/01-tutorial/30-graphql/) |
| Transactions, batch, advanced cache | [`32-transactions`](../../examples/01-tutorial/32-transactions/) → [`33-batch-operations`](../../examples/01-tutorial/33-batch-operations/) → [`34-advanced-cache`](../../examples/01-tutorial/34-advanced-cache/) |
| Enums, security, semantics, hasOne | [`35-advanced-enums`](../../examples/01-tutorial/35-advanced-enums/) → [`36-field-security`](../../examples/01-tutorial/36-field-security/) → [`37-semantic-types`](../../examples/01-tutorial/37-semantic-types/) → [`38-hasone-relationship`](../../examples/01-tutorial/38-hasone-relationship/) |
| Webhooks, validation, files | [`39-webhooks-idempotency`](../../examples/01-tutorial/39-webhooks-idempotency/) → [`40-advanced-validation`](../../examples/01-tutorial/40-advanced-validation/) → [`41-file-operations`](../../examples/01-tutorial/41-file-operations/) |

Full table: [`examples/01-tutorial/README.md`](../../examples/01-tutorial/README.md).

---

## 2. Domain applications (`examples/02-domains/`)

End-to-end multi-service designs with `system.dtrx`, `common.dtrx` (where used), per-service `*.dtrx`, and `config/`.

| Domain | Folder |
|--------|--------|
| Blog / CMS | [`blog-cms`](../../examples/02-domains/blog-cms/) |
| E-commerce | [`ecommerce`](../../examples/02-domains/ecommerce/) |
| Healthcare | [`healthcare`](../../examples/02-domains/healthcare/) |
| Learning / LMS | [`learning-management`](../../examples/02-domains/learning-management/) |
| Social | [`social-platform`](../../examples/02-domains/social-platform/) |
| Tasks / projects | [`task-management`](../../examples/02-domains/task-management/) |

Overview: [`examples/02-domains/README.md`](../../examples/02-domains/README.md).

---

## 3. Generate code from an example

Always pass the **`system.dtrx`** entry file and an output directory. Profile defaults to **`test`** if omitted.

```bash
# Validate everything under a tutorial or domain folder
datrix validate examples/01-tutorial/03-basic-api

# Generate (language + hosting from YAML for profile test)
datrix generate --source examples/01-tutorial/03-basic-api/system.dtrx --output ./generated

# Same with explicit profile
datrix generate --source examples/02-domains/ecommerce/system.dtrx --output ./generated --profile test
```

Optional **one-shot overrides** (see [`datrix-cli/docs/commands.md`](../../datrix-cli/docs/commands.md)):

```bash
datrix generate --source examples/02-domains/ecommerce/system.dtrx --output ./generated -L python -H docker -P compose
```

(`-L` = `--language`, `-H` = `--hosting`, `-P` = `--platform`.)

Some domains also ship **pre-generated** trees under `generated/` for inspection; regenerating is still the supported workflow.

---

## 4. Patterns illustrated in examples

Cross-cutting patterns are documented in [`examples/README.md`](../../examples/README.md): named `rdbms` / `cache` / `pubsub` blocks, `discovery`, internal REST routes, `resource` + `access`, computed fields, lifecycle hooks, and imports between services/modules.

For narrative explanations, see [Writing Datrix Applications](./writing-datrix-applications.md) and [Patterns and Best Practices](./patterns-and-best-practices.md).

---

## Next steps

- New users: [Your First Project](../getting-started/first-project.md)
- DSL details: [Language Reference](../reference/language-reference.md)
- YAML: [Configuration Guide](./configuration-guide.md)
