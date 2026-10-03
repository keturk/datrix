# Identity Configuration — application (test)

This document describes the identity provider configuration for the **application** application
in the **test** deployment environment.

> **Generated file — do not edit manually.** Regenerate by running `datrix generate`.

---

## Providers

### identity

| Field | Value |
|---|---|
| Provider Type | `zitadel` |
| Audience | `customer` |
| Mode | `platformManaged` |
| Credential | `jwt` |
| Issuer | `http://localhost:8085` |
| Revocation Mode | `none` |
| Public Client Metadata | `identity-client-identity.test.json` |

#### Revocation Guarantee

Tokens remain valid until their expiry time (TTL). Revoked credentials are NOT invalidated immediately — the revocation window equals the token TTL.

#### External Prerequisites (Manual Setup Required)

The following infrastructure must be provisioned manually before this provider is operational.
Datrix generates client code and configuration; it does not provision the provider itself.

- Zitadel instance running and reachable at the configured origin.
- Project and OIDC application exist in the Zitadel instance.
- Redirect URIs registered on the OIDC application.

### platform

| Field | Value |
|---|---|
| Provider Type | `zitadel` |
| Audience | `machine` |
| Mode | `platformManaged` |
| Credential | `jwt` |
| Issuer | `http://localhost:8085` |
| Revocation Mode | `none` |

#### Revocation Guarantee

Tokens remain valid until their expiry time (TTL). Revoked credentials are NOT invalidated immediately — the revocation window equals the token TTL.

#### External Prerequisites (Manual Setup Required)

The following infrastructure must be provisioned manually before this provider is operational.
Datrix generates client code and configuration; it does not provision the provider itself.

- Zitadel instance running and reachable at the configured origin.
- Project and OIDC application exist in the Zitadel instance.
- Redirect URIs registered on the OIDC application.

### customerKeys

| Field | Value |
|---|---|
| Provider Type | `apiKey` |
| Audience | `customer` |
| Mode | `self` |
| Credential | `apiKey` |
| Key Header | `X-Customer-Api-Key` |
| Key Store Service | `ecommerce.UserService` |
| Verify Route | `/internal/identity/api-keys/customerKeys/verify` |

#### Revocation Guarantee

Every request presenting a key is verified against the owning service's key store with exactly one lookup; no verifying service caches the result. Deactivating, expiring or deleting a key takes effect on the next request.

#### External Prerequisites (Manual Setup Required)

The following infrastructure must be provisioned manually before this provider is operational.
Datrix generates client code and configuration; it does not provision the provider itself.

- The owning service, RDBMS block and entity declared in the provider's apiKey { } config (store/storeBlock/entity) exist and are reachable.
- Every service admitting this provider on a route declares the owning service in its discovery { } block.
- The application issues raw keys with Crypto.randomBytes(32) and stores only Crypto.sha256(rawKey) -- the raw key is never persisted.
- The provider's header is excluded from every httpSecurity.corsHeaders and gateway.cors.headers allow-list.

---

## Artifact Files

| Artifact | Path |
|---|---|
| Provider Plan | `config/generated/identity-providers.json` |
| Public Client Metadata (identity) | `config/generated/identity-client-identity.test.json` |

---

> **Secret handling:** Secret values are never stored in generated files. The provider plan
> references secrets by environment-variable name (`*_SECRET_REF`). Inject secrets at
> runtime via your secret management solution (e.g. AWS Secrets Manager, Azure Key Vault,
> Docker Secrets).
