import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from xml.etree import ElementTree

import yaml

from c4o import site_page
from c4o import common
from c4o import rtl
from c4o import sim

# What `coverage` writes. Everything under here is rebuilt on each run.
COVERAGE_DIR = "build/coverage"

# The coverage kinds Verilator writes, by the prefix of a record's `page`
# (v_line/<module>, v_toggle/<module>, ...), in the order the page lists them.
COVERAGE_TYPES = [("line", "v_line"), ("branch", "v_branch"),
                  ("toggle", "v_toggle"), ("user", "v_user")]

# What a reader sees, where the .dat and summary.json say `line`.
COVERAGE_NAMES = {"line": "block"}

def coverage_percent(hit, total):
    """One decimal, or None when the design has nothing of that kind to cover."""
    return round(hit * 100 / total, 1) if total else None

def parse_coverage_dat(path):
    """
    Per-type and per-module numbers from a Verilator coverage.dat, counted from
    the typed records: the `page` of each `C` line is v_<type>/<module>, and a
    point is hit when its count is at least one.

    Not from `--write-info`. Its lcov lines take the smallest of the line,
    branch and toggle counts on each source line, so a DA number is none of
    the three.

    Returns (types, modules, files). types is {type: {hit, total, percent}},
    with line, branch and toggle always present and user only when the design
    has a `cover property`. modules is {module: types}. files is the source
    files the points sit in.
    """
    counts = {}   # (module, type) -> [hit, total]
    files = set()
    with open(path) as f:
        for text in f:
            m = re.match(r"C '(.*)' (\d+)$", text.rstrip("\n"))
            if not m:
                continue
            # Fields are \x01 apart and a key is split from its value by \x02.
            fields = dict(item.split("\x02", 1) for item in m.group(1).split("\x01") if "\x02" in item)
            kind, _, module = fields.get("page", "").partition("/")
            kind = {prefix: name for name, prefix in COVERAGE_TYPES}.get(kind)
            if kind is None:
                continue
            point = counts.setdefault((module, kind), [0, 0])
            point[1] += 1
            point[0] += int(m.group(2)) >= 1
            if "f" in fields:
                files.add(fields["f"])

    def summarise(selected):
        out = {}
        for name, _ in COVERAGE_TYPES:
            hit = sum(h for (_, k), (h, _) in selected.items() if k == name)
            total = sum(t for (_, k), (_, t) in selected.items() if k == name)
            if total or name != "user":
                out[name] = {"hit": hit, "total": total, "percent": coverage_percent(hit, total)}
        return out

    modules = {}
    for module in sorted({m for m, _ in counts}):
        modules[module] = summarise({k: v for k, v in counts.items() if k[0] == module})
    return summarise(counts), modules, sorted(files)

def display_path(path):
    """A source path as the page shows it: relative to the repository when it is in it."""
    rel = os.path.relpath(path)
    return path if rel.startswith("..") else rel

def uncovered_lines(dat):
    """
    The source lines that a line or branch point sits on and no test hit, from
    the records of a coverage.dat. Where a record has an `S` field, that is the
    lines its block spans, as "166,169-177". Otherwise it is the `l` field.

    A signal that only failed toggle coverage is not here: its declaration is
    not code that did not run. The Toggle row and the module table show it.

    Returns [{file, line, text}] in file and line order. text is the line of
    the source, empty when the file cannot be read.
    """
    missed = {}
    with open(dat) as f:
        for text in f:
            m = re.match(r"C '(.*)' (\d+)$", text.rstrip("\n"))
            if not m or int(m.group(2)) >= 1:
                continue
            fields = dict(item.split("\x02", 1) for item in m.group(1).split("\x01") if "\x02" in item)
            if fields.get("page", "").partition("/")[0] not in ("v_line", "v_branch"):
                continue
            lines = set()
            for part in fields.get("S", fields.get("l", "")).split(","):
                first, _, last = part.partition("-")
                if first.isdigit():
                    lines.update(range(int(first), int(last or first) + 1))
            missed.setdefault(fields.get("f", "?"), set()).update(lines)

    out = []
    for path in sorted(missed):
        try:
            with open(path, errors="replace") as f:
                source = f.read().splitlines()
        except OSError:
            source = []
        for number in sorted(missed[path]):
            code = source[number - 1].strip() if 0 < number <= len(source) else ""
            out.append({"file": display_path(path), "line": number, "text": code})
    return out

