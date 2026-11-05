# Port Alder 311

A city's service desk, built as a complete application: residents report a problem from a street address on the web or a phone, and city staff work the queue, with spatial answers from PostGIS. The text and address vendors run as mocks in the same stack, so nothing here needs an account with anyone. Port Alder is invented.

## What it shows

| Feature | Where |
|---|---|
| A public app with no sign-in, on web and mobile, from one app definition | [citizen-app.dtrx](citizen-app.dtrx) |
| A staff app whose sign-in and roles follow from the routes each page reaches | [operations-app.dtrx](operations-app.dtrx) |
| Spatial columns and queries: point in polygon, distance, area | `GeoSql` in [district-service.dtrx](district-service.dtrx), [facility-service.dtrx](facility-service.dtrx) |
| Maps with markers on both clients | `Places` in [citizen-app.dtrx](citizen-app.dtrx), `Board` in [operations-app.dtrx](operations-app.dtrx) |
| A job that turns seeded text into spatial columns | `ConvertBoundaries`, `ConvertShapes` |
| A service calling a peer with a machine credential | `forLocation`, `auth(service, providers: [machine])` |
| A status history the database keeps append-only | `RequestUpdate` in [request-service.dtrx](request-service.dtrx) |
| Texts sent from an event through a transactional outbox, once per key | `RequestStatusChanged` |
| Third parties behind `extern service` contracts | [providers/](providers/) |
| Mock vendors that authenticate callers with API keys, storing only hashes | [mocks/](mocks/) |
| A failure that stays safe: a report the vendor cannot place is kept and flagged | `place` in [request-service.dtrx](request-service.dtrx) |

## The parts

| Part | Port | What it does |
|---|---|---|
| Citizen app | 4200 | Report a problem, track it by reference, find city places on a map |
| Operations app | 4300 | The board, the queue, districts, facilities, and what the vendors received |
| `DistrictService` | 8001 | Districts and zoning, and the application's identity block |
| `FacilityService` | 8002 | Public places and parks |
| `RequestService` | 8003 | Service requests and their history |
| `SmsMock` | 8090 | Stands in for the text message vendor |
| `GeocoderMock` | 8091 | Stands in for the address vendor |

## Third parties

The product services call a contract and do not know a mock answers it. To use a real vendor, point the URL in [config/providers/](config/providers/) at it and supply the secret. No `.dtrx` file changes.

| Contract | Mock | What the mock does |
|---|---|---|
| `SmsProvider` | `SmsMock` | Keeps every text in a log. A number starting `+1555010` fails |
| `GeocoderProvider` | `GeocoderMock` | Answers from its table of known addresses, which staff can extend. Anything else does not match |

## Run it

```bash
datrix generate -s examples/03-domains/city-services/system.dtrx -L python
cd <the generated output>
cp .env.example .env
./scripts/deploy.sh        # Windows: scripts\deploy.ps1
```

TypeScript generates from the same source with `-L typescript`. Only one example can hold the default ports at a time, and `.env` moves them.

Then open:

- Citizen: <http://localhost:4200>
- Operations: <http://localhost:4300>

## Things to try

1. **Report a problem.** In the Citizen app, report a pothole at `12 Main Street` and leave a phone number. You get a reference, the report lands in Old Town because the point falls inside that district's polygon, and a text appears in Operations under Texts sent.
2. **Report from nowhere.** Use the address `behind the old mill`. The report is still kept, and the board counts it under Needs a location. Add the address under Address lookups and the next report from there is placed.
3. **Work a request.** In Operations, open a request from the queue, assign it, start work and resolve it. The history keeps every step, and each change texts the reporter once.
4. **Close a facility.** Close a facility in Operations and it drops off the public map.

## Sign-in and roles

Sign-in runs on the Zitadel in the stack, so nothing here handles a password. Residents need no account. Staff accounts are not self-service: sign in to the Zitadel console at <http://localhost:8085/ui/console> as the admin named in `.env`, create the user, then grant `dispatcher`, `admin` or `operator` on the `portalder-identity` project. The vendor pages need `operator`.

## The development keys

`config/request-service.dcfg` carries a `localDefault` for each vendor key, named `dev-only-…-not-a-credential`, and `seed/` holds its SHA-256 hash. Both only let this stack's services reach this stack's mocks. Any other deployment has to supply its own value.

Every person, place and phone number in the seed data is invented.
