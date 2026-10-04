#!/usr/bin/env bash
# One page with what `make report` prints, the layout, the schematic and the
# cocotb verdicts.
set -euo pipefail
make site
ls -lh build/site/

# After make gds these four come from the run's own reports. Each is left out
# silently when its report is missing, so a LibreLane upgrade that moved one
# would otherwise just shrink the page.
sections=("Signoff checks" "Worst setup path" "Area" "Power")
# Only when asked for: deleting the key is how a design opts out of it.
if grep -q '^"//WAVE_SIGNALS":' config.yaml; then
  sections+=("Waveform")
fi
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
