#!/usr/bin/env bash
set -euo pipefail
image=$(grep -E '^C4O_IMAGE :=' Makefile | sed 's/.*:= *//')
docker pull "$image"
echo "image=$image" >> "$GITHUB_OUTPUT"
