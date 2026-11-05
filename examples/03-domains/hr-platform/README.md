# Alderbrook People

An HR platform built as a complete application: a candidate applies on a public site, HR takes them through a background check and a signed offer, and the signature makes them an employee who books time off and reads payslips. Payroll needs two people to approve it. The bank, the background check vendor and the e-signature vendor run as mocks in the same stack, so nothing here needs an account with anyone and no money moves. Alderbrook is invented, and so is everyone in it.

## What it shows

| Feature | Where |
|---|---|
| Three apps for three audiences, one of them public and one on web and mobile | [careers-app.dtrx](careers-app.dtrx), [console-app.dtrx](console-app.dtrx), [employee-app.dtrx](employee-app.dtrx) |
| A read model built from events, holding only what colleagues may see | the `cqrs` block in [employee-service.dtrx](employee-service.dtrx) |
| A pay run nobody can approve alone | `approve` in [payroll-service.dtrx](payroll-service.dtrx) |
| Paying a whole run safely twice: one key per person per run | `pay` in [payroll-service.dtrx](payroll-service.dtrx) |
| A row lock so two approvals cannot spend the same vacation days | `approveTimeOff` in [employee-service.dtrx](employee-service.dtrx) |
| A hiring board you drag, where only a signature can reach Hired | `PipelineBoard` in [console-app.dtrx](console-app.dtrx), `hrMayMove` in [recruitment-service.dtrx](recruitment-service.dtrx) |
| A public form that gives back a reference, and a page that shows only how far it came | `CareersAPI` in [recruitment-service.dtrx](recruitment-service.dtrx) |
| Long-running vendor work: start it, then a job asks until it is settled | `SyncVendors` in [recruitment-service.dtrx](recruitment-service.dtrx) |
| A dashboard over several services, with a chart | `Dashboard` in [console-app.dtrx](console-app.dtrx) |
| Third parties behind `extern service` contracts | [providers/](providers/) |
| Mock vendors that authenticate callers with API keys, storing only hashes | [mocks/](mocks/) |

## The parts

| Part | Port | What it does |
|---|---|---|
| Employee app | 4200 | Your balance, time off, payslips and the directory |
| Console app | 4300 | The dashboard, people, time off, pay runs, roles and candidates, and the vendor pages |
| Careers app | 4400 | Open roles, applying, and following an application. No sign-in |
| `EmployeeService` | 8001 | People, time off and the directory, and the application's identity block |
| `PayrollService` | 8002 | Pay profiles, pay runs and payslips |
| `RecruitmentService` | 8003 | Roles and applications |
| `BankMock` | 8090 | Stands in for the payroll bank |
| `CheckMock` | 8091 | Stands in for the background check vendor |
| `SignatureMock` | 8092 | Stands in for the e-signature vendor |

## Third parties

The product services call a contract and do not know a mock answers it. To use a real vendor, point the URL in [config/providers/](config/providers/) at it and supply the secret. No `.dtrx` file changes.

| Contract | Mock | What the mock does |
|---|---|---|
| `BankProvider` | `BankMock` | Keeps every payout in a log. An account number ending in 0000 is rejected |
| `CheckProvider` | `CheckMock` | Holds each check in progress until an operator clears or flags it |
| `SignatureProvider` | `SignatureMock` | Holds each envelope until an operator signs or declines it |

## Run it

```bash
datrix generate -s examples/03-domains/hr-platform/system.dtrx -L python
cd <the generated output>
cp .env.example .env
./scripts/deploy.sh        # Windows: scripts\deploy.ps1
```

TypeScript generates from the same source with `-L typescript`. Only one example can hold the default ports at a time, and `.env` moves them.

Then open:

- Employee: <http://localhost:4200>
- Console: <http://localhost:4300>
- Careers: <http://localhost:4400>

## Things to try

1. **Apply.** On the Careers site, apply for Backend engineer. Keep the reference, and look it up under Follow an application.
2. **Hire them.** As `hr`, open the role's candidates in the Console and drag the application along. Try dragging it to Hired, and the service refuses. Start the background check, and as `operator` clear it on the vendor's page. Within two minutes the candidate shows Clear and you can make an offer. Sign it on the e-signature page, and within two minutes they are on the People page with a pay profile.
3. **Run payroll.** As `hr`, prepare a run for this month, for example `2026-11`. Try approving it yourself, and the service refuses. Have a second `hr` user approve it, then press Pay everyone. Noor Haddad's account ends in 0000, so their payslip fails with the bank's reason and the others are paid.
4. **Take time off.** Add yourself under People with your sign-in address, then ask for vacation in the Employee app. Approve it in the Console, and your balance goes down. Ask for more days than you have left, and the approval is refused.
5. **Find a colleague.** Rename someone in the data and the directory catches up from the event, without ever seeing a salary.

## Sign-in and roles

Sign-in runs on the Zitadel in the stack, so nothing here handles a password. Anyone can create a sign-in, and it reaches an employee record only if HR has that work address on file. `hr`, `manager` and `operator` are granted, never self-assigned: sign in to the Zitadel console at <http://localhost:8085/ui/console> as the admin named in `.env`, then grant the role on the `alderbrook-identity` project.

The vendor pages in the Console need `operator`. The Careers site needs no account.

## The development keys

`config/*-service.dcfg` carries a `localDefault` for each vendor key, named `dev-only-…-not-a-credential`, and `seed/` holds its SHA-256 hash. Both only let this stack's services reach this stack's mocks. Any other deployment has to supply its own value.

This is an example and not a payroll system: the tax rate is a single invented figure, and nothing here has been assessed against employment or data protection law.
