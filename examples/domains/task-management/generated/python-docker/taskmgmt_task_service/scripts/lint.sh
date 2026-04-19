#!/usr/bin/env bash
# Lint taskmgmt.TaskService

set -e
ruff check .
mypy .
