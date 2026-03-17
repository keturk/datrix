#!/usr/bin/env bash
# Lint taskmgmt.ProjectService

set -e
ruff check .
mypy .
