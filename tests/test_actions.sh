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

# --- report/results-page.sh --------------------------------------------------
# `make site` is stubbed: what is tested is what the script demands of the page.
reset
mkdir -p "$work/bin" "$work/build/site"
printf '#!/bin/sh\nexit 0\n' > "$work/bin/make"
chmod +x "$work/bin/make"
page() {  # page <extra html> <commit>
  printf '<h2>Power</h2><h2>Signoff checks</h2>%s<a href="/commit/%s">' "$1" "$2" \
    > "$work/build/site/index.html"
}
results() {  # results <extra sections>
  (cd "$work" && PATH="$work/bin:$PATH" GITHUB_SHA=abc123 EXTRA_SECTIONS="$1" \
    bash "$actions/report/results-page.sh")
}

echo 'DESIGN_NAME: x' > "$work/config.yaml"
page '' abc123
expect 0 "results page: the two flow sections" results ''
expect 1 "results page: an extra section asked for and missing" results 'Tests'
page '<h2>Tests</h2>' abc123
expect 0 "results page: the extra section is there" results 'Tests'
page '' zzz999
expect 1 "results page: links another commit" results ''
# Power and Signoff checks are the headings every 2.x image gives its page.
for gone in Power "Signoff checks"; do
  printf '<h2>Power</h2><h2>Signoff checks</h2><a href="/commit/abc123">' \
    | sed "s#<h2>$gone</h2>##" > "$work/build/site/index.html"
  refuses "results page: the $gone section missing" "The results page has no '$gone' section." results ''
done
# A page of this image's own sections, and a page of the 2.18 image's: both
# pass, since the script demands nothing a 2.x image may not have.
printf '<h2>Timing</h2><h2>Area and Instances</h2><h2>Power</h2><h2>Signoff checks</h2><a href="/commit/abc123">' \
  > "$work/build/site/index.html"
expect 0 "results page: the sections of a newer image" results ''
printf '<h2>Signoff checks</h2><h2>Worst setup path</h2><h2>Area</h2><h2>Power</h2><h2>Waveform</h2><a href="/commit/abc123">' \
  > "$work/build/site/index.html"
expect 0 "results page: the sections of the 2.18 image" results ''
# Coverage is demanded only when the caller lists it.
page '' abc123
expect 1 "results page: a Coverage section asked for and missing" results 'Coverage'
page '<h2>Coverage</h2>' abc123
expect 0 "results page: the Coverage section is there" results 'Coverage'
page '<h2>Coverage</h2>' abc123
expect 0 "results page: a page with Coverage that the caller did not ask for" results ''
# The obsolete key is not read.
printf '"//WAVE_SIGNALS":\n  - tb.clk\n' >> "$work/config.yaml"
page '' abc123
expect 0 "results page: //WAVE_SIGNALS in the config asks for no Waveform section" results ''

# --- report/action.yml: when the Pages step runs ------------------------------
# The `if:` of the step is read out of the action and evaluated for each event.
# A manual run on main republishes the page; nothing off main does.
pages_runs() {  # pages_runs <event> <ref>: exit 0 when the step would run
  python3 - "$actions/report/action.yml" "$1" "$2" <<'PY'
import re, sys, yaml
steps = yaml.safe_load(open(sys.argv[1]))["runs"]["steps"]
cond = next(s["if"] for s in steps if s.get("id") == "pages")
expr = cond.replace("github.event_name", "event").replace("github.ref", "ref")
expr = expr.replace("&&", " and ").replace("||", " or ")
assert re.fullmatch(r"[\w\s'=/()]+", expr), expr
sys.exit(0 if eval(expr, {}, {"event": sys.argv[2], "ref": sys.argv[3]}) else 1)
PY
}
expect 0 "pages: a push to main publishes" pages_runs push refs/heads/main
expect 0 "pages: a manual run on main publishes" pages_runs workflow_dispatch refs/heads/main
expect 1 "pages: a manual run on another branch does not" pages_runs workflow_dispatch refs/heads/feature
expect 1 "pages: a push to another branch does not" pages_runs push refs/heads/feature
expect 1 "pages: a pull request does not" pages_runs pull_request refs/pull/1/merge
expect 1 "pages: a schedule on main does not" pages_runs schedule refs/heads/main

