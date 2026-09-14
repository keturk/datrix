#!/usr/bin/env bash
# Lint ecommerce.ShippingService

set -e
ruff check .
mypy .
