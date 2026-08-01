#!/usr/bin/env bash
# Lint library.BookService

set -e
./mvnw -q -DskipTests compile
