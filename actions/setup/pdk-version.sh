#!/usr/bin/env bash
set -euo pipefail
image=$1
source=/opt/c4o-core/scripts/entrypoint.py
version=$(docker run --rm --entrypoint grep "$image" -oE 'commit_hash = "[0-9a-f]{40}"' "$source" | grep -oE '[0-9a-f]{40}' || true)
if [ "$(wc -w <<<"$version")" -ne 1 ]; then
  echo "::error::Could not read one PDK version out of $image (found: '$version')."
  exit 1
fi
echo "version=$version" >> "$GITHUB_OUTPUT"
