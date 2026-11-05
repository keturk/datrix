# Larkhill Academy

A learning platform built as a complete application: a student finds a course, pays for it, reads each lesson and answers its question, asks a tutor when stuck, and gets a certificate or, if an instructor agrees, their money back. The card vendor, the email vendor and the model behind the tutor run as mocks in the same stack, so nothing here needs an account with anyone and no money moves. Larkhill is invented.

## What it shows

| Feature | Where |
|---|---|
| Two apps for two audiences, one on web and mobile, with an open catalog and sign-in only for what needs it | [student-app.dtrx](student-app.dtrx), [instructor-app.dtrx](instructor-app.dtrx) |
| An agent with human approval: the tutor reads the lesson through one tool and can only ask for a refund through another marked `approval`, so its run suspends until an instructor decides | `agents tutor` in [tutor-service.dtrx](tutor-service.dtrx), `Refunds` in [instructor-app.dtrx](instructor-app.dtrx) |
| A secret that stays on the server: the right answer never reaches a browser | `rightAnswer`, `LessonView` and `checkAnswer` in [course-service.dtrx](course-service.dtrx) |
| Charging safely twice: one key per student per course | `enroll` in [enrollment-service.dtrx](enrollment-service.dtrx) |
| Every read of a student's work scoped to the signed-in student | `enrollmentOfCaller` in [enrollment-service.dtrx](enrollment-service.dtrx) |
| An app deciding through the service's approval endpoints, which refuse anyone without the approver role and the student who asked | `TutorService.ApprovalAPI` in [instructor-app.dtrx](instructor-app.dtrx), `approvals` in [config/tutor-service.dcfg](config/tutor-service.dcfg) |
| A job that notices someone has gone quiet | `RemindQuietStudents` in [enrollment-service.dtrx](enrollment-service.dtrx) |
| Third parties behind `extern service` contracts | [providers/](providers/) |
| Mock vendors that authenticate callers with API keys, storing only hashes | [mocks/](mocks/) |

## The parts

| Part | Port | What it does |
|---|---|---|
| Student app | 4200 | The catalog, enrolling, lessons, quizzes and the tutor. Also generated as a Flutter app |
| Instructor app | 4300 | The dashboard, courses, students, refunds and what the tutor said, and the vendor pages |
| `CourseService` | 8001 | Courses and lessons, and the application's identity block |
| `EnrollmentService` | 8002 | Enrollments, progress, certificates and refunds |
| `TutorService` | 8003 | The tutor agent, its approval requests and a log of what it said |
| `PaymentMock` | 8090 | Stands in for the card vendor |
| `EmailMock` | 8091 | Stands in for the email vendor |
| `ModelMock` | 8092 | Stands in for the model the agent calls |

## Third parties

The product services call a contract and do not know a mock answers it. To use a real vendor, point the URL in [config/providers/](config/providers/) at it and supply the secret. No `.dtrx` file changes.

| Contract | Mock | What the mock does |
|---|---|---|
| `PaymentProvider` | `PaymentMock` | Keeps every charge in a log. The token `tok_declined` is declined |
| `EmailProvider` | `EmailMock` | Keeps every email in an outbox. An address at `bounce.example.com` bounces |

The model is not a contract: the `agents` block names a provider, and `ModelMock` speaks that provider's wire format. It follows a script: a question about getting money back asks for the `offerRefund` tool, and anything else reads the lesson and answers with its opening. It does not think. The `production` profile in [config/tutor-service.dcfg](config/tutor-service.dcfg) is the same agent on a real model, with a key you supply.

## Run it

```bash
datrix generate -s examples/03-domains/learning-management/system.dtrx -L python --profile development
cd <the generated output>
cp .env.example .env
./scripts/deploy.sh        # Windows: scripts\deploy.ps1
```

Use the `development` profile: the `test` profile plays recorded model turns for the spec tests instead of calling `ModelMock`.

This example is Python only, because `agents` has no TypeScript runtime yet. Every service sets `language = "python"`, since one system generates in one language, so `-L typescript` still generates Python here. Only one example can hold the default ports at a time, and `.env` moves them.

Then open:

- Student: <http://localhost:4200>
- Instructor: <http://localhost:4300>

## Things to try

1. **Enroll.** Open Reading maps and enroll with the card that is declined, and you are told so. Enroll with the card that pays, and the Instructor app's Charges and Outbox pages show the charge and the welcome email.
2. **Learn.** Read a lesson and answer its question. A wrong answer changes nothing. A right one moves your progress, and finishing the course gives you a certificate code by email and on the page.
3. **Ask the tutor.** On a lesson, ask why contour lines never cross. The Model turns page shows the agent reading the lesson and then answering.
4. **Ask for your money back.** Tell the tutor you want a refund. The agent asks for its `offerRefund` tool and its run suspends. The request appears on the Instructor app's Refunds page, and nothing moves until an instructor decides. Approve it and the run picks up where it stopped: the card is refunded and the student gets an email. Decline it and the tool never runs, and the student is told by email.
5. **Build a course.** As `instructor`, start a course, add a lesson with a question, and publish it. It appears in the catalog.

## Sign-in and roles

Sign-in runs on the Zitadel in the stack, so nothing here handles a password. Anyone can create a sign-in and enroll. `instructor` and `operator` are granted, never self-assigned: sign in to the Zitadel console at <http://localhost:8085/ui/console> as the admin named in `.env`, then grant the role on the `larkhill-identity` project.

The vendor pages in the Instructor app need `operator`.

## The development keys

`config/enrollment-service.dcfg` carries a `localDefault` for each vendor key, named `dev-only-…-not-a-credential`, and `seed/` holds its SHA-256 hash. Both only let this stack's services reach this stack's mocks. Any other deployment has to supply its own value.
