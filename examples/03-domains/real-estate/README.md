# Cobblestone Homes

A home-selling agency built as a complete application: anyone can search the homes for sale, a buyer books a viewing and makes an offer, with a lender's pre-approval if they need one, and an agent accepts one offer and sends the contract for signature. The lender, the e-signature vendor and the email vendor run as mocks in the same stack, so nothing here needs an account with anyone and no money moves. Cobblestone is invented.

## What it shows

| Feature | Where |
|---|---|
| Two apps for two audiences, one on web and mobile, with an open search and sign-in only for what needs it | [homes-app.dtrx](homes-app.dtrx), [console-app.dtrx](console-app.dtrx) |
| Full-text search over a home's title, description and neighbourhood | `fulltext` on `Listing` and `search` in [listing-service.dtrx](listing-service.dtrx) |
| A public response that is shaped by hand, so an agent's address never leaves the server | `ListingCard` and `HomesAPI` in [listing-service.dtrx](listing-service.dtrx) |
| A map, a calendar, a chart and a price history | `Map` and `HomeDetail` in [homes-app.dtrx](homes-app.dtrx), `Viewings` and `Dashboard` in [console-app.dtrx](console-app.dtrx) |
| A rule kept under a lock and by the database: one home, one contract | `accept` and `Contract.listingId` in [deal-service.dtrx](deal-service.dtrx) |
| A rule read across rows: one agent's confirmed viewings never overlap | `confirm` in [viewing-service.dtrx](viewing-service.dtrx) |
| Every read and write scoped to who signed in, as a buyer and as an agent | `mine`, `ownAsAgent` and `ownListing` |
| An event that reaches people: a price change emails everyone with a viewing coming up | `ListingPriceChanged` in [listing-service.dtrx](listing-service.dtrx) and [viewing-service.dtrx](viewing-service.dtrx) |
| A job that follows a slow third party and acts when it answers | `SyncSignatures` in [deal-service.dtrx](deal-service.dtrx) |
| A reminder sent once, from a job | `RemindTomorrowsViewings` in [viewing-service.dtrx](viewing-service.dtrx) |
| An append-only history | `PriceChange` in [listing-service.dtrx](listing-service.dtrx) |
| Declared images chosen by what the row says | `HomeArt` in [homes-app.dtrx](homes-app.dtrx) |
| Third parties behind `extern service` contracts | [providers/](providers/) |
| Mock vendors that authenticate callers with API keys, storing only hashes | [mocks/](mocks/) |

## The parts

| Part | Port | What it does |
|---|---|---|
| Homes app | 4200 | Search, the map, a home's page, viewings and offers. Also generated as a Flutter app |
| Console app | 4300 | An agent's dashboard, listings, viewings, offers and contracts, and the vendor pages |
| `ListingService` | 8001 | Homes for sale, and the application's identity block |
| `ViewingService` | 8002 | Viewings and their reminders |
| `DealService` | 8003 | Offers and contracts |
| `MortgageMock` | 8090 | Stands in for the lender |
| `SignatureMock` | 8091 | Stands in for the e-signature vendor |
| `EmailMock` | 8092 | Stands in for the email vendor |

## Third parties

The product services call a contract and do not know a mock answers it. To use a real vendor, point the URL in [config/providers/](config/providers/) at it and supply the secret. No `.dtrx` file changes.

| Contract | Mock | What the mock does |
|---|---|---|
| `MortgageProvider` | `MortgageMock` | Pre-approves up to $900,000 and declines anything over it. No credit is checked |
| `SignatureProvider` | `SignatureMock` | Keeps every envelope. An operator plays the buyer, signing or declining on the Console's E-signature page |
| `EmailProvider` | `EmailMock` | Keeps every email in an outbox. An address at `bounce.example.com` bounces |

## Run it

```bash
datrix generate -s examples/03-domains/real-estate/system.dtrx -L python
cd <the generated output>
cp .env.example .env
./scripts/deploy.sh        # Windows: scripts\deploy.ps1
```

TypeScript generates from the same source with `-L typescript`. Only one example can hold the default ports at a time, and `.env` moves them.

Then open:

- Homes: <http://localhost:4200>
- Console: <http://localhost:4300>

## Things to try

1. **Look around.** On the Homes app, without signing in, search for `garden` and open the Rose Street bungalow. Open the Map page and press a pin.
2. **Book a viewing.** Press Book a viewing and sign up. It waits under My viewings until the agent answers.
3. **Make an offer on a mortgage.** On Oak Lane, offer $1,000,000 with a mortgage. The lender declines and the offer goes nowhere. Offer $890,000 and it reaches the agent.
4. **Be the agent.** Sign up as `dana@cobblestone.example.com` and be granted `agent`. In the Console, confirm the viewing, then try to confirm another at the same time. The service refuses.
5. **Choose between two buyers.** End of the terrace has two offers. Accept Owen's. Ruth's is turned down in the same step, the home goes under offer, and the contract appears under Contracts.
6. **Sign it.** As `operator`, sign the envelope on the E-signature page. Within two minutes the contract shows signed, the home is sold, and the Outbox holds the email to Owen.
7. **Change a price.** On a home with a viewing coming up, change the price. The buyer's email is in the Outbox a moment later, sent by an event.

## Sign-in and roles

Sign-in runs on the Zitadel in the stack, so nothing here handles a password. Anyone can sign up to book a viewing or make an offer. `agent` and `operator` are granted, never self-assigned: sign in to the Zitadel console at <http://localhost:8085/ui/console> as the admin named in `.env`, then grant the role on the `cobblestone-identity` project.

An agent's sign-in address is what ties them to their listings, so the seeded homes belong to whoever signs in as `dana@cobblestone.example.com` or `noor@cobblestone.example.com`. The vendor pages in the Console need `operator`.

## The development keys

`config/viewing-service.dcfg` and `config/deal-service.dcfg` carry a `localDefault` for each vendor key, named `dev-only-…-not-a-credential`, and `seed/` holds its SHA-256 hash. Both only let this stack's services reach this stack's mocks. Any other deployment has to supply its own value.

## Photographs

A home here is drawn from one of five declared images, chosen by its kind, because this example stores no uploads. Storing files, and limiting what can be uploaded, is the `storage` block in [the storage feature example](../../02-features/03-infrastructure-blocks/storage/).
