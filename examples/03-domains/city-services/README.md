# City Services

A city government platform managing districts, public facilities, parks, and citizen service requests with spatial data. This example demonstrates the **geo extension** for PostGIS-backed spatial operations.

## Services

| Service | Port | Description |
|---------|------|-------------|
| DistrictService | 8001 | City districts and zoning areas with polygon boundaries |
| FacilityService | 8002 | Public facilities (point locations) and parks (polygon boundaries) |
| RequestService | 8003 | Citizen service requests with location context |

## Geo Extension Features

This example requires `use extension geo;` in the system block and demonstrates:

### GeoSql (SQL-level spatial queries)

| Function | Usage |
|----------|-------|
| `GeoSql.containsPoint(boundary, lat, lng)` | Find districts/parks containing a point |
| `GeoSql.withinDistanceMeters(location, lat, lng, meters)` | Find nearby facilities and requests |
| `GeoSql.distanceMeters(location, lat, lng)` | Order results by proximity |
| `GeoSql.area(boundary)` | Order districts/parks by area |
| `GeoSql.centroid(boundary)` | Compute district centroids |

### GeoShape (value-level geometry operations)

| Function | Usage |
|----------|-------|
| `GeoShape.area(geometry)` | Compute area for a single entity |
| `GeoShape.centroid(geometry)` | Compute centroid for a single entity |
| `GeoShape.containsPoint(geometry, lat, lng)` | Check if a point falls inside a boundary |
| `GeoShape.toGeoJson(geometry)` | Convert boundary to GeoJSON for map rendering |
| `GeoShape.fromGeoJson(geojsonText)` | Accept GeoJSON input from citizens |
| `GeoShape.toWkt(geometry)` | Convert geometry to WKT format |
| `GeoShape.fromWkt(wktText)` | Parse WKT string to geometry |

## Infrastructure

- **Databases**: PostgreSQL with PostGIS extension (one per service)
- **Message Queue**: Kafka for event-driven communication
- **Cache**: Redis for district and facility caching
- **Service Discovery**: Consul
- **Observability**: Prometheus, Jaeger, Loki, Grafana

## Key Features

- Spatial entity fields with automatic GiST index generation
- SQL-level spatial predicates for efficient database queries
- Value-level geometry operations for application logic
- GeoJSON conversion for map rendering integration
- Cross-service event subscriptions for location-aware routing
- Full-text search on service request titles and descriptions

## Usage

```bash
# Generate Python service
datrix generate examples/03-domains/city-services/system.dtrx -l python -p docker

# Generate TypeScript service
datrix generate examples/03-domains/city-services/system.dtrx -l typescript -p docker
```

## Files

### Datrix Files
- `system.dtrx` — Entry point with geo extension declaration
- `common.dtrx` — Shared enums and utility functions
- `district-service.dtrx` — District and zoning management
- `facility-service.dtrx` — Facility and park management
- `request-service.dtrx` — Service request management

### Configuration
- `config/system.dcfg` — System-level configuration
- `config/district-service.dcfg` — District service configuration
- `config/facility-service.dcfg` — Facility service configuration
- `config/request-service.dcfg` — Request service configuration
