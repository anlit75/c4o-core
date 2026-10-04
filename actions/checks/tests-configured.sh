#!/usr/bin/env bash
# A repository with no test at all must not pass the checks in silence. Asked
# for and absent is an error. Not asked for is a skip, which the steps after
# this one do on their own.
set -euo pipefail

if ! grep -q -e '^"//TEST_FILES":' -e '^"//COCOTB_TESTS":' config.yaml; then
  echo '::error::config.yaml has neither "//TEST_FILES" (Verilog testbenches) nor "//COCOTB_TESTS" (Python tests). Nothing would be tested.'
  exit 1
fi
