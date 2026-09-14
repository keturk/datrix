#!/usr/bin/env bash
# Lint ecommerce.PaymentService

set -e
ruff check .
mypy .
