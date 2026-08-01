#!/usr/bin/env bash
# Start development server for library.BookService

set -e
uvicorn main:app --reload
