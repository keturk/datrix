# Multi-stage build for WarehouseService (Java 25 / Spring Boot 4.1)
FROM eclipse-temurin:25-jdk AS build
WORKDIR /app

# Install dependencies first (layer caching) via the Maven wrapper.
COPY .mvn/ .mvn/
COPY mvnw pom.xml ./
RUN chmod +x mvnw && ./mvnw -B -q -DskipTests dependency:go-offline

# Copy application source and build the fat jar.
COPY src/ src/
RUN ./mvnw -B -DskipTests package

FROM eclipse-temurin:25-jre AS runtime
WORKDIR /app

# target/*.jar must resolve to exactly one artifact -- guaranteed by the
# generated pom.xml's packaging config, not by shell logic here.
COPY --from=build /app/target/*.jar /app/app.jar

# Set environment variables
ENV PORT=8000
ENV SERVICE_NAME=warehouse-warehouse-service

# Expose service port
EXPOSE 8000

# Health check (runtime image ships busybox wget)
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8000/health || exit 1

# Run the application
CMD ["java", "-jar", "/app/app.jar"]
