#!/usr/bin/env bash
# Install dependencies for ecommerce.UserService

set -e
./mvnw -B dependency:resolve
