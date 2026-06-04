# Config Store Example

A minimal `shop` catalog service that demonstrates the **runtime config store** — an
additive, runtime-mutable configuration plane for values that must change without
redeploying the application (feature flags, kill switches, rate-limit tuning).

## What this demonstrates

- A system-level `configStore` block attached to a profile in `config/system.dcfg`.
- A **local Consul** config store (`engine = "consul"`, `flavor = "container"`), so the
  example runs without any cloud credentials. Authors write `flavor`; it is mapped to the
  canonical `platform` at the emitter boundary.
- Two profiles:
  - `featureFlags` — a `featureFlag` profile (Boolean-only keys), e.g. `enableNewCheckout`.
  - `rateLimits` — a `freeform` profile with a bounded `Integer` key
    (`apiRequestsPerMinute`, constrained to `1..10000`).
- A single `Product` entity with a REST API, so the config store is exercised alongside a
  real, generatable service.

The config store is **additive**: services receive a generated runtime client only when
`configStore` is present. Examples without it produce byte-equivalent output.

## File structure

```
config-store/
├── system.dtrx                    # Entry point (includes catalog-service.dtrx)
├── catalog-service.dtrx           # Product catalog service (one entity + REST API)
└── config/
    ├── system.dcfg                # System config + configStore block (Consul, container)
    └── catalog-service.dcfg       # Service config
```

## Expected generated artifacts

Generating this example (Python, Docker) produces, in addition to the normal service code:

- A **runtime config-store client** with typed accessors
  (`get_bool`, `get_int`, `get_float`, `get_string`, `get_namespace`).
- A **`remote_defaults.json`** artifact seeding the cache from the declared key defaults.
- A Docker **`config-store`** service (Consul container) in the compose output, since the
  profile uses `flavor = "container"`.

## Generate

```bash
datrix generate examples/02-features/03-infrastructure-blocks/config-store/system.dtrx -l python -p docker
```
