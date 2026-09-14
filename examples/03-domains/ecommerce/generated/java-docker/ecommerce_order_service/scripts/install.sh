#!/usr/bin/env bash
# Install dependencies for ecommerce.OrderService

set -e
./mvnw -B dependency:resolve
