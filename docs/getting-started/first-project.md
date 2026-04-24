# Your First Project

**Last updated:** April 24, 2026

Walkthrough for a minimal **library** service with one entity and a REST API—the same shape as [`examples/02-features/01-core-data-modeling/rest-api`](../../examples/02-features/01-core-data-modeling/rest-api/).

**Time:** about 15–20 minutes (plus installs).

---

## Overview

You will:

- Define `library.BookService` with a named RDBMS block `bookDb`, a `Book` entity, and a `rest_api`.
- Point the `system` block at YAML under `config/`.
- Validate and generate Python (FastAPI) output, then run the service.

**Fastest path:** copy the folder [`examples/02-features/01-core-data-modeling/rest-api`](../../examples/02-features/01-core-data-modeling/rest-api/) and skip to [Validate and generate](#step-4-validate-and-generate).

---

## Step 1: Project layout

Tutorial-style projects keep `.dtrx` files at the **project root** next to `config/` (see [`examples/README.md`](../../examples/README.md)). Create:

```text
my-library/
├── system.dtrx
├── book-service.dtrx
└── config/
    ├── system-config.yaml
    ├── registry.yaml
    ├── gateway.yaml
    ├── observability.yaml
    └── book-service/
        ├── book-service-config.yaml
        ├── registration.yaml
        ├── resilience.yaml
        └── datasources.yaml
```

Copy the YAML files from [`examples/02-features/01-core-data-modeling/rest-api/config/`](../../examples/02-features/01-core-data-modeling/rest-api/config/) so paths and profile keys match what the generators expect.

---

## Step 2: Entry point (`system.dtrx`)

```datrix
include 'book-service.dtrx';

system library.System : version('1.0.0') {
    config('config/system-config.yaml');
    registry('config/registry.yaml');
    gateway('config/gateway.yaml');
    observability('config/observability.yaml');
}
```

---

## Step 3: Service (`book-service.dtrx`)

This matches the reference tutorial (comments optional in your own tree):

```datrix
service library.BookService : version('1.0.0'), description('Book management service') {

    config('config/book-service/book-service-config.yaml');
    registration('config/book-service/registration.yaml');
    discovery { }
    resilience('config/book-service/resilience.yaml');

    enum BookStatus {
        Available,
        CheckedOut,
        Reserved,
        Maintenance
    }

    enum BookFormat {
        Hardcover,
        Paperback,
        eBook,
        Audiobook
    }

    rdbms bookDb('config/book-service/datasources.yaml') {

        abstract entity BaseEntity {
            UUID id : primaryKey, server = uuid();
            UDateTime createdAt : server = utcNow();
            UDateTime updatedAt : server = utcNow();
        }

        entity Book extends BaseEntity {
            String(200) title : trim;
            String(20) isbn;
            String(100) author : trim;
            Int publicationYear;
            BookStatus status = BookStatus.Available;
            BookFormat format = BookFormat.Hardcover;
        }
    }

    rest_api BookServiceAPI : basePath("/api/v1") {
        resource bookDb.Book;
    }
}
```

### Field attributes (short list)

- **`server`** — server-managed field (system-populated; not accepted on create/update APIs). Use the `server` modifier in the field’s modifier list after `:` (for example `UUID id : primaryKey, server = uuid();` or `UDateTime createdAt : server = utcNow();`).
- **`trim`** — trim string input.
- **`unique`** — unique constraint.
- **`index`** — index (including FKs).
- **`hidden`** — omit from API responses.
- **`immutable`** — on create only, not updates.

Details: [Language Reference](../reference/language-reference.md).

---

## Step 4: Install CLI and generators

```bash
pip install datrix-cli datrix-codegen-python datrix-codegen-sql datrix-codegen-docker
```

Install only what you need; the CLI discovers generator plugins at runtime.

---

## Step 5: Validate and generate

From the project root (or repo root with adjusted paths):

```bash
datrix validate .
datrix generate --source system.dtrx --output ./generated --profile test
```

`language` and `hosting` come from `config/system-config.yaml` for the active profile (default CLI profile is **`test`**). To override for one run:

```bash
datrix generate --source system.dtrx --output ./generated --language python --hosting docker
# Short flags: --language / -L , --hosting / -H , --platform / -P
```

---

## Step 6: Generated layout (Python)

For `library.BookService`, the Python package directory is derived from the qualified name (e.g. `library.BookService` → `library_book_service`):

```text
generated/
└── library_book_service/
    ├── src/
    │   └── library_book_service/
    │       ├── main.py
    │       ├── models/
    │       ├── routes/
    │       ├── schemas/
    │       └── ...
    ├── sql/
    └── pyproject.toml
```

SQL migrations and Docker Compose (when hosting is Docker) are emitted alongside the service. Exact files depend on your spec and config.

---

## Step 7: Run the app

```bash
cd generated/library_book_service
pip install -e .
# or: pip install -r requirements.txt when that is what the project emits
uvicorn library_book_service.main:app --reload --host 0.0.0.0 --port <port>
```

Use the HTTP port from generated config or Compose for your profile. Open **`/docs`** for OpenAPI (FastAPI).

---

## Step 8: Call the API

CRUD paths are generated from the `Book` resource and `basePath` (exact paths appear in `/docs`). A typical create:

```bash
curl -X POST "http://127.0.0.1:<port>/api/v1/books" \
  -H "Content-Type: application/json" \
  -d "{\"title\":\"Datrix Guide\",\"isbn\":\"9780000000000\",\"author\":\"You\",\"publicationYear\":2026,\"status\":\"Available\",\"format\":\"Hardcover\"}"
```

---

## Next steps

1. Explore focused feature examples under [`examples/02-features/`](../../examples/02-features/) (relationships, events, CQRS, GraphQL, jobs, and more).
2. Study full domains under [`examples/03-domains/`](../../examples/03-domains/).
3. Read [Writing Datrix Applications](../guide/writing-datrix-applications.md) and the [Configuration Guide](../guide/configuration-guide.md).

---

## Troubleshooting

**Validation or path errors** — `include` and `config('...')` paths are relative to the **file** that contains them; keep `config/` aligned with those strings.

**Imports / module not found** — Run from the generated service root and install the package (`pip install -e .`) so `library_book_service` is on `PYTHONPATH`.

**Wrong language or platform** — Check the active profile in `system-config.yaml` and per-service YAML; use `--language`, `--hosting`, and `--platform` only when you intentionally override.

Full CLI options: [`datrix-cli/docs/commands.md`](../../datrix-cli/docs/commands.md).
