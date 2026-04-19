#!/usr/bin/env bash
# Start development server for taskmgmt.TaskService

set -e
uvicorn main:app --reload
