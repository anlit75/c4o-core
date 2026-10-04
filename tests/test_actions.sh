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

# --- report/cocotb-gates.sh --------------------------------------------------
# The two logs the cocotb gate step compares. Each case writes what cocotb
# prints, and states the exit code and the reason the script must give.
refuses() {  # refuses <label> <text the output must have> <command...>
  local label=$1 text=$2 out got
  shift 2
  out=$("$@" 2>&1)
  got=$?
  if [ "$got" -ne 1 ]; then
    echo "FAIL  $label: exit $got, expected 1"
    failures=$((failures + 1))
  elif ! grep -qF -- "$text" <<<"$out"; then
    echo "FAIL  $label: no '$text' in the output"
    echo "$out" | sed 's/^/        /'
    failures=$((failures + 1))
  else
    echo "ok    $label"
  fi
}
reset
summary_line() { echo "** TESTS=$1 PASS=$2 FAIL=$3 SKIP=$4 ** 123.45 ns"; }
gates() { (cd "$work" && bash "$actions/report/cocotb-gates.sh"); }
mkdir -p "$work/build"
summary_line 4 4 0 0 > "$work/build/cocotb-rtl.log"
summary_line 4 4 0 0 > "$work/build/cocotb-gl.log"
expect 0 "cocotb gates: the same summary on both" gates

summary_line 4 3 1 0 > "$work/build/cocotb-gl.log"
refuses "cocotb gates: a failure on the gates" "did not pass everything" gates

summary_line 3 3 0 0 > "$work/build/cocotb-gl.log"
refuses "cocotb gates: fewer tests on the gates" "did not run the same tests" gates

summary_line 4 3 0 1 > "$work/build/cocotb-gl.log"
refuses "cocotb gates: a skipped test on the gates" "did not pass everything" gates

echo "no summary here" > "$work/build/cocotb-gl.log"
refuses "cocotb gates: no summary line on the gates" "printed no summary" gates

rm "$work/build/cocotb-gl.log"
refuses "cocotb gates: no gate log at all" "printed no summary" gates

summary_line 4 4 0 0 > "$work/build/cocotb-gl.log"
rm "$work/build/cocotb-rtl.log"
refuses "cocotb gates: no RTL log is an error, not a skip" "cocotb-rtl.log is missing" gates

# --- checks/tests-configured.sh ----------------------------------------------
reset
configured() { (cd "$work" && bash "$actions/checks/tests-configured.sh"); }
printf 'DESIGN_NAME: x\n"//TEST_FILES":\n  - dir::a.v\n' > "$work/config.yaml"
expect 0 "tests configured: a Verilog testbench" configured
printf 'DESIGN_NAME: x\n"//COCOTB_TESTS":\n  - dir::a.py\n' > "$work/config.yaml"
expect 0 "tests configured: Python tests" configured
printf '"//TEST_FILES":\n  - dir::a.v\n"//COCOTB_TESTS":\n  - dir::a.py\n' > "$work/config.yaml"
expect 0 "tests configured: both" configured
printf 'DESIGN_NAME: x\n' > "$work/config.yaml"
refuses "tests configured: neither names both keys" '"//TEST_FILES"' configured
refuses "tests configured: ... and the other key" '"//COCOTB_TESTS"' configured
printf 'DESIGN_NAME: x\n"//TEST_FILES_OLD":\n  - dir::a.v\n"//GATE_TESTS":\n  - dir::g.v\n' > "$work/config.yaml"
refuses "tests configured: a near name or a gate testbench does not count" "neither" configured

# --- scripts/move-major-branch.sh --------------------------------------------
# Against a bare repository standing in for origin. Two commits, a then b.
script="$actions/../scripts/move-major-branch.sh"
remote="$work/origin.git"
clone="$work/clone"
git init -q --bare "$remote"
git init -q "$clone"
git -C "$clone" -c user.name=t -c user.email=t@t commit -q --allow-empty -m a
a=$(git -C "$clone" rev-parse HEAD)
git -C "$clone" -c user.name=t -c user.email=t@t commit -q --allow-empty -m b
b=$(git -C "$clone" rev-parse HEAD)
move() {  # move <tag> <sha>
  (cd "$clone" && REMOTE="$remote" GITHUB_REF_NAME="$1" GITHUB_SHA="$2" bash "$script")
}
branch_is() {  # branch_is <branch> <sha or "absent">
  local at
  at=$(git -C "$remote" rev-parse -q --verify "refs/heads/$1" || echo absent)
  [ "$at" = "$2" ]
}

expect 0 "major branch: a pre-release tag is left alone" move v2.16.0-rc1 "$a"
expect 0 "major branch: ... and created no branch" branch_is v2 absent
expect 0 "major branch: the first release creates it" move v2.16.0 "$a"
expect 0 "major branch: ... at the release commit" branch_is v2 "$a"
expect 0 "major branch: the next release moves it forward" move v2.16.1 "$b"
expect 0 "major branch: ... to the new commit" branch_is v2 "$b"
expect 1 "major branch: a release behind the branch is refused" move v2.15.9 "$a"
expect 0 "major branch: ... and the branch did not move" branch_is v2 "$b"
expect 0 "major branch: another major gets its own branch" move v3.0.0 "$b"
expect 0 "major branch: ... named v3" branch_is v3 "$b"

if [ "$failures" -ne 0 ]; then
  echo "$failures case(s) failed."
  exit 1
fi
echo "all cases passed"
