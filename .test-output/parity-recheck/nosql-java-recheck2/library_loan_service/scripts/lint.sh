#!/usr/bin/env bash
# Lint library.LoanService

set -e
./mvnw -q -DskipTests compile
