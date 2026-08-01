# library.MemberService

Version: 1.0.0
## Quick start

```bash
# Install dependencies
# See scripts/install.sh

# Run service (port 8001)
# See scripts/dev.sh
```

## Entities

| Entity | Fields | Primary key |
|--------|--------|-------------|
| Member | createdAt, updatedAt, id, name, email, emailVerificationToken | id |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/members/members | list_members |
| GET | /api/v1/members/members/:id | get_member |
| POST | /api/v1/members/members | create_member |
| PUT | /api/v1/members/members/:id | update_member |
| DELETE | /api/v1/members/members/:id | delete_member |






## Runtime configuration

Runtime configuration is resolved from generated bootstrap constants, the runtime config store, and the secrets resolver. This service does not use a `.env.example` contract.

