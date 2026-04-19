# taskmgmt.ProjectService

Version: 1.0.0
## Quick start

```bash
# Install dependencies
# See scripts/install.sh

# Run service (port 8011)
# See scripts/dev.sh
```

## Entities

| Entity | Fields | Primary key |
|--------|--------|-------------|
| Project | id, createdAt, updatedAt, name, ownerId | id |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/projects/projects | list_projects |
| GET | /api/v1/projects/projects/:id | get_project |
| POST | /api/v1/projects/projects | create_project |
| PUT | /api/v1/projects/projects/:id | update_project |
| DELETE | /api/v1/projects/projects/:id | delete_project |



## Environment variables

See `.env.example` for required environment variables.

## Dependencies

- taskmgmt.UserService
