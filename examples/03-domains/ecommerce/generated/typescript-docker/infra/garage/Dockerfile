# Garage, the self-hosted S3-compatible server behind every compose-local
# storage block. The upstream image is a scratch image holding one static
# binary and runs as root; this build only adds a data directory owned by an
# unprivileged user, so a fresh named volume mounted there inherits that
# ownership and the server never runs as root.

# ---- Data directory preparation ----
FROM alpine:3.22.6 AS prep

RUN mkdir -p /var/lib/garage/meta /var/lib/garage/data \
    && chown -R 1000:1000 /var/lib/garage

# ---- Runtime ----
FROM dxflrs/garage:v2.4.1

COPY --from=prep --chown=1000:1000 /var/lib/garage /var/lib/garage

USER 1000:1000
