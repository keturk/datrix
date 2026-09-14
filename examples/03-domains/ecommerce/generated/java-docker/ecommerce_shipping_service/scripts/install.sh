#!/usr/bin/env bash
# Install dependencies for ecommerce.ShippingService

set -e
./mvnw -B dependency:resolve