# --- report/coverage.sh --------------------------------------------------------
# `make` is stubbed twice: an image with the target, and one from before 2.21.
reset
mkdir -p "$work/bin"
cat > "$work/bin/make" <<'SH'
#!/bin/sh
echo "make $*" >> "$STUB_LOG"
case "$STUB" in
  new) exit 0 ;;
  old) [ "$1" = -n ] && { echo "make: *** No rule to make target 'coverage'.  Stop." >&2; exit 2; }; exit 0 ;;
  broken) [ "$1" = -n ] && { echo "Cannot get the image" >&2; exit 2; }; exit 0 ;;
  fails) [ "$1" = -n ] && exit 0; exit 1 ;;
esac
SH
chmod +x "$work/bin/make"
coverage_step() {  # coverage_step <stub> [sections, default Coverage]
  (cd "$work" && : > "$work/stub.log" && PATH="$work/bin:$PATH" STUB="$1" STUB_LOG="$work/stub.log" \
    EXTRA_SECTIONS="${2-Coverage}" bash "$actions/report/coverage.sh")
}
printf 'DESIGN_NAME: x\n"//COCOTB_TESTS":\n  - dir::a.py\n' > "$work/config.yaml"
expect 0 "coverage step: an image with the target runs it" coverage_step new
grep -qx "make coverage" "$work/stub.log" && echo "ok    coverage step: ... and ran make coverage" \
  || { echo "FAIL  coverage step: make coverage was not run"; failures=$((failures + 1)); }
refuses_text() {  # refuses_text <label> <exit> <text> <command...>: any exit code
  local label=$1 want=$2 text=$3 out got
  shift 3
  out=$("$@" 2>&1)
  got=$?
  if [ "$got" -ne "$want" ]; then
    echo "FAIL  $label: exit $got, expected $want"; echo "$out" | sed 's/^/        /'; failures=$((failures + 1))
  elif ! grep -qF -- "$text" <<<"$out"; then
    echo "FAIL  $label: no '$text' in the output"; echo "$out" | sed 's/^/        /'; failures=$((failures + 1))
  else
    echo "ok    $label"
  fi
}
no_make_call() {  # no_make_call <label>
  [ ! -s "$work/stub.log" ] && echo "ok    $1" || { echo "FAIL  $1: make was called"; cat "$work/stub.log" | sed 's/^/        /'; failures=$((failures + 1)); }
}
# Opt-in: the caller lists Coverage, or nothing runs and make is not asked.
refuses_text "coverage step: not in sections is skipped" 0 "not measuring code coverage" coverage_step new ""
no_make_call "coverage step: ... and make was not called"
refuses_text "coverage step: other sections only is skipped" 0 "not measuring code coverage" coverage_step new $'Tests\nPower'
no_make_call "coverage step: ... and make was not called for other sections"
refuses_text "coverage step: a near name does not opt in" 0 "not measuring code coverage" coverage_step new $'Coverage report\ncoverage'
no_make_call "coverage step: ... and make was not called for a near name"
expect 0 "coverage step: Coverage among other sections runs it" coverage_step new $'Tests\nCoverage'
grep -qx "make coverage" "$work/stub.log" && echo "ok    coverage step: ... and ran make coverage among others" \
  || { echo "FAIL  coverage step: make coverage was not run among other sections"; failures=$((failures + 1)); }
refuses_text "coverage step: an image from before 2.21 is a notice, not a failure" 0 "::notice::This c4o-core image has no 'make coverage'" coverage_step old
grep -qx "make coverage" "$work/stub.log" && { echo "FAIL  coverage step: an old image ran make coverage"; failures=$((failures + 1)); } \
  || echo "ok    coverage step: ... and did not run it"
refuses_text "coverage step: make failing for another reason is not a skip" 1 "Cannot get the image" coverage_step broken
refuses_text "coverage step: a failing make coverage fails the step" 1 "" coverage_step fails
printf 'DESIGN_NAME: x\n"//TEST_FILES":\n  - dir::a.v\n' > "$work/config.yaml"
refuses_text "coverage step: no //COCOTB_TESTS is skipped" 0 "no Python tests to measure" coverage_step new
no_make_call "coverage step: ... without asking make"
printf 'DESIGN_NAME: x\n"//COCOTB_TESTS":\n  - dir::a.py\n' > "$work/config.yaml"

