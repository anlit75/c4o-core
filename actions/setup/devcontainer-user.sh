#!/usr/bin/env bash
# The Dev Container runs as a named user. That user comes from the base image,
# so check it is really there -- otherwise an image rebuild breaks the Dev
# Container silently, in a way nothing else would catch.
set -euo pipefail
if [ ! -f .devcontainer/devcontainer.json ]; then
  echo "No .devcontainer/devcontainer.json here -- nothing to check."
  exit 0
fi
set -- $(python3 -c "
import json, re
src = open('.devcontainer/devcontainer.json').read()
d = json.loads(re.sub(r'^\s*//.*$', '', src, flags=re.M))
print(d['image'], d.get('remoteUser', ''))
")
if [ -z "${2:-}" ]; then
  echo "devcontainer.json names no remoteUser -- nothing to check."
  exit 0
fi
echo "image=$1 remoteUser=$2"
docker run --rm --entrypoint id "$1" -u "$2"
