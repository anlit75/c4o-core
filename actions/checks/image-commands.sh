#!/usr/bin/env bash
# Which commands the image has. `@v2` of this action runs against whatever
# c4o-core image a copy pins, and the commands changed in 2.26: `make rtl` and
# `make check` exist, and `make sim` runs the cocotb tests as well as the
# Verilog testbenches. An older image has neither of the two targets.
#
# Asked of make rather than of a version number: the target is what is needed.
# Only "no such target" is an old image. Any other failure of make -n is a
# real one, and is not turned into a guess. `check` and not `rtl`, because a
# repository may have a target of its own named rtl.
set -uo pipefail

out=$(make -n check 2>&1)
if [ $? -eq 0 ]; then
  new=true
elif grep -qE "No rule to make target .check" <<<"$out"; then
  new=false
else
  echo "$out"
  exit 1
fi
echo "This image has the commands of 2.26 or newer: $new"
echo "new=$new" >> "${GITHUB_OUTPUT:?GITHUB_OUTPUT is not set}"
