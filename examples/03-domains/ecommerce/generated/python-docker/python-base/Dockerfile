# Shared per-system base image.
# Installs the UNION of every service's requirements ONCE; per-service
# Dockerfiles are FROM this image and add only their own thin app-code layer.
FROM python:3.12-slim AS runtime

# Unbuffered stdio so a crash cannot swallow the last log lines before the
# process dies. CPython block-buffers stdout whenever it is not a TTY (always
# the case under a container, whose stdout is a pipe), so a fatal error --
# followed by definition by process death -- is the single most likely thing
# to be lost with the buffer. PYTHONFAULTHANDLER additionally dumps a C-level
# traceback on a hard crash (segfault, OOM kill) that the Python logging path
# cannot capture at all. Set on the base so all service images inherit it.
ENV PYTHONUNBUFFERED=1
ENV PYTHONFAULTHANDLER=1

WORKDIR /app

# Install union of all services' dependencies (cached until the union
# requirements content changes -- see BaseImageBuilder.base_image_tag()).
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Create non-root user (each service image inherits this; per-service
# Dockerfiles switch to it again after copying their own app code).
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser
