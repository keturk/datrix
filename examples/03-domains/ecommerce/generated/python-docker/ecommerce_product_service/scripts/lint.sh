#!/usr/bin/env bash
# Lint ecommerce.ProductService

set -e
ruff check .
mypy .
