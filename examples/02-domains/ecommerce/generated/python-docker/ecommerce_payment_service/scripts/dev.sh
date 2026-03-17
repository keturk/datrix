#!/usr/bin/env bash
# Start development server for ecommerce.PaymentService

set -e
uvicorn main:app --reload
