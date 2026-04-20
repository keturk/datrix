# Specification-Level Testing

**Last Updated:** April 16, 2026

---

## Overview

Datrix supports **specification-level tests** — `test` blocks at the service level that verify business logic. Unlike auto-generated tests (which verify wiring, structure, types, and routing), spec tests verify **user-defined behavior**: lifecycle hooks, computed fields, validation rules, entity functions, and event emission.

Spec tests use the same imperative syntax as handlers and jobs. They run against a real deployed service with a real database — `.create()` really creates, `.save()` really persists, lifecycle hooks fire naturally through the service layer. No fakes, no in-memory substitutes.

### Test category separation

```
tests/
  unit/               <-- auto-generated, no DB (structure, types, factories)
  integration/        <-- auto-generated, with DB (repositories, relationships)
  spec/               <-- user-authored, with DB (business logic scenarios)
```

---

## Syntax

A `test` block is a **service member** (alongside `rdbms`, `rest_api`, `pubsub`, etc.):

```datrix
service library.BookService : version('1.0.0') {
    rdbms db('config/book-service/datasources.yaml') {
        entity Book extends BaseEntity {
            String(200) title;
            DateTime dueDate;
            BookStatus status = BookStatus.Available;

            String displayTitle := "[{status}] {title}";

            validate {
                if (title.trim().isEmpty()) ValidationError("Title is required");
            }

            beforeUpdate {
                if (dueDate < utcNow() && status == BookStatus.Available)
                    status = BookStatus.Overdue;
            }

            afterCreate {
                emit BookCreated(id, title);
            }
        }
    }

    test("overdue books are flagged on update") {
        #Book book = db.Book.create({
            dueDate: today().subtractDays(1),
            status: BookStatus.Available
        });
        book.title = "Trigger Update";
        book.save();
        assert book.status == BookStatus.Overdue;
    }

    test("future books stay available on update") {
        #Book book = db.Book.create({
            dueDate: today().addDays(7),
            status: BookStatus.Available
        });
        book.title = "Trigger Update";
        book.save();
        assert book.status == BookStatus.Available;
    }

    test("computed displayTitle is correct") {
        #Book book = db.Book.create({
            title: "Domain-Driven Design",
            status: BookStatus.Available
        });
        assert book.displayTitle == "[Available] Domain-Driven Design";
    }

    test("validation rejects empty title") {
        assert throws(() => db.Book.create({ title: "" }), ValidationError("Title is required"));
    }

    test("afterCreate emits BookCreated") {
        #Book book = db.Book.create({ title: "New Book" });
        assert emitted(BookCreated(book.id, book.title));
    }
}
```

---

## Assertions

### `assert`

The only new statement type. Boolean assertion that fails the test if the expression evaluates to false.

```datrix
assert book.status == BookStatus.Overdue;
assert book.displayTitle == "[Available] Domain-Driven Design";
assert order.total > 0;
```

Multiple assertions per test are allowed.

### `throws(lambda, error)`

Test-context builtin. Verifies that a call raises an error. The first argument is a lambda (deferred evaluation) so the call can be caught.

```datrix
assert throws(() => db.Book.create({ title: "" }), ValidationError("Title is required"));
```

### `emitted(event)`

Test-context builtin. Verifies that an event was emitted during the test.

```datrix
assert emitted(BookCreated(book.id, book.title));
```

The capture mechanism integrates with each language's existing event infrastructure:

| Language | Mechanism |
|----------|-----------|
| **Python** | Producer spy replaces the real producer singleton. The spy implements the same typed interface but appends events to an internal list instead of publishing to a broker. |
| **TypeScript** | Wildcard listener on `EventEmitter2` captures all emitted events into a list. |

The spy is reset before each test — every test starts with an empty event list.

---

## Design rules

