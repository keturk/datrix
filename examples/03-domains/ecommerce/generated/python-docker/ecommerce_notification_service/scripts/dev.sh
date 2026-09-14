#!/usr/bin/env bash
# Start development server for ecommerce.NotificationService

set -e
uvicorn main:app --reload
