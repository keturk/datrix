# Event Contracts

**Last Updated:** April 16, 2026

Event contracts enforce **value-level invariants** on event payloads using `ensure` clauses. They complement the structural validation already performed by the semantic analyzer (EVT001-EVT006) by catching semantically invalid data **before** it propagates to subscribers.

---

## Problem

The semantic analyzer validates **structural** correctness: parameter counts match, parameter types match, topics exist, subscribers reference real events. But nothing prevents a publisher from emitting structurally valid yet semantically broken payloads:

```python
# Structurally correct, semantically wrong — negative amount
await producer.publish_order_placed(order_id, Decimal("-50.00"))
```

Service B receives `totalAmount = -50.00`, processes it, and corrupts downstream state. The bug originated in Service A but manifests in Service B — the hardest kind to debug in distributed systems.

---

## Solution

`ensure` clauses inside event declarations express value invariants on event parameters. Contracts are enforced at the **publisher** side — fail-fast at `emit`, before bad data propagates. Subscribers can trust the contract.

---

## Syntax

Ensure clauses live inside the `publish` event declaration body:

```datrix
service ecommerce.OrderService : version('1.0.0') {
    pubsub mq('config/pubsub.yaml') {
        topic OrderEvents {
            publish OrderPlaced(UUID orderId, Decimal totalAmount, Int itemCount) {
                ensure totalAmount > 0;
                ensure itemCount > 0;
                ensure orderId != null;
            }

            publish OrderCancelled(UUID orderId, String reason) {
                ensure reason.length > 0;
                ensure reason.length <= 500;
            }
        }

        subscribe OrderEvents from ecommerce.OrderService {
            on OrderPlaced(orderId, totalAmount, itemCount) { ... }
        }
    }
}
```

Events without contracts keep the existing semicolon-terminated syntax:

```datrix
publish OrderShipped(UUID orderId, DateTime shippedAt);
```

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Enforcement point | Publisher side (fail-fast at `emit`) | Datrix philosophy is fail-fast. If Service A emits invalid data, that's A's bug — catch it before propagation. Subscribers can trust the contract. |
| Placement | Inside the `publish` event declaration body | Eliminates scoping ambiguity — event names are unique within a topic but not across topics in the same pubsub block. Inline placement makes scope unambiguous. |
| Syntax | `ensure <expression>;` (semicolon-terminated) | Consistent with the rest of the Datrix grammar. Declarative style fits the DSL philosophy. |
| No separate `contract` block | `ensure` clauses live directly in the event body | A separate `contract` block at the pubsub level would require binding to events by name, creating ambiguity when two topics share an event name. Inline ensures avoid this entirely. |
| Language coverage | Python + TypeScript together | Both languages get every feature. Parallel stacks are a core invariant. |
| Static validation | Semantic analyzer checks field existence and expression types | Catches contract definition errors at parse time, not runtime. |
| Custom messages | Auto-generated from expression text | Audience is developers, not end users. Message includes event name, clause text, and actual values — sufficient for debugging. |
| Expression subset | Full expression language, no restrictions | `ensure` accepts any expression the grammar supports. The semantic validator only checks that identifiers resolve to event parameters and the expression is boolean-typed. |
| Redundant null checks | Warning (CTR003) | No silent fallbacks. If `orderId` is `UUID` (non-nullable), `ensure orderId != null` is a dead check — the type system already guarantees it. |
| Subscriber-side validation | Not needed | Subscribers already have a full `function_body` block — they can write any validation logic they want in the handler. No special syntax required. |
| Observability | Log + metric + throw | Contract violations are operational signals — log at ERROR level and emit a counter metric before raising. |

---

## Enforcement

Contracts are validated at two levels:

### 1. Static Analysis (Parse Time)

The semantic analyzer's `ContractValidator` (runs after `EventValidator` in Phase 6) checks:

| Code | Severity | Check |
|------|----------|-------|
| CTR001 | ERROR | `ensure` expression references an identifier not in the event's parameters |
| CTR002 | ERROR | `ensure` expression is not boolean-typed |
| CTR003 | WARNING | `ensure` null check on a non-nullable parameter (redundant — type system already guarantees it) |

### 2. Runtime Assertion (Generated Code)

Generated producer code calls a `_validate_{event_name}_contract(...)` function before serializing the payload. On violation:
1. Log at ERROR with event name, clause text, and actual values
2. Increment a Prometheus counter metric (`contract_violation_total`)
3. Raise `ContractViolationError` with event name, clause text, and actual parameter values

---

## Generated Code

### Python

