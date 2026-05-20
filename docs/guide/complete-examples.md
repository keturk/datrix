# Complete Examples

**Last updated:** April 24, 2026

The **canonical, maintained examples** live under [`examples/`](../../examples/) in this repository. They are validated against the current DSL and generators. Use them as copy-paste starting points and as the ground truth for syntax.

This page **indexes** those trees. Older narrative “synthetic” multi-page specs were removed so the docs do not drift from what actually parses and generates.

---

## 1. Foundation (`examples/01-foundation/`)

Baseline example showing the minimal multi-file project shape:

- [`system.dtrx`](../../examples/01-foundation/system.dtrx)
- [`common.dtrx`](../../examples/01-foundation/common.dtrx)
- [`book-service-base.dtrx`](../../examples/01-foundation/book-service-base.dtrx)

---

## 2. Feature examples (`examples/02-features/`)

Focused examples grouped by topic:

| Group | Folder |
|------|--------|
| Core data modeling | [`01-core-data-modeling`](../../examples/02-features/01-core-data-modeling/) |
| Service architecture | [`02-service-architecture`](../../examples/02-features/02-service-architecture/) |
| Infrastructure blocks | [`03-infrastructure-blocks`](../../examples/02-features/03-infrastructure-blocks/) |
| Advanced data features | [`04-advanced-data-features`](../../examples/02-features/04-advanced-data-features/) |
| Infrastructure combinations | [`05-infrastructure-combinations`](../../examples/02-features/05-infrastructure-combinations/) |
| Advanced language features | [`06-advanced-language-features`](../../examples/02-features/06-advanced-language-features/) |

Commonly referenced feature folders:

- REST APIs: [`01-core-data-modeling/rest-api`](../../examples/02-features/01-core-data-modeling/rest-api/)
- Relationships: [`01-core-data-modeling/relationships`](../../examples/02-features/01-core-data-modeling/relationships/)
- Lifecycle hooks: [`01-core-data-modeling/lifecycle-hooks`](../../examples/02-features/01-core-data-modeling/lifecycle-hooks/)
- Authentication: [`01-core-data-modeling/authentication`](../../examples/02-features/01-core-data-modeling/authentication/)
- Jobs: [`03-infrastructure-blocks/jobs`](../../examples/02-features/03-infrastructure-blocks/jobs/)
- GraphQL: [`03-infrastructure-blocks/graphql`](../../examples/02-features/03-infrastructure-blocks/graphql/)
- **Queues (task dispatch):** [`03-infrastructure-blocks/queue`](../../examples/02-features/03-infrastructure-blocks/queue/) — producer `queues('config/.../queue.yaml')`, consumer `enqueue BookService.TaskName(…)`, `dispatch` from hooks; includes `config/book-service/queue.yaml` and paired `notification-service` consumer.

**Generated output (high level):** the producer service gets **`queue/payloads`** and **`queue/client`** modules; the consumer gets **`workers/queue_worker`** plus per-queue **handler** modules. Platform generators add broker containers (Compose/K8s) and cloud queue resources when enabled.

---

## 3. Domain applications (`examples/03-domains/`)

End-to-end multi-service designs with `system.dtrx`, `common.dtrx` (where used), per-service `*.dtrx`, and `config/`.

| Domain | Folder |
|--------|--------|
| Blog / CMS | [`blog-cms`](../../examples/03-domains/blog-cms/) |
| E-commerce | [`ecommerce`](../../examples/03-domains/ecommerce/) |
| Healthcare | [`healthcare`](../../examples/03-domains/healthcare/) |
| Learning / LMS | [`learning-management`](../../examples/03-domains/learning-management/) |
| Social | [`social-platform`](../../examples/03-domains/social-platform/) |
| Tasks / projects | [`task-management`](../../examples/03-domains/task-management/) |
| Finance | [`finance`](../../examples/03-domains/finance/) |
| Food delivery | [`food-delivery`](../../examples/03-domains/food-delivery/) |
| HR platform | [`hr-platform`](../../examples/03-domains/hr-platform/) |
| IoT platform | [`iot-platform`](../../examples/03-domains/iot-platform/) |
| Logistics | [`logistics`](../../examples/03-domains/logistics/) |
| Real estate | [`real-estate`](../../examples/03-domains/real-estate/) |

---

## 4. Generate code from an example

Always pass the **`system.dtrx`** entry file and an output directory. Profile defaults to **`test`** if omitted.

