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
- **Consul** (development) / **Kubernetes** (production)

### Observability
- **Prometheus** - Metrics collection
- **Jaeger** - Distributed tracing
- **JSON logging** - Structured logs

### API Gateway
- **JWT authentication** (HS256)
- **Rate limiting** per endpoint
- **CORS** configuration

## Key Features

- Team member management with roles (admin, member, viewer)
- Project creation with description and deadlines
- Project team assignment and permissions
- Milestone tracking with target dates
- Task creation with title, description, and priority
- Task assignment to team members
- Status workflow (todo → in progress → review → done)
- Due date tracking with overdue detection
- Labels and categories for task organization
- Event-driven assignment notifications
- Activity feed and audit log

## Usage

```bash
# Generate Python services with Docker
datrix generate examples/02-domains/task-management/system.dtrx -l python -p docker

# Generate TypeScript services with Kubernetes
datrix generate examples/02-domains/task-management/system.dtrx -l typescript -p kubernetes
```

## Files

```
task-management/
├── system.dtrx                 # Entry point - system configuration
├── user-service.dtrx           # Team member management
├── project-service.dtrx        # Project and milestone management
├── task-service.dtrx           # Task tracking and assignments
└── config/
    ├── config.yaml             # Application configuration
    ├── discovery.yaml          # Service discovery (Consul/Kubernetes)
    ├── gateway.yaml            # API gateway (JWT, rate limits, CORS)
    ├── observability.yaml      # Metrics, tracing, logging
    ├── user-service/
    │   ├── datasources.yaml    # PostgreSQL, Redis, Kafka
    │   ├── resilience.yaml     # Timeouts, retries, circuit breakers
    │   ├── registration.yaml   # Service registration
    ├── project-service/
    │   └── ...
    └── task-service/
        └── ...
```
