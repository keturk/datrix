#!/usr/bin/env bash
# Start development server for ecommerce.ShippingService

set -e
uvicorn main:app --reload
