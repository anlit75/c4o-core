#!/usr/bin/env bash
# One page with the cocotb verdicts, timing, area, power, signoff and the layout.
set -euo pipefail
make site
ls -lh build/site/

# After make gds these two come from the run's own reports. Each is left out
# silently when its report is missing, so a LibreLane upgrade that moved one
# would otherwise just shrink the page.
# Only the headings that every 2.x image gives its page. This script runs with
# any 2.x image, so it must not demand a section a newer image renamed. The
# page's own structure is tested in c4o-core.
sections=("Power" "Signoff checks")
while IFS= read -r extra; do
  if [ -n "$extra" ]; then
    sections+=("$extra")
  fi
done <<<"${EXTRA_SECTIONS:-}"

for section in "${sections[@]}"; do
  grep -qF "<h2>$section</h2>" build/site/index.html \
    || { echo "::error::The results page has no '$section' section."; exit 1; }
done

# The page names the commit it was built from. c4o-core only writes that line
# when GITHUB_* reach it, which they do only if `make site` passes them into
# the container.
grep -qF "/commit/$GITHUB_SHA" build/site/index.html \
  || { echo "::error::The results page does not link commit $GITHUB_SHA. make site has to pass GITHUB_* into the container."; exit 1; }
printf 'results page has: %s\n' "${sections[*]}"
