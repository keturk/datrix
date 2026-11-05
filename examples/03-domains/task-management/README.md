# Millrace

A team's projects on a board, built as a complete application. Tasks move across columns, a task cannot start while another one blocks it, and whoever needs to know hears about it in chat and by email. The chat and email vendors run as mocks in the same stack, so nothing here needs an account with anyone. Millrace is invented.

## What it shows

| Feature | Where |
|---|---|
| A board you drag across, with the rule kept on the server | `ProjectBoard` in [workspace-app.dtrx](workspace-app.dtrx), `moveTask` in [task-service.dtrx](task-service.dtrx) |
| Data scoped to membership: someone not on a project cannot learn it exists | `myMembership` in [project-service.dtrx](project-service.dtrx), `accessTo` in [task-service.dtrx](task-service.dtrx) |
| A per-project number handed out under a lock, so two tasks never share WEB-42 | `nextNumber` in [project-service.dtrx](project-service.dtrx) |
| Several rows changed in one transaction: finishing a task frees what waits on it | `finish` in [task-service.dtrx](task-service.dtrx) |
| A GraphQL API beside the REST one, answering only with the caller's own tasks | `TaskGraph` in [task-service.dtrx](task-service.dtrx) |
| An event turned into a stored notice, then a delivery, so a vendor being down loses nothing | `tell`, `deliver` and `RetryNotices` in [notice-service.dtrx](notice-service.dtrx) |
| An append-only activity feed | `Activity` in [task-service.dtrx](task-service.dtrx) |
| A once-a-day report from a job that runs more often | `TellOverdueTasks` in [task-service.dtrx](task-service.dtrx) |
| Two apps for two audiences, one on web and mobile, with no id or key on any page | [workspace-app.dtrx](workspace-app.dtrx), [desk-app.dtrx](desk-app.dtrx) |
| Third parties behind `extern service` contracts, one with a path variable and a body | [providers/](providers/) |
| Mock vendors that authenticate callers with API keys, storing only hashes | [mocks/](mocks/) |

## The parts

| Part | Port | What it does |
|---|---|---|
| Workspace app | 4200 | What is on your plate, your projects, each project's board. Also generated as a Flutter app |
| Desk app | 4300 | Every task, the notices and the vendor pages, for an operator |
| `ProjectService` | 8001 | Projects, members and milestones, and the application's identity block |
| `TaskService` | 8002 | Tasks, blockers, comments and activity |
| `NoticeService` | 8003 | Turns events into chat messages and emails |
| `ChatMock` | 8090 | Stands in for the team chat vendor |
| `EmailMock` | 8091 | Stands in for the email vendor |

## Third parties

The product services call a contract and do not know a mock answers it. To use a real vendor, point the URL in [config/providers/](config/providers/) at it and supply the secret. No `.dtrx` file changes.

| Contract | Mock | What the mock does |
|---|---|---|
| `ChatProvider` | `ChatMock` | Keeps every message by channel. A channel named `closed` refuses them, so a notice stays undelivered and is tried again |
| `EmailProvider` | `EmailMock` | Keeps every email in an outbox. An address at `bounce.example.com` bounces |

## Run it

```bash
datrix generate -s examples/03-domains/task-management/system.dtrx -L python
cd <the generated output>
cp .env.example .env
./scripts/deploy.sh        # Windows: scripts\deploy.ps1
```

TypeScript generates from the same source with `-L typescript`. Only one example can hold the default ports at a time, and `.env` moves them.

Then open:

- Workspace: <http://localhost:4200>
- Desk: <http://localhost:4300>

## Things to try

1. **See what is yours.** Sign up as `sam@millrace.example.com`. The home page shows Sam's tasks, with WEB-2 and LCH-1 overdue.
2. **Hit the rule.** Open the New website board and drag WEB-5 to In progress. The service refuses, because WEB-3 blocks it.
3. **Clear the way.** Drag WEB-3 to Done. WEB-5's warning goes away, and the Desk's Chat page has the news within a moment.
4. **Try to read someone else's project.** Sign up as anyone else. Neither project appears, and opening a board's address gets "Project not found".
5. **Be a viewer.** Sign up as `priya@millrace.example.com`. Priya can read the website project, but there is no New task button, and the service refuses a drag.
6. **Give someone a task.** Open WEB-6 and give it to Maya. An email reaches the Desk's Outbox a moment later, sent by an event.
7. **Watch a refusal.** Start a project with `closed` as its chat channel and finish a task on it. The Desk's Notices page shows it undelivered, with its attempts counting up.

## Sign-in and roles

Sign-in runs on the Zitadel in the stack, so nothing here handles a password. Anyone can sign up and start a project. A person's address is what ties them to the seeded projects. The Desk needs `operator`, which is granted, never self-assigned: sign in to the Zitadel console at <http://localhost:8085/ui/console> as the admin named in `.env`, then grant the role on the `millrace-identity` project.

## The development keys

`config/notice-service.dcfg` carries a `localDefault` for each vendor key, named `dev-only-…-not-a-credential`, and `seed/` holds its SHA-256 hash. Both only let this stack's services reach this stack's mocks. Any other deployment has to supply its own value.
