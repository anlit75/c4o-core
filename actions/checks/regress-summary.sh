#!/usr/bin/env bash
# What `make regress` found, on the run's summary page: runs passed for each
# test, and the replay command of every run that failed. Read from
# build/regress/summary.json, the same file the results page reads.
set -euo pipefail
python3 - build/regress/summary.json >> "${GITHUB_STEP_SUMMARY:?GITHUB_STEP_SUMMARY is not set}" <<'PY'
import json, sys

summary = json.load(open(sys.argv[1]))
runs = summary["runs"]
counts = {}
for run in runs:
    row = counts.setdefault(run["entry"], [0, 0])
    row[1] += 1
    row[0] += run["verdict"] == "pass"
print("## Regression")
print()
print(f"{summary['passed']}/{summary['total']} runs passed. Base seed `{summary['seed']}`: "
      f"`make regress SEED={summary['seed']}` reruns the whole list.")
print()
print("| test | passed |")
print("|---|---|")
for entry, (done, total) in counts.items():
    print(f"| `{entry}` | {done}/{total} |")
failed = [run for run in runs if run["verdict"] != "pass"]
if failed:
    print()
    print("Replay a failed run:")
    print()
    print("```text")
    for run in failed:
        print(f"make cocotb SEED={run['seed']} TEST={run['entry']}")
    print("```")
PY
