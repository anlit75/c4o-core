#!/usr/bin/env bash
# rules.mk and stub.mk, used the way a repository made from the template uses
# them: a Makefile with two image names and the stub, in a directory of its own.
#
# Needs Docker and an image that carries this checkout's rules.mk. In CI that is
# the image the job has just built. C4O_TEST_IMAGE names it.
#
# Each case states what it must see. A stub that swallows a failure, or rules
# that stop honouring a variable people use, fails this file.
set -uo pipefail

image=${C4O_TEST_IMAGE:-c4o-core:test}
repo=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failures=0

ok()   { echo "ok    $1"; }
fail() { echo "FAIL  $1"; [ $# -gt 1 ] && echo "$2" | sed 's/^/        /'; failures=$((failures + 1)); }

# check <label> <expected exit: 0 or "fail"> <text the output must have, or ""> <command...>
check() {
  local label=$1 want=$2 text=$3
  shift 3
  local out got
  out=$("$@" 2>&1)
  got=$?
  if [ "$want" = fail ] && [ "$got" -eq 0 ]; then fail "$label: exit 0, expected a failure" "$out"; return; fi
  if [ "$want" = 0 ] && [ "$got" -ne 0 ]; then fail "$label: exit $got" "$out"; return; fi
  if [ -n "$text" ] && ! grep -qF -- "$text" <<<"$out"; then fail "$label: no '$text' in the output" "$out"; return; fi
  ok "$label"
}

# A repository made from the template: two image names, the stub, a config.
new_repo() {  # new_repo <dir> <image>
  mkdir -p "$1"
  {
    echo "C4O_IMAGE := $2"
    echo "LIBRELANE_IMAGE := ghcr.io/librelane/librelane:3.0.14"
    echo
    cat "$repo/stub.mk"
  } > "$1/Makefile"
  echo 'DESIGN_NAME: demo' > "$1/config.yaml"
}
in_repo() { (cd "$1" && shift && "$@"); }

docker image inspect "$image" >/dev/null 2>&1 \
  || { echo "FAIL  the test image '$image' is not here. Build it, or set C4O_TEST_IMAGE."; exit 1; }

# --- on a host: the rules are copied out of the image -------------------------
host="$work/host"
new_repo "$host" "$image"

check "host: a bare make is 'check'" 0 "$image check" in_repo "$host" make -n
out=$(in_repo "$host" make -n 2>&1)
if grep -qE "$image (rtl|all|lint|sim|cocotb|regress|gatesim)" <<<"$out"; then
  fail "host: a bare make must check the config and run no tool" "$out"
else
  ok "host: a bare make runs no tool"
fi
copied=$(ls "$host"/.c4o/*.mk 2>/dev/null | wc -l)
[ "$copied" -eq 1 ] && ok "host: one rules file in .c4o/" || fail "host: $copied rules files in .c4o/, expected 1"
id=$(docker image inspect -f '{{.Id}}' "$image" | sed 's/sha256://')
[ -f "$host/.c4o/$id.mk" ] && ok "host: named after the image id" || fail "host: no .c4o/$id.mk" "$(ls "$host/.c4o")"
cmp -s "$host/.c4o/$id.mk" "$repo/rules.mk" && ok "host: it is this checkout's rules.mk" \
  || fail "host: the copied rules differ from rules.mk. Does '$image' carry this checkout?"

before=$(stat -c %Y "$host/.c4o/$id.mk")
sleep 1
check "host: a second make" 0 "$image rtl" in_repo "$host" make -n rtl
[ "$(stat -c %Y "$host/.c4o/$id.mk")" = "$before" ] && ok "host: ... does not copy the rules again" \
  || fail "host: the rules were copied again on the second make"

check "host: make help" 0 "Available targets:" in_repo "$host" make help
# The new names are listed. The old ones are aliases, and the help leaves them out.
for t in check rtl sim regress gatesim gds; do
  check "host: make help lists $t" 0 "make $t " in_repo "$host" make help
done
for t in all lint synth coverage cocotb; do
  out=$(in_repo "$host" make help 2>&1)
  if grep -qE "^  make $t( |$)" <<<"$out"; then fail "host: make help lists the alias $t" "$out"; else ok "host: make help leaves out the alias $t"; fi
done
check "host: make help says how to run one test" 0 "make sim SEED=<n> TEST=<entry>" in_repo "$host" make help
check "host: make help says how to leave out coverage" 0 "make regress COVERAGE=0" in_repo "$host" make help
check "host: gds checks the config of the physical design flow first" 0 "$image check --for gds" in_repo "$host" make -n gds
out=$(in_repo "$host" make -n gds 2>&1)
if [ "$(grep -n -m1 -e 'check --for gds' <<<"$out" | cut -d: -f1)" -lt "$(grep -n -m1 -e 'make pdk' <<<"$out" | cut -d: -f1)" ]; then
  ok "host: ... before the PDK is installed"
else
  fail "host: the check of the config must come before make pdk" "$out"
fi
check "host: gds starts from an empty run" 0 "--overwrite" in_repo "$host" make -n gds
check "host: gds names the run after DESIGN_NAME" 0 "--run-tag demo_run" in_repo "$host" make -n gds
out=$(in_repo "$host" make -n gds LIBRELANE_ARGS="--from OpenROAD.Floorplan --with-initial-state x.json" 2>&1)
if grep -qF -- "--from OpenROAD.Floorplan" <<<"$out" && ! grep -qF -- "--overwrite" <<<"$out"; then
  ok "host: a resume keeps the previous run"
else
  fail "host: a resume must pass --from and no --overwrite" "$out"
fi
check "host: SEED reaches the container" 0 "-e RANDOM_SEED=7" in_repo "$host" make -n cocotb SEED=7
check "host: WAVES reaches the container" 0 "-e WAVES=1 $image cocotb" in_repo "$host" make -n cocotb WAVES=1
check "host: SEED and WAVES reach the container together" 0 "-e RANDOM_SEED=7 -e WAVES=1 $image cocotb" \
  in_repo "$host" make -n cocotb SEED=7 WAVES=1
out=$(in_repo "$host" make -n cocotb 2>&1)
if grep -qF -- "WAVES" <<<"$out"; then
  fail "host: a plain make cocotb must not pass WAVES" "$out"
else
  ok "host: a plain make cocotb passes no WAVES"
fi
check "host: TEST reaches the container" 0 "-e TEST=test_a.f $image cocotb" in_repo "$host" make -n cocotb TEST=test_a.f
check "host: SEED, WAVES and TEST reach the container together" 0 "-e RANDOM_SEED=7 -e WAVES=1 -e TEST=test_a $image cocotb" \
  in_repo "$host" make -n cocotb SEED=7 WAVES=1 TEST=test_a
out=$(in_repo "$host" make -n cocotb SEED=7 2>&1)
if grep -qF -- "TEST" <<<"$out"; then
  fail "host: a make cocotb without TEST must not pass TEST" "$out"
else
  ok "host: a make cocotb without TEST passes no TEST"
fi
check "host: SEED reaches the cocotb tests that gatesim runs" 0 "-e RANDOM_SEED=7 $image gatesim" \
  in_repo "$host" make -n gatesim SEED=7
# gatesim reads the cell models of the PDK, wherever PDK_ROOT says the PDK is.
check "host: gatesim mounts the PDK_ROOT it is given" 0 "-v /x:/pdks -e PDK_ROOT=/pdks" in_repo "$host" make -n gatesim PDK_ROOT=/x
check "host: ... and mounts pdks/ of the checkout without one" 0 "-v $host/pdks:/pdks -e PDK_ROOT=/pdks" in_repo "$host" make -n gatesim
check "host: ... and makes it first, so Docker does not make it as root" 0 "mkdir -p /x" in_repo "$host" make -n gatesim PDK_ROOT=/x
check "host: ... and still passes SEED" 0 "-v /x:/pdks -e PDK_ROOT=/pdks -e RANDOM_SEED=7 $image gatesim" in_repo "$host" make -n gatesim PDK_ROOT=/x SEED=7
# A run of the cocotb tests on the netlist, in a target of your own, finds the PDK
# when it is there. When it is not, nothing is mounted, and Docker makes no directory.
out=$(in_repo "$host" make -n cocotb 2>&1)
if grep -qF -- ":/pdks" <<<"$out"; then fail "host: make cocotb mounts a PDK_ROOT that is not there" "$out"; else ok "host: make cocotb mounts no PDK_ROOT that is not there"; fi
mkdir -p "$host/pdks"
check "host: C4O_COCOTB mounts a PDK_ROOT that is there" 0 "-v $host/pdks:/pdks -e PDK_ROOT=/pdks" in_repo "$host" make -n cocotb
rmdir "$host/pdks"
# sim is the ledger: rtl, the config of the tests, then each kind the config lists.
# The kinds that are not configured are skipped inside it, so make passes no flag.
check "host: sim is one container that prints the ledger" 0 "$image all" in_repo "$host" make -n sim
check "host: all is sim" 0 "$image all" in_repo "$host" make -n all
out=$(in_repo "$host" make -n sim 2>&1)
if grep -qF -- "--if-configured" <<<"$out"; then fail "host: make sim passes no --if-configured" "$out"; else ok "host: make sim passes no --if-configured"; fi
check "host: lint is rtl" 0 "$image rtl" in_repo "$host" make -n lint
check "host: synth is rtl" 0 "$image rtl" in_repo "$host" make -n synth
out=$(in_repo "$host" make -n lint synth 2>&1)
if [ "$(grep -c "$image rtl" <<<"$out")" -eq 1 ]; then ok "host: lint and synth together run rtl once"; else fail "host: make lint synth should run rtl once" "$out"; fi
check "host: rtl runs the rtl command" 0 "$image rtl" in_repo "$host" make -n rtl
check "host: check runs the check command" 0 "$image check" in_repo "$host" make -n check
out=$(in_repo "$host" make -n cocotb 2>&1)
if grep -qF "$image cocotb" <<<"$out" && ! grep -qF -- "--if-configured" <<<"$out"; then
  ok "host: cocotb is still the Python tests alone, and does not skip"
else
  fail "host: make cocotb should run '$image cocotb' and not pass --if-configured" "$out"
fi

# The progress ledger: make all and make gds print one line for each command or
# stage, with the tools' own output in build/log/. Only those two.
out=$(in_repo "$host" make -n sim 2>&1)
if grep -qF "$image all" <<<"$out" && ! grep -qE "$image (rtl|check|sim|cocotb)" <<<"$out"; then
  ok "host: sim is one container that prints the ledger"
else
  fail "host: make sim should run '$image all' and not the four commands" "$out"
fi
check "host: PROGRESS=raw reaches the ledger, which streams the tools" 0 "-e C4O_PROGRESS=raw" in_repo "$host" make -n sim PROGRESS=raw
out=$(C4O_PROGRESS=raw in_repo "$host" make -n sim 2>&1)
if grep -qF -- "-e C4O_PROGRESS=raw" <<<"$out"; then ok "host: C4O_PROGRESS=raw in the environment is PROGRESS=raw"
else fail "host: C4O_PROGRESS=raw in the environment did not reach the ledger" "$out"; fi
check "host: PROGRESS reaches the container as C4O_PROGRESS" 0 "-e C4O_PROGRESS=plain" in_repo "$host" make -n all PROGRESS=plain
check "host: the terminal's own variables reach the container" 0 "-e NO_COLOR -e CI -e TERM -e GITHUB_ACTIONS" in_repo "$host" make -n sim
check "host: the container gets -t when make's output is a terminal" 0 'if [ -t 1 ]; then T=-t; else T=; fi' in_repo "$host" make -n sim
check "host: SEED reaches the ledger run" 0 "-e RANDOM_SEED=7" in_repo "$host" make -n sim SEED=7
check "host: TEST reaches the ledger run" 0 "-e TEST=test_a" in_repo "$host" make -n sim TEST=test_a
check "host: WAVES reaches the ledger run" 0 "-e WAVES=1" in_repo "$host" make -n sim WAVES=1
for t in check rtl lint synth cocotb regress coverage gatesim; do
  out=$(in_repo "$host" make -n $t 2>&1)
  if grep -qF "C4O_PROGRESS" <<<"$out"; then fail "host: make $t must not start the ledger" "$out"; else ok "host: make $t prints what it always did"; fi
done
check "host: gds starts LibreLane in the background and the ledger beside it" 0 "progress --run-dir runs/demo_run --status build/log/status" in_repo "$host" make -n gds
check "host: ... with LibreLane's whole output in a file" 0 "> build/log/librelane.log 2>&1" in_repo "$host" make -n gds
check "host: ... and its exit status in another" 0 "echo \$? > build/log/status.tmp" in_repo "$host" make -n gds
check "host: ... and Ctrl-C does not end make before LibreLane stops" 0 "trap '' INT" in_repo "$host" make -n gds
check "host: a full run deletes the previous run first" 0 "rm -rf runs/demo_run" in_repo "$host" make -n gds
check "host: ... and counts its steps beforehand" 0 "gating_config_vars" in_repo "$host" make -n gds
check "host: PROGRESS reaches the gds ledger" 0 "-e C4O_PROGRESS=plain" in_repo "$host" make -n gds PROGRESS=plain
out=$(in_repo "$host" make -n gds PROGRESS=raw 2>&1)
if grep -qE "progress --run-dir|build/log" <<<"$out"; then
  fail "host: PROGRESS=raw must run LibreLane in the foreground, as it did" "$out"
elif grep -qF -- "--run-tag demo_run config.yaml" <<<"$out" && grep -qF -- "cp runs/demo_run/final/gds/demo.gds build/demo.gds" <<<"$out"; then
  ok "host: PROGRESS=raw runs LibreLane in the foreground, as it did"
else
  fail "host: PROGRESS=raw lost the LibreLane run or the copy of the GDS" "$out"
fi
# The picture of each stage, in both modes: drawn after the flow, and on a failed one.
check "host: gds draws the stages in the LibreLane image" 0 "klayout" in_repo "$host" make -n gds
check "host: ... listing them first, in the c4o-core image" 0 "$image stages --run-dir runs/demo_run" in_repo "$host" make -n gds
check "host: ... and writing stages.json when they are drawn" 0 "$image stages --run-dir runs/demo_run --collect" in_repo "$host" make -n gds
check "host: PROGRESS=raw draws them too" 0 "$image stages --run-dir runs/demo_run --collect --quiet" in_repo "$host" make -n gds PROGRESS=raw
out=$(in_repo "$host" make -n gds PROGRESS=raw 2>&1)
if grep -qE '\|\| \{ code=\$\?;.*klayout.*exit \$code; \}' <<<"$out"; then
  ok "host: PROGRESS=raw draws what a failed flow left, and keeps its status"
else
  fail "host: PROGRESS=raw must draw the stages of a failed flow and exit with LibreLane's status" "$out"
fi
for args in "--from OpenROAD.Floorplan --with-initial-state x.json" "--to OpenROAD.CTS" "--skip OpenROAD.CTS" "--only OpenROAD.CTS"; do
  out=$(in_repo "$host" make -n gds LIBRELANE_ARGS="$args" 2>&1)
  if grep -qF -- "--partial" <<<"$out"; then
    ok "host: gds with '$args' shows step numbers and no total"
  else
    fail "host: gds with '$args' should show step numbers and no total" "$out"
  fi
done
out=$(in_repo "$host" make -n gds 2>&1)
if grep -qF -- "--partial" <<<"$out"; then
  fail "host: a whole run has a total" "$out"
else
  ok "host: a whole run is not partial"
fi
out=$(in_repo "$host" make -n gds LIBRELANE_ARGS="--from OpenROAD.Floorplan --with-initial-state x.json" 2>&1)
if grep -qF "rm -rf runs/demo_run" <<<"$out"; then
  fail "host: a resume must keep the previous run" "$out"
else
  ok "host: a resume does not delete the previous run"
fi

# The exit status of make gds is LibreLane's. A pipe to the ledger would return
# the ledger's, which is 0 whatever LibreLane did. docker is a stand-in here: it
# answers `run` and passes the rest to the real one. LibreLane exits 2.
shim="$work/shim"
mkdir -p "$shim"
real_docker=$(command -v docker)
cat > "$shim/docker" <<SHIM
#!/bin/sh
if [ "\$1" = run ]; then
  echo "\$*" >> "$work/docker-calls"
  case "\$*" in
    *"-m librelane"*)
      if [ -n "\$SHIM_FLOW_OK" ]; then mkdir -p runs/demo_run/final/gds; : > runs/demo_run/final/gds/demo.gds; exit 0; fi
      exit 2 ;;
    *klayout*) [ -n "\$SHIM_STAGES_FAIL" ] && exit 1; echo drew >> "$work/rendered"; exit 0 ;;
    *" stages "*) [ -n "\$SHIM_STAGES_FAIL" ] && exit 1; exit 0 ;;
    *"python3 -c"*) exit 1 ;;
  esac
  exit 0
fi
exec "$real_docker" "\$@"
SHIM
chmod +x "$shim/docker"
fake="$work/fake"
new_repo "$fake" "$image"
in_repo "$fake" make -n lint >/dev/null 2>&1      # the rules are copied out of the image before the stand-in is used
: > "$work/docker-calls"
out=$(cd "$fake" && PATH="$shim:$PATH" make gds 2>&1)
got=$?
if [ "$got" -ne 0 ] && grep -qE "Error 2" <<<"$out"; then
  ok "gds: make fails when LibreLane does, with LibreLane's status"
else
  fail "gds: LibreLane exited 2 and make exited $got" "$out"
fi
[ "$(cat "$fake/build/log/status" 2>/dev/null)" = 2 ] && ok "gds: the status file holds LibreLane's exit status" \
  || fail "gds: build/log/status is not LibreLane's exit status" "$(cat "$fake/build/log/status" 2>&1)"
[ -f "$fake/build/log/librelane.log" ] && ok "gds: LibreLane's output is in build/log/librelane.log" || fail "gds: no build/log/librelane.log"
if [ -e "$fake/build/demo.gds" ]; then fail "gds: a failed flow must not copy a GDS"; else ok "gds: a failed flow copies no GDS"; fi
# The stages are drawn after a flow that failed, and nothing about them changes the status.
# The stand-in draws nothing itself, so what `stages` would have listed is put there.
seed_jobs() { mkdir -p "$1/build/stages"; echo '[]' > "$1/build/stages/jobs.json"; }
for mode in plain raw; do
  : > "$work/docker-calls"; rm -f "$work/rendered"; seed_jobs "$fake"
  out=$(cd "$fake" && PATH="$shim:$PATH" make gds PROGRESS=$mode 2>&1)
  got=$?
  if [ "$got" -ne 0 ] && grep -qE "Error 2" <<<"$out"; then
    ok "gds ($mode): a failed flow still ends make with LibreLane's status"
  else
    fail "gds ($mode): LibreLane exited 2 and make exited $got" "$out"
  fi
  if [ -f "$work/rendered" ] && grep -qE "$image stages --run-dir runs/demo_run --collect" "$work/docker-calls"; then
    ok "gds ($mode): a failed flow is drawn and its stages written"
  else
    fail "gds ($mode): no render or no stages.json call after a failed flow" "$(cat "$work/docker-calls")"
  fi
  # whatever the stage calls do, the status is the flow's
  : > "$work/docker-calls"; seed_jobs "$fake"
  out=$(cd "$fake" && SHIM_STAGES_FAIL=1 PATH="$shim:$PATH" make gds PROGRESS=$mode 2>&1)
  got=$?
  if [ "$got" -ne 0 ] && grep -qE "Error 2" <<<"$out"; then
    ok "gds ($mode): stage calls that fail do not change the status of a failed flow"
  else
    fail "gds ($mode): with failing stage calls make exited $got, not with LibreLane's 2" "$out"
  fi
  # a flow that passed: drawn too, and a failing render is not a failure
  for broken in "" 1; do
    : > "$work/docker-calls"; rm -f "$work/rendered"; seed_jobs "$fake"
    out=$(cd "$fake" && SHIM_FLOW_OK=1 SHIM_STAGES_FAIL=$broken PATH="$shim:$PATH" make gds PROGRESS=$mode 2>&1)
    got=$?
    if [ "$got" -eq 0 ] && grep -qE "$image stages --run-dir runs/demo_run --collect" "$work/docker-calls" \
       && { [ -n "$broken" ] || [ -f "$work/rendered" ]; } \
       && { { [ "$mode" = raw ] && grep -qF -- "--collect --quiet" "$work/docker-calls"; } \
            || { [ "$mode" != raw ] && ! grep -qF -- "--quiet" "$work/docker-calls"; }; }; then
      ok "gds ($mode): a flow that passed is drawn${broken:+, and a render that fails is no failure}"
    else
      fail "gds ($mode): passing flow, stage calls ${broken:+failing}: exit $got" "$out"
    fi
  done
done
# make all: a terminal for the container exactly when make's output is one.
: > "$work/docker-calls"
(cd "$fake" && PATH="$shim:$PATH" make all >/dev/null 2>&1)
if grep -qE "$image all" "$work/docker-calls" && ! grep -E "$image all" "$work/docker-calls" | grep -qE " -t "; then
  ok "all: not a terminal, no -t"
else
  fail "all: a pipe must not get a terminal, and the ledger container must start" "$(cat "$work/docker-calls")"
fi
if command -v script >/dev/null 2>&1; then
  : > "$work/docker-calls"
  (cd "$fake" && PATH="$shim:$PATH" script -qec "make all" /dev/null >/dev/null 2>&1)
  if grep -E "$image all" "$work/docker-calls" | grep -qE " -t "; then
    ok "all: a terminal gets -t"
  else
    fail "all: on a terminal the container needs -t" "$(cat "$work/docker-calls")"
  fi
else
  echo "skip  all: no script(1) here to give make a terminal"
fi

# coverage is an alias of regress, which measures it after the runs, and is not part of sim.
check "host: coverage is regress, with the coverage run" 0 "$image regress --coverage" in_repo "$host" make -n coverage
check "host: SEED reaches the coverage run" 0 "-e RANDOM_SEED=7 $image regress --coverage" in_repo "$host" make -n coverage SEED=7
out=$(in_repo "$host" make -n coverage 2>&1)
if grep -qF -- "--if-configured" <<<"$out"; then
  fail "host: make coverage by itself must not skip" "$out"
else
  ok "host: make coverage by itself does not skip"
fi
out=$(in_repo "$host" make -n sim 2>&1)
if grep -qF "coverage" <<<"$out"; then
  fail "host: make sim must not run coverage" "$out"
else
  ok "host: make sim does not run coverage"
fi

# The last line of a target says what to run next. -n prints the echo, so the
# hint shows without running anything.
check "host: make sim points to make gds" 0 "Next: make gds turns the design into a GDSII layout" in_repo "$host" make -n sim
check "host: make all points to make gds" 0 "Next: make gds turns the design into a GDSII layout" in_repo "$host" make -n all
out=$(in_repo "$host" make -n all 2>&1)
if [ "$(grep -c 'Next:' <<<"$out")" -eq 1 ]; then ok "host: make all says what comes next once"; else fail "host: make all should print one Next: hint" "$out"; fi
check "host: make gds points to make site" 0 "Next: make site puts the results on one page" in_repo "$host" make -n gds
out=$(in_repo "$host" make -n gds 2>&1)
if [ "$(grep -n 'Next:' <<<"$out" | tail -1 | cut -d: -f1)" = "$(grep -c '' <<<"$out")" ]; then
  ok "host: the make site hint is the last thing make gds does"
else
  fail "host: the make site hint is not last in make gds" "$out"
fi
out=$(in_repo "$host" make -n rtl 2>&1)
if grep -qF "Next:" <<<"$out"; then
  fail "host: make rtl must not print a Next: hint" "$out"
else
  ok "host: make rtl prints no Next: hint"
fi

# regress is a target of its own and is not part of sim.
check "host: regress runs the regress command, then coverage" 0 "$image regress --coverage" in_repo "$host" make -n regress
check "host: SEED reaches the regress run" 0 "-e RANDOM_SEED=7 $image regress --coverage" in_repo "$host" make -n regress SEED=7
out=$(in_repo "$host" make -n regress COVERAGE=0 2>&1)
if grep -qF "$image regress" <<<"$out" && ! grep -qF -- "--coverage" <<<"$out"; then
  ok "host: COVERAGE=0 leaves the coverage run out"
else
  fail "host: make regress COVERAGE=0 should run regress without --coverage" "$out"
fi
out=$(in_repo "$host" make -n regress COVERAGE=1 2>&1)
if grep -qF -- "--coverage" <<<"$out"; then ok "host: COVERAGE=1 keeps it"; else fail "host: make regress COVERAGE=1 should keep --coverage" "$out"; fi
if grep -qF "COVERAGE" <<<"$(in_repo "$host" make -n regress COVERAGE=0 2>&1)"; then
  fail "host: COVERAGE is make's, and must not reach the container"
else
  ok "host: COVERAGE does not reach the container"
fi
out=$(in_repo "$host" make -n regress 2>&1)
if grep -qF -- "--if-configured" <<<"$out"; then
  fail "host: make regress by itself must not skip" "$out"
else
  ok "host: make regress by itself does not skip"
fi
out=$(in_repo "$host" make -n sim 2>&1)
if grep -qF "regress" <<<"$out"; then
  fail "host: make sim must not run regress" "$out"
else
  ok "host: make sim does not run regress"
fi

# --- what a repository adds below the include ---------------------------------
own="$work/own"
new_repo "$own" "$image"
# One target above the include, to see that it does not become the default.
{ printf 'first:\n\t@echo first-target-ran\n\n'; cat "$own/Makefile"; } > "$own/Makefile.new"
mv "$own/Makefile.new" "$own/Makefile"
cat >> "$own/Makefile" <<'EOF'

help::
	@echo "  make ral     - a target of this repository"

ral:
	$(call c4o_tool,peakrdl) pyuvm regs/x.rdl

cocotb-gl:
	$(C4O_COCOTB) cocotb --netlist
EOF
check "own: a target above the include is not the default" 0 "$image check" in_repo "$own" make -n
check "own: help:: adds a line" 0 "a target of this repository" in_repo "$own" make help
check "own: ... after the standard ones" 0 "Available targets:" in_repo "$own" make help
check "own: c4o_tool runs an image tool" 0 "--entrypoint peakrdl $image pyuvm regs/x.rdl" in_repo "$own" make -n ral
check "own: C4O_COCOTB is usable" 0 "$image cocotb --netlist" in_repo "$own" make -n cocotb-gl
# A cocotb run on the netlist of its own finds the PDK when it is there.
mkdir -p "$own/pdks"
check "own: ... and mounts the PDK for a run on the netlist" 0 "-v $own/pdks:/pdks -e PDK_ROOT=/pdks" in_repo "$own" make -n cocotb-gl
check "own: ... wherever PDK_ROOT is" 0 "-v $own/pdks:/pdks" in_repo "$own" make -n cocotb-gl PDK_ROOT=$own/pdks
rmdir "$own/pdks"

# --- inside the image: the rules are a local file -----------------------------
inside="$work/inside"
new_repo "$inside" "$image"
chmod -R a+rwX "$inside"
dmake() { docker run --rm -v "$inside:/w" -w /w --entrypoint make "$image" "$@"; }
check "inside: commands call the entrypoint directly" 0 "python3 /opt/c4o-core/scripts/entrypoint.py rtl" dmake -n lint
check "inside: check is the entrypoint's check" 0 "python3 /opt/c4o-core/scripts/entrypoint.py check" dmake -n check
check "inside: gds checks its own scope first" 0 "python3 /opt/c4o-core/scripts/entrypoint.py check --for gds" dmake -n gds
check "inside: gatesim gets the PDK_ROOT of make" 0 "env PDK_ROOT=/w/pdks RANDOM_SEED=7 python3 /opt/c4o-core/scripts/entrypoint.py gatesim" dmake -n gatesim SEED=7
check "inside: ... and the one it was given" 0 "env PDK_ROOT=/x python3 /opt/c4o-core/scripts/entrypoint.py gatesim" dmake -n gatesim PDK_ROOT=/x
check "inside: WAVES reaches the entrypoint" 0 "env WAVES=1 python3 /opt/c4o-core/scripts/entrypoint.py cocotb" dmake -n cocotb WAVES=1
check "inside: SEED and WAVES reach the entrypoint" 0 "env RANDOM_SEED=7 WAVES=1 python3 /opt/c4o-core/scripts/entrypoint.py cocotb" \
  dmake -n cocotb SEED=7 WAVES=1
check "inside: TEST reaches the entrypoint" 0 "env TEST=test_a.f python3 /opt/c4o-core/scripts/entrypoint.py cocotb" dmake -n cocotb TEST=test_a.f
check "inside: SEED, WAVES and TEST reach the entrypoint" 0 "env RANDOM_SEED=7 WAVES=1 TEST=test_a python3 /opt/c4o-core/scripts/entrypoint.py cocotb" \
  dmake -n cocotb SEED=7 WAVES=1 TEST=test_a
check "inside: SEED reaches regress" 0 "env RANDOM_SEED=7 python3 /opt/c4o-core/scripts/entrypoint.py regress --coverage" dmake -n regress SEED=7
check "inside: all is the ledger, called directly" 0 "env C4O_PROGRESS= python3 /opt/c4o-core/scripts/entrypoint.py all" dmake -n all
check "inside: PROGRESS reaches the entrypoint" 0 "env C4O_PROGRESS=plain python3 /opt/c4o-core/scripts/entrypoint.py all" dmake -n all PROGRESS=plain
check "inside: SEED reaches the ledger run" 0 "env C4O_PROGRESS= RANDOM_SEED=7 python3 /opt/c4o-core/scripts/entrypoint.py all" dmake -n all SEED=7
check "inside: PROGRESS=raw reaches the ledger" 0 "env C4O_PROGRESS=raw python3 /opt/c4o-core/scripts/entrypoint.py all" dmake -n sim PROGRESS=raw
check "inside: gds follows the run with the entrypoint, not a second container" 0 "python3 /opt/c4o-core/scripts/entrypoint.py progress --run-dir runs/demo_run" dmake -n gds
check "inside: coverage is regress with the coverage run" 0 "python3 /opt/c4o-core/scripts/entrypoint.py regress --coverage" dmake -n coverage
[ ! -e "$inside/.c4o" ] && ok "inside: nothing is copied to .c4o/" || fail "inside: .c4o/ was written inside the image"
cat >> "$inside/Makefile" <<'EOF'

ral:
	$(call c4o_tool,peakrdl) pyuvm regs/x.rdl
EOF
out=$(dmake -n ral 2>&1)
if grep -qxF "peakrdl pyuvm regs/x.rdl" <<<"$out"; then ok "inside: c4o_tool is the tool itself"
else fail "inside: c4o_tool should be the bare tool" "$out"; fi

# --- the image changes behind the same name -----------------------------------
moving="$work/moving"
tag="c4o-rules-test:moving-$$"
docker tag "$image" "$tag"
new_repo "$moving" "$tag"
in_repo "$moving" make -n rtl >/dev/null 2>&1
first=$(ls "$moving"/.c4o/*.mk)
# Another image under the same name: the first one plus a marker in its rules.
printf 'FROM %s\nRUN echo "# marker-of-the-newer-image" >> /opt/c4o-core/rules.mk\n' "$image" \
  | docker build -q -t "$tag" - >/dev/null
check "moving: make still works after the image changed" 0 "$tag rtl" in_repo "$moving" make -n rtl
now=$(ls "$moving"/.c4o/*.mk)
if [ "$(wc -l <<<"$now")" -eq 1 ] && [ "$now" != "$first" ] && grep -q "marker-of-the-newer-image" $now; then
  ok "moving: the rules are the newer image's, and the old copy is gone"
else
  fail "moving: expected one rules file, from the newer image" "before: $first"$'\n'"after: $now"
fi
docker rmi -f "$tag" >/dev/null 2>&1

# --- an image that cannot be had ----------------------------------------------
bad="$work/bad"
new_repo "$bad" "c4o-rules-test.invalid/nope:0"
check "bad image: make fails" fail "Cannot get c4o-rules-test.invalid/nope:0" in_repo "$bad" make -n lint
leftover=$(ls -A "$bad/.c4o" 2>/dev/null | wc -l)
[ "$leftover" -eq 0 ] && ok "bad image: nothing is left in .c4o/" || fail "bad image: $leftover file(s) left in .c4o/" "$(ls -A "$bad/.c4o")"

# An image that is there but has no rules.mk: an older c4o-core.
old="$work/old"
oldtag="c4o-rules-test:old-$$"
printf 'FROM %s\nRUN rm /opt/c4o-core/rules.mk\n' "$image" | docker build -q -t "$oldtag" - >/dev/null
new_repo "$old" "$oldtag"
check "old image: make fails and says which version it needs" fail "needs c4o-core 2.17 or newer" in_repo "$old" make -n lint
leftover=$(ls -A "$old/.c4o" 2>/dev/null | wc -l)
[ "$leftover" -eq 0 ] && ok "old image: no empty rules file is left" || fail "old image: $leftover file(s) left in .c4o/" "$(ls -lA "$old/.c4o")"
docker rmi -f "$oldtag" >/dev/null 2>&1

# --- C4O_RULES: a rules file, and no Docker ------------------------------------
override="$work/override"
new_repo "$override" "c4o-rules-test.invalid/nope:0"
check "C4O_RULES: works with an image that cannot be had" 0 "c4o-rules-test.invalid/nope:0 rtl" \
  in_repo "$override" make -n rtl C4O_RULES="$repo/rules.mk"
[ ! -e "$override/.c4o" ] && ok "C4O_RULES: nothing is copied" || fail "C4O_RULES: .c4o/ was written"

# --- rules.mk refuses to be included without the two image names --------------
bare="$work/bare"
mkdir -p "$bare"
echo 'DESIGN_NAME: demo' > "$bare/config.yaml"
echo "include $repo/rules.mk" > "$bare/Makefile"
check "rules.mk: no C4O_IMAGE is an error" fail "C4O_IMAGE is not set" in_repo "$bare" make -n lint

if [ "$failures" -ne 0 ]; then
  echo "$failures case(s) failed."
  exit 1
fi
echo "all cases passed"
