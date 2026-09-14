#!/usr/bin/env bash
# Install dependencies for ecommerce.ProductService

set -e
./mvnw -B dependency:resolve
