#!/usr/bin/env bash
# Install dependencies for warehouse.WarehouseService

set -e
./mvnw -B dependency:resolve
