#!/usr/bin/env bash
# The cocotb tests ran on the RTL (the checks action wrote build/cocotb-rtl.log)
# and on the gates (build/cocotb-gl.log). The gates must run the same tests and
# reach the same verdicts.
#
# Compared against the RTL run's own summary line, not against a count written
# here. That the two lines are identical is exactly the claim, and a hardcoded
# number needs editing each time a test is added. Asserts the content because
# `make gatesim` would also exit 0 having run one test of four.
#
# A missing RTL log is an error, not a skip. This step runs because config.yaml
# asks for cocotb tests, so the RTL run was due too. Without its log nothing is
# there to compare to, and passing would claim a match nobody checked.
set -euo pipefail

rtl_log=${1:-build/cocotb-rtl.log}
gl_log=${2:-build/cocotb-gl.log}

# `|| true` because a log with no summary line is a case reported below, not
# one to die on: with pipefail an empty grep would end the script at the
# assignment, before the message that explains why.
summary() {
  [ -f "$1" ] || return 0
  grep -o 'TESTS=[0-9]* PASS=[0-9]* FAIL=[0-9]* SKIP=[0-9]*' "$1" | tail -1 || true
}

if [ ! -f "$rtl_log" ]; then
  echo "::error::$rtl_log is missing, so the RTL run is not there to compare with. Run the checks action before this one."
  exit 1
fi
rtl=$(summary "$rtl_log")
gates=$(summary "$gl_log")
echo "RTL:   $rtl"
echo "gates: $gates"

case "$gates" in
  "") echo "::error::The gate-level run printed no summary line at all."; exit 1 ;;
  *"FAIL=0 SKIP=0") ;;
  *) echo "::error::The gate-level run did not pass everything it ran."; exit 1 ;;
esac
if [ "$rtl" != "$gates" ]; then
  echo "::error::The gates did not run the same tests as the RTL. Compare the two lines above."
  exit 1
fi
