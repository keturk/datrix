# Wrenwood

A homeware shop. A customer browses without an account, fills a cart that stays on their device, pays, and
watches a parcel reach their door. Staff run the catalog, the orders and the refunds. A prerendered public
site tells the story in two languages. The card vendor, the parcel carrier and the email vendor run as mocks
in the same stack, so everything works with nothing to sign up for.

```bash
datrix generate -s examples/03-domains/ecommerce/system.dtrx -L python
cd .generated/python/docker-compose/local/03-domains/ecommerce
cp .env.example .env
powershell -File scripts/deploy.ps1 deploy     # or: bash scripts/deploy.sh deploy
```

| App | Open | Who it is for | Sign-in |
|-----|------|---------------|---------|
| [Storefront](storefront-app.dtrx) | <http://localhost:4200> | Customers, on the web and on a phone | Only to check out, see orders or manage an account |
| [Admin](admin-app.dtrx) | <http://localhost:4300> | Staff | The `admin` role |
| [Site](site-app.dtrx) | <http://localhost:4400> | The public | None; prerendered, in English and Turkish |
| [Provider Desk](desk-app.dtrx) | <http://localhost:4500> | Whoever is looking after the mocks | The `operator` role |

The hosted login is Zitadel at <http://localhost:8085>. A new sign-up is a customer. To see the Admin and the
Provider Desk, give that user the `admins` or `operators` group in Zitadel's console.

## Try this

1. **Look around as a visitor.** Open the Storefront. Nothing asks you to sign in until you reach the checkout.
2. **Fill a cart.** Add a Bonfire Candle, which is low on stock and marked down. The cart survives a reload,
   and a sign-in, because it lives on the device. The cart page can ask the shop what those things cost today,
   and corrects itself if a price has moved.
3. **Be declined.** At the checkout, choose *The card that is declined*. The order appears, then cancels with
   the vendor's reason, and the stock returns to the shelf. Nothing was charged.
4. **Pay.** Order again with *The card that pays*. Keep the order page open: within a minute it is paid and
   being packed, and over about four minutes it moves through picked up, on the road, out for delivery and
   delivered. The tracking number has a link to a page anyone can open, which shows a city and no name.
5. **Read the outbox.** The Provider Desk shows the charge, the parcel and each email you were sent.
6. **Lose a parcel.** On another order, press *Lose it* in the Provider Desk. The next tracking sync marks the
   shipment lost, the order shows a delivery problem, and the customer gets an email.
7. **Cancel a paid order.** Before the parcel is picked up, cancel it from the order page. Nothing calls the
   payment service: it hears the event, refunds the card, and the order becomes refunded.
8. **Run the shop.** In the Admin, read the dashboard, filter the orders by stage, give part of a refund, then
   the rest, and watch the order turn refunded. Suspend a customer and their API keys stop working.
9. **Script your orders.** On the Account page, issue an API key and call
   `GET /api/v1/orders/by-key` with it in the `X-Customer-Api-Key` header. Revoke it and the call is refused.
10. **Push news as the carrier.** `POST /api/v1/shipments/webhook/carrier` needs an `X-Carrier-Signature` of the
    HMAC-SHA256 of the raw body, keyed by the `carrier_webhook_secret` handle. Without it the body never runs.

## What it shows

