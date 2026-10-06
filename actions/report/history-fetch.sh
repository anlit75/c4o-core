#!/usr/bin/env bash
# The history of the earlier runs, from the page they published. The deploy job
# replaces the whole site, so the page that is live now is the only place the
# earlier rows are. `make site` adds this run's row to build/history.json.
# PAGES_URL is the address of the live page, from the Pages step.
set -euo pipefail
if [ -z "${PAGES_URL:-}" ]; then
  echo "::error::GitHub Pages named no address for the page, so its history.json cannot be fetched."
  exit 1
fi
url="${PAGES_URL%/}/history.json"
answer="$RUNNER_TEMP/history.json"
# A request that cannot be made at all has no HTTP code: curl prints 000, and
# it is reported below like any other answer that is not 200 or 404.
code=$(curl -sS -L --retry 3 -o "$answer" -w '%{http_code}' "$url") || true
case "$code" in
  200)
    mkdir -p build
    mv "$answer" build/history.json
    echo "Fetched the history of earlier runs from $url" ;;
  404)
    # Normal on the first run, and on the first run after an image that wrote
    # no history.json. Not a failure.
    echo "::notice::$url does not exist yet, so the history of this page starts with this run." ;;
  *)
    echo "::error::Fetching $url returned HTTP $code."
    exit 1 ;;
esac
