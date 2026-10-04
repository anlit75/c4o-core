#!/usr/bin/env bash
# What `make report` prints, on the run's summary page.
#
# pipefail, or a report that failed would pass through tee as a green step.
set -euo pipefail
mkdir -p build
make -s report | tee build/report.txt
{
  echo '## Signoff'
  echo '```text'
  grep -v '\[INFO\]' build/report.txt
  echo '```'
} >> "$GITHUB_STEP_SUMMARY"
