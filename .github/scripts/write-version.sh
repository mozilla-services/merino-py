#!/usr/bin/env bash
set -eu

printf '{"commit":"%s","version":"%s","source":"%s","build":"%s"}\n' \
  "$GITHUB_SHA" "$GITHUB_REF_NAME" \
  "$GITHUB_SERVER_URL/$GITHUB_REPOSITORY" \
  "$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID" > version.json
