# Quillon Bank

A small retail bank, built as a complete application: customers open accounts and move money on the web or a phone, and staff check customers, take deposits and review alerts. A real double-entry ledger sits underneath, and an AI analyst reads an alert for an officer and can propose freezing the account, which waits for a second officer. The payment network, the identity check, the sanctions list and the model run as mocks in the same stack, so nothing here needs an account with anyone and no real money moves. Quillon Bank is invented.

## What it shows

| Feature | Where |
|---|---|
| A ledger the database protects: entries are append-only, and a posting that does not balance cannot commit | `LedgerEntry` and its `invariant` in [transaction-service.dtrx](transaction-service.dtrx) |
| Row locks taken in a fixed order, so concurrent transfers cannot overspend or deadlock | `post` in [transaction-service.dtrx](transaction-service.dtrx) |
| Exact money, in columns, requests and forms | every `Money` field, `Fmt.money` in the apps |
| A customer app on web and mobile where each route only reads the caller's own rows | [banking-app.dtrx](banking-app.dtrx), `ownedAccount` |
| A staff app whose sign-in and roles follow from the routes each page reaches | [back-office-app.dtrx](back-office-app.dtrx) |
| Personal data handled with care: the identity document is never stored, and the date of birth never leaves the service | `register`, `dateOfBirth : hidden` in [account-service.dtrx](account-service.dtrx) |
| Compliance built only on events, with an audit trail the database keeps append-only | [compliance-service.dtrx](compliance-service.dtrx) |
| Jobs that keep their own record: nightly reconciliation and a daily report | `ReconcileYesterday`, `ReportYesterday` |
| An AI agent with tools that a person has to approve: a proposal pauses the run, and a second officer's decision wakes it | `agents analyst` in [compliance-service.dtrx](compliance-service.dtrx) |
| The approval endpoints an `agents` block brings, called from a designed page | the Freezes page in [back-office-app.dtrx](back-office-app.dtrx) |
| Agent tests that replay a recorded conversation, so a spec test never reaches a model | `: replay('advice')`, [config/fixtures/agents/](config/fixtures/agents/) |
| Third parties behind `extern service` contracts | [providers/](providers/) |
| Mock vendors that authenticate callers with API keys, storing only hashes | [mocks/](mocks/) |
| Payments that are safe to retry: one key per transfer | `idempotencyKey` in `payout` |

## The parts

| Part | Port | What it does |
|---|---|---|
| Banking app | 4200 | Accounts, statements, transfers, paying someone at another bank, the identity check |
| Back Office app | 4300 | Customers, accounts, transfers, the counter, alerts, freezes waiting on an officer, the audit trail, the ledger, and what the vendors received |
| `AccountService` | 8001 | Customers and accounts, and the application's identity block |
| `TransactionService` | 8002 | The ledger and transfers |
| `ComplianceService` | 8003 | Alerts, the audit trail, daily reports and the AI analyst |
| `BankMock` | 8090 | Stands in for the payment network |
| `KycMock` | 8091 | Stands in for the identity check vendor |
| `SanctionsMock` | 8092 | Stands in for the sanctions vendor |
| `ModelMock` | 8093 | Stands in for the model behind the analyst |

## Third parties

The product services call a contract and do not know a mock answers it. To use a real vendor, point the URL in [config/providers/](config/providers/) at it and supply the secret. No `.dtrx` file changes.

| Contract | Mock | What the mock does |
|---|---|---|
| `BankProvider` | `BankMock` | Keeps every payment in a log. An IBAN starting `XX` is refused, and the money comes back |
| `KycProvider` | `KycMock` | A document number ending `0000` is declined, one ending `9999` goes to a person, anything else is clear |
| `SanctionsProvider` | `SanctionsMock` | Screens a payee against a short invented list staff can edit |

`ModelMock` is different: it speaks the wire format of the model provider the `agents` block names, so the analyst needs no contract. It follows a short script and does not think. The `production` profile in [config/compliance-service.dcfg](config/compliance-service.dcfg) is the same agent with a real model and a key.

## Run it

```bash
datrix generate -s examples/03-domains/finance/system.dtrx -L python --profile development
cd <the generated output>
cp .env.example .env
./scripts/deploy.sh        # Windows: scripts\deploy.ps1
```

The `development` profile runs the analyst against the model mock. The default `test` profile replays recorded answers instead, for spec tests. This example generates in Python only, because TypeScript does not realize `agents` yet; every service's config names its language. Only one example can hold the default ports at a time, and `.env` moves them.

Then open:

- Banking: <http://localhost:4200>
- Back Office: <http://localhost:4300>

## Things to try

1. **Become a customer.** Register in the Banking app and complete your profile with a document number such as `AB123456`. Your identity check clears, and you can open an account.
2. **Put money in.** As a teller, use the Counter in the Back Office to deposit into your new account's number.
3. **Move money.** Transfer to `QB1000000001`. Your statement shows the debit, and the Back Office ledger shows both sides.
4. **Try to overspend.** Move more than your balance. Nothing posts, and the error says why.
5. **Hit the sanctions list.** Pay `Ivor Blackwood`. The payment holds, no money moves, and a critical alert appears under Alerts.
6. **Have a payment refused.** Pay anyone at an IBAN starting `XX`. The transfer is rejected and the money comes back.
7. **Trip compliance.** Transfer 10,000 or more, and an alert appears for an officer.
8. **Ask the analyst.** As an officer, use *Ask the analyst* on that alert. A routine alert gets advice. On a critical one, or a second open alert on the same account, the analyst proposes a freeze and its run pauses.
9. **Be the second officer.** The proposal waits under Freezes. The officer who asked is refused, so sign in as another officer and approve it: the run wakes up and freezes the account. Decline one and the account stays open.

## Sign-in and roles

Sign-in runs on the Zitadel in the stack, so nothing here handles a password. Anyone can register as a customer. `teller`, `officer` and `operator` are granted, never self-assigned: sign in to the Zitadel console at <http://localhost:8085/ui/console> as the admin named in `.env`, then grant the role on the `quillon-identity` project.

A teller works the counter, an officer reviews customers and alerts, and the vendor pages need `operator`.

## The development keys

`config/*-service.dcfg` carries a `localDefault` for each vendor key, named `dev-only-…-not-a-credential`, and `seed/` holds its SHA-256 hash. Both only let this stack's services reach this stack's mocks. Any other deployment has to supply its own value.

Every person, name and account in the seed data is invented, and every address is on the reserved `example.com` domain.
