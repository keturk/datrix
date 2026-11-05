# Rookery

A place to post short notes and follow people, built as a complete application. Anyone can read. Every post goes past a moderation vendor before anyone sees it, and a person on the Trust and Safety desk decides what the vendor is unsure of. The moderation, push and email vendors run as mocks in the same stack, so nothing here needs an account with anyone. Rookery is invented.

## What it shows

| Feature | Where |
|---|---|
| Two apps for two audiences, one on web and mobile, readable with no account | [social-app.dtrx](social-app.dtrx), [desk-app.dtrx](desk-app.dtrx) |
| A check that fails closed: a moderation vendor that does not answer holds the post | `reviewed` in [post-service.dtrx](post-service.dtrx) |
| A short-lived Redis counter that slows down anyone posting too fast | `slowDownIfNeeded` in [post-service.dtrx](post-service.dtrx) |
| A public response shaped by hand, so an address never leaves the service | `ProfileCard` and `PublicPeopleAPI` in [people-service.dtrx](people-service.dtrx) |
| Counters changed under a lock, with the row they count | `follow` and `removeFollow` in [people-service.dtrx](people-service.dtrx) |
| Full-text search in two services, and hashtags with counts | `search` in each, `indexTags` in [post-service.dtrx](post-service.dtrx) |
| One event fanned out to one row per follower | `PostPublished` in [notice-service.dtrx](notice-service.dtrx) |
| A device the push vendor says is gone is forgotten | `pushTo` in [notice-service.dtrx](notice-service.dtrx) |
| A weekly job that sends one email however often it runs | `SendWeeklyDigest` in [notice-service.dtrx](notice-service.dtrx) |
| A token kept out of every response with `sensitive` | `Device` in [notice-service.dtrx](notice-service.dtrx) |
| Third parties behind `extern service` contracts | [providers/](providers/) |
| Mock vendors that authenticate callers with API keys, storing only hashes | [mocks/](mocks/) |

## The parts

| Part | Port | What it does |
|---|---|---|
| Social app | 4200 | Explore, the people you follow, profiles, posts, notifications. Also generated as a Flutter app |
| Desk app | 4300 | The Trust and Safety desk and the vendor pages |
| `PeopleService` | 8001 | Profiles and who follows whom, and the application's identity block |
| `PostService` | 8002 | Posts, comments, likes, tags and reports |
| `NoticeService` | 8003 | Notifications, push and email |
| `ModerationMock` | 8090 | Stands in for the content moderation vendor |
| `PushMock` | 8091 | Stands in for the push notification vendor |
| `EmailMock` | 8092 | Stands in for the email vendor |

## Third parties

The product services call a contract and do not know a mock answers it. To use a real vendor, point the URL in [config/providers/](config/providers/) at it and supply the secret. No `.dtrx` file changes.

| Contract | Mock | What the mock does |
|---|---|---|
| `ModerationProvider` | `ModerationMock` | Three fixed rules. `buy followers` is rejected, `http://` and `idiot` are held, and anything else is allowed. It reads no meaning into anything |
| `PushProvider` | `PushMock` | Keeps every push, and reaches no phone. A token starting `dead-` is reported gone |
| `EmailProvider` | `EmailMock` | Keeps every email in an outbox. An address at `bounce.example.com` bounces |

## Run it

```bash
datrix generate -s examples/03-domains/social-platform/system.dtrx -L python
cd <the generated output>
cp .env.example .env
./scripts/deploy.sh        # Windows: scripts\deploy.ps1
```

TypeScript generates from the same source with `-L typescript`. Only one example can hold the default ports at a time, and `.env` moves them.

Then open:

- Social: <http://localhost:4200>
- Desk: <http://localhost:4300>

## Things to try

1. **Read without an account.** Open Explore, press `#waders` under Trending, and open Iris's profile.
2. **Step into a profile.** Sign up as `iris@rookery.example.com`. Following shows the people Iris follows, and two notifications are waiting.
3. **Post something.** Post a note with a `#tag`. It appears under Explore and the tag, and Tom and Nia each get a notification.
4. **Be held.** Post something with `http://` in it. Only you can see it, under My posts, with the reason.
5. **Be refused.** Post `buy followers`. The vendor rejects it and nothing is saved.
6. **Post too fast.** Post six times in a minute. The sixth is refused, and the limit lifts by itself.
7. **Be the moderator.** Sign up as anyone and be granted `moderator`. On the Desk, filter Posts by Held and approve Tom's post. Only then do his followers hear about it.
8. **Forget a phone.** Like one of Tom's posts as Iris. The Desk's Push page shows the vendor reported his old phone gone, and his device row is removed.

## Sign-in and roles

Sign-in runs on the Zitadel in the stack, so nothing here handles a password. Anyone can sign up and choose a handle in Settings. `moderator` is granted, never self-assigned: sign in to the Zitadel console at <http://localhost:8085/ui/console> as the admin named in `.env`, then grant the role on the `rookery-identity` project.

## The development keys

`config/post-service.dcfg` and `config/notice-service.dcfg` carry a `localDefault` for each vendor key, named `dev-only-…-not-a-credential`, and `seed/` holds its SHA-256 hash. Both only let this stack's services reach this stack's mocks. Any other deployment has to supply its own value.

## Devices

A phone registers with `POST /api/v1/notices/devices` once its platform gives it a token. The seed holds two tokens, so a push works without a phone.
