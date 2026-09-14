#!/usr/bin/env bash
# Lint ecommerce.PaymentService

set -e
./mvnw -q -DskipTests compile
