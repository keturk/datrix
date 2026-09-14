#!/usr/bin/env bash
# Lint ecommerce.ShippingService

set -e
./mvnw -q -DskipTests compile