| Feature | Where |
|---------|-------|
| Six services that meet only through contracts, queues and events | [`order-service.dtrx`](order-service.dtrx) and its neighbours |
| A saga with no orchestrator: decline, cancel and refund each undo what came before | `OrderCancelled` in [`payment-service.dtrx`](payment-service.dtrx) and [`product-service.dtrx`](product-service.dtrx) |
| Inventory reservation with a time limit, released by event or by a job | `reserveInventory`, `ReleaseExpiredReservations` |
| Work queues on RabbitMQ, one of them FIFO per merchant | `queues` in `order-service.dtrx`; `SettlePayment` |
| Topics with a transactional outbox: Kafka in the stack, SNS and SQS on AWS, Event Hubs on Azure | `pubsub mq` in each service |
| Third parties behind `extern service` contracts, with mocks that authenticate as a vendor would | [`providers/`](providers), [`mocks/`](mocks), [`config/providers/`](config/providers) |
| A signed inbound webhook | `carrierWebhook` in [`shipping-service.dtrx`](shipping-service.dtrx) |
| A document store beside the relational catalog | `nosql docdb` in `product-service.dtrx`: reviews |
| Redis counters, and hashes kept right by events | `ProductViews`, `OrderCache` |
| Customer-issued API keys: hash stored, shown once, revocable, rate limited | `issueApiKey` in [`user-service.dtrx`](user-service.dtrx) |
| An audited database | `rdbms paymentDb : audit`, `entity Order : audit` |
| Public pages beside signed-in ones, with each page's guard derived from what it reaches | [`storefront-app.dtrx`](storefront-app.dtrx) |
| Designed tables: named columns and filters, money and dates formatted, no ids | [`admin-app.dtrx`](admin-app.dtrx) |
| A workspace minted over a resource | `workspace Products` |
| A prerendered site with Markdown content, two languages and search metadata | [`site-app.dtrx`](site-app.dtrx), [`content/articles`](content/articles) |
| Two languages in one app | [`config/strings/storefront.tr-TR.dcfg`](config/strings/storefront.tr-TR.dcfg) |
| Web and mobile from one app, with push | `targets` in [`config/storefront-app.dcfg`](config/storefront-app.dcfg) |
| Spec tests in the DSL, for services and apps | the `test(...)` blocks |
| Cloud targets as profiles of the same system | [`config/system.dcfg`](config/system.dcfg) |

Security decisions worth reading: the order total comes from the server and never from a client; a card reaches
the shop only as the vendor's token; a public tracking number reveals a city and nothing else; every read of an
order, a payment or a shipment checks whose it is; and a suspended customer's keys are turned off by an event.

## Services

| Service | Port | What it owns |
|---------|------|--------------|
| `UserService` | 8006 | Customers, API keys, and the identity block |
| `ProductService` | 8004 | Categories, products, stock, reservations, reviews |
| `OrderService` | 8002 | Orders and their lifecycle, and the queues |
| `PaymentService` | 8003 | Payments, refunds, settlements |
| `ShippingService` | 8005 | Shipments and tracking |
| `NotificationService` | 8001 | Customer email, from the queues |
| `PaymentMock`, `CarrierMock`, `EmailMock` | 8090-8092 | The three vendors, in the stack |

## Pointing it at a real vendor

Each contract's location is one file under [`config/providers/`](config/providers). Change `url` there, supply
the value of the secret handle it names, and nothing else in the shop changes. The mocks and the Provider Desk
then have nothing to do and can be removed from [`system.dtrx`](system.dtrx).

## Deployment targets

The target language is a generation parameter, and the deployment target is a config profile.

| Profile | Target | Notes |
|---------|--------|-------|
| `test`, `development`, `production` | docker-compose on the developer machine | nginx gateway, self-hosted Zitadel, Prometheus, Jaeger, Loki, Grafana, Alertmanager |
| `aws` | ECS Fargate, with SQS-triggered Lambdas for the consumers | API Gateway, RDS, ElastiCache, SNS, SQS, DocumentDB, CloudWatch, X-Ray, AppConfig, Cognito |
| `azure` | Web App for Containers | API Management, Flexible Server, Azure Cache for Redis, Event Hubs, Service Bus, Cosmos DB, Azure Monitor, App Configuration, Entra |
| `azureVm` | docker-compose on one Azure VM | The compose stack behind API Management, with PostgreSQL on Flexible Server |

```bash
datrix generate -s examples/03-domains/ecommerce/system.dtrx -L python --profile aws
```

Python realizes every profile. `-L typescript` generates the compose profiles.

## Secrets

Every secret is a logical handle declared by the service that uses it. On a local profile each handle has a
default, which is a development value and not a credential, and the mocks store only its SHA-256 hash. On any
other profile the deploy refuses to start until an operator has supplied the value.