```python
# contracts.py — generated from ensure clauses
import logging
from app.errors import ContractViolationError
from app.metrics import CONTRACT_VIOLATION_COUNTER

logger = logging.getLogger(__name__)

def _validate_order_placed_contract(
    order_id: UUID, total_amount: Decimal, item_count: int
) -> None:
    if not (total_amount > 0):
        logger.error(
            "contract_violation event=OrderPlaced clause='totalAmount > 0' totalAmount=%s",
            total_amount,
        )
        CONTRACT_VIOLATION_COUNTER.labels(event="OrderPlaced", clause="totalAmount > 0").inc()
        raise ContractViolationError(
            event="OrderPlaced",
            clause="totalAmount > 0",
            actual={"totalAmount": total_amount},
        )
    # ... additional clauses ...


# producer.py — contract validation before publish
async def publish_order_placed(
    self, order_id: UUID, total_amount: Decimal, item_count: int
) -> None:
    _validate_order_placed_contract(order_id, total_amount, item_count)
    payload = {"orderId": str(order_id), "totalAmount": str(total_amount), ...}
    await self._publish("OrderPlaced", payload)
```

### TypeScript

```typescript
// contracts.ts — generated from ensure clauses
import { ContractViolationError } from './errors';

export function validateOrderPlacedContract(
    orderId: string, totalAmount: number, itemCount: number
): void {
    if (!(totalAmount > 0)) {
        throw new ContractViolationError(
            'OrderPlaced',
            'totalAmount > 0',
            { totalAmount },
        );
    }
    // ... additional clauses ...
}
```

### Generated Tests

Contract test files verify:
- Valid payloads pass all clauses
- Each clause individually violated produces `ContractViolationError` with correct message and actual values

---

## Infrastructure Leveraged

Event contracts build on existing Datrix infrastructure:

| Component | Role |
|-----------|------|
| **Expression AST** | 16 expression node types in `datrix_common.datrix_model.expressions` — `ensure` clauses use the full expression language |
| **Event model** | `PubsubBlock` > `Topic` > `Event` > `Parameter` — ensure clauses attach directly to `Event` via `ensure_clauses: tuple[EnsureClause, ...]` |
| **Event validator** | EVT001-EVT006 validate structural event correctness — contract validation (CTR001-CTR003) runs after and extends this |
| **Transpilers** | Visitor-based `PythonTranspiler` and `TypeScriptTranspiler` — contract validation functions are transpiled from `ensure` expressions |

---

## AST Model

The `EnsureClause` node lives in `datrix_common.datrix_model.contract`:

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Stable name (e.g. `ensure_0`, `ensure_1`) |
| `condition` | `ExpressionNode` | Boolean expression over event parameters |

Owner: `Event.ensure_clauses: tuple[EnsureClause, ...]` in `datrix_common.datrix_model.pubsub`.

---

## Implementation Packages

| Package | What it provides |
|---------|-----------------|
| **datrix-language** | Grammar rule `ensure_clause` inside `event_declaration`; CST-to-AST transformer produces `EnsureClause` nodes |
| **datrix-common** | `EnsureClause` AST node (`datrix_model.contract`); `ContractValidator` (`semantic/validators/contract.py`) with CTR001-CTR003 |
| **datrix-codegen-python** | Template `messaging/contracts.py.j2` for validation functions; producer templates call validation before publish; `ContractViolationError` in generated error classes; contract test templates |
| **datrix-codegen-typescript** | Template `messaging/contracts.ts.j2` for validation functions; producer templates call validation before publish; `ContractViolationError` in generated error classes; contract test templates |

---

## Domain Example

See [iot-platform](../../examples/03-domains/iot-platform/system.dtrx) for a complete multi-service example with `ensure` clauses, showing publisher-side enforcement and generated contract tests.

---

## References

- [Language Reference — Events](../reference/language-reference.md#event-driven-messaging)
- [Syntax Reference — Event Contracts](../../../datrix-language/docs/reference/datrix-syntax-reference.md#event-contracts-ensure-clauses)
- [Grammar Reference — Ensure Clauses](../../../datrix-language/docs/reference/datrix-grammar.md#ensure-clauses-event-contracts)
- [Validator Reference — CTR rules](../../../datrix-language/docs/reference/datrix-validators.md#contract-validator-ctr)
- [AST Nodes — EnsureClause](../../../datrix-language/docs/reference/datrix-ast-nodes.md#ensureclause-ast--datrix_commondatrix_modelcontract)
- [Architecture Overview](../architecture/architecture-overview.md) — mentions event contracts as a key feature
