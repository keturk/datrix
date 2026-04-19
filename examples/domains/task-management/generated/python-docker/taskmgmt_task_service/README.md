# taskmgmt.TaskService

Version: 1.0.0
## Quick start

```bash
# Install dependencies
# See scripts/install.sh

# Run service (port 8012)
# See scripts/dev.sh
```

## Entities

| Entity | Fields | Primary key |
|--------|--------|-------------|
| Task | id, createdAt, updatedAt, projectId, assigneeId, title, completed | id |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/tasks/tasks | list_tasks |
| GET | /api/v1/tasks/tasks/:id | get_task |
| POST | /api/v1/tasks/tasks | create_task |
| PUT | /api/v1/tasks/tasks/:id | update_task |
| DELETE | /api/v1/tasks/tasks/:id | delete_task |



## Environment variables

See `.env.example` for required environment variables.

## Dependencies

- taskmgmt.ProjectService
- taskmgmt.UserService
