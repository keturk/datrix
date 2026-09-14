# Per-service image: thin layer on the shared per-system base.
FROM ecommerce-python-base:102f5a0b5c23 AS runtime

WORKDIR /app

# Copy this service's application code onto the shared base's dependencies.
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps --no-build-isolation .

# Copy Alembic migration configuration and scripts
COPY alembic-shipping-db.ini ./
COPY migrations-shipping-db/ ./migrations-shipping-db/

# Set environment variables
ENV PORT=8005
ENV SERVICE_NAME=ecommerce-shipping-service

# Expose service port
EXPOSE 8005

# Health check: the language's own command against the readiness route the
# language declares it mounts (supplied by its LanguageRuntimeSpec.dockerfile_context).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8005/ready')" || exit 1

# Switch to non-root user
USER appuser

# Run the application. Wrap in ``sh -c exec`` so the shell expands ${PORT}
# (the entrypoint binds to ${PORT}, injected via ENV/compose): a bare exec-form
# CMD bypasses the shell and would pass the literal string "${PORT}" to gunicorn.
# ``exec`` replaces the shell with gunicorn so it stays PID 1 (clean SIGTERM/SIGINT).
CMD ["sh", "-c", "exec gunicorn --bind=0.0.0.0:${PORT} --timeout 600 -k uvicorn.workers.UvicornWorker ecommerce_shipping_service.main:app"]