```bash
# Validate everything under a foundation/feature/domain folder
datrix validate examples/02-features/01-core-data-modeling/rest-api

# Generate (language + hosting from YAML for profile test)
datrix generate --source examples/02-features/01-core-data-modeling/rest-api/system.dtrx --output ./generated

# Same with explicit profile
datrix generate --source examples/03-domains/ecommerce/system.dtrx --output ./generated --profile test
```

Optional **language override** for development (see [`datrix-cli/docs/commands.md`](../../datrix-cli/docs/commands.md)):

```bash
datrix generate --source examples/03-domains/ecommerce/system.dtrx --output ./generated -L python
```

**Note:** Deployment configuration (runtime and provider) is specified in the ConfigDSL files, not via CLI flags.

Some domains also ship **pre-generated** trees under `generated/` for inspection; regenerating is still the supported workflow.

---

## 5. Extern service integration

A complete example showing an `extern service` declaration alongside a consuming Datrix service.

### Spec (`specs/system.dtrx`)

```dtrx
system ecommerce('config/system.dcfg') {}
```

### Spec (`specs/pricing-engine.dtrx`)

```dtrx
extern service pricing.PricingEngine('config/pricing-engine.yaml')
    : version('1.0.0'), description('External pricing engine') {

    struct PricingRequest {
        String productId;
        Int quantity;
    }

    struct PricingResponse {
        Decimal totalPrice;
        String currency;
    }

    rest_api PricingAPI : basePath('/api/v1') {
        post calculatePrice(PricingRequest req) -> PricingResponse {
            ensure req.quantity > 0;
            ensure req.productId != null;
        }
    }

    errors {
        PricingNotFound(String message);
    }

    auth : apiKey(header: 'X-API-Key');
    health : path('/health');
}
```

### Spec (`specs/order-service.dtrx`)

```dtrx
service ecommerce.OrderService('config/order-service.yaml') {
    uses PricingEngine;

    rdbms db('config/order-service/datasources.dcfg') {
        entity Order extends BaseEntity {
            UUID customerId;
            Money total;
        }
    }

    rest_api OrderAPI : basePath('/api/v1/orders') {
        post createOrder(UUID customerId, String productId, Int quantity) -> Order {
            // PricingRequest and PricingResponse types are available here
            // Generated PricingEngineClient is used for the HTTP call
        }
    }
}
```

### Config (`config/pricing-engine.yaml`)

```yaml
development:
  deployment: container
  image: myregistry/pricing-engine:dev
  port: 8080
  auth:
    type: apiKey
    header: X-API-Key
    secret: PRICING_API_KEY

production:
  deployment: external
  url: https://pricing.prod.internal/api
  auth:
    type: bearer
    secret: PRICING_BEARER_TOKEN
```

### What you build

The extern service implementation (the `pricing-engine` container) is built and deployed by **you** — Datrix does not generate its code. Your implementation must:

- Serve `POST /api/v1/calculatePrice` accepting `PricingRequest` JSON and returning `PricingResponse` JSON
- Expose a health endpoint at `/health`
- Accept an API key via the `X-API-Key` header

### What Datrix generates

For `OrderService`, Datrix generates:

| Artifact | Description |
|----------|-------------|
| `clients/pricing_engine.py` (or `.ts`) | Async HTTP client with `calculate_price()` method |
| `clients/pricing_engine_models.py` (or `.models.ts`) | `PricingRequest`, `PricingResponse` data models |
| `clients/pricing_engine_errors.py` (or `.errors.ts`) | `PricingNotFoundError` exception class |
| `clients/pricing_engine_contracts.py` (or `.contracts.ts`) | `validate_calculate_price_contract()` function |
| Docker Compose entry | `pricing-engine` service (dev profile) with health check |

---

## 6. Patterns illustrated in examples

Cross-cutting patterns are documented in [`examples/README.md`](../../examples/README.md): named `rdbms` / `cache` / `pubsub` blocks, `discovery`, internal REST routes, `resource` + `access`, computed fields, lifecycle hooks, and imports between services/modules.

For narrative explanations, see [Writing Datrix Applications](./writing-datrix-applications.md) and [Patterns and Best Practices](./patterns-and-best-practices.md).

---

## Next steps

- New users: [Your First Project](../getting-started/first-project.md)
- DSL details: [Language Reference](../reference/language-reference.md)
- YAML: [Configuration Guide](./configuration-guide.md)
