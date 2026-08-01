#!/usr/bin/env bash
# Install dependencies for library.BookService

set -e
./mvnw -B dependency:resolve
