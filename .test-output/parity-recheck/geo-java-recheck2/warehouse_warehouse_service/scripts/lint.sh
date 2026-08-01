#!/usr/bin/env bash
# Lint warehouse.WarehouseService

set -e
./mvnw -q -DskipTests compile
