# Per-service image: thin layer on the shared per-system base.
FROM library-system-python-base:138a7c14f0ab AS runtime

WORKDIR /app

# Copy this service's application code onto the shared base's dependencies.
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps --no-build-isolation .

# Set environment variables
ENV PORT=8000
ENV SERVICE_NAME=library-book-service

# Expose service port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/ready')" || exit 1

# Switch to non-root user
USER appuser

# Run the application. Wrap in ``sh -c exec`` so the shell expands ${PORT}
# (the entrypoint binds to ${PORT}, injected via ENV/compose): a bare exec-form
# CMD bypasses the shell and would pass the literal string "${PORT}" to gunicorn.
# ``exec`` replaces the shell with gunicorn so it stays PID 1 (clean SIGTERM/SIGINT).
CMD ["sh", "-c", "exec gunicorn --bind=0.0.0.0:${PORT} --timeout 600 -k uvicorn.workers.UvicornWorker library_book_service.main:app"]
