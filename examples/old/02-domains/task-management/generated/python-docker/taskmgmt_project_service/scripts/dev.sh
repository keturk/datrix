#!/usr/bin/env bash
# Start development server for taskmgmt.ProjectService

set -e
uvicorn main:app --reload