| Rule | Description |
|------|-------------|
| **Real execution** | `.create()` persists, `.save()` updates, lifecycle hooks fire naturally through the service layer. No fake persistence, no mocks. |
| **Standard DSL** | `#Type` declarations, object literals, method calls, field access, comparisons — the same expression syntax used in lifecycle hooks and functions. |
| **Self-contained tests** | Each test sets up its own data. No shared setup mechanism across tests. |
| **Unique descriptions** | Test descriptions must be unique within the same service (validator TST009 enforces this). |
| **Cross-block references** | Tests live at the service level and can reference entities from any rdbms block in that service (e.g., `db1.Book` and `db2.Author`). |

---

## What spec tests exercise

Spec tests are designed for verifying **behavioral logic** declared in the DSL:

| Behavior | Example test |
|----------|-------------|
| **Lifecycle hooks** (`beforeCreate`, `afterCreate`, `beforeUpdate`, etc.) | Create/update an entity and assert the hook's side effects |
| **Computed fields** (`:=` expressions) | Create an entity and assert the computed field value |
| **Validation rules** (`validate { }`) | Assert `throws` on invalid input |
| **Entity functions** (`fn` on entities) | Call the function and assert the return value |
| **Event emission** (`emit` in hooks) | Assert `emitted(EventName(...))` after an operation |

Spec tests do **not** replace auto-generated tests. Auto-generated tests verify wiring (structure, types, factories, routing). Spec tests verify that user-defined business logic works correctly through real execution.

---

## Transpilation

Each `test("description")` block becomes one test function in the generated output:

| Target | Output file | Test framework |
|--------|-------------|----------------|
| **Python** | `tests/spec/test_{service_name}_spec.py` | pytest (async) |
| **TypeScript** | `test/spec/{service-name}.spec.ts` | Jest |

### Python transpilation

| DSL | Python |
|-----|--------|
| `assert expr` | `assert transpiled_expression` |
| `throws(() => call, error)` | `with pytest.raises(ErrorType, match=message): call` |
| `emitted(BookCreated(id, title))` | `assert event_spy.has("BookCreated", book_id=id, title=title)` |

### TypeScript transpilation

| DSL | TypeScript |
|-----|-----------|
| `assert expr` | `expect(transpiled_expression).toBe(true)` |
| `throws(() => call, error)` | `expect(() => call).toThrow(message)` |
| `emitted(BookCreated(id, title))` | `expect(eventSpy.has('BookCreated', { bookId: id, title: title })).toBe(true)` |

---

## Semantic validation

The `TestValidator` (Phase 6) enforces correctness of test block contents:

| Code | Severity | Rule |
|------|----------|------|
| TST001 | error | Entity construction references unknown entity (block-qualified name not found in service) |
| TST002 | error | Object literal field not found on entity |
| TST003 | error | Object literal field type mismatch |
| TST004 | error | Method call references unknown function on entity |
| TST005 | error | `assert` expression references unknown field on entity |
| TST006 | error | `emitted()` references unknown event |
| TST007 | error | `emitted()` parameter count mismatch with event declaration |
| TST008 | error | `throws()` missing lambda as first argument |
| TST009 | error | Duplicate test description within the same service |

---

## Best practices

1. **One scenario per test** — Each test should verify one specific behavior. Use the description to state what is being verified.

2. **Descriptive test names** — The description string appears in test runner output. Write it as a behavior statement:
   - Good: `"overdue books are flagged on update"`
   - Avoid: `"test book update"`

3. **Assert the effect, not the mechanism** — Assert the observable result (field values, raised errors, emitted events), not internal implementation details.

4. **Use `throws` for validation** — When testing that invalid input is rejected, use `throws(() => operation, ExpectedError("message"))`.

5. **Use `emitted` for events** — When testing that a lifecycle hook emits an event, use `emitted(EventName(params))` rather than inspecting internal state.

6. **Cover all trigger types** — For entities with lifecycle hooks, computed fields, and validation rules, write spec tests that exercise each trigger through real operations.

---

## Tutorial example

See `examples/02-features/06-advanced-language-features/advanced-flow-control/` for a complete example with lifecycle hooks, computed fields, validation rules, and `test` blocks exercising all trigger types.
