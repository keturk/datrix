# Blog CMS

A content management system for blogs and articles with author management, content publishing, and commenting.

## Services

| Service | Port | Description |
|---------|------|-------------|
| AuthorService | 8000 | Author profiles, authentication, and management |
| ContentService | 8001 | Articles, drafts, categories, and publishing workflow |
| CommentService | 8002 | Reader comments, threading, and moderation |

## Infrastructure

### Databases
- **PostgreSQL** - Each service has its own database
  - `blog_authors` - Author profiles and credentials
  - `blog_content` - Articles, categories, and tags
  - `blog_comments` - Comments and moderation status

### Message Queue
- **Kafka** - Event-driven communication
  - Topics: `AuthorEvents`, `ContentEvents`, `CommentEvents`

### Caching
- **Redis** - Content caching and session storage

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

- Author profiles with bio, avatar, and social links
- Article drafts with publish/unpublish/schedule workflow
- Rich content with categories, tags, and SEO metadata
- Comment threading with nested replies
- Comment moderation (pending, approved, spam)
- Event-driven notifications for new comments
- Content versioning and revision history

## Usage

```bash
# Generate Python services with Docker
datrix generate examples/02-domains/blog-cms/system.dtrx -l python -p docker

# Generate TypeScript services with Kubernetes
datrix generate examples/02-domains/blog-cms/system.dtrx -l typescript -p kubernetes
```

## Files

```
blog-cms/
├── system.dtrx                 # Entry point - system configuration
├── author-service.dtrx         # Author profiles and authentication
├── content-service.dtrx        # Articles, categories, and publishing
├── comment-service.dtrx        # Comments and moderation
└── config/
    ├── config.yaml             # Application configuration
    ├── discovery.yaml          # Service discovery (Consul/Kubernetes)
    ├── gateway.yaml            # API gateway (JWT, rate limits, CORS)
    ├── observability.yaml      # Metrics, tracing, logging
    ├── author-service/
    │   ├── datasources.yaml    # PostgreSQL, Redis, Kafka
    │   ├── resilience.yaml     # Timeouts, retries, circuit breakers
    │   ├── integrations.yaml   # External service configs
    │   ├── registration.yaml   # Service registration
    ├── content-service/
    │   └── ...
    └── comment-service/
        └── ...
```
