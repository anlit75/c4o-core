#!/usr/bin/env bash
# The scripts behind actions/, run against the inputs they exist to refuse.
#
# The actions themselves only run inside somebody's workflow, where a check
# that has stopped failing looks exactly like one that passes. So each case
# here states the exit code it must get, and a script that accepts what it
# should refuse fails this file.
set -uo pipefail

actions=$(cd "$(dirname "$0")/../actions" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failures=0

expect() {  # expect <exit code> <label> <command...>
  local want=$1 label=$2
  shift 2
  local out got
  out=$("$@" 2>&1)
  got=$?
  if [ "$got" -eq "$want" ]; then
    echo "ok    $label"
  else
    echo "FAIL  $label: exit $got, expected $want"
    echo "$out" | sed 's/^/        /'
    failures=$((failures + 1))
  fi
}

for script in "$actions"/*/*.sh; do
  expect 0 "parses: ${script#"$actions"/}" bash -n "$script"
done

# --- setup/pins.py -----------------------------------------------------------
pins() { (cd "$work" && python3 "$actions/setup/pins.py"); }
reset() { rm -rf "$work"/* "$work"/.devcontainer; mkdir -p "$work/.devcontainer"; }

reset
echo 'C4O_IMAGE := ghcr.io/x/c4o-core:2.15' > "$work/Makefile"
printf '{\n  // a comment, as devcontainer.json allows\n  "image": "ghcr.io/x/c4o-core:2.15"\n}\n' > "$work/.devcontainer/devcontainer.json"
expect 0 "pins: Makefile and devcontainer.json agree" pins

sed -i 's/2\.15"/2.14"/' "$work/.devcontainer/devcontainer.json"
expect 1 "pins: they disagree" pins

rm -r "$work/.devcontainer"
expect 0 "pins: no devcontainer.json is not an error" pins

echo 'IMAGE = x' > "$work/Makefile"
expect 1 "pins: a Makefile with no C4O_IMAGE" pins

rm "$work/Makefile"
expect 1 "pins: no Makefile" pins

# --- report/results-page.sh --------------------------------------------------
# `make site` is stubbed: what is tested is what the script demands of the page.
reset
mkdir -p "$work/bin" "$work/build/site"
printf '#!/bin/sh\nexit 0\n' > "$work/bin/make"
chmod +x "$work/bin/make"
page() {  # page <extra html> <commit>
  printf '<h2>Signoff checks</h2><h2>Worst setup path</h2><h2>Area</h2><h2>Power</h2>%s<a href="/commit/%s">' "$1" "$2" \
    > "$work/build/site/index.html"
}
results() {  # results <extra sections>
  (cd "$work" && PATH="$work/bin:$PATH" GITHUB_SHA=abc123 EXTRA_SECTIONS="$1" \
    bash "$actions/report/results-page.sh")
}

echo 'DESIGN_NAME: x' > "$work/config.yaml"
page '' abc123
expect 0 "results page: the four flow sections" results ''
expect 1 "results page: an extra section asked for and missing" results 'Block diagram'
page '<h2>Block diagram</h2>' abc123
expect 0 "results page: the extra section is there" results 'Block diagram'
page '' zzz999
expect 1 "results page: links another commit" results ''
printf '<h2>Area</h2><h2>Power</h2><a href="/commit/abc123">' > "$work/build/site/index.html"
expect 1 "results page: a flow section missing" results ''
printf '"//WAVE_SIGNALS":\n  - tb.clk\n' >> "$work/config.yaml"
page '' abc123
expect 1 "results page: //WAVE_SIGNALS set and no Waveform section" results ''
page '<h2>Waveform</h2>' abc123
expect 0 "results page: //WAVE_SIGNALS set and Waveform there" results ''

if [ "$failures" -ne 0 ]; then
  echo "$failures case(s) failed."
  exit 1
fi
echo "all cases passed"
