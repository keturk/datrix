#!/usr/bin/env bash
# Install dependencies for ecommerce.PaymentService

set -e
./mvnw -B dependency:resolve
