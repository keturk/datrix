# Pack: DSL Features — Documentation, Enums, Work Lifecycle, Extern Services, Grammar

**Read when:** you touch DSL comments/doc channels, enum keywords or enum wire/stored values, `work { }` blocks, `extern service`, or need the `.dtrx` grammar snapshot.
**Not for:** generation of the emitted code itself ([codegen-engine.md](./codegen-engine.md)).
**Core map:** [architecture-cheat-sheet.md](../architecture-cheat-sheet.md)

## DSL Comment Preservation, Two-Channel Documentation

[Decision 39](../architecture-overview.md#decision-39-dsl-comment-preservation-and-two-channel-generated-documentation-adopted) — Adopted.

Every comment is a **source comment**; only `///` and `/** … */` is **published documentation** (OpenAPI summary/description, schema field description, GraphQL descriptions, README, and the database comment — `COMMENT ON TABLE/COLUMN`, migrated as `set_comment`). Publication is opt-in and doc-vs-note is a function of comment text, not a grammar token. Author text is sanitized per language (planted-hostile-text test). A documented construct documents on every language target; an unrealized surface is a counted gap. A documentation-only edit regenerates its service but never plans a migration. Python's docstring is a published surface, so an unmarked note is an ordinary comment. Gate: documentation-realization parity gate, baseline `datrix/scripts/config/documentation-coverage-baseline.json`.

## Enum Keyword Classification

[Decision 40](../architecture-overview.md#decision-40-enum-keyword-classification-and-generated-classifiers-adopted) — Adopted.

`keywords('PU','IT')` on an enum value yields generated `equalsKeyword`/`containsKeyword` classifiers, realized per enum-emitting language. Enum-value attributes are a closed set (`ENUM001`–`ENUM006`); a no-match error discloses neither input nor vocabulary; keywords never reach storage/DDL.

## Enum Wire and Stored Values

[Decision 56](../architecture-overview.md#decision-56-enum-wire-and-stored-values--one-rule-each-both-shared-adopted) — Adopted.

- **Wire** (what services emit and accept, client types, `@IsEnum`, keyword classifier): the declared `value('…')`, else the raw DSL member name (`PendingReview`). **Stored** (database column label): the declared `value('…')`, else the snake_case name (`pending_review`); an integer `value(1)` is the text `'1'`, and every emitted enum literal is a string literal. One rule each, in `datrix_common.datrix_model.enum_literals`, shared by every language and engine.
- `EnumLiteralSetValidator` (`ENUM008`–`ENUM011`) rejects empty, NUL, over-63-byte, or duplicate stored/wire values. A changed stored label is a migration (`ChangeKind.ENUM_VALUE_RELABELED` → `relabel_enum_value`; Python renders a guarded `ALTER TYPE … RENAME VALUE`). An unknown stored label fails on read without echoing it. TypeScript binds persisted columns to a generated `<Enum>Storage` (`EnumStoredType`), so a TypeScript consumer of a value-less enum now sees `PendingReview`, not `pending_review` (breaking wire change).

## Declared Work Lifecycle

An entity whose rows record a unit of work declares a `work { }` block (entity *and* trait member; an entity's own block overrides an inherited one): the state field, in-progress (`inFlight`, a list) and interrupted members, **who performs the work** (`owner`), and what may recover a stranded row (`onOrphan`). Before it, a generator inferred this from enum member *spelling* and emitted a destructive startup `UPDATE` that destroyed live records on a cross-service queue table.

- No generator branches on a user enum's member values: `check-enum-value-literals.ps1` — AST scan of every `datrix-codegen-*`/`datrix-common`/`datrix-language` `src/`, hard zero, no exemption file, self-testing.
- A destructive statement is emitted only where declared; the emitter names only columns the resolved contract proves exist (`WRK002`/`WRK006`/`WRK007`); work performed elsewhere is never recovered locally (`WRK008` rejects `owner: external` with `onOrphan: failAtStartup`).
- The contract is language-neutral (`datrix_model/work.py` in `datrix-common`); python realizes `onOrphan: failAtStartup`; any other target realizes it or carries a counted `capability_gaps` row. The stored value is `enum_member_stored_literal`.

Syntax and diagnostics: [datrix-syntax-reference.md — Work Contracts](../../../../datrix-language/docs/reference/datrix-syntax-reference.md#work-contracts-work--).

## Paginated Responses: `Page<T>`, `PageRequest`, `.page(...)`

A route pages exactly when it is a `GET` returning **`Page<T>`** (`endpoint_is_paginated` in `datrix_common.datrix_model.api`), takes one **`PageRequest`** (a builtin value struct: `Int offset`, `Int limit`, always counted in rows) and ends its chain with the **`.page(request)`** query terminal. A `Page<T>` serializes as `{items, total, offset, limit}` (`PAGE_MEMBERS` in `datrix_common.datrix_model.pagination`, read by every serializer, decoder and template); `offset`/`limit` are the window the server applied.

- **Not a collection.** `PageType` is deliberately not a `CollectionKind`: a page is not iterable rows, so it cannot flow through the sites that treat a `CollectionType` as rows. Every resolver implements `TypeVisitor.visit_page`; a target without one cannot instantiate.
- **One terminal, one count.** `.page` lowers once, in `datrix_codegen_common.algorithms.entity_query_chain.transpile_page_terminal`; each language supplies syntax only. The count runs over the same chain with order, offset and limit removed, so it carries every `where`/`whereIn`/`fulltext`/tenant predicate the items carry and can never see a row the items could not (Python `page_query`, TypeScript `getResultAndCount`).
- **One bound.** The offset/limit pair is bound from `pagination_query_param_rows`, which carries `minimum`/`maximum`/`default` from `datrix.foundation` (`MAX_PAGE_SIZE`, `DEFAULT_PAGE_SIZE`); out-of-range input is refused, never clamped. A backend whose declared position is a page index converts at its handler boundary (`PageRequestBinding`).
- **Derived lists page too.** The resource `list` operation, the empty-body `LIST`/`LIST_BY_FIELD` derivations, view lists and nested relationship lists all produce `Page<E>`; an empty-body list declared `Array<E>` is `API023`.
- **Clients.** A service-to-service call sends its `PageRequest` in the callee's declared pair (`EndpointContract.page_window`) and decodes the envelope; a browser/mobile client types the response `Page<T>`, and its `PagedBinding` loads one page per request and numbers pages from `total` (see [frontend-clients](./frontend-clients.md)).

Diagnostics `API020`–`API023`, `UI042`, `UI053`; syntax: [datrix-syntax-reference.md — Windows and pages](../../../../datrix-language/docs/reference/datrix-syntax-reference.md#windows-and-pages).

## Extern Services

Contract-only declarations for external libraries/tools Datrix does not generate; consumed via `uses`.

- **Container kinds:** `system`, `module`, `service`, `shared`, `extern service`. The user builds and deploys the implementation.
- **Allowed members:** `struct`, `enum`, `rest_api` (signature-only), `errors`, `auth`, `health`. No infrastructure blocks.
- **Config:** `deployment: container` (image + port, compose entries generated) or `deployment: external` (remote URL, no deployment artifacts).
- **Generated per consuming service:** typed HTTP client, request/response models, error classes, contract validation.
- **AST:** `ExternService` in `datrix_common.datrix_model.extern_service`, on `Application.extern_services`. `uses` resolves shared block → extern service → regular service.

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
