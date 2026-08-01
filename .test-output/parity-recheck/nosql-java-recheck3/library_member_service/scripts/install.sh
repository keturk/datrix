#!/usr/bin/env bash
# Install dependencies for library.MemberService

set -e
./mvnw -B dependency:resolve
