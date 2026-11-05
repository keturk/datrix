# Ferncrest Clinic

A small clinic built as a complete application: a patient books a visit on the web or a phone, the front desk runs the day from a board, a clinician signs the note and sends the prescription, and the insurer settles the claim. The insurer, the pharmacy and the text message vendor run as mocks in the same stack, so nothing here needs an account with anyone. Ferncrest is invented, and so is everyone in it.

## What it shows

| Feature | Where |
|---|---|
| Two apps for two audiences, one of them on web and mobile | [portal-app.dtrx](portal-app.dtrx), [clinic-app.dtrx](clinic-app.dtrx) |
| A live board: drag a patient across columns, polled every 15 seconds | `Today` in [clinic-app.dtrx](clinic-app.dtrx) |
| A calendar of every visit ahead | `Calendar` in [clinic-app.dtrx](clinic-app.dtrx) |
| Two patients taking one slot: a row lock lets exactly one win | `takeSlot` in [appointment-service.dtrx](appointment-service.dtrx) |
| A note kept out of logs and out of every response unless a route asks for it | `VisitNote.note` and `NoteView` in [record-service.dtrx](record-service.dtrx) |
| An access log nobody can edit, which the patient can read | `ChartAccess`, an `appendOnly` entity, and `Privacy` in [portal-app.dtrx](portal-app.dtrx) |
| Scheduled jobs that remind, mark no-shows, open slots and poll vendors | `jobs` in [appointment-service.dtrx](appointment-service.dtrx) and [record-service.dtrx](record-service.dtrx) |
| A workflow across services by event: a finished visit opens its note | `AppointmentStatusChanged` |
| Services calling peers with a machine credential | `auth(service, providers: [machine])` in [patient-service.dtrx](patient-service.dtrx) |
| Failures that stay safe: an insurer that cannot be reached leaves a patient unverified and a claim waiting | `verifyCoverage`, `submitClaim` |
| Third parties behind `extern service` contracts | [providers/](providers/) |
| Mock vendors that authenticate callers with API keys, storing only hashes | [mocks/](mocks/) |

## The parts

| Part | Port | What it does |
|---|---|---|
| Portal app | 4200 | Find a clinician, book, read notes, follow prescriptions and bills, see who opened your chart |
| Clinic app | 4300 | The day's board, the calendar, charts, notes to sign, billing, and the vendor pages |
| `PatientService` | 8001 | Patients and their coverage, and the application's identity block |
| `AppointmentService` | 8002 | Clinicians, open slots and visits |
| `RecordService` | 8003 | Notes, prescriptions, claims and the access log |
| `InsurerMock` | 8090 | Stands in for the health insurer |
| `PharmacyMock` | 8091 | Stands in for the pharmacy network |
| `SmsMock` | 8092 | Stands in for the text message vendor |

## Third parties

The product services call a contract and do not know a mock answers it. To use a real vendor, point the URL in [config/providers/](config/providers/) at it and supply the secret. No `.dtrx` file changes.

| Contract | Mock | What the mock does |
|---|---|---|
| `InsurerProvider` | `InsurerMock` | Covers the members on its list. Pays a claim less the copay, sends one over $500 to a person, and denies a lapsed member |
| `PharmacyProvider` | `PharmacyMock` | Takes prescriptions, and an operator moves each ticket along by hand |
| `SmsProvider` | `SmsMock` | Keeps every text in a log |

## Run it

```bash
datrix generate -s examples/03-domains/healthcare/system.dtrx -L python
cd <the generated output>
cp .env.example .env
./scripts/deploy.sh        # Windows: scripts\deploy.ps1
```

TypeScript generates from the same source with `-L typescript`. Only one example can hold the default ports at a time, and `.env` moves them.

Then open:

- Portal: <http://localhost:4200>
- Clinic: <http://localhost:4300>

## Things to try

1. **Book a visit.** Register in the Portal, add your details with the member id `SIL-3000`, and your coverage turns Active with a $25 copay. Pick Dr. Imani Osei and a time. Your visit shows on the Clinic's calendar.
2. **Run the day.** As `frontDesk`, drag today's patients across the board. A patient can go from Checked in to In room, and the service refuses a jump straight to Completed.
3. **Sign a note.** Drag Ana Ferreira to Completed. As `clinician`, open Visit notes, write the note and sign it. Her claim is approved for $155, and she owes her $25 copay. Her chart shows you opened it.
4. **Send a large claim to review.** Finish a visit with Dr. Tomas Varga, who charges $640. The claim waits under Billing as In review. As `operator`, approve it on the insurer's page, and the next `SettleClaims` run brings the answer back.
5. **Fill a prescription.** From a chart, prescribe something. As `operator`, move the ticket to Ready for pickup on the pharmacy's page. The next `SyncPharmacy` run updates it and a text appears under Texts sent.
6. **See who looked.** Sign in to the Portal as the patient and open Privacy.

## Sign-in and roles

Sign-in runs on the Zitadel in the stack, so nothing here handles a password. Anyone can register as a patient. `clinician`, `frontDesk` and `operator` are granted, never self-assigned: sign in to the Zitadel console at <http://localhost:8085/ui/console> as the admin named in `.env`, then grant the role on the `ferncrest-identity` project.

The vendor pages in the Clinic app need `operator`. Looking through the clinicians needs no account.

## The development keys

`config/*-service.dcfg` carries a `localDefault` for each vendor key, named `dev-only-…-not-a-credential`, and `seed/` holds its SHA-256 hash. Both only let this stack's services reach this stack's mocks. Any other deployment has to supply its own value.

This is an example and not a medical record system: notes are stored as plain text in the database, and no part of it has been assessed against any health privacy regulation.
