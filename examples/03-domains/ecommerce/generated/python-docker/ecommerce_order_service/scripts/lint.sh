#!/usr/bin/env bash
# Lint ecommerce.OrderService

set -e
ruff check .
mypy .
