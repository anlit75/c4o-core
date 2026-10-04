#!/usr/bin/env bash
set -euo pipefail
answer="$RUNNER_TEMP/pages.json"
code=$(curl -sS -o "$answer" -w '%{http_code}' \
  -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json" \
  "$GITHUB_API_URL/repos/$GITHUB_REPOSITORY/pages")
case "$code" in
  200)
    build_type=$(python3 -c "import json, sys; print(json.load(open(sys.argv[1])).get('build_type'))" "$answer")
    if [ "$build_type" = workflow ]; then
      echo "publish=true" >> "$GITHUB_OUTPUT"
    else
      echo "::notice::GitHub Pages publishes from a branch here (build_type: $build_type), so the results page was not published. Settings > Pages > Source: GitHub Actions publishes it."
    fi ;;
  404)
    echo "::notice::GitHub Pages is off for this repository, so the results page was not published. Settings > Pages > Source: GitHub Actions turns it on." ;;
  *)
    echo "::error::Asking GitHub whether Pages is on returned HTTP $code:"
    cat "$answer"
    exit 1 ;;
esac
