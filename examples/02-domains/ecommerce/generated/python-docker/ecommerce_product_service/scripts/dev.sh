#!/usr/bin/env bash
# Start development server for ecommerce.ProductService

set -e
uvicorn main:app --reload
