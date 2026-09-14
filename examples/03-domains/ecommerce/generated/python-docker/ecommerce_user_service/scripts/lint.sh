#!/usr/bin/env bash
# Lint ecommerce.UserService

set -e
ruff check .
mypy .
