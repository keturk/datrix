# Task Management

A project and task management system for team collaboration.

## Services

| Service | Port | Description |
|---------|------|-------------|
| UserService | 8000 | Team members, roles, and permissions |
| ProjectService | 8001 | Projects, milestones, and team assignment |
| TaskService | 8002 | Tasks, assignments, and status tracking |

## Infrastructure

### Databases
- **PostgreSQL** - Each service has its own database
  - `taskman_users` - Team members and roles
  - `taskman_projects` - Projects and milestones
  - `taskman_tasks` - Tasks and assignments

### Message Queue
- **Kafka** - Event-driven communication
  - Topics: `UserEvents`, `ProjectEvents`, `TaskEvents`

### Caching
- **Redis** - Session storage and query caching

### Service Discovery
- **Consul**

### Observability
- **Prometheus** - Metrics collection
- **Jaeger** - Distributed tracing
- **JSON logging** - Structured logs

### API Gateway
- **JWT authentication** (RS256)
- **Rate limiting** per endpoint
- **CORS** configuration

## Key Features

- Team member management with roles (admin, member, viewer)
- Project creation with description and deadlines
- Project team assignment and permissions
- Milestone tracking with target dates
- Task creation with title, description, and priority
- Task assignment to team members
- Status workflow (todo â†’ in progress â†’ review â†’ done)
- Due date tracking with overdue detection
- Labels and categories for task organization
- Event-driven assignment notifications
- Activity feed and audit log

## Usage

```bash
# Generate Python services with Docker
datrix generate examples/02-domains/task-management/system.dtrx -l python -p docker

# Generate TypeScript services with Docker
datrix generate examples/02-domains/task-management/system.dtrx -l typescript -p docker
```

## Files

config/ contains the ConfigDSL files referenced by system.dtrx and each service:
    - config/project-service.dcfg
    - config/system.dcfg
    - config/task-service.dcfg
    - config/user-service.dcfg

