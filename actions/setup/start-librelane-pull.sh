#!/usr/bin/env bash
# Runs in the caller's workspace: the Makefile read here is the caller's.
set -euo pipefail
image=$(grep -E '^LIBRELANE_IMAGE :=' Makefile | sed 's/.*:= *//')
nohup docker pull "$image" > "$RUNNER_TEMP/librelane-pull.log" 2>&1 &
echo "started: docker pull $image"
