# Pack: DSL Features — Documentation, Enums, Work Lifecycle, Extern Services, Grammar

**Read when:** you touch DSL comments/doc channels, enum keywords or enum wire/stored values, `work { }` blocks, `extern service`, or need the `.dtrx` grammar snapshot.
**Not for:** generation of the emitted code itself ([codegen-engine.md](./codegen-engine.md)).
**Core map:** [architecture-cheat-sheet.md](../architecture-cheat-sheet.md)

**Where DSL facts are tested.** A diagnostic is a `// @expect <CODE>.<variant>` annotation on the fixture line that provokes it; every catalog variant has a per-code fixture under `datrix-semantic/tests/fixtures/diagnostics/` (a census test holds that). A documented example is a `datrix` docs fence, parsed, and analyzed when it is a whole application. An annotation is a source comment, never published documentation.

## DSL Comment Preservation, Two-Channel Documentation

[Decision 39](../architecture-overview.md#decision-39-dsl-comment-preservation-and-two-channel-generated-documentation-adopted) — Adopted.

Every comment is a **source comment**; only `///` and `/** … */` is **published documentation** (OpenAPI summary/description, schema field description, GraphQL descriptions, README, and the database comment — `COMMENT ON TABLE/COLUMN`, migrated as `set_comment`). Publication is opt-in and doc-vs-note is a function of comment text, not a grammar token. A published run that reaches no model node -- detached by a blank line, or sitting against a construct that carries no documentation -- is a located parse error (`datrix_language.transformers.doc_comments`); an unclaimed `//` note is dropped silently by design. Author text is sanitized per language (planted-hostile-text test). A documented construct documents on every language target; an unrealized surface is a counted gap. A documentation-only edit regenerates its service but never plans a migration. Python's docstring is a published surface, so an unmarked note is an ordinary comment. Gate: documentation-realization parity gate, baseline `datrix/scripts/config/documentation-coverage-baseline.json`.

## Enum Keyword Classification

[Decision 40](../architecture-overview.md#decision-40-enum-keyword-classification-and-generated-classifiers-adopted) — Adopted.

`keywords('PU','IT')` on an enum value yields generated `equalsKeyword`/`containsKeyword` classifiers, realized per enum-emitting language. Enum-value attributes are a closed set (`ENUM001`–`ENUM006`); a no-match error discloses neither input nor vocabulary; keywords never reach storage/DDL.

## Enum Wire and Stored Values

[Decision 56](../architecture-overview.md#decision-56-enum-wire-and-stored-values--one-rule-each-both-shared-adopted) — Adopted.

- **Wire** (what services emit and accept, client types, `@IsEnum`, keyword classifier): the declared `value('…')`, else the raw DSL member name (`PendingReview`). **Stored** (database column label): the declared `value('…')`, else the snake_case name (`pending_review`); an integer `value(1)` is the text `'1'`, and every emitted enum literal is a string literal. One rule each, in `datrix_common.datrix_model.enum_literals`, shared by every language and engine. A `.dseed` enum cell names the DSL member; a seed writer that binds straight to the column (Python's named-placeholder statements and `@lookup` matches) binds that member's stored label, never the name as written.
- `EnumLiteralSetValidator` (`ENUM008`–`ENUM012`) rejects empty, NUL, over-63-byte, or duplicate stored/wire values, and a value holding a code point `hidden_in_source` flags (`ENUM012`: an enum value is a machine identifier on every target, so no SQL or source literal of it needs an escape). A changed stored label is a migration (`ChangeKind.ENUM_VALUE_RELABELED` → `relabel_enum_value`; Python renders a guarded `ALTER TYPE … RENAME VALUE`). An unknown stored label fails on read without echoing it. TypeScript binds persisted columns to a generated `<Enum>Storage` (`EnumStoredType`), so a TypeScript consumer of a value-less enum now sees `PendingReview`, not `pending_review` (breaking wire change).

## Declared Work Lifecycle

An entity whose rows record a unit of work declares a `work { }` block (entity *and* trait member; an entity's own block overrides an inherited one): the state field, in-progress (`inFlight`, a list) and interrupted members, **who performs the work** (`owner`), and what may recover a stranded row (`onOrphan`). Before it, a generator inferred this from enum member *spelling* and emitted a destructive startup `UPDATE` that destroyed live records on a cross-service queue table.

- No generator branches on a user enum's member values: `check-enum-value-literals.ps1` — AST scan of every `datrix-codegen-*`/`datrix-common`/`datrix-language` `src/`, hard zero, no exemption file, self-testing.
- A destructive statement is emitted only where declared; the emitter names only columns the resolved contract proves exist (`WRK002`/`WRK006`/`WRK007`); work performed elsewhere is never recovered locally (`WRK008` rejects `owner: external` with `onOrphan: failAtStartup`).
- The contract is language-neutral (`datrix_model/work.py` in `datrix-common`); python realizes `onOrphan: failAtStartup` with the statements the block's SQL dialect renders (`work_recovery_for` in the kernel, never SQL of its own); any other target realizes it or carries a counted `capability_gaps` row. The stored value is `enum_member_stored_literal`.

Syntax and diagnostics: [datrix-syntax-reference.md — Work Contracts](../../../../datrix-language/docs/reference/datrix-syntax-reference.md#work-contracts-work--).

## Paginated Responses: `Page<T>`, `PageRequest`, `.page(...)`

A route pages exactly when it is a `GET` returning **`Page<T>`** (`endpoint_is_paginated` / `route_is_paginated` in `datrix_common.datrix_model.api`), takes one **`PageRequest`** (a builtin value struct: `Int offset`, `Int limit`, always counted in rows) and ends its chain with the **`.page(request)`** query terminal. A `Page<T>` serializes as `{items, total, offset, limit, maxLimit}` (`PAGE_MEMBERS` in `datrix_common.datrix_model.pagination`, read by every serializer, decoder and template through the `PAGE_WIRE` template global of `datrix_codegen_common.generation.page_template_globals`); `offset`/`limit` are the window the server applied and `maxLimit` the largest size the profile accepts (`resolve_page_size_bounds`), written as a per-profile constant of each backend's page schema (`PAGE_MAX_LIMIT`).

- **Not a collection.** `PageType` is deliberately not a `CollectionKind`: a page is not iterable rows, so it cannot flow through the sites that treat a `CollectionType` as rows. Every resolver implements `TypeVisitor.visit_page`; a target without one cannot instantiate.
- **One terminal, one count.** `.page` lowers once, in `datrix_codegen_common.algorithms.entity_query_chain.transpile_page_terminal`; each language supplies syntax only. The count runs over the same chain with order, offset and limit removed, so it carries every `where`/`whereIn`/`fulltext`/tenant predicate the items carry and can never see a row the items could not (Python `page_query`, TypeScript `getResultAndCount`).
- **One bound.** The offset/limit pair is bound from `pagination_query_param_rows`, which carries `minimum`/`maximum`/`default` from `datrix.foundation` (`MAX_PAGE_SIZE`, `DEFAULT_PAGE_SIZE`); out-of-range input is refused, never clamped. A backend whose declared position is a page index converts at its handler boundary (`PageRequestBinding`).
- **Derived lists page too.** The resource `list` operation, the empty-body `LIST`/`LIST_BY_FIELD` derivations, view lists and nested relationship lists all produce `Page<E>`; an empty-body list declared `Array<E>` is `API023`.
- **Clients.** A service-to-service call sends its `PageRequest` in the callee's declared pair (`EndpointContract.page_window`) and decodes the envelope; a browser/mobile client types the response `Page<T>`, and its paged binding loads one page per request and numbers pages from `total` (see [frontend-clients](./frontend-clients.md)). A client may request a size (the second member of the backend's pair); the server bounds it and refuses an out-of-range one.
- **Sort and filter: one derivation.** A route's list query rows are `datrix_codegen_kernel.generation.list_query.derive_list_query_rows` over the DSL facts of `datrix_common.datrix_model.list_query.derived_list_fields`: its filters are its declared optional query parameters plus, on a derived resource `list`, one row per `filterable` field; its sort (`sortBy`/`sortOrder`, single column) is present on a resource list whose entity has a `sortable` field and on a custom `Page<E>` route declaring `sortable(field, ...)` (`API027`). Query keys are the declared query rule (`datrix_common.datrix_model.wire_naming.query_wire_name`, camelCase) on every backend; `sortBy` values are body wire names on every backend and `sortOrder` is `asc`/`desc` (default `asc`). Every backend binds `route_query_wire_keys` exactly (each backend's seam test and the `query-keys` parity rows), binds the sort as an enumerated value so any other is a `request-validation` problem (`location=query`, code `invalid`), translates `sortBy` through a generated allow-map from wire value to column, and appends the primary key as the last order key when a field is requested. On a custom route the page terminal orders by the requested field, then the chain's own `orderBy`, then the primary key (`datrix_codegen_common.transpiler.page_sort`); a query held in a variable takes the `orderBy` steps of the chain that pages it (`return q.orderBy(...).page(page);`) as those tie-breakers, and ordering it in any earlier statement is refused on every language. A row whose name shares its words with a pagination or sort parameter is `API028`.
- **Pages of a struct.** A route answering `Page<S>` for a struct `S` ends its entity chain with `.page(request, row => S {...})`: the query, the count and the sort are the entity chain's, and the mapper builds one `S` per row of the window. The facts live in `datrix_common.datrix_model.page_projection` (the returned terminals, the mapper, the chain's entity, the fields a struct-literal mapper copies from a column unchanged); `page_element_entity` answers the chain's entity for a `Page<S>` route, so the sort derivation and every renderer of it are the entity page's. Analysis refuses a missing, misplaced, mis-shaped or mis-typed mapper (`API022`) and a sort key the mapper does not copy unchanged from its column (`API027`). `transpile_page_terminal` lowers the request and `page_terminal_mapper` hands the mapper to the language, which applies it to the page's items after the query ran (Python `Page.with_items` over a comprehension, TypeScript `mapPage`). Clients see a page of a struct like any other `Page<T>`.
- **Read shape.** The client contract records each route's `ReadShape` (`classify_client_read_shape`): `PAGED`, `LIST` (`Array<T>`), `SINGLE`, or `MUTATION` for every write; no renderer re-derives it.

Diagnostics `API020`–`API023`, `API027`, `API028`, `UI042`, `UI053`; syntax: [datrix-syntax-reference.md — Windows and pages](../../../../datrix-language/docs/reference/datrix-syntax-reference.md#windows-and-pages).

## Extern Services

Contract-only declarations for external libraries/tools Datrix does not generate; consumed via `uses`.

- **Container kinds:** `system`, `module`, `service`, `shared`, `extern service`. The user builds and deploys the implementation.
- **Allowed members:** `struct`, `enum`, `rest_api` and `graphql_api` (signature-only; a GraphQL operation's document is derived from its signature), `errors`, `auth`, `health`. No infrastructure blocks.
- **Config:** `deployment: container` (image + port, compose entries generated) or `deployment: external` (remote URL, no deployment artifacts).
- **Generated per consuming service:** typed HTTP client, request/response models, error classes, contract validation.
- **AST:** `ExternService` in `datrix_common.datrix_model.extern_service`, on `Application.extern_services`. `uses` resolves shared block → extern service → regular service.

## Embedded Fields and Amounts

- **`: embedded`** on a struct-typed entity field is lowered once by semantic analysis (`datrix_semantic.embedded_fields`, after inheritance and FK synthesis, before index resolution and type checking): the declared field is replaced, in its position, by one ordinary field per struct member (`priceMinor`, `priceCurrency`, marked `Field.embedded_in` / `embedded_member`) and a computed field of the declared name rebuilds the struct. Every target, the migration snapshot and seeds therefore see ordinary typed columns; nothing target-side knows `embedded`. Misuse is `EMB001`.
- **`Amount`** (`datrix.billing`, with `CurrencyUnits`, `RoundingMode`, `SafeMinor`) is a stdlib struct, not a builtin object: its arithmetic is DSL code every language transpiles. Mixed currencies throw at run time and are `AMT001` where both are literal.

## DSL Grammar Snapshot (`.dtrx`)

Detail: [language-reference.md](../../reference/language-reference.md), [datrix-syntax-reference.md](../../../../datrix-language/docs/reference/datrix-syntax-reference.md).

| Layer | Constructs |
|-------|------------|
| File structure | `include`, `from X import Y`, `system`, `module`, `service`, `extern service` |
| Declarations | `entity`, `abstract entity`, `trait`, `enum`, `struct`, `const`, `fn` |
| Field features | Types, optional (`?`), sized (`String(200)`), collections (`Array<T>`, `Map<K,V>`, `Set<T>`), modifiers (`: unique, indexed, immutable, server, …`), defaults (`= expr`). Server-managed fields use the **`server`** modifier (`UUID id : primaryKey, server = uuid();`) — **no** `@` prefix on field types |
| Catalog types | `scalar Name : BaseType { constraints… }` |
| Work contracts | `work { state; inFlight; interrupted; owner; onOrphan; … }` |
| Errors | `exceptions { … }` with `Name : status(N), message("…");` and optional structured fields |
| Decorators | Endpoint decorators (`@retry`, `@rateLimit`, `@cache`, `@produces`, `@crossTenant`) are `@`-prefixed; field modifiers are not |
| Comments | `//` and `/* … */` anywhere (grammar `extras`); `///` and `/** … */` are doc comments, the opt-in published channel |
