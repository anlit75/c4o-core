#!/usr/bin/env bash
# `make coverage`, when the caller asked for it and the image has it.
set -uo pipefail

# Opt-in: a caller lists Coverage in `sections`. A new c4o-core release alone
# changes nothing in a caller's CI, because a design that lint accepts can
# still fail the Verilator build.
if ! grep -qxF "Coverage" <<<"${EXTRA_SECTIONS:-}"; then
  echo "Coverage is not in sections -- not measuring code coverage."
  exit 0
fi

# The Python tests are what coverage measures. The cocotb steps skip without
# the key, and so does this.
if ! grep -q '^"//COCOTB_TESTS":' config.yaml; then
  echo "config.yaml has no //COCOTB_TESTS -- no Python tests to measure."
  exit 0
fi

# Asked of make rather than of a version number: the target is what is needed.
# Only "no such target" is an old image. Any other failure of make -n is a
# real one, and is not turned into a skip.
out=$(make -n coverage 2>&1)
if [ $? -ne 0 ]; then
  if grep -qE "No rule to make target .coverage" <<<"$out"; then
    echo "::notice::This c4o-core image has no 'make coverage' (it came with 2.21), so the results page has no Coverage section."
    exit 0
  fi
  echo "$out"
  exit 1
fi

# The seed of the RTL run that the page shows, so that both runs get the same
# random stimulus. A SEED the caller set wins.
args=()
if [ -z "${SEED:-}" ] && [ -f build/cocotb-results.xml ]; then
  seed=$(python3 - <<'PY'
import xml.etree.ElementTree as ET
try:
    root = ET.parse("build/cocotb-results.xml").getroot()
    print(next((p.get("value") for p in root.iter("property") if p.get("name") == "random_seed"), ""))
except (OSError, ET.ParseError):
    print("")
PY
)
  if [ -n "$seed" ]; then
    echo "Using the RTL run's seed $seed."
    args=("SEED=$seed")
  fi
fi

mkdir -p build
make coverage "${args[@]}"