# The seed of the RTL run, so that both runs get one stimulus.
mkdir -p "$work/build"
printf '<testsuites><testsuite><properties><property name="random_seed" value="1789965785"/></properties></testsuite></testsuites>' \
  > "$work/build/cocotb-results.xml"
expect 0 "coverage step: runs with the RTL run's seed" coverage_step new
grep -qx "make coverage SEED=1789965785" "$work/stub.log" && echo "ok    coverage step: ... as make coverage SEED=<that seed>" \
  || { echo "FAIL  coverage step: expected 'make coverage SEED=1789965785'"; cat "$work/stub.log" | sed 's/^/        /'; failures=$((failures + 1)); }
(cd "$work" && : > stub.log && PATH="$work/bin:$PATH" STUB=new STUB_LOG="$work/stub.log" EXTRA_SECTIONS=Coverage SEED=42 \
  bash "$actions/report/coverage.sh" >/dev/null 2>&1)
grep -qx "make coverage" "$work/stub.log" && echo "ok    coverage step: a SEED the caller set is not overridden" \
  || { echo "FAIL  coverage step: a caller's SEED was overridden"; cat "$work/stub.log" | sed 's/^/        /'; failures=$((failures + 1)); }
printf 'not xml' > "$work/build/cocotb-results.xml"
expect 0 "coverage step: an unreadable results file runs without a seed" coverage_step new
grep -qx "make coverage" "$work/stub.log" && echo "ok    coverage step: ... and passed no SEED" \
  || { echo "FAIL  coverage step: expected a bare make coverage"; failures=$((failures + 1)); }
# After make regress its base seed is the one: coverage then runs the same list.
mkdir -p "$work/build/regress"
printf '{"seed": 4711, "runs": []}' > "$work/build/regress/summary.json"
printf '<testsuites><testsuite><properties><property name="random_seed" value="1789965785"/></properties></testsuite></testsuites>' \
  > "$work/build/cocotb-results.xml"
expect 0 "coverage step: a regression summary is there" coverage_step new
grep -qx "make coverage SEED=4711" "$work/stub.log" && echo "ok    coverage step: ... its base seed wins over the RTL run's" \
  || { echo "FAIL  coverage step: expected 'make coverage SEED=4711'"; sed 's/^/        /' "$work/stub.log"; failures=$((failures + 1)); }
(cd "$work" && : > stub.log && PATH="$work/bin:$PATH" STUB=new STUB_LOG="$work/stub.log" EXTRA_SECTIONS=Coverage SEED=42 \
  bash "$actions/report/coverage.sh" >/dev/null 2>&1)
grep -qx "make coverage" "$work/stub.log" && echo "ok    coverage step: a SEED the caller set wins over the regression's" \
  || { echo "FAIL  coverage step: a caller's SEED was overridden by the regression's"; sed 's/^/        /' "$work/stub.log"; failures=$((failures + 1)); }
printf 'not json' > "$work/build/regress/summary.json"
expect 0 "coverage step: an unreadable regression summary" coverage_step new
grep -qx "make coverage SEED=1789965785" "$work/stub.log" && echo "ok    coverage step: ... falls back to the RTL run's seed" \
  || { echo "FAIL  coverage step: expected the RTL run's seed"; sed 's/^/        /' "$work/stub.log"; failures=$((failures + 1)); }
rm -r "$work/build"

# --- report/cocotb-gates.sh --------------------------------------------------
# The two logs the cocotb gate step compares. Each case writes what cocotb
# prints, and states the exit code and the reason the script must give.
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

# --- checks/regress-summary.sh -----------------------------------------------
# What the run's summary page says about a regress run, from the same
# build/regress/summary.json the results page reads.
reset
mkdir -p "$work/build/regress"
regress_summary() { (cd "$work" && : > summary.md && GITHUB_STEP_SUMMARY="$work/summary.md" bash "$actions/checks/regress-summary.sh"); }
printf '{"seed": 99, "runs": [
  {"entry": "test_a", "seed": 1, "verdict": "pass"},
  {"entry": "test_a", "seed": 2, "verdict": "pass"},
  {"entry": "test_b.f", "seed": 7, "verdict": "fail"}], "total": 3, "passed": 2, "failed": 1}' \
  > "$work/build/regress/summary.json"
