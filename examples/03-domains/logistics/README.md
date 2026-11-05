# Quayline Freight

A parcel carrier built as a complete application: a dispatcher books a parcel, plans it onto a van's route and sends the route out, a driver follows it stop by stop, and the recipient follows it on a public page and by text. A parcel outside the delivery area goes to a partner carrier. The carrier, the geocoder and the text vendor run as mocks in the same stack, so nothing here needs an account with anyone and no parcel moves. Quayline is invented.

## What it shows

| Feature | Where |
|---|---|
| Three apps for three audiences: a public page with no sign-in, a desk app, and a driver app on web and mobile | [tracking-app.dtrx](tracking-app.dtrx), [dispatch-app.dtrx](dispatch-app.dtrx), [driver-app.dtrx](driver-app.dtrx) |
| A public route that says only what a stranger holding the number may know, down to a rounded map point | `TrackingAPI` in [shipment-service.dtrx](shipment-service.dtrx) |
| A map with markers and a route line | `RouteDetail` in [dispatch-app.dtrx](dispatch-app.dtrx), `RunRoute` in [driver-app.dtrx](driver-app.dtrx) |
| A queue, so a slow text vendor delays a text and nothing else, and a repeated delivery sends nothing twice | `TextRecipient` in [shipment-service.dtrx](shipment-service.dtrx), [notice-service.dtrx](notice-service.dtrx) |
| Events between services, with a parcel coming back to the planning list after a failed attempt | `ShipmentBooked` in [shipment-service.dtrx](shipment-service.dtrx) and [route-service.dtrx](route-service.dtrx) |
| A rule kept under a lock: two dispatchers adding to one van cannot overload it | `addStop` in [route-service.dtrx](route-service.dtrx) |
| Every read and write a driver makes checked against who they signed in as | `ownRoute` in [route-service.dtrx](route-service.dtrx) |
| A job that asks a vendor about what it holds, where one failed question stops nothing else | `SyncPartnerConsignments` in [shipment-service.dtrx](shipment-service.dtrx) |
| An append-only history, and a phone number no response carries | `TrackingEvent` and `recipientPhone` in [shipment-service.dtrx](shipment-service.dtrx) |
| Third parties behind `extern service` contracts | [providers/](providers/) |
| Mock vendors that authenticate callers with API keys, storing only hashes | [mocks/](mocks/) |

## The parts

| Part | Port | What it does |
|---|---|---|
| Tracking app | 4200 | The public page |
| Dispatch app | 4300 | Today, parcels, planning, routes, the fleet, and the vendor pages |
| Driver app | 4400 | A driver's routes and stops. Also generated as a Flutter app |
| `ShipmentService` | 8001 | Parcels and their history, and the application's identity block |
| `FleetService` | 8002 | Vans, drivers and services |
| `RouteService` | 8003 | Routes and stops |
| `NoticeService` | 8004 | Takes texts off the queue and sends them |
| `CarrierMock` | 8090 | Stands in for the partner carrier |
| `GeocodeMock` | 8091 | Stands in for the geocoding vendor |
| `SmsMock` | 8092 | Stands in for the text vendor |

## Third parties

The product services call a contract and do not know a mock answers it. To use a real vendor, point the URL in [config/providers/](config/providers/) at it and supply the secret. No `.dtrx` file changes.

| Contract | Mock | What the mock does |
|---|---|---|
| `CarrierProvider` | `CarrierMock` | Keeps every consignment. Each one goes in transit after a minute and is delivered after four |
| `GeocodeProvider` | `GeocodeMock` | Knows the cities in [seed/geocode-mock.dseed](seed/geocode-mock.dseed) and refuses others. Portland and the towns around it are in the delivery area |
| `SmsProvider` | `SmsMock` | Keeps every text in a log. Nothing reaches a phone |

## Run it

```bash
datrix generate -s examples/03-domains/logistics/system.dtrx -L python
cd <the generated output>
cp .env.example .env
./scripts/deploy.sh        # Windows: scripts\deploy.ps1
```

TypeScript generates from the same source with `-L typescript`. Only one example can hold the default ports at a time, and `.env` moves them.

Then open:

- Tracking: <http://localhost:4200>
- Dispatch: <http://localhost:4300>
- Driver: <http://localhost:4400>

## Things to try

1. **Follow a parcel.** On the Tracking page, enter `QL-7KM2PQ9XTR`. No sign-in, no name and no street, and a map point only good to a few miles.
2. **Book one.** As `dispatcher`, book a parcel to Tigard. It appears under Plan, waiting for a route. The Text vendor page shows the text the recipient got.
3. **Overload a van.** Start a route on the City van, or add a heavy parcel to a small van, until the service refuses.
4. **Send a route out.** Put the parcel on a route and press Send it out. The route's page draws the line between its stops.
5. **Drive it.** Sign in to the Driver app as a user with the address of a driver in the fleet, for example `ines@quayline.example.com`, with the `driver` role. Their route is there, and nobody else's. Mark a stop delivered, and mark another as nobody home. Back in Dispatch, that parcel can go on another route or to the partner.
6. **Send one further.** Book a parcel to Eugene. It goes straight to the partner carrier, and within a few minutes it shows as delivered.

## Sign-in and roles

Sign-in runs on the Zitadel in the stack, so nothing here handles a password. Recipients never sign in. `dispatcher`, `driver` and `operator` are granted, never self-assigned: sign in to the Zitadel console at <http://localhost:8085/ui/console> as the admin named in `.env`, then grant the role on the `quayline-identity` project.

The vendor pages in the Dispatch app need `operator`.

## The development keys

`config/shipment-service.dcfg` and `config/notice-service.dcfg` carry a `localDefault` for each vendor key, named `dev-only-…-not-a-credential`, and `seed/` holds its SHA-256 hash. Both only let this stack's services reach this stack's mocks. Any other deployment has to supply its own value.
