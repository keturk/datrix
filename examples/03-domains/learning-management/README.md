# Learning Management System

An educational platform for online courses, student enrollment, and progress tracking.

## Services

| Service | Port | Description |
|---------|------|-------------|
| CourseService | 8000 | Course catalog, modules, and lessons |
| EnrollmentService | 8001 | Student enrollment and progress tracking |
| StudentService | 8002 | Student profiles and achievements |

## Infrastructure

### Databases
- **PostgreSQL** - Each service has its own database
  - `lms_courses` - Courses, modules, and lesson content
  - `lms_enrollments` - Enrollment records and progress
  - `lms_students` - Student profiles and achievements

### Message Queue
- **Kafka** - Event-driven communication
  - Topics: `CourseEvents`, `EnrollmentEvents`, `StudentEvents`

### Caching
- **Redis** - Course content caching and session storage

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

- Course catalog with modules and lessons
- Lesson content with video, text, and attachments
- Student enrollment workflow
- Progress tracking per module and lesson
- Quiz and assignment management
- Completion certificates generation
- Instructor course management
- Event-driven deadline notifications
- Achievement badges and gamification

## Usage

```bash
# Generate Python services with Docker
datrix generate examples/02-domains/learning-management/system.dtrx -l python -p docker

# Generate TypeScript services with Kubernetes
datrix generate examples/02-domains/learning-management/system.dtrx -l typescript -p kubernetes
```

## Files

config/ contains the ConfigDSL files referenced by system.dtrx and each service:
    - config/course-service.dcfg
    - config/enrollment-service.dcfg
    - config/student-service.dcfg
    - config/system.dcfg

