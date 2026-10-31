#!/usr/bin/env bash
set -euo pipefail
answer="$RUNNER_TEMP/pages.json"
settings="${GITHUB_SERVER_URL:-https://github.com}/$GITHUB_REPOSITORY/settings/pages"
# The notice and the job summary both carry the address of the setting, so a
# first run says where to click and not only what to set.
not_published() {  # not_published <why>
  echo "::notice::$1 Open $settings and set Source to GitHub Actions to publish it."
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    printf '### Results page not published\n\n%s [Settings > Pages](%s): set Source to GitHub Actions, then run this workflow again.\n' \
      "$1" "$settings" >> "$GITHUB_STEP_SUMMARY"
  fi
}
code=$(curl -sS -o "$answer" -w '%{http_code}' \
  -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json" \
  "$GITHUB_API_URL/repos/$GITHUB_REPOSITORY/pages")
case "$code" in
  200)
    build_type=$(python3 -c "import json, sys; print(json.load(open(sys.argv[1])).get('build_type'))" "$answer")
    if [ "$build_type" = workflow ]; then
      echo "publish=true" >> "$GITHUB_OUTPUT"
      # Where the page is live, for the step that fetches its history.json.
      python3 -c "import json, sys; print('url=' + (json.load(open(sys.argv[1])).get('html_url') or ''))" "$answer" >> "$GITHUB_OUTPUT"
    else
      not_published "GitHub Pages publishes from a branch here (build_type: $build_type), so the results page was not published."
    fi ;;
  404)
    not_published "GitHub Pages is off for this repository, so the results page was not published." ;;
  *)
    echo "::error::Asking GitHub whether Pages is on returned HTTP $code:"
    cat "$answer"
    exit 1 ;;
esac
