#!/usr/bin/env bash
# Moves the branch vMAJOR to the commit of the release tag being published.
#
# Reads GITHUB_REF_NAME (the tag, vX.Y.Z) and GITHUB_SHA. The remote is
# "origin" unless REMOTE says otherwise, which is how the test runs it.
set -euo pipefail

version="${GITHUB_REF_NAME#v}"
# Only a plain vX.Y.Z moves the branch. A pre-release must not become what
# every caller runs.
case "$version" in
  *[!0-9.]*) echo "$GITHUB_REF_NAME is not a plain vX.Y.Z tag; the major branch stays where it is."; exit 0 ;;
  *.*.*) ;;
  *) echo "$GITHUB_REF_NAME is not a plain vX.Y.Z tag; the major branch stays where it is."; exit 0 ;;
esac

branch="v${version%%.*}"
echo "moving $branch to $GITHUB_SHA ($GITHUB_REF_NAME)"
# No --force: git refuses a push that is not a fast-forward.
git push "${REMOTE:-origin}" "$GITHUB_SHA:refs/heads/$branch"
