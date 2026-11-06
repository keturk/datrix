# Marram House

A small hotel on the coast, built as a complete application. A guest searches for dates, holds a room for ten minutes while they pay, and looks after the stay afterwards. The front desk runs arrivals, departures and housekeeping. The card vendor, the email vendor and the channel manager run as mocks in the same stack, so nothing here needs an account with anyone. Marram House is invented.

## What it shows

| Feature | Where |
|---|---|
| Availability computed per night from what is sold and held | `takenOn` and `leftFor` in [stay-service.dtrx](stay-service.dtrx) |
| A row lock that keeps the last room from going to two guests | `hold` in [stay-service.dtrx](stay-service.dtrx) |
| A hold with a time limit: it stops counting the moment it lapses, and a job tells the guest | `takenOn` and `ExpireHolds` in [stay-service.dtrx](stay-service.dtrx) |
| A retried payment that cannot charge twice | `idempotencyKey` in `pay`, and `createCharge` in [mocks/payment-mock.dtrx](mocks/payment-mock.dtrx) |
| A refund before the row changes, so a failed refund leaves the stay as it was | `cancelStay` in [stay-service.dtrx](stay-service.dtrx) |
| A choice that survives the trip through sign-in | the `: persisted` state in [guest-app.dtrx](guest-app.dtrx) |
| A page's guard derived from what it reaches: a visitor can search, and only holding asks for a sign-in | `Offers` and `Review` in [guest-app.dtrx](guest-app.dtrx) |
| A calendar and a board you drag across, for two kinds of work at the desk | `CalendarPage` and `Housekeeping` in [front-desk-app.dtrx](front-desk-app.dtrx) |
| A checkout that moves its room to Dirty by itself | `checkOut` in [stay-service.dtrx](stay-service.dtrx) |
| A job that keeps an outside system current | `PushAvailability` in [stay-service.dtrx](stay-service.dtrx) |
| An event turned into a stored notice, then a delivery, so a vendor being down loses nothing | `tell`, `deliver` and `RetryNotices` in [notice-service.dtrx](notice-service.dtrx) |
| A guest app on web and mobile, with no id or key on any page | [guest-app.dtrx](guest-app.dtrx) |
| Three third parties behind `extern service` contracts | [providers/](providers/) |
| Mock vendors that authenticate callers with API keys, storing only hashes | [mocks/](mocks/) |

## The parts

| Part | Port | What it does |
|---|---|---|
| Guest app | 4200 | The rooms, a search by date, paying, and your stays. Also generated as a Flutter app |
| Front Desk app | 4300 | Today, the calendar, housekeeping, every stay, rates and the vendor pages |
| `StayService` | 8001 | Rooms, availability, holds and stays, and the application's identity block |
| `NoticeService` | 8002 | Turns events into emails |
| `PaymentMock` | 8090 | Stands in for the card vendor |
| `EmailMock` | 8091 | Stands in for the email vendor |
| `ChannelMock` | 8092 | Stands in for the channel manager |

## Third parties

The product services call a contract and do not know a mock answers it. To use a real vendor, point the URL in [config/providers/](config/providers/) at it and supply the secret. No `.dtrx` file changes.

| Contract | Mock | What the mock does |
|---|---|---|
| `PaymentProvider` | `PaymentMock` | Keeps every charge. The token `tok_declined` is declined |
| `EmailProvider` | `EmailMock` | Keeps every email in an outbox. An address at `bounce.example.com` bounces |
| `ChannelProvider` | `ChannelMock` | Keeps the latest figure per room type and night, which is what the travel sites would believe |

## Run it

```bash
datrix generate -s examples/03-domains/hotel-booking/system.dtrx -L python
cd <the generated output>
cp .env.example .env
./scripts/deploy.sh        # Windows: scripts\deploy.ps1
```

TypeScript generates from the same source with `-L typescript`. Only one example can hold the default ports at a time, and `.env` moves them.

Then open:

- Guest app: <http://localhost:4200>
- Front Desk: <http://localhost:4300>

## Things to try

1. **Look around signed out.** Open the guest app, choose dates and see what is free. Nothing asks you to sign in until you hold a room.
2. **Hold, then be declined.** Sign up, hold a room and try the card that is declined. The room stays held and you can try again.
3. **Pay.** Use the card that works. An email reaches the Front Desk's Outbox a moment later, sent by an event, and the charge is on its Charges page.
4. **Let a hold lapse.** Hold another room and do nothing. Ten minutes later it is back on sale and you get an email saying so.
5. **Run the morning.** In the Front Desk, Today shows who is arriving and leaving. Open Pia Lund's stay and check her into a clean room.
6. **Check someone out.** Open Eli Marsh's stay and check out. Room 201 appears under Dirty on Housekeeping, and it cannot be given out until you drag it back to Ready.
7. **See what the sites believe.** The Travel sites page shows the figures a job sends every five minutes. Book a room and the figure for those nights drops at the next push.

## Sign-in and roles

Sign-in runs on the Zitadel in the stack, so nothing here handles a password. Anyone can sign up as a guest. The Front Desk needs `frontDesk`, and its vendor pages also need `operator`. Both are granted, never self-assigned: sign in to the Zitadel console at <http://localhost:8085/ui/console> as the admin named in `.env`, then grant the roles on the `marram-identity` project.

## The development keys

`config/stay-service.dcfg` and `config/notice-service.dcfg` carry a `localDefault` for each vendor key, named `dev-only-…-not-a-credential`, and `seed/` holds its SHA-256 hash. Both only let this stack's services reach this stack's mocks. Any other deployment has to supply its own value.
