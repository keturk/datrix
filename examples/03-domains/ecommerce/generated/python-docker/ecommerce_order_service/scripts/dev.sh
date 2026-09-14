#!/usr/bin/env bash
# Start development server for ecommerce.OrderService

set -e
uvicorn main:app --reload
