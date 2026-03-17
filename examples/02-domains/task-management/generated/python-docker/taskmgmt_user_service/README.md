# taskmgmt.UserService

Version: 1.0.0
## Quick start

```bash
# Install dependencies
# See scripts/install.sh

# Run service (port 8010)
# See scripts/dev.sh
```

## Entities

| Entity | Fields | Primary key |
|--------|--------|-------------|
| User | id, createdAt, updatedAt, name, email | id |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/users/users | list_users |
| GET | /api/v1/users/users/:id | get_user |
| POST | /api/v1/users/users | create_user |
| PUT | /api/v1/users/users/:id | update_user |
| DELETE | /api/v1/users/users/:id | delete_user |



## Environment variables

See `.env.example` for required environment variables.

