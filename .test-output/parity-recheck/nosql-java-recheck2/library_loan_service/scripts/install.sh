#!/usr/bin/env bash
# Install dependencies for library.LoanService

set -e
./mvnw -B dependency:resolve
