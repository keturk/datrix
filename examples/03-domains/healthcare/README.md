# Healthcare System

A healthcare management system for patient records, appointments, and medical history.

## Services

| Service | Port | Description |
|---------|------|-------------|
| PatientService | 8000 | Patient registration, demographics, and profiles |
| AppointmentService | 8001 | Appointment scheduling and availability management |
| MedicalRecordService | 8002 | Medical records, diagnoses, and treatment history |

## Infrastructure

### Databases
- **PostgreSQL** - Each service has its own database with encryption at rest
  - `healthcare_patients` - Patient demographics and contact info
  - `healthcare_appointments` - Appointments and scheduling
  - `healthcare_records` - Medical records and history

### Message Queue
- **Kafka** - Event-driven communication
  - Topics: `PatientEvents`, `AppointmentEvents`, `MedicalRecordEvents`

### Caching
- **Redis** - Session storage and availability caching

### Service Discovery
- **Consul** (development) / **Kubernetes** (production)

### Observability
- **Prometheus** - Metrics collection
- **Jaeger** - Distributed tracing
- **JSON logging** - Structured logs with audit trail

### API Gateway
- **JWT authentication** (HS256)
- **Rate limiting** per endpoint
- **CORS** configuration

## Key Features

- Patient demographics with contact information
- Medical record number (MRN) generation
- Appointment scheduling with provider availability
- Appointment status workflow (scheduled → confirmed → completed)
- Medical record history with diagnoses and treatments
- Provider assignment and referral tracking
- Appointment reminders via events
- Audit logging for compliance

## Usage

```bash
# Generate Python services with Docker
datrix generate examples/02-domains/healthcare/system.dtrx -l python -p docker

# Generate TypeScript services with Kubernetes
datrix generate examples/02-domains/healthcare/system.dtrx -l typescript -p kubernetes
```

## Files

```
healthcare/
├── system.dtrx                     # Entry point - system configuration
├── common.dtrx                     # Shared healthcare types
├── patient-service.dtrx            # Patient management
├── appointment-service.dtrx        # Scheduling and availability
├── medical-record-service.dtrx     # Medical records and history
└── config/
    ├── config.yaml                 # Application configuration
    ├── discovery.yaml              # Service discovery (Consul/Kubernetes)
    ├── gateway.yaml                # API gateway (JWT, rate limits, CORS)
    ├── observability.yaml          # Metrics, tracing, logging
    ├── patient-service/
    │   ├── datasources.yaml        # PostgreSQL, Redis, Kafka
    │   ├── resilience.yaml         # Timeouts, retries, circuit breakers
    │   ├── registration.yaml       # Service registration
    ├── appointment-service/
    │   ├── integrations.yaml       # External calendar/notification services
    │   └── ...
    └── medical-record-service/
        └── ...
```
