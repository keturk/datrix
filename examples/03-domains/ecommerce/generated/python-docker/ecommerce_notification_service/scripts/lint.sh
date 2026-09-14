#!/usr/bin/env bash
# Lint ecommerce.NotificationService

set -e
ruff check .
mypy .