expect 0 "regress summary: a summary file is written to the page" regress_summary
page_has() {  # page_has <label> <text the summary page must have>
  grep -qF -- "$2" "$work/summary.md" && echo "ok    $1" \
    || { echo "FAIL  $1: no '$2' on the page"; sed 's/^/        /' "$work/summary.md"; failures=$((failures + 1)); }
}
page_has "regress summary: the total" "2/3 runs passed"
page_has "regress summary: the base seed reruns the list" "make regress SEED=99"
page_has "regress summary: a row for each test" "| \`test_a\` | 2/2 |"
page_has "regress summary: ... with its failures" "| \`test_b.f\` | 0/1 |"
page_has "regress summary: a failed run has its replay command" "make cocotb SEED=7 TEST=test_b.f"
if grep -qF "SEED=1 " "$work/summary.md"; then
  echo "FAIL  regress summary: a passing seed must not get a replay command"; failures=$((failures + 1))
else
  echo "ok    regress summary: a passing seed gets no replay command"
fi
printf '{"seed": 5, "runs": [{"entry": "t", "seed": 1, "verdict": "pass"}], "total": 1, "passed": 1, "failed": 0}' \
  > "$work/build/regress/summary.json"
expect 0 "regress summary: all passed" regress_summary
if grep -qF "Replay" "$work/summary.md"; then
  echo "FAIL  regress summary: nothing failed, so no replay section"; failures=$((failures + 1))
else
  echo "ok    regress summary: nothing failed, so no replay section"
fi
rm "$work/build/regress/summary.json"
expect 1 "regress summary: no summary file is an error, not an empty section" regress_summary

# --- report/action.yml: the order of the steps that carry the history -----------
# The page is built after the Pages answer and the fetch, or the build has no
# build/history.json to add its row to. The fetch runs only when the answer was yes.
step_order() {  # step_order <step name before> <step name after>: exit 0 when it comes first
  python3 - "$actions/report/action.yml" "$1" "$2" <<'PY'
import sys, yaml
names = [s["name"] for s in yaml.safe_load(open(sys.argv[1]))["runs"]["steps"]]
sys.exit(0 if names.index(sys.argv[2]) < names.index(sys.argv[3]) else 1)
PY
}
expect 0 "history: Pages answers before the fetch" step_order "Is GitHub Pages set to publish from Actions?" "Fetch the history of earlier runs"
expect 0 "history: the fetch comes before the page is built" step_order "Fetch the history of earlier runs" "Build the results page"
expect 0 "history: the page is built before it is uploaded" step_order "Build the results page" "Upload the results page"
expect 1 "history: the page is not built before the Pages step" step_order "Build the results page" "Is GitHub Pages set to publish from Actions?"
fetch_condition() {
  python3 - "$actions/report/action.yml" <<'PY'
import sys, yaml
steps = yaml.safe_load(open(sys.argv[1]))["runs"]["steps"]
fetch = next(s for s in steps if s["name"] == "Fetch the history of earlier runs")
pages = next(s for s in steps if s.get("id") == "pages")
assert fetch["if"] == "steps.pages.outputs.publish == 'true'", fetch["if"]
assert "steps.pages.outputs.url" in fetch["env"]["PAGES_URL"]
assert "(github.event_name == 'push' || github.event_name == 'workflow_dispatch') && github.ref == 'refs/heads/main'" in pages["if"]
PY
}
expect 0 "history: the fetch runs when Pages said publish, and the Pages step keeps its condition" fetch_condition
no_required_sections() {
  python3 - "$actions/report/action.yml" <<'PY'
import sys, yaml
inputs = yaml.safe_load(open(sys.argv[1]))["inputs"]
assert not inputs["sections"].get("required"), "sections must stay optional"
assert "History" not in inputs["sections"]["default"]
PY
}
expect 0 "history: no new required section for the report action" no_required_sections

