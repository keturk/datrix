#!/usr/bin/env bash
# Lint library.BookService

set -e
ruff check .
mypy .
