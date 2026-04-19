# ---- Builder stage ----
FROM python:3.12-slim AS builder

WORKDIR /app

# Install dependencies (cached until requirements.txt changes)
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Install package (fast rebuild with --no-deps, --no-build-isolation uses pre-installed build tools)
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps --no-build-isolation .

# ---- Runtime stage ----
FROM python:3.12-slim AS runtime

WORKDIR /app

# Create non-root user
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

# Copy installed packages, CLI scripts, and application from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/
COPY --from=builder /app/src/ ./src/

# Copy Alembic migration configuration and scripts
COPY alembic-db.ini ./
COPY migrations-db/ ./migrations-db/

# Set environment variables
ENV PORT=8012
ENV SERVICE_NAME=taskmgmt-task-service

# Expose service port
EXPOSE 8012

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8012/health')" || exit 1

# Switch to non-root user
USER appuser

# Run the application
CMD ["python", "-m", "uvicorn", "taskmgmt_task_service.main:app", "--host", "0.0.0.0", "--port", "8012"]
