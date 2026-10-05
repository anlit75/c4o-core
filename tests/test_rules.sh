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

check "host: a bare make is 'all'" 0 "$image lint" in_repo "$host" make -n
check "host: ... and all ends with synth" 0 "$image synth" in_repo "$host" make -n
copied=$(ls "$host"/.c4o/*.mk 2>/dev/null | wc -l)
[ "$copied" -eq 1 ] && ok "host: one rules file in .c4o/" || fail "host: $copied rules files in .c4o/, expected 1"
id=$(docker image inspect -f '{{.Id}}' "$image" | sed 's/sha256://')
[ -f "$host/.c4o/$id.mk" ] && ok "host: named after the image id" || fail "host: no .c4o/$id.mk" "$(ls "$host/.c4o")"
cmp -s "$host/.c4o/$id.mk" "$repo/rules.mk" && ok "host: it is this checkout's rules.mk" \
  || fail "host: the copied rules differ from rules.mk. Does '$image' carry this checkout?"

before=$(stat -c %Y "$host/.c4o/$id.mk")
sleep 1
check "host: a second make" 0 "$image lint" in_repo "$host" make -n lint
[ "$(stat -c %Y "$host/.c4o/$id.mk")" = "$before" ] && ok "host: ... does not copy the rules again" \
  || fail "host: the rules were copied again on the second make"

check "host: make help" 0 "Available targets:" in_repo "$host" make help
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
check "host: SEED reaches the cocotb tests that gatesim runs" 0 "-e RANDOM_SEED=7 $image gatesim" \
  in_repo "$host" make -n gatesim SEED=7
# all asks for no test kind by name, so it skips the one that is not configured.
# Named by themselves, sim and cocotb must keep failing without their key.
check "host: all runs sim only if configured" 0 "$image sim --if-configured" in_repo "$host" make -n all
check "host: all runs cocotb only if configured" 0 "$image cocotb --if-configured" in_repo "$host" make -n all
out=$(in_repo "$host" make -n sim cocotb 2>&1)
if grep -qF "$image sim" <<<"$out" && grep -qF "$image cocotb" <<<"$out" && ! grep -qF -- "--if-configured" <<<"$out"; then
  ok "host: sim and cocotb named by themselves do not skip"
else
  fail "host: make sim and make cocotb must not pass --if-configured" "$out"
fi

# coverage is a target of its own and is not part of all.
check "host: make help lists coverage" 0 "make coverage" in_repo "$host" make help
check "host: coverage runs the coverage command" 0 "$image coverage" in_repo "$host" make -n coverage
check "host: SEED reaches the coverage run" 0 "-e RANDOM_SEED=7 $image coverage" in_repo "$host" make -n coverage SEED=7
out=$(in_repo "$host" make -n coverage 2>&1)
if grep -qF -- "--if-configured" <<<"$out"; then
  fail "host: make coverage by itself must not skip" "$out"
else
  ok "host: make coverage by itself does not skip"
fi
out=$(in_repo "$host" make -n all 2>&1)
if grep -qF "coverage" <<<"$out"; then
  fail "host: make all must not run coverage" "$out"
else
  ok "host: make all does not run coverage"
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
check "own: a target above the include is not the default" 0 "$image lint" in_repo "$own" make -n
check "own: help:: adds a line" 0 "a target of this repository" in_repo "$own" make help
check "own: ... after the standard ones" 0 "Available targets:" in_repo "$own" make help
check "own: c4o_tool runs an image tool" 0 "--entrypoint peakrdl $image pyuvm regs/x.rdl" in_repo "$own" make -n ral
check "own: C4O_COCOTB is usable" 0 "$image cocotb --netlist" in_repo "$own" make -n cocotb-gl

# --- inside the image: the rules are a local file -----------------------------
inside="$work/inside"
new_repo "$inside" "$image"
chmod -R a+rwX "$inside"
dmake() { docker run --rm -v "$inside:/w" -w /w --entrypoint make "$image" "$@"; }
check "inside: commands call the entrypoint directly" 0 "python3 /opt/c4o-core/scripts/entrypoint.py lint" dmake -n lint
check "inside: WAVES reaches the entrypoint" 0 "env WAVES=1 python3 /opt/c4o-core/scripts/entrypoint.py cocotb" dmake -n cocotb WAVES=1
check "inside: SEED and WAVES reach the entrypoint" 0 "env RANDOM_SEED=7 WAVES=1 python3 /opt/c4o-core/scripts/entrypoint.py cocotb" \
  dmake -n cocotb SEED=7 WAVES=1
check "inside: coverage calls the entrypoint directly" 0 "python3 /opt/c4o-core/scripts/entrypoint.py coverage" dmake -n coverage
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
in_repo "$moving" make -n lint >/dev/null 2>&1
first=$(ls "$moving"/.c4o/*.mk)
# Another image under the same name: the first one plus a marker in its rules.
printf 'FROM %s\nRUN echo "# marker-of-the-newer-image" >> /opt/c4o-core/rules.mk\n' "$image" \
  | docker build -q -t "$tag" - >/dev/null
check "moving: make still works after the image changed" 0 "$tag lint" in_repo "$moving" make -n lint
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
check "C4O_RULES: works with an image that cannot be had" 0 "c4o-rules-test.invalid/nope:0 lint" \
  in_repo "$override" make -n lint C4O_RULES="$repo/rules.mk"
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
