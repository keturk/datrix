# Social Platform

A social networking platform with user profiles, posts, and notifications.

## Services

| Service | Port | Description |
|---------|------|-------------|
| UserService | 8000 | User profiles, followers, and connections |
| PostService | 8001 | Posts, comments, likes, and media |
| NotificationService | 8002 | Real-time and push notifications |

## Infrastructure

### Databases
- **PostgreSQL** - Each service has its own database
  - `social_users` - User profiles and connections
  - `social_posts` - Posts, comments, and likes
  - `social_notifications` - Notification records

### Message Queue
- **Kafka** - Event-driven communication
  - Topics: `UserEvents`, `PostEvents`, `NotificationEvents`

### Caching
- **Redis** - Feed caching, session storage, and real-time presence

### Service Discovery
- **Consul** (development) / **Kubernetes** (production)

### Observability
- **Prometheus** - Metrics collection
- **Jaeger** - Distributed tracing
- **JSON logging** - Structured logs

### API Gateway
- **JWT authentication** (RS256)
- **Rate limiting** per user and endpoint
- **CORS** configuration

## Key Features

- User profiles with bio, avatar, and settings
- Follow/unfollow with followers/following lists
- Post creation with text, images, and videos
- Comments with nested threading
- Likes and reactions on posts
- Real-time notification delivery
- Push notifications for mobile
- Feed generation with algorithmic ranking
- Privacy controls (public, friends, private)
- User blocking and muting

## Usage

```bash
# Generate Python services with Docker
datrix generate examples/02-domains/social-platform/system.dtrx -l python -p docker

# Generate TypeScript services with Kubernetes
datrix generate examples/02-domains/social-platform/system.dtrx -l typescript -p kubernetes
```

## Files

config/ contains the ConfigDSL files referenced by system.dtrx and each service:
    - config/notification-service.dcfg
    - config/post-service.dcfg
    - config/system.dcfg
    - config/user-service.dcfg

