#!/usr/bin/env bash
# Start development server for taskmgmt.UserService

set -e
uvicorn main:app --reload
