#!/bin/sh
set -e
mc alias set local http://ingestion-pipeline-minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
mc mb local/files --ignore-existing
echo "Bucket files created successfully"