def merge_coverage(dats, merged):
    """Sums the counts of several coverage.dat into one. Verilator overwrites its own."""
    common.run_command(["verilator_coverage", "--write", merged] + dats)

def cmd_coverage(args, config):
    """
    Measures how much of the RTL the cocotb tests ran. Same tests as `cocotb`,
    run again on Verilator with its coverage counters compiled in.

    It measures; it does not judge. The verdict on the tests is `cocotb`, which
    runs on Icarus: Verilator is 2-state, so a signal that reads x on Icarus
    before reset reads 0 here, and a test can pass in one and fail in the other.
    A test failing here is reported and the command still succeeds, with the
    coverage the run wrote. A design Verilator cannot build fails it.
    """
    test_files = common.get_files(args, config, key="COCOTB_TESTS")
    if not test_files and getattr(args, "if_configured", False) is True:
        sim.skip_unconfigured(config, "coverage", "COCOTB_TESTS", "TEST_FILES")
        return
    if not test_files:
        common.log_error(
            "No cocotb tests: set COCOTB_TESTS (or \"//COCOTB_TESTS\") to the "
            "Python test files in the config."
        )
        sys.exit(1)

    toplevel = common.config_get(config, "DESIGN_NAME")
    if not toplevel:
        common.log_error("coverage needs DESIGN_NAME to know which module to drive.")
        sys.exit(1)

    # Rebuilt from nothing, so a file left by an earlier run is never reported.
    if os.path.isdir(COVERAGE_DIR):
        shutil.rmtree(COVERAGE_DIR)
    # With a test list the runs are the list's, as `regress` makes them: one
    # simulation for each entry and seed, their counts merged. Checked before
    # the build, like every other problem with the list.
    base = plan = None
    if common.config_get(config, "REGRESSION"):
        base, plan = regression_plan(config, test_files)
        common.log_info(f"Base seed {base}, {len(plan)} runs. The same runs as `regress`.")
    work = os.path.abspath(os.path.join(COVERAGE_DIR, "work"))
    os.makedirs(work)
    results = os.path.abspath(os.path.join(COVERAGE_DIR, "results.xml"))

    sources = [os.path.abspath(f) for f in common.get_files(args, config, key="VERILOG_FILES")]
    modules = [os.path.splitext(os.path.basename(f))[0] for f in test_files]
    search = [os.path.dirname(os.path.abspath(f)) for f in test_files]
    flags = ["--coverage"] + rtl.disable_warnings(config)

    # cocotb's own Makefile does the Verilator build and run, as it does for
    # anyone who writes `SIM=verilator`. It is called from a directory of its
    # own: Verilator writes coverage.dat into the current directory.
    env = dict(os.environ)
    env.update({
        "SIM": "verilator",
        "TOPLEVEL": toplevel,
        "TOPLEVEL_LANG": "verilog",
        "MODULE": ",".join(modules),
        "VERILOG_SOURCES": " ".join(sources),
        "VERILOG_INCLUDE_DIRS": " ".join(os.path.abspath(d) for d in common.get_include_dirs(config)),
        "COMPILE_ARGS": " ".join(flags),
        "SIM_BUILD": os.path.join(work, "sim_build"),
        "COCOTB_RESULTS_FILE": results,
        "PYTHONPATH": os.pathsep.join(dict.fromkeys(search + [os.getcwd()])),
    })
    makefile = os.path.join(sim.cocotb_config("--makefiles"), "Makefile.sim")

    build = subprocess.run(
        ["make", "-f", makefile, os.path.join(work, "sim_build", "Vtop")],
        cwd=work, env=env, capture_output=True, text=True,
    )
    with open(os.path.join(COVERAGE_DIR, "build.log"), "w") as f:
        f.write(build.stdout + build.stderr)
    if build.returncode != 0:
        print("\n".join((build.stdout + build.stderr).splitlines()[-40:]))
        common.log_error("Verilator could not build the design with coverage. The log is build/coverage/build.log.")
        sys.exit(1)
    # One run of everything in COCOTB_TESTS without a list. With one, a run for
    # each entry and seed. Each is renamed on the way out: Verilator writes
    # coverage.dat again, on top of itself, for each simulation it runs.
    runs = plan or [(None, None, None, None)]
    dats, tests, single_seed = [], None, None
    for number, (entry, module, function, seed) in enumerate(runs, 1):
        run_env = env
        if entry:
            run_env = run_environment(env, module, function, seed)
            common.log_info(f"Run {number}/{len(runs)} on Verilator: {entry}, seed {seed}")
        else:
            common.log_info("Running the cocotb tests on Verilator")
        sys.stdout.flush()
        # cocotb's makefile treats an existing results file as an up-to-date
        # run, and skips the simulation.
        if os.path.exists(results):
            os.remove(results)
        started = time.monotonic()
        ran = subprocess.run(["make", "-f", makefile], cwd=work, env=run_env)
        if entry:
            common.log_info(f"Run {number} took {time.monotonic() - started:.1f} s")

        raw = os.path.join(work, "coverage.dat")
        if not os.path.exists(raw):
            common.log_error(f"Verilator wrote no coverage.dat (make exit code {ran.returncode}).")
            sys.exit(1)
        run_dat = os.path.join(COVERAGE_DIR, f"run-{number}.dat")
        os.replace(raw, run_dat)
        dats.append(run_dat)

        if os.path.exists(results):
            try:
                run_seed, cases = site_page.cocotb_cases(results)
                got = {"total": len(cases), "passed": sum(v == "PASS" for _, v, _ in cases)}
                tests = got if tests is None else {k: tests[k] + got[k] for k in got}
                single_seed = run_seed
            except ElementTree.ParseError:
                pass
    shutil.rmtree(work)  # the compiled model is large and is not a result
    merged = os.path.join(COVERAGE_DIR, "coverage.dat")
    merge_coverage(dats, merged)

    types, per_module, files = parse_coverage_dat(merged)

    # The seed of the one run, or the list's base seed.
    seed = base if plan else single_seed

    summary = {
        "tests": tests,
        "seed": seed,
        "files": [display_path(f) for f in files],
        "types": types,
        "modules": [{"name": name, "types": t} for name, t in per_module.items()],
        "uncovered": uncovered_lines(merged),
    }
    if plan:
        summary["runs"] = len(plan)
    with open(os.path.join(COVERAGE_DIR, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")

    print()
    for name, _ in COVERAGE_TYPES:
        if name in types:
            t = types[name]
            pct = "n/a" if t["percent"] is None else f"{t['percent']:.1f}%"
            print(f"  {COVERAGE_NAMES.get(name, name).ljust(8)} {pct.rjust(6)}  ({t['hit']}/{t['total']})")
    print()
    if tests:
        common.log_info(f"Verilator ran {tests['passed']}/{tests['total']} tests. Pass or fail is decided by `cocotb` on Icarus, not by this run.")
    common.log_info(f"Wrote {os.path.join(COVERAGE_DIR, 'summary.json')}")

# What `regress` writes. Everything under here is rebuilt on each run.
REGRESS_DIR = "build/regress"

def load_regression(config, test_files):
    """
    Reads the list REGRESSION names and checks every entry before anything runs.
    Returns [(entry, module, function or None, seeds)], where the entry is the
    `test` string as written. Each problem is logged, and any problem exits 1.
    """
    value = common.config_get(config, "REGRESSION")
    if not isinstance(value, str) or not value.strip():
        common.log_error("REGRESSION must be the path of a test list, such as dir::tb/regression.yaml.")
        sys.exit(1)
    path = common.strip_path_prefix(value)
    try:
        with open(path) as f:
            entries = yaml.safe_load(f)
    except OSError as e:
        common.log_error(f"Could not read the test list {path}: {e.strerror or e}")
        sys.exit(1)
    except yaml.YAMLError as e:
        common.log_error(f"Failed to parse {path}: {e}")
        sys.exit(1)
    if not isinstance(entries, list) or not entries:
        common.log_error(f"{path} must be a list with at least one entry, each with a `test` and optionally `seeds`.")
        sys.exit(1)

    modules = sim.test_modules(test_files)
    problems, tests, seen = [], [], set()
    for number, entry in enumerate(entries, 1):
        where = f"{path}, entry {number}"
        if not isinstance(entry, dict) or not isinstance(entry.get("test"), str) or not entry["test"].strip():
            problems.append(f"{where}: needs a `test`, the name of a module of COCOTB_TESTS, "
                            "optionally followed by .<function>.")
            continue
        name = entry["test"].strip()
        where = f"{path}, entry {number} ({name})"
        extra = sorted(set(entry) - {"test", "seeds"})
        if extra:
            problems.append(f"{where}: unknown key {', '.join(map(str, extra))}. An entry has `test` and `seeds`.")
        module, _, function = name.partition(".")
        if module not in modules:
            problems.append(f"{where}: no module {module} in COCOTB_TESTS. The modules are: {', '.join(modules)}.")
        elif "." in name and not function:
            problems.append(f"{where}: ends in a dot. Write <module> or <module>.<function>.")
        seeds = entry.get("seeds", 1)
        # bool is an int to Python, and `seeds: true` is not a count.
        if type(seeds) is not int or seeds < 1:
            problems.append(f"{where}: seeds must be a whole number of 1 or more, not {seeds!r}.")
        if name in seen:
            problems.append(f"{where}: listed twice. Give the seeds in one entry.")
        seen.add(name)
        tests.append((name, module, function or None, seeds))
    for problem in problems:
        common.log_error(problem)
    if problems:
        sys.exit(1)
    return tests

def derive_seeds(base, entry, count):
    """
    `count` distinct seeds for one entry from the base seed. The same base
    gives the same seeds, and each entry draws from its own stream, so adding
    or reordering entries leaves the others' seeds alone.
    """
    return random.Random(f"{base}:{entry}").sample(range(1, 2**31), count)

def base_seed():
    """RANDOM_SEED from the environment, else a new random one."""
    given = os.environ.get("RANDOM_SEED")
    if given is None or given == "":
        return random.SystemRandom().randrange(1, 2**31)
    try:
        return int(given)
    except ValueError:
        common.log_error(f"RANDOM_SEED must be a whole number, not '{given}'.")
        sys.exit(1)

def regression_plan(config, test_files):
    """
    The base seed and every run of the list: [(entry, module, function, seed)]
    in order. `regress` and `coverage` both take their runs from here, so for
    one base seed they run the same entries with the same seeds.
    """
    tests = load_regression(config, test_files)
    base = base_seed()
    plan = [(entry, module, function, seed)
            for entry, module, function, seeds in tests
            for seed in derive_seeds(base, entry, seeds)]
    return base, plan

def run_verdict(path):
    """
    "pass" or "fail" for one run, from its results file. No file, an unreadable
    one, a test that failed and a file with no test in it are all "fail": the
    simulator exits 0 in every one of those cases.
    """
    try:
        cases = list(ElementTree.parse(path).getroot().iter("testcase"))
    except (OSError, ElementTree.ParseError):
        return "fail"
    if not cases:
        return "fail"
    broken = any(c.find("failure") is not None or c.find("error") is not None for c in cases)
    return "fail" if broken else "pass"

def run_environment(env, module, function, seed):
    """`env` for one run of the list: one module, perhaps one test, one seed."""
    run_env = dict(env)
    run_env.pop("TESTCASE", None)  # not one the caller's shell left behind
    run_env.update({"MODULE": module, "RANDOM_SEED": str(seed)})
    if function:
        run_env["TESTCASE"] = function
    return run_env

def replay_command(entry, seed):
    return f"make cocotb SEED={seed} TEST={entry}"

def regress_table(runs):
    """Rows of (entry, passed, total, failed seeds), in the order of the list."""
    rows = {}
    for run in runs:
        row = rows.setdefault(run["entry"], [0, 0, []])
        row[1] += 1
        if run["verdict"] == "pass":
            row[0] += 1
        else:
            row[2].append(run["seed"])
    return [(entry, *row) for entry, row in rows.items()]

def cmd_regress(args, config):
    """
    Runs a list of cocotb tests, each over several seeds, against one compile
    of the RTL. REGRESSION names the list; see docs/commands.md.

    Every run is its own vvp with its own results file, so one verdict is one
    seed of one entry, and a failure prints the command that replays it. A
    failed run does not stop the rest. The exit code is 1 if any run failed.
    """
    # Cleared first, even when the command then stops: a summary left over from
    # an earlier run must never be read as this one's.
    if os.path.isdir(REGRESS_DIR):
        shutil.rmtree(REGRESS_DIR)

    if not common.config_get(config, "REGRESSION"):
        if getattr(args, "if_configured", False) is True:
            common.log_info("regress skipped: REGRESSION is not set.")
            return
        common.log_error("No test list: set REGRESSION (or \"//REGRESSION\") to a YAML file of tests and seeds.")
        sys.exit(1)

    test_files = common.get_files(args, config, key="COCOTB_TESTS")
    if not test_files:
        common.log_error("REGRESSION runs tests of COCOTB_TESTS, and the config sets none.")
        sys.exit(1)
    toplevel = common.config_get(config, "DESIGN_NAME")
    if not toplevel:
        common.log_error("regress needs DESIGN_NAME to know which module to drive.")
        sys.exit(1)
    base, plan = regression_plan(config, test_files)
    common.log_info(f"Base seed {base}. RANDOM_SEED={base} reruns this whole list.")

    common.ensure_build_dir()
    os.makedirs(REGRESS_DIR)
    vvp_file = "build/cocotb.vvp"
    sim.compile_cocotb(args, config, toplevel, vvp_file)
    env, lib_dir = sim.cocotb_env(test_files, toplevel, "")
    command = sim.cocotb_vvp(vvp_file, lib_dir)

    runs = []
    for entry, module, function, seed in plan:
        results = os.path.join(REGRESS_DIR, f"{entry}-{seed}.xml")
        run_env = run_environment(env, module, function, seed)
        run_env["COCOTB_RESULTS_FILE"] = results
        common.log_info(f"Run {len(runs) + 1}/{len(plan)}: {entry}, seed {seed}")
        started = time.monotonic()
        # Not run_command: it exits on a nonzero status, and one failed
        # run must not hide the verdicts of the rest.
        subprocess.run(command, env=run_env)
        verdict = run_verdict(results)
        common.log_info(f"{entry} seed {seed}: {verdict} in {time.monotonic() - started:.1f} s")
        runs.append({"entry": entry, "seed": seed, "verdict": verdict})

    failed = [r for r in runs if r["verdict"] != "pass"]
    summary = {"seed": base, "runs": runs, "total": len(runs),
               "passed": len(runs) - len(failed), "failed": len(failed)}
    with open(os.path.join(REGRESS_DIR, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")

    rows = regress_table(runs)
    width = max(len("test"), *(len(entry) for entry, *_ in rows))
    print(f"\n{'test':<{width}}  passed  failed seeds")
    for entry, passed, count, seeds in rows:
        print(f"{entry:<{width}}  {passed:>2}/{count:<3}  {', '.join(map(str, seeds)) or '-'}")
    print(f"\n{summary['passed']}/{summary['total']} runs passed, base seed {base}.")
    if failed:
        for run in failed:
            common.log_error(f"{run['entry']} seed {run['seed']} failed. Replay it: {replay_command(run['entry'], run['seed'])}")
        sys.exit(1)
    common.log_info("All regression runs passed.")
