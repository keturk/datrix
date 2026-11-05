# Saltbox

Food delivery with its three audiences, built as a complete application: a customer orders on the web or a phone, a kitchen moves the order across a board, and a driver follows a route to the door. Card payments, routes and texts run as mocks in the same stack, so nothing here needs an account with anyone and no card is ever touched. Saltbox is invented.

## What it shows

| Feature | Where |
|---|---|
| Three apps for three audiences around one order, two of them on web and mobile | [customer-app.dtrx](customer-app.dtrx), [kitchen-app.dtrx](kitchen-app.dtrx), [driver-app.dtrx](driver-app.dtrx) |
| A live board: drag an order across columns, polled every 10 seconds | `Board` in [kitchen-app.dtrx](kitchen-app.dtrx) |
| A map with a route on it | `Route` in [driver-app.dtrx](driver-app.dtrx) |
| Prices that come from the server, never from the customer's device | `PricingAPI` in [restaurant-service.dtrx](restaurant-service.dtrx) |
| Services calling peers with a machine credential | `auth(service, providers: [machine])` |
| Two drivers claiming one delivery: a row lock lets exactly one win | `claim` in [delivery-service.dtrx](delivery-service.dtrx) |
| A card charge safe to retry, and a refund when an order is cancelled | `checkout`, `refund` in [order-service.dtrx](order-service.dtrx) |
| Events between services through a transactional outbox | `OrderStatusChanged` |
| A failure that stays safe: no route from the vendor still leaves a delivery | `plan` in [delivery-service.dtrx](delivery-service.dtrx) |
| Third parties behind `extern service` contracts | [providers/](providers/) |
| Mock vendors that authenticate callers with API keys, storing only hashes | [mocks/](mocks/) |

## The parts

| Part | Port | What it does |
|---|---|---|
| Customer app | 4200 | Restaurants, menus, a cart, checkout, order tracking |
| Kitchen app | 4300 | The board, dishes, deliveries on the road, and what the vendors received |
| Driver app | 4400 | Waiting deliveries, a route map, and picked-up and delivered buttons |
| `RestaurantService` | 8001 | Restaurants, menus and zones, and the application's identity block |
| `OrderService` | 8002 | Carts and orders |
| `DeliveryService` | 8003 | Drivers and deliveries |
| `PaymentMock` | 8090 | Stands in for the card payment vendor |
| `RouteMock` | 8091 | Stands in for the maps vendor |
| `SmsMock` | 8092 | Stands in for the text message vendor |

## Third parties

The product services call a contract and do not know a mock answers it. To use a real vendor, point the URL in [config/providers/](config/providers/) at it and supply the secret. No `.dtrx` file changes.

| Contract | Mock | What the mock does |
|---|---|---|
| `PaymentProvider` | `PaymentMock` | Keeps every charge in a log. The token `tok_declined` is declined, and any other token succeeds |
| `RouteProvider` | `RouteMock` | Works out road distance and time from the straight line between two points |
| `SmsProvider` | `SmsMock` | Keeps every text in a log |

## Run it

```bash
datrix generate -s examples/03-domains/food-delivery/system.dtrx -L python
cd <the generated output>
cp .env.example .env
./scripts/deploy.sh        # Windows: scripts\deploy.ps1
```

TypeScript generates from the same source with `-L typescript`. Only one example can hold the default ports at a time, and `.env` moves them.

Then open:

- Customer: <http://localhost:4200>
- Kitchen: <http://localhost:4300>
- Driver: <http://localhost:4400>

## Things to try

1. **Order dinner.** Register in the Customer app, add dishes to your cart, and check out with the card token `tok_good` and a phone number. The charge shows under Card charges in the Kitchen app.
2. **Have a card declined.** Check out with `tok_declined`. The order is not placed and your cart stays as it was.
3. **Cook it.** As `kitchen`, open Lemongrass's board and drag your order to Preparing, then to Ready for pickup. A text goes out for each step, shown under Texts sent. Try dragging it straight to Delivered, and the service refuses.
4. **Drive it.** As `driver`, start a shift, claim the delivery and follow the route. Picked up and delivered move the order, and the customer's page updates on its own.
5. **Cancel one.** From the board, drag a Placed order to Cancelled. The charge shows Refunded.

## Sign-in and roles

Sign-in runs on the Zitadel in the stack, so nothing here handles a password. Anyone can register as a customer. `kitchen`, `driver` and `operator` are granted, never self-assigned: sign in to the Zitadel console at <http://localhost:8085/ui/console> as the admin named in `.env`, then grant the role on the `saltbox-identity` project.

The vendor pages in the Kitchen app need `operator`. Browsing restaurants needs no account.

## The development keys

`config/*-service.dcfg` carries a `localDefault` for each vendor key, named `dev-only-…-not-a-credential`, and `seed/` holds its SHA-256 hash. Both only let this stack's services reach this stack's mocks. Any other deployment has to supply its own value.

Every person, kitchen and address in the seed data is invented.
