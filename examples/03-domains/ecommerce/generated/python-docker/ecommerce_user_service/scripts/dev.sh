#!/usr/bin/env bash
# Start development server for ecommerce.UserService

set -e
uvicorn main:app --reload
