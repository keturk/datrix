#!/usr/bin/env bash
# Lint taskmgmt.UserService

set -e
ruff check .
mypy .