# --- report/pages-setting.sh: the address of the page --------------------------
reset
mkdir -p "$work/bin"
cat > "$work/bin/curl" <<'SH'
#!/bin/sh
out=
while [ $# -gt 0 ]; do [ "$1" = -o ] && out=$2; shift; done
printf '%s' "$STUB_BODY" > "$out"
printf '%s' "$STUB_CODE"
SH
chmod +x "$work/bin/curl"
pages_answer() {  # pages_answer <http code> <body>
  : > "$work/github-output"
  (cd "$work" && PATH="$work/bin:$PATH" STUB_CODE="$1" STUB_BODY="$2" RUNNER_TEMP="$work" GH_TOKEN=x \
    GITHUB_API_URL=https://api.example GITHUB_REPOSITORY=o/r GITHUB_OUTPUT="$work/github-output" \
    bash "$actions/report/pages-setting.sh")
}
output_has() {  # output_has <line>
  grep -qxF -- "$1" "$work/github-output"
}
expect 0 "pages setting: a workflow build says publish" pages_answer 200 '{"build_type": "workflow", "html_url": "https://o.github.io/r/"}'
expect 0 "pages setting: ... and gives the address of the page" output_has "url=https://o.github.io/r/"
expect 0 "pages setting: ... and publish=true" output_has "publish=true"
expect 0 "pages setting: a branch build is a notice" pages_answer 200 '{"build_type": "legacy", "html_url": "https://o.github.io/r/"}'
expect 1 "pages setting: ... that does not publish" output_has "publish=true"
expect 1 "pages setting: ... and gives no address" output_has "url=https://o.github.io/r/"

# --- report/history-fetch.sh ---------------------------------------------------
# Against a real HTTP server, since the script is the way it calls curl: -L, the
# retry, and the code it reads.
reset
mkdir -p "$work/site/r" "$work/build"
printf '[{"sha": "abc"}]' > "$work/site/r/history.json"
port=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
(cd "$work/site" && exec python3 -m http.server "$port" --bind 127.0.0.1 >/dev/null 2>&1) &
server=$!
trap 'kill "$server" 2>/dev/null; rm -rf "$work"' EXIT
for _ in $(seq 50); do curl -s -o /dev/null "http://127.0.0.1:$port/" && break; sleep 0.1; done
fetch() {  # fetch <page url>
  (cd "$work" && rm -f build/history.json && PAGES_URL="$1" RUNNER_TEMP="$work" bash "$actions/report/history-fetch.sh")
}
expect 0 "history fetch: a page with a history.json" fetch "http://127.0.0.1:$port/r/"
[ "$(cat "$work/build/history.json" 2>/dev/null)" = '[{"sha": "abc"}]' ] && echo "ok    history fetch: ... saved as build/history.json" \
  || { echo "FAIL  history fetch: build/history.json is not the file served"; failures=$((failures + 1)); }
grep -q -- '--retry 3' "$actions/report/history-fetch.sh" && echo "ok    history fetch: asks with --retry 3" \
  || { echo "FAIL  history fetch: curl is not called with --retry 3"; failures=$((failures + 1)); }
expect 0 "history fetch: ... and an address with no slash at the end" fetch "http://127.0.0.1:$port/r"
refuses_text "history fetch: no history.json yet is a notice, not a failure" 0 "::notice::" fetch "http://127.0.0.1:$port/missing/"
refuses_text "history fetch: ... that says the history starts with this run" 0 "starts with this run" fetch "http://127.0.0.1:$port/missing/"
[ ! -e "$work/build/history.json" ] && echo "ok    history fetch: ... and saves nothing" \
  || { echo "FAIL  history fetch: a 404 left a build/history.json"; failures=$((failures + 1)); }
kill "$server"; wait "$server" 2>/dev/null
refuses_text "history fetch: a server that does not answer is an error" 1 "::error::" fetch "http://127.0.0.1:$port/r/"
refuses_text "history fetch: ... that names the code" 1 "returned HTTP 000" fetch "http://127.0.0.1:$port/r/"
refuses_text "history fetch: no address is an error" 1 "::error::" fetch ""

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
