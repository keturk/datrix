#!/usr/bin/env bash
# Install dependencies for ecommerce.NotificationService

set -e
./mvnw -B dependency:resolve
