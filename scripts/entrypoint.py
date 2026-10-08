#!/usr/bin/env python3
import argparse
import glob
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import timezone
from xml.etree import ElementTree

import yaml

import site_page

# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def _color(code):
    # https://no-color.org: NO_COLOR set to anything but "" turns color off.
    # A pipe or a CI log is not a terminal, so it gets plain text too.
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return ""
    return code

def log_info(msg):
    print(f"{_color(GREEN)}[INFO] {msg}{_color(RESET)}")

def log_error(msg):
    print(f"{_color(RED)}[ERROR] {msg}{_color(RESET)}")

def log_warn(msg):
    print(f"{_color(YELLOW)}[WARN] {msg}{_color(RESET)}")

def run_command(cmd, shell=False, env=None):
    """Runs a command and exits if it fails."""
    # Convert list to string for logging if it's a list
    cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
    log_info(f"Running: {cmd_str}")
    try:
        subprocess.run(cmd, shell=shell, check=True, env=env)
    except subprocess.CalledProcessError as e:
        log_error(f"Command failed with exit code {e.returncode}")
        sys.exit(e.returncode)

def ensure_build_dir():
    if not os.path.exists("build"):
        os.makedirs("build")
        log_info("Created build/ directory")

# Searched in order. These are the names LibreLane uses for its own configs,
# so the same file can be handed to both this engine and the GDS flow.
CONFIG_FILENAMES = ["config.yaml", "config.yml", "config.json"]

def load_config():
    """Loads the first configuration file found in the working directory."""
    for name in CONFIG_FILENAMES:
        config_path = os.path.join(os.getcwd(), name)
        if not os.path.exists(config_path):
            continue
        log_info(f"Loading config from {config_path}")
        try:
            with open(config_path, 'r') as f:
                if name.endswith(".json"):
                    return json.load(f) or {}
                return yaml.safe_load(f) or {}
        except (json.JSONDecodeError, yaml.YAMLError) as e:
            log_error(f"Failed to parse {config_path}: {e}")
            sys.exit(1)
    return {}

def read_text(path):
    """A source file's text, or "" when it cannot be read as text."""
    try:
        with open(path, errors="replace") as f:
            return f.read()
    except OSError:
        return ""

def config_get(config, key, default=None):
    """
    Reads a config key, also accepting it under a '//' prefix.

    LibreLane ignores keys beginning with '//' outright, so prefixing the keys
    it does not own is what keeps a shared config file valid under its strict
    validation (which is the default for .yaml). Both spellings work here.
    """
    if key in config:
        return config[key]
    return config.get(f"//{key}", default)

def strip_path_prefix(pattern):
    """
    Drops LibreLane's 'dir::' prefix, which marks a path as relative to the
    design directory. Commands run with the workspace as the working directory,
    so the remainder globs correctly as-is.
    """
    return pattern[len("dir::"):] if pattern.startswith("dir::") else pattern

def get_files(args, config, key="VERILOG_FILES"):
    """
    Returns a list of files to process.
    Prioritizes CLI arguments. If empty, falls back to the config file.
    Supports globbing (e.g. rtl/**/*.v).

    Args:
        args: Parsed arguments (may contain .files)
        config: Config dictionary
        key: The config key to look up (default: VERILOG_FILES)
    """
    initial_files = []

    # CLI args override the config entirely. Use getattr because not all parsers
    # have a 'files' argument (e.g., cmd_gds), and drop empty strings so that a
    # blank --files does not shadow the config.
    cli_files = [f for f in (getattr(args, "files", None) or []) if f.strip()]

    if cli_files:
        for f in cli_files:
            initial_files.extend(f.strip().split())
    else:
        config_files = config_get(config, key)
        if config_files is not None:
            if not isinstance(config_files, list):
                log_error(f"{key} in the config file must be a list.")
                sys.exit(1)
            initial_files = config_files

    if not initial_files:
        # A key that is simply absent is the caller's problem to judge; RTL is
        # the one thing no command can do without.
        if key == "VERILOG_FILES":
            log_error("No Verilog files provided via CLI or VERILOG_FILES in the config file.")
            sys.exit(1)
        return []

    # Expand globs and deduplicate
    final_files = set()
    for pattern in initial_files:
        # Use recursive globbing
        matched = glob.glob(strip_path_prefix(pattern), recursive=True)
        if matched:
            final_files.update(matched)

    sorted_files = sorted(list(final_files))

    # A configured pattern that matches nothing is a mistake -- a renamed
    # directory, a typo, a file that never got committed. Continuing with what
    # is left means lint or sim quietly covers less than the config says it
    # does, and passes. That silence is the bug; say so and stop.
    if not sorted_files:
        log_error(f"{key} matched no files: {', '.join(initial_files)}")
        sys.exit(1)

    return sorted_files

def get_include_dirs(config):
    """Verilog include directories, with LibreLane's 'dir::' prefix removed."""
    return [strip_path_prefix(d) for d in config_get(config, "VERILOG_INCLUDE_DIRS", [])]

def disable_warnings(config):
    """
    The '-Wno-<CODE>' flags LINTER_DISABLE_WARNINGS asks for.

    Generated RTL is why this exists. sv2v's output trips WIDTHEXPAND four
    times on its own `1'sb0` constants, and the SystemVerilog it was converted
    from trips MULTIDRIVEN on struct fields -- measured against verilator
    5.020, on a PeakRDL register block that synthesises clean. Neither warning
    is about the design, and until now there was no way to say so: `lint` built
    its command line from the config and ignored this key entirely, so a config
    that named it was silently refused all the same.

    LINTER_DISABLE_WARNINGS is LibreLane's own key and means the same thing
    there, which is what keeps one config file honest across both tools.
    LibreLane writes the codes into a .vlt file as `lint_off -rule <CODE>`;
    -Wno-<CODE> is the same instruction without the temporary file. It is left
    with no default here: `lint` adds LibreLane's default (lint_flags), and
    `coverage` builds without -Wall, where those codes do not fire.
    """
    codes = config_get(config, "LINTER_DISABLE_WARNINGS", [])
    if isinstance(codes, str):
        # One code without the brackets is the easy YAML mistake to make, and
        # iterating it would spell out -Wno-W -Wno-I -Wno-D. Say so instead.
        log_error(
            "LINTER_DISABLE_WARNINGS must be a list of warning codes, not a "
            f"single string: write [{codes}] rather than {codes}."
        )
        sys.exit(1)
    return [f"-Wno-{code}" for code in codes]

# LibreLane's default for LINTER_DISABLE_WARNINGS. Both codes are -Wall
# warnings, so `lint` needs the default now that it runs with -Wall.
LINTER_DEFAULT_WAIVERS = ["DECLFILENAME", "EOFNEWLINE"]

def lint_flags(config):
    """
    The flags of LibreLane's Verilator.Lint step, so `make lint` and the flow
    report the same warnings: -Wall, warnings that do not fail, the waivers of
    LINTER_DISABLE_WARNINGS (LibreLane's default when the key is absent), and
    LATCH and MULTIDRIVEN as errors unless LINTER_ERROR_ON_LATCH or
    LINTER_ERROR_ON_MULTIDRIVEN is false. A waived code is not made an error
    again: LibreLane waives through a .vlt file, which wins, and -Werror-<CODE>
    after -Wno-<CODE> would turn the warning back on.
    """
    if config_get(config, "LINTER_DISABLE_WARNINGS") is None:
        config = dict(config, LINTER_DISABLE_WARNINGS=LINTER_DEFAULT_WAIVERS)
    waived = disable_warnings(config)
    flags = ["--Wall", "--Wno-fatal"] + waived
    for code, key in (("LATCH", "LINTER_ERROR_ON_LATCH"), ("MULTIDRIVEN", "LINTER_ERROR_ON_MULTIDRIVEN")):
        if config_get(config, key, True) and f"-Wno-{code}" not in waived:
            flags.append(f"--Werror-{code}")
    top = config_get(config, "DESIGN_NAME")
    if top:
        flags += ["--top-module", top]
    return flags

def cmd_lint(args, config):
    # Lint only checks RTL
    files = get_files(args, config, key="VERILOG_FILES")
    cmd = ["verilator", "--lint-only"]

    cmd += lint_flags(config)

    # Add include directories
    for inc in get_include_dirs(config):
        cmd.append(f"-I{inc}")

    cmd += files
    run_command(cmd)

def root_args(config, test_files, key):
    """
    The '-s <top>' Icarus needs, or nothing when there is only one candidate.

    Icarus elaborates every module nobody instantiates as its own root, and the
    first $finish ends the whole simulation -- so a second testbench runs
    partway and is cut off, with nothing in the exit code to show for it. -s
    names the one root, which is why it is required as soon as there is more
    than one file it could be hiding in.
    """
    top = config_get(config, key)
    if top:
        return ["-s", top]
    if len(test_files) > 1:
        log_error(
            "More than one testbench file, so the top module is ambiguous: "
            f"{', '.join(test_files)}. Set {key} (or \"//{key}\") to the "
            "testbench module to run."
        )
        sys.exit(1)
    return []

def skip_unconfigured(config, command, key, other_key):
    """
    What `--if-configured` does when its key is absent: skip and say so, unless
    the other kind of test is absent too. A repository with no test at all must
    not pass `make all` in silence. Asked for and missing is an error, and only
    `make all` asks for neither by name.
    """
    if not config_get(config, other_key):
        log_error(
            f"No tests to run: set {key} (Verilog testbenches) or {other_key} "
            "(Python tests) in the config."
        )
        sys.exit(1)
    log_info(f"{command} skipped: {key} is not set.")

def cmd_sim(args, config):
    # Sim needs RTL + TEST

    # If CLI args are provided, they override the concept of keys completely.
    if getattr(args, "files", None):
        files = get_files(args, config) # key doesn't matter if args.files is set
        test_files = []
    else:
        rtl_files = get_files(args, config, key="VERILOG_FILES")
        test_files = get_files(args, config, key="TEST_FILES")
        if not test_files and getattr(args, "if_configured", False) is True:
            skip_unconfigured(config, "sim", "TEST_FILES", "COCOTB_TESTS")
            return
        if not test_files:
            log_error(
                "sim has no testbench: set TEST_FILES (or \"//TEST_FILES\") in the "
                "config, or pass --files."
            )
            sys.exit(1)
        files = rtl_files + test_files

    ensure_build_dir()
    # iverilog -o build/sim.vvp <files> && vvp build/sim.vvp
    #
    # -g2012 for the same reason cocotb and gatesim pass it: one source file is
    # not more or less valid depending on which command reads it. Without it,
    # `logic` or `always_ff` fails here and passes there, and the physical flow
    # -- LibreLane reads everything with `read_verilog -sv` -- accepts both.
    # It is a superset, so Verilog-2005 still compiles, with one exception, and
    # it was worth measuring rather than guessing: a design using `bit`, `do`,
    # `final`, `soft`, `global`, `byte` or `type` as an identifier compiled
    # before this line and does not after it. Not `logic` -- iverilog reserves
    # that in either mode -- and not on the yosys side, where `read_verilog -sv`
    # accepted all seven.
    compile_cmd = ["iverilog", "-g2012", "-o", "build/sim.vvp"]

    compile_cmd += root_args(config, test_files, "SIM_TOP")

    # Add include directories
    for inc in get_include_dirs(config):
        compile_cmd.append(f"-I{inc}")

    compile_cmd += files
    run_command(compile_cmd)

    run_sim_cmd = ["vvp", "build/sim.vvp"]
    run_command(run_sim_cmd)

# LibreLane writes the synthesised netlist under final/nl/. ChipForAll then
# moves the whole run into build/, so look in both places.
NETLIST_GLOBS = ["runs/*/final/nl/*.v", "build/runs/*/final/nl/*.v"]

def find_netlist(explicit):
    """The newest gate-level netlist a run left behind, unless named."""
    if explicit:
        return explicit
    found = [path for pattern in NETLIST_GLOBS for path in glob.glob(pattern)]
    if not found:
        log_error(
            "No netlist found under runs/ or build/runs/. Run the physical "
            "design flow first, or name the file: gatesim <path>, "
            "cocotb --netlist <path>."
        )
        sys.exit(1)
    return max(found, key=os.path.getmtime)

def cell_models(config):
    """
    The PDK's own Verilog models for the cells the netlist instantiates.

    Derived from PDK and STD_CELL_LIBRARY rather than a key of its own: the
    config already says which PDK and which library, and a third key that had
    to agree with both would only be somewhere else for them to disagree.
    """
    pdk = config_get(config, "PDK")
    library = config_get(config, "STD_CELL_LIBRARY")
    if not pdk or not library:
        log_error("gatesim needs PDK and STD_CELL_LIBRARY to find the cell models.")
        sys.exit(1)

    pdk_root = os.environ.get("PDK_ROOT") or os.path.join(os.getcwd(), "pdks")
    verilog = os.path.join(pdk_root, pdk, "libs.ref", library, "verilog")
    models = [
        os.path.join(verilog, "primitives.v"),
        os.path.join(verilog, f"{library}.v"),
    ]

    missing = [m for m in models if not os.path.exists(m)]
    if missing:
        log_error(
            f"Cell models not found: {', '.join(missing)}. Install the PDK with "
            "the 'pdk' command, or set PDK_ROOT if it lives elsewhere."
        )
        sys.exit(1)
    return models

def cmd_gatesim(args, config):
    """
    Simulates the synthesised netlist against the PDK's own cell models.

    `sim` shows the RTL behaves. This shows the gates synthesis actually
    produced still behave, which is a different claim -- latch inference, reset
    handling and how a tool reads an ambiguous always block all sit between the
    two, and none of them are visible from the RTL.

    The testbench is yours, like TEST_FILES and COCOTB_TESTS. It cannot be the
    RTL one: synthesis resolves parameters, so a testbench that shrinks the
    design by overriding one has nothing left to override.

    Without GATE_TESTS the cocotb tests run on the netlist instead.
    """
    tests = get_files(args, config, key="GATE_TESTS")
    if not tests:
        # No Verilog gate testbench: the cocotb tests, if there are any, are
        # the gate-level tests. That is what `cocotb --netlist` runs.
        if config_get(config, "COCOTB_TESTS"):
            args.netlist = getattr(args, "netlist", None) or ""
            cmd_cocotb(args, config)
            return
        log_error(
            "No gate-level tests: set GATE_TESTS (or \"//GATE_TESTS\") for a Verilog "
            "testbench, or COCOTB_TESTS (or \"//COCOTB_TESTS\") for Python tests."
        )
        sys.exit(1)

    netlist = find_netlist(getattr(args, "netlist", None))
    log_info(f"Netlist: {netlist}")

    ensure_build_dir()
    vvp_file = "build/gatesim.vvp"

    # FUNCTIONAL drops the timing checks Icarus cannot run anyway; without
    # UNIT_DELAY the models leave every gate at zero delay and warn once per
    # cell. Both verified against sky130_fd_sc_hd: this pair compiles silently,
    # neither alone does.
    compile_cmd = ["iverilog", "-g2012", "-DFUNCTIONAL", "-DUNIT_DELAY=#1",
                   "-o", vvp_file]
    compile_cmd += root_args(config, tests, "GATE_TOP")
    compile_cmd += cell_models(config) + [netlist] + tests
    run_command(compile_cmd)

    run_command(["vvp", vvp_file])

def cocotb_config(*args):
    """Asks cocotb where its own files live rather than hardcoding paths."""
    try:
        return subprocess.run(
            ["cocotb-config", *args], check=True, capture_output=True, text=True
        ).stdout.strip()
    except subprocess.CalledProcessError as e:
        log_error(
            f"cocotb-config {' '.join(args)} failed: {e.stderr.strip() or e}"
        )
        sys.exit(1)
    except OSError as e:
        log_error(f"Could not run cocotb-config: {e}")
        sys.exit(1)

def write_dump_module(toplevel):
    """
    A second root that dumps the design to build/<toplevel>.vcd. cocotb's own
    runner does the same for Icarus (cocotb.runner, _create_iverilog_dump_file)
    because the DUT is the root here and there is no testbench to hold $dumpvars.
    The signal names in the file start at the design: <toplevel>.<signal>.
    """
    path = os.path.join("build", "c4o_dump.v")
    with open(path, "w") as f:
        f.write("module c4o_dump();\n")
        f.write("initial begin\n")
        f.write(f'    $dumpfile("build/{toplevel}.vcd");\n')
        f.write(f"    $dumpvars(0, {toplevel});\n")
        f.write("end\n")
        f.write("endmodule\n")
    return path

def cmd_cocotb(args, config):
    """
    Runs cocotb tests: Python coroutines driving the design, rather than a
    Verilog testbench. Same simulator underneath, so this is an alternative to
    `sim`, not a replacement for it.

    With --netlist it drives what synthesis produced instead of the RTL, and
    the tests do not change. That is the point: a testbench that only touches
    the top-level ports survives synthesis, and one that reaches inside the
    design does not -- the nets it names are gone. `gatesim` cannot show that,
    because its testbench is a separate Verilog file written for the netlist;
    here it is the same Python, run twice.
    """
    test_files = get_files(args, config, key="COCOTB_TESTS")
    if not test_files and getattr(args, "if_configured", False) is True:
        skip_unconfigured(config, "cocotb", "COCOTB_TESTS", "TEST_FILES")
        return
    if not test_files:
        log_error(
            "No cocotb tests: set COCOTB_TESTS (or \"//COCOTB_TESTS\") to the "
            "Python test files in the config."
        )
        sys.exit(1)

    toplevel = config_get(config, "DESIGN_NAME")
    if not toplevel:
        log_error("cocotb needs DESIGN_NAME to know which module to drive.")
        sys.exit(1)

    # TEST=<module>[.<function>] narrows the run to one module of COCOTB_TESTS,
    # or one test of it. It is what `make cocotb TEST=<entry>` sets, and what a
    # failed `make regress` run prints to replay. The gate-level run ignores it.
    gate_level = getattr(args, "netlist", None) is not None
    only = None
    if os.environ.get("TEST") and not gate_level:
        only = resolve_test(os.environ["TEST"], test_modules(test_files))

    # Separate names so a gate-level run and an RTL run do not overwrite each
    # other's verdict. `make cocotb` keeps the names it always had.
    stem = "cocotb-gl" if gate_level else "cocotb"

    ensure_build_dir()
    vvp_file = f"build/{stem}.vvp"
    results = os.path.join("build", f"{stem}-results.xml")
    if os.path.exists(results):
        os.remove(results)  # never report a previous run's verdict

    netlist = find_netlist(args.netlist or None) if gate_level else None
    compile_cocotb(args, config, toplevel, vvp_file, netlist)

    env, lib_dir = cocotb_env(test_files, toplevel, results)
    if only:
        env["MODULE"] = only[0]
        env.pop("TESTCASE", None)
        if only[1]:
            env["TESTCASE"] = only[1]

    run_command(cocotb_vvp(vvp_file, lib_dir), env=env)

    # vvp exits 0 even when every test failed -- verified against cocotb 1.9.
    # The verdict only exists in the results file, so that is what decides here.
    check_cocotb_results(results)

def compile_cocotb(args, config, toplevel, vvp_file, netlist=None):
    """
    Compiles the design for cocotb to build/*.vvp: the RTL, or with a netlist
    the gates. -s names the DUT as the root: there is no Verilog testbench to
    elaborate. Shared by `cocotb` and `regress`, which compile the same way.
    """
    if netlist:
        log_info(f"Netlist: {netlist}")
        # FUNCTIONAL and UNIT_DELAY for the reason cmd_gatesim gives: that pair
        # compiles the cell models silently, neither of them alone does. The
        # include dirs are left out -- a netlist has no `include to resolve.
        compile_cmd = ["iverilog", "-g2012", "-DFUNCTIONAL", "-DUNIT_DELAY=#1",
                       "-s", toplevel, "-o", vvp_file]
        compile_cmd += cell_models(config) + [netlist]
    else:
        compile_cmd = ["iverilog", "-g2012", "-s", toplevel, "-o", vvp_file]
        compile_cmd += [f"-I{inc}" for inc in get_include_dirs(config)]
        sources = get_files(args, config, key="VERILOG_FILES")
        compile_cmd += sources
        # A debug VCD is opt-in: WAVES=1 in the environment, which `make
        # cocotb WAVES=1` passes into the container. Only the RTL run dumps.
        if os.environ.get("WAVES") == "1":
            compile_cmd += ["-s", "c4o_dump", write_dump_module(toplevel)]
        # Without a `timescale Icarus runs at 1 s precision, and the first
        # Clock(..., units="ns") dies with "Unable to accurately represent
        # 10(ns)" -- which names neither the cause nor the file. `make sim`
        # never shows it: the Verilog testbench carries its own `timescale.
        if not any("`timescale" in read_text(f) for f in sources):
            log_warn("None of VERILOG_FILES declares a `timescale. So the simulator runs at "
                     "1 s precision, and a cocotb Clock in ns fails with \"Unable to "
                     "accurately represent\". Put `timescale 1ns/1ps on the first line "
                     "of your RTL.")
    run_command(compile_cmd)

def test_modules(test_files):
    """The module names cocotb finds the test files by."""
    return [os.path.splitext(os.path.basename(f))[0] for f in test_files]

def resolve_test(spec, modules):
    """
    Checks a `<module>[.<function>]` name against the modules of COCOTB_TESTS
    and returns (module, function or None). An unknown name is an error that
    lists the modules there are, before anything is compiled.
    """
    module, _, function = spec.partition(".")
    if module not in modules:
        log_error(f"'{spec}' names no module of COCOTB_TESTS. The modules are: {', '.join(modules)}.")
        sys.exit(1)
    if "." in spec and not function:
        log_error(f"'{spec}' ends in a dot. Write <module> or <module>.<function>.")
        sys.exit(1)
    return module, function or None

def cocotb_env(test_files, toplevel, results):
    """
    The environment cocotb's simulator side reads, and the library directory
    the vvp command needs. cocotb finds tests by module name on PYTHONPATH, so
    it gets both.
    """
    modules = test_modules(test_files)
    search = [os.path.dirname(os.path.abspath(f)) for f in test_files]

    # cocotb's GPI dlopens libpython at runtime and cannot find it by itself
    # here: this image has libpython3.12.so.1.0 but not the unversioned symlink,
    # which only the -dev package ships. Without LIBPYTHON_LOC the simulator
    # prints "Unable to open lib libpython3.12.so" and then exits 0 having run
    # nothing. cocotb's own Makefile sets this; so do we.
    libpython = cocotb_config("--libpython")
    if not os.path.exists(libpython):
        log_error(
            f"cocotb points at {libpython} for libpython, and it is not there. "
            "Install the matching libpython package in the image."
        )
        sys.exit(1)

    lib_dir = cocotb_config("--lib-dir")

    env = dict(os.environ)
    env.update({
        "MODULE": ",".join(modules),
        "TOPLEVEL": toplevel,
        "TOPLEVEL_LANG": "verilog",
        "COCOTB_RESULTS_FILE": results,
        "LIBPYTHON_LOC": libpython,
        "PYTHONPATH": os.pathsep.join(dict.fromkeys(search + [os.getcwd()])),
        "LD_LIBRARY_PATH": os.pathsep.join(
            [lib_dir] + ([os.environ["LD_LIBRARY_PATH"]] if "LD_LIBRARY_PATH" in os.environ else [])
        ),
    })
    return env, lib_dir

def cocotb_vvp(vvp_file, lib_dir):
    """The command that runs a compiled design under cocotb."""
    return ["vvp", "-M", lib_dir,
            "-m", cocotb_config("--lib-name", "vpi", "icarus"), vvp_file]

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
    run_command(["verilator_coverage", "--write", merged] + dats)

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
    test_files = get_files(args, config, key="COCOTB_TESTS")
    if not test_files and getattr(args, "if_configured", False) is True:
        skip_unconfigured(config, "coverage", "COCOTB_TESTS", "TEST_FILES")
        return
    if not test_files:
        log_error(
            "No cocotb tests: set COCOTB_TESTS (or \"//COCOTB_TESTS\") to the "
            "Python test files in the config."
        )
        sys.exit(1)

    toplevel = config_get(config, "DESIGN_NAME")
    if not toplevel:
        log_error("coverage needs DESIGN_NAME to know which module to drive.")
        sys.exit(1)

    # Rebuilt from nothing, so a file left by an earlier run is never reported.
    if os.path.isdir(COVERAGE_DIR):
        shutil.rmtree(COVERAGE_DIR)
    # With a test list the runs are the list's, as `regress` makes them: one
    # simulation for each entry and seed, their counts merged. Checked before
    # the build, like every other problem with the list.
    base = plan = None
    if config_get(config, "REGRESSION"):
        base, plan = regression_plan(config, test_files)
        log_info(f"Base seed {base}, {len(plan)} runs. The same runs as `regress`.")
    work = os.path.abspath(os.path.join(COVERAGE_DIR, "work"))
    os.makedirs(work)
    results = os.path.abspath(os.path.join(COVERAGE_DIR, "results.xml"))

    sources = [os.path.abspath(f) for f in get_files(args, config, key="VERILOG_FILES")]
    modules = [os.path.splitext(os.path.basename(f))[0] for f in test_files]
    search = [os.path.dirname(os.path.abspath(f)) for f in test_files]
    flags = ["--coverage"] + disable_warnings(config)

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
        "VERILOG_INCLUDE_DIRS": " ".join(os.path.abspath(d) for d in get_include_dirs(config)),
        "COMPILE_ARGS": " ".join(flags),
        "SIM_BUILD": os.path.join(work, "sim_build"),
        "COCOTB_RESULTS_FILE": results,
        "PYTHONPATH": os.pathsep.join(dict.fromkeys(search + [os.getcwd()])),
    })
    makefile = os.path.join(cocotb_config("--makefiles"), "Makefile.sim")

    build = subprocess.run(
        ["make", "-f", makefile, os.path.join(work, "sim_build", "Vtop")],
        cwd=work, env=env, capture_output=True, text=True,
    )
    with open(os.path.join(COVERAGE_DIR, "build.log"), "w") as f:
        f.write(build.stdout + build.stderr)
    if build.returncode != 0:
        print("\n".join((build.stdout + build.stderr).splitlines()[-40:]))
        log_error("Verilator could not build the design with coverage. The log is build/coverage/build.log.")
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
            log_info(f"Run {number}/{len(runs)} on Verilator: {entry}, seed {seed}")
        else:
            log_info("Running the cocotb tests on Verilator")
        sys.stdout.flush()
        # cocotb's makefile treats an existing results file as an up-to-date
        # run, and skips the simulation.
        if os.path.exists(results):
            os.remove(results)
        started = time.monotonic()
        ran = subprocess.run(["make", "-f", makefile], cwd=work, env=run_env)
        if entry:
            log_info(f"Run {number} took {time.monotonic() - started:.1f} s")

        raw = os.path.join(work, "coverage.dat")
        if not os.path.exists(raw):
            log_error(f"Verilator wrote no coverage.dat (make exit code {ran.returncode}).")
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
        log_info(f"Verilator ran {tests['passed']}/{tests['total']} tests. Pass or fail is decided by `cocotb` on Icarus, not by this run.")
    log_info(f"Wrote {os.path.join(COVERAGE_DIR, 'summary.json')}")

def check_cocotb_results(path):
    """Exits non-zero if the run recorded a failure. vvp will not."""
    if not os.path.exists(path):
        log_error(f"cocotb wrote no results to {path}. The run counts that as a failure.")
        sys.exit(1)
    try:
        cases = ElementTree.parse(path).getroot().iter("testcase")
    except ElementTree.ParseError as e:
        log_error(f"Could not read {path}: {e}")
        sys.exit(1)

    failed = [
        case.get("name")
        for case in cases
        if case.find("failure") is not None or case.find("error") is not None
    ]
    if failed:
        log_error(f"cocotb tests failed: {', '.join(failed)}")
        sys.exit(1)
    log_info("All cocotb tests passed.")

# What `regress` writes. Everything under here is rebuilt on each run.
REGRESS_DIR = "build/regress"

def load_regression(config, test_files):
    """
    Reads the list REGRESSION names and checks every entry before anything runs.
    Returns [(entry, module, function or None, seeds)], where the entry is the
    `test` string as written. Each problem is logged, and any problem exits 1.
    """
    value = config_get(config, "REGRESSION")
    if not isinstance(value, str) or not value.strip():
        log_error("REGRESSION must be the path of a test list, such as dir::tb/regression.yaml.")
        sys.exit(1)
    path = strip_path_prefix(value)
    try:
        with open(path) as f:
            entries = yaml.safe_load(f)
    except OSError as e:
        log_error(f"Could not read the test list {path}: {e.strerror or e}")
        sys.exit(1)
    except yaml.YAMLError as e:
        log_error(f"Failed to parse {path}: {e}")
        sys.exit(1)
    if not isinstance(entries, list) or not entries:
        log_error(f"{path} must be a list with at least one entry, each with a `test` and optionally `seeds`.")
        sys.exit(1)

    modules = test_modules(test_files)
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
        log_error(problem)
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
        log_error(f"RANDOM_SEED must be a whole number, not '{given}'.")
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

    if not config_get(config, "REGRESSION"):
        if getattr(args, "if_configured", False) is True:
            log_info("regress skipped: REGRESSION is not set.")
            return
        log_error("No test list: set REGRESSION (or \"//REGRESSION\") to a YAML file of tests and seeds.")
        sys.exit(1)

    test_files = get_files(args, config, key="COCOTB_TESTS")
    if not test_files:
        log_error("REGRESSION runs tests of COCOTB_TESTS, and the config sets none.")
        sys.exit(1)
    toplevel = config_get(config, "DESIGN_NAME")
    if not toplevel:
        log_error("regress needs DESIGN_NAME to know which module to drive.")
        sys.exit(1)
    base, plan = regression_plan(config, test_files)
    log_info(f"Base seed {base}. RANDOM_SEED={base} reruns this whole list.")

    ensure_build_dir()
    os.makedirs(REGRESS_DIR)
    vvp_file = "build/cocotb.vvp"
    compile_cocotb(args, config, toplevel, vvp_file)
    env, lib_dir = cocotb_env(test_files, toplevel, "")
    command = cocotb_vvp(vvp_file, lib_dir)

    runs = []
    for entry, module, function, seed in plan:
        results = os.path.join(REGRESS_DIR, f"{entry}-{seed}.xml")
        run_env = run_environment(env, module, function, seed)
        run_env["COCOTB_RESULTS_FILE"] = results
        log_info(f"Run {len(runs) + 1}/{len(plan)}: {entry}, seed {seed}")
        started = time.monotonic()
        # Not run_command: it exits on a nonzero status, and one failed
        # run must not hide the verdicts of the rest.
        subprocess.run(command, env=run_env)
        verdict = run_verdict(results)
        log_info(f"{entry} seed {seed}: {verdict} in {time.monotonic() - started:.1f} s")
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
            log_error(f"{run['entry']} seed {run['seed']} failed. Replay it: {replay_command(run['entry'], run['seed'])}")
        sys.exit(1)
    log_info("All regression runs passed.")

def cmd_synth(args, config):
    # Synth only checks RTL
    files = get_files(args, config, key="VERILOG_FILES")
    ensure_build_dir()

    # Generate include commands
    include_cmds = []
    for inc in get_include_dirs(config):
        include_cmds.append(f"verilog_defaults -add -I{inc}")

    # Generate read_verilog commands for each file. -sv for the reason sim
    # passes -g2012: the same file has to read the same way everywhere, and
    # LibreLane's own synthesis reads with -sv too.
    read_cmds = [f"read_verilog -sv {f}" for f in files]

    # Combine commands
    parts = []
    if include_cmds:
        parts.append("; ".join(include_cmds))
    if read_cmds:
        parts.append("; ".join(read_cmds))

    # Determine top module
    synth_cmd = "synth -auto-top"
    if "DESIGN_NAME" in config:
        design_name = config["DESIGN_NAME"]
        log_info(f"Using design name from config: {design_name}")
        synth_cmd = f"synth -top {design_name}"

    parts.append(synth_cmd)
    parts.append("write_json build/synthesis.json")

    yosys_cmd = "; ".join(parts)
    cmd = ["yosys", "-p", yosys_cmd]
    run_command(cmd)

def declared_modules(paths):
    """
    The module names the given Verilog files declare.

    Comments are stripped first, so a commented-out module does not count as
    one. A string literal containing '//' could in principle confuse this, but
    only near a module header, and the failure direction is safe: it would let
    a check pass that should have failed, never the reverse.
    """
    names = set()
    for path in paths:
        try:
            with open(path, errors="replace") as f:
                text = f.read()
        except OSError as e:
            log_error(f"Could not read {path}: {e}")
            sys.exit(1)
        text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
        text = re.sub(r"//[^\n]*", " ", text)
        names.update(re.findall(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)", text))
    return names

def die_area_error(value):
    """
    The sentence to print when DIE_AREA is unusable, or None when it is fine.

    LibreLane accepts it as a list or as a space-separated string, so both are
    read here. Pure arithmetic, no Verilog parsing, so this can be an error
    rather than a warning.
    """
    if isinstance(value, str):
        parts = value.split()
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        return f"DIE_AREA must be four numbers (x0 y0 x1 y1), got {value!r}."

    if len(parts) != 4:
        return f"DIE_AREA needs four numbers (x0 y0 x1 y1), got {len(parts)}: {value!r}."

    try:
        x0, y0, x1, y1 = (float(p) for p in parts)
    except (TypeError, ValueError):
        return f"DIE_AREA must be four numbers (x0 y0 x1 y1), got {value!r}."

    if x1 <= x0 or y1 <= y0:
        return (
            f"DIE_AREA has no area: x {x0} to {x1}, y {y0} to {y1}. "
            "The order is x0 y0 x1 y1, and the second corner must be the larger one."
        )
    return None

# yosys writes <prefix>.dot and, with -format svg, runs dot over it to produce
# <prefix>.svg beside it.
SCHEMATIC_PREFIX = "build/schematic"

def cmd_schematic(args, config):
    """
    Draws the circuit the RTL describes, as build/schematic.svg.

    Deliberately not `synth`'s yosys script. A fully synthesised netlist is a
    wall of technology cells -- blinky alone is 243 of them -- and the picture
    teaches nobody anything. Stopping after `proc; opt` leaves the design at
    the level it was written: flops, adders, muxes, with the names from the
    source still on them.

    SVG rather than the Yosys JSON `synth` already writes, because a file any
    browser and editor opens beats one that needs a particular extension. The
    extension ChipForAll used to point at for that JSON was pulled from the
    marketplace, which is how that lesson arrived.
    """
    files = get_files(args, config, key="VERILOG_FILES")
    ensure_build_dir()

    parts = [f"verilog_defaults -add -I{inc}" for inc in get_include_dirs(config)]
    parts += [f"read_verilog -sv {f}" for f in files]

    design_name = config_get(config, "DESIGN_NAME")
    if design_name:
        log_info(f"Using design name from config: {design_name}")
        parts.append(f"hierarchy -top {design_name}")
    else:
        parts.append("hierarchy -auto-top")

    # proc turns always blocks into registers and muxes; opt clears the
    # obvious clutter. Anything past this and the picture stops resembling
    # the code it came from.
    parts += ["proc", "opt"]

    # -viewer none because yosys otherwise tries to launch a picture viewer
    # for the file it just wrote, which inside a container is an error on the
    # way out rather than a window.
    #
    # 'A:top' is the selection, and without it this command only works on a
    # design of one module. `show` draws everything selected, and for anything
    # but ps or dot yosys refuses more than one:
    #
    #   ERROR: For formats different than 'ps' or 'dot' only one module must
    #          be selected.
    #
    # A design with a submodule is the normal case and blinky, with none, is
    # not -- so this went unnoticed until a real design arrived. 'top' is the
    # attribute `hierarchy` has just set on the root, which makes this the same
    # one module whether DESIGN_NAME named it or -auto-top worked it out.
    parts.append(f"show -format svg -viewer none -prefix {SCHEMATIC_PREFIX} A:top")

    run_command(["yosys", "-p", "; ".join(parts)])
    log_info(f"Wrote {SCHEMATIC_PREFIX}.svg")

def cmd_check(args, config):
    """
    Validates that the configuration is complete enough for the physical design
    flow. It produces no layout of its own -- LibreLane does that -- so this is
    a pre-flight check, which is what the command is named after.

    It checks values, not just that keys are present. A DESIGN_NAME that names
    no module is the first wall anyone hits after putting their own design in
    the template, and without this it surfaces minutes later as a Yosys error,
    or as a LibreLane run that dies partway through.

    A false alarm here is worse than no check, since it blocks a design that
    would have built. So only the two things that can be decided without
    parsing Verilog properly are errors; the port check, which cannot, warns.
    """
    # Which floorplan variable is required depends on how the die is sized.
    # 'absolute' reads DIE_AREA; 'relative' computes the die from FP_CORE_UTIL
    # and ignores DIE_AREA outright. Demanding both meant a relative config --
    # the one a newcomer wants, since it resizes itself around their design --
    # was refused here for a key LibreLane would never have read.
    #
    # Anything that is not 'relative' asks for DIE_AREA, which is what this did
    # before. A value LibreLane does not accept is its error to report; a
    # second opinion here would only turn a future third sizing mode into a
    # false alarm.
    sized_by = "FP_CORE_UTIL" if config_get(config, "FP_SIZING") == "relative" else "DIE_AREA"

    required_keys = [
        "PDK", "STD_CELL_LIBRARY", sized_by,
        "FP_SIZING", "CLOCK_PORT", "CLOCK_PERIOD"
    ]

    missing_keys = [key for key in required_keys if key not in config]

    if missing_keys:
        log_error(f"Missing required keys in the config file for the physical design flow: {', '.join(missing_keys)}")
        sys.exit(1)

    # Validate that we have RTL files
    files = get_files(args, config, key="VERILOG_FILES")
    if not files:
        log_error("No RTL files found. The physical design flow requires valid RTL.")
        sys.exit(1)

    # Checked whenever it is there, not only when it is the sizing variable:
    # LibreLane validates DIE_AREA's shape either way, so a malformed one is an
    # error it would raise too, three minutes later.
    if config_get(config, "DIE_AREA") is not None:
        error = die_area_error(config_get(config, "DIE_AREA"))
        if error:
            log_error(error)
            sys.exit(1)

    design_name = config_get(config, "DESIGN_NAME")
    modules = declared_modules(files)
    if design_name not in modules:
        log_error(
            f"DESIGN_NAME is '{design_name}', but no module by that name is "
            f"declared in VERILOG_FILES. Declared there: "
            f"{', '.join(sorted(modules)) or 'nothing'}."
        )
        sys.exit(1)

    # A warning, not an error: finding a port properly means parsing a port
    # list, which spans lines, carries attributes and can come from a macro.
    # What is safe to say is that a name absent from the RTL entirely is not a
    # port of it -- which is the typo this catches.
    clock_port = config_get(config, "CLOCK_PORT")
    if clock_port and not re.search(rf"\b{re.escape(str(clock_port))}\b", "\n".join(
            open(f, errors="replace").read() for f in files)):
        log_warn(
            f"CLOCK_PORT is '{clock_port}', which does not appear anywhere in "
            "VERILOG_FILES. The flow will not find a clock to constrain."
        )

    log_info("Configuration verified for the physical design flow.")
    # `gds` is an alias of this command, and it exits 0 -- so say outright
    # that nothing was built, or "make gds" reads as a finished layout. Worded
    # to hold both run alone and as the step before LibreLane in a template's
    # `make gds`, where "no layout was produced" read like a failure.
    log_info("This step builds no layout. LibreLane does that.")

# LibreLane writes each timing metric once per corner and again with no
# '__corner:' suffix. The bare key already holds the worst value across every
# corner -- verified against a real run, where timing__setup__ws equalled the
# minimum of its nine per-corner values -- so the bare key is the one to report.
METRICS_GLOBS = ["runs/*/final/metrics.json", "build/runs/*/final/metrics.json"]

def find_metrics(explicit):
    """The newest metrics.json a LibreLane run left behind, unless named."""
    if explicit:
        return explicit
    found = [path for pattern in METRICS_GLOBS for path in glob.glob(pattern)]
    if not found:
        log_error(
            "No metrics.json found under runs/ or build/runs/. Run the physical "
            "design flow first, or name the file: report <path>."
        )
        sys.exit(1)
    return max(found, key=os.path.getmtime)

# The manufacturability checks LibreLane's Classic flow runs after routing.
# Every one of them errors the flow by default (ERROR_ON_MAGIC_DRC and friends
# all default to True), so a run that produced a metrics.json has already
# passed them -- which is exactly why they are worth printing. The other rows
# answer 'is my design any good'; without these, nothing answers 'can it be
# made', and the reader is left inferring it from the absence of a crash.
#
# The two DRC decks are one check, "DRC": two independent tools asked the same
# question. Antenna is its own row because in this flow neither deck checks it.
DRC_TOOLS = [("Magic", "magic__drc_error__count"), ("KLayout", "klayout__drc_error__count")]
SIGNOFF_CHECKS = [
    ("LVS", "design__lvs_error__count"),
    ("antenna", "route__antenna_violation__count"),
    ("XOR", "design__xor_difference__count"),
]

def signoff_checks(metrics):
    """
    (check, errors, tools, failed) per check the run reported, DRC first.

    `tools` names the DRC tools that reported, `failed` the ones with errors
    and their counts: "KLayout", or "Magic 2, KLayout 3" when both. Both are
    empty for the other checks. A key present but null is not a check that
    ran, so it is left out.
    """
    out = []
    drc = [(tool, metrics[key]) for tool, key in DRC_TOOLS if metrics.get(key) is not None]
    if drc:
        bad = [(tool, count) for tool, count in drc if count]
        failed = (bad[0][0] if len(bad) == 1 else ", ".join(f"{t} {c}" for t, c in bad)) if bad else ""
        out.append(("DRC", sum(count for _, count in drc), " and ".join(t for t, _ in drc), failed))
    out += [(label, metrics[key], "", "") for label, key in SIGNOFF_CHECKS
            if metrics.get(key) is not None]
    return out

def signoff_row(metrics):
    """
    One line summarising the checks above, or None when the run reported none.

    Named rather than counted when something is wrong -- '3 DRC (KLayout), 1 LVS'
    is the sentence you want; a column of zeroes with one non-zero hidden in it
    is not.
    """
    present = signoff_checks(metrics)
    if not present:
        return None

    failed, ran = site_page.signoff_words(present)
    if failed:
        return ("signoff", failed)
    # Name the checks that actually ran: 'clean' is only as strong as its list.
    # DRC says its tools, since one of the two may be all that reported.
    return ("signoff", f"clean  ({ran})")

# KLAYOUT_RENDER is registered with extension "png" and folder "render", so the
# file is <design>.png -- not <design>.klayout.png, which is what the format's
# name suggests and what this first looked for. Confirmed against a real
# LibreLane 3.0.14 run, not inferred from the step's f-string.
RENDER_GLOBS = ["final/render/*.png", "*-klayout-render/*.png"]

def step_ordinal(path, run_dir):
    """The number LibreLane gave the step directory a path is under, or -1."""
    head = os.path.relpath(path, run_dir).split("-", 1)[0]
    return int(head) if head.isdigit() else -1

def last_finished_step(run_dir):
    """
    The number of the last step of the run final/metrics.json describes, or
    None when no step directory says.

    LibreLane writes final/ only when a flow reaches its end. A resume that is
    interrupted -- a crash, a kill, Ctrl-C -- leaves step directories newer
    than final/, and reading those puts the timing of a run that never
    finished under the summary of the one that did. Measured on 3.0.14: the
    last step of a finished flow carries exactly final/'s metrics in its
    state_out.json, and no step of a later, different run does.

    Compared as text, so that a NaN in the metrics still equals itself.
    """
    def text(metrics):
        return json.dumps(metrics, sort_keys=True)

    try:
        with open(os.path.join(run_dir, "final", "metrics.json")) as f:
            final = text(json.load(f))
    except (OSError, ValueError):
        return None
    states = glob.glob(os.path.join(run_dir, "*-*", "state_out.json"))
    for state in sorted(states, key=lambda p: -step_ordinal(p, run_dir)):
        try:
            with open(state) as f:
                metrics = json.load(f).get("metrics")
        except (OSError, ValueError):
            continue
        if metrics is not None and text(metrics) == final:
            return step_ordinal(state, run_dir)
    return None

def newest_step(run_dir, pattern):
    """
    The newest match of a pattern that starts with a step directory, among the
    steps of the run final/ describes, or None.

    LibreLane numbers the step directories, and a resumed run adds its steps
    after the ones already there. So 119-openroad-stapostpnr is newer than
    55-openroad-stapostpnr -- and sorts before it as a string, which is how
    the page once showed the timing of the run before the resume.

    Steps after last_finished_step() are left out. When it has no answer --
    a run directory copied without its state files -- every step counts.
    """
    last = last_finished_step(run_dir)
    found = [path for path in sorted(glob.glob(os.path.join(run_dir, pattern)))
             if last is None or step_ordinal(path, run_dir) <= last]
    return max(found, key=lambda p: step_ordinal(p, run_dir)) if found else None

def find_render(metrics_path):
    """
    The PNG KLayout.Render drew of the finished layout.

    The Classic flow renders one on every run and leaves it in the run
    directory, where nobody goes looking. It lands twice: in the step's own
    directory, and again under final/ in the folder KLAYOUT_RENDER is
    registered with. final/ is the copy worth pointing at, so it is tried
    first.

    Both patterns name the directory rather than globbing the whole run for
    *.png, so an unrelated image a step happens to write cannot be reported as
    the layout.

    Only looked for when the file sits where a run leaves it, at
    <run>/final/metrics.json. A metrics.json named on the command line can be
    anywhere, and globbing two directories up from an arbitrary path is how a
    report ends up pointing at a PNG from an unrelated run -- or walking
    someone's entire home directory to find one.
    """
    final_dir = os.path.dirname(os.path.abspath(metrics_path))
    if os.path.basename(final_dir) != "final":
        return None

    run_dir = os.path.dirname(final_dir)
    for pattern in RENDER_GLOBS:
        found = newest_step(run_dir, pattern)
        if not found:
            continue
        # Printed for a human to open, so spell it the way they would type it.
        relative = os.path.relpath(found)
        return found if relative.startswith(os.pardir) else relative
    return None

def find_gds(metrics_path):
    """
    The run's final GDS, at <run>/final/gds/, or None -- including when the
    metrics.json does not sit at <run>/final/, for the reason find_render gives.
    """
    final_dir = os.path.dirname(os.path.abspath(metrics_path))
    if os.path.basename(final_dir) != "final":
        return None
    found = sorted(glob.glob(os.path.join(final_dir, "gds", "*.gds")))
    return found[0] if found else None

# The PDKs Tiny Tapeout's GDS viewer has layer maps for (its src/pdk_layers.js).
# Any other and the page offers the GDS as a download only.
GDS_VIEWER_PDKS = {"sky130A", "ihp-sg13g2", "gf180mcuD"}

def sta_step(metrics_path):
    """
    The newest post-PnR STA step directory of the run a metrics.json belongs
    to, or None -- including when the file does not sit at <run>/final/, for
    the reason find_render gives.
    """
    final_dir = os.path.dirname(os.path.abspath(metrics_path))
    if os.path.basename(final_dir) != "final":
        return None
    return newest_step(os.path.dirname(final_dir), "*-openroad-stapostpnr")

def sta_config(metrics_path):
    """
    The config.json the newest post-PnR STA step ran with, as a dict, or {}.
    It holds the whole resolved config, so it states the constraints the
    result depends on whether config.yaml set them or the flow defaulted them.
    """
    sta = sta_step(metrics_path)
    path = os.path.join(sta, "config.json") if sta else None
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except ValueError:
        return {}

def default_power(metrics_path):
    """(DEFAULT_CORNER, power_groups rows) from that corner's power.rpt, or None."""
    sta = sta_step(metrics_path)
    corner = sta_config(metrics_path).get("DEFAULT_CORNER")
    if not sta or not corner:
        return None
    report = os.path.join(sta, corner, "power.rpt")
    if not os.path.exists(report):
        return None
    with open(report) as f:
        rows = site_page.power_groups(f.read())
    return (corner, rows) if any(r[0] == "Total" for r in rows) else None

def synthesis_design(metrics_path):
    """
    The `design` object of the stat.json Yosys.Synthesis wrote, or {}. Read
    from the run's own step directory, for the reason find_render gives, and
    from the steps of the run final/ describes.
    """
    final_dir = os.path.dirname(os.path.abspath(metrics_path))
    if os.path.basename(final_dir) != "final":
        return {}
    stat = newest_step(os.path.dirname(final_dir), "*-yosys-synthesis/reports/stat.json")
    if not stat:
        return {}
    try:
        with open(stat) as f:
            design = json.load(f).get("design", {})
    except (OSError, ValueError):
        return {}
    return design if isinstance(design, dict) else {}

def synthesis_instances(metrics_path):
    """The cell count Yosys.Synthesis reported (design.num_cells), or None."""
    count = synthesis_design(metrics_path).get("num_cells")
    return count if isinstance(count, int) else None

# A standard cell as the netlists and stat.json name it: sky130_fd_sc_hd__dfrtp_2
# is library sky130_fd_sc_hd, function dfrtp, drive strength 2. The `_sc_` and
# the double underscore are the sky130 naming; a macro or a Yosys-internal
# type does not match and is not counted.
STD_CELL = re.compile(r"\w+?_sc_\w+?__(?P<function>\w+)_(?P<drive>\d+)$")

# Cells with no logic function, which have no drive strength to choose: well
# taps, decap, fill and antenna diodes. LibreLane files the first three under
# tap_cell and fill_cell (decap is fill's). A diode's _2 is its size, not a
# driver's strength, and the flow places it, not the design.
PHYSICAL_ONLY = ("tap", "decap", "fill", "diode")

def drive_strengths(cells):
    """{drive strength: count} of the logic cells in a {cell name: count} map."""
    out = {}
    for name, count in cells.items():
        m = STD_CELL.match(name)
        if m and not m["function"].startswith(PHYSICAL_ONLY):
            out[int(m["drive"])] = out.get(int(m["drive"]), 0) + count
    return out

def routed_cells(metrics_path):
    """
    {cell name: instances} of the routed design, or None. From the netlist
    LibreLane copies to final/nl/, the one list of instances that is plain
    text and needs no tool to open: one line per instance, `<cell> <name> (`.
    Measured on 3.0.14 it holds every instance -- the 274 of a run whose
    metrics count 113 standard cells, 161 fill and decap, and 27 taps -- and
    so does final/pnl/. 53-odb-cellfrequencytables's cell.rpt has the same
    counts, but as a terminal table that the next LibreLane may redraw.
    """
    final_dir = os.path.dirname(os.path.abspath(metrics_path))
    if os.path.basename(final_dir) != "final":
        return None
    found = sorted(glob.glob(os.path.join(final_dir, "nl", "*.nl.v")))
    if not found:
        return None
    counts = {}
    try:
        with open(found[0]) as f:
            for line in f:
                m = re.match(r"\s*(\w+_sc_\w+__\w+)\s+\S+\s*\(", line)
                if m:
                    counts[m[1]] = counts.get(m[1], 0) + 1
    except OSError:
        return None
    return counts

def drive_table(metrics_path):
    """
    [(drive strength, after synthesis, after routing)] by strength, smallest
    first. A stage whose source is missing is None in every row, never a zero;
    [] when neither stage is known.
    """
    synthesized = synthesis_design(metrics_path).get("num_cells_by_type")
    synthesized = drive_strengths(synthesized) if isinstance(synthesized, dict) else None
    routed = routed_cells(metrics_path)
    routed = drive_strengths(routed) if routed is not None else None
    if synthesized is None and routed is None:
        return []
    count = lambda stage, n: None if stage is None else stage.get(n, 0)
    sizes = sorted(set(synthesized or ()) | set(routed or ()))
    return [(n, count(synthesized, n), count(routed, n)) for n in sizes]

# LibreLane's names for the classes a real 3.0.14 run reported, in words. A
# class not listed here is printed under its own name, underscores spaced.
CELL_CLASSES = {
    "multi_input_combinational_cell": "logic",
    "sequential_cell": "sequential",
    "inverter": "inverters",
    "timing_repair_buffer": "timing-repair buffers",
    "clock_buffer": "clock buffers",
    "clock_inverter": "clock inverters",
    "tap_cell": "well taps",
}

# Which classes the flow adds rather than synthesis producing them. Counted
# against a real run: its 198 instances were synthesis's 110 plus 42
# clock-tree, hold and fanout buffers and 46 well taps. A class in neither set
# is shown as "other" rather than guessed at.
FROM_SYNTHESIS = {"multi_input_combinational_cell", "sequential_cell", "inverter"}
ADDED_BY_FLOW = {"timing_repair_buffer", "clock_buffer", "clock_inverter", "tap_cell"}

def cell_classes(metrics):
    """(class, count) per class LibreLane filed cells under, largest first, fill left out."""
    return sorted(
        ((key.split(":", 1)[1], count) for key, count in metrics.items()
         if key.startswith("design__instance__count__class:")
         and not key.endswith(":fill_cell") and count),
        key=lambda c: -c[1])

def report_rows(metrics, path):
    """The (label, value) rows `report` prints, in the order it prints them."""
    rows = []

    bbox = metrics.get("design__die__bbox")
    area = metrics.get("design__die__area")
    if bbox and area is not None:
        x0, y0, x1, y1 = (float(v) for v in bbox.split())
        rows.append(("die", f"{x1 - x0:g} x {y1 - y0:g} um  ({area:g} um^2)"))

    utilization = metrics.get("design__instance__utilization")
    if utilization is not None:
        rows.append(("utilization", f"{utilization * 100:.1f}%"))

    # Instances, not "cells": the count after synthesis is what the design is,
    # and the count after routing adds what the flow put in.
    # Not design__instance__count: that one counts fill instances too, which
    # say nothing about the design -- 544 of this run's 787 were fill. Well
    # taps are in the stdcell count: 46 of this run's 198.
    routed = metrics.get("design__instance__count__stdcell")
    synthesized = synthesis_instances(path)
    if synthesized is not None and routed is not None:
        rows.append(("instances", f"{synthesized} after synthesis, {routed} after routing"))
    elif routed is not None:
        rows.append(("instances", f"{routed} after routing"))
    elif synthesized is not None:
        rows.append(("instances", f"{synthesized} after synthesis"))

    # What the routed instances are, by the class LibreLane files each one
    # under, largest first. Fill is left out for the reason above; in a real
    # run the rest add up to the routed count -- 198, of which 88 are buffers
    # and taps the flow added, not logic the RTL asked for.
    classes = cell_classes(metrics)
    if classes:
        rows.append(("instance classes", ", ".join(
            f"{count} {CELL_CLASSES.get(name, name.replace('_', ' '))}"
            for name, count in classes)))

    # What drive strength the cells have, before and after the flow. Taps, decap
    # and fill have none and are left out. Only the stages that are known.
    drive = drive_table(path)
    if drive:
        if all(s is not None and r is not None for _, s, r in drive):
            text = ", ".join(f"X{n} {s}->{r}" for n, s, r in drive)
            stage = "synthesis->routing"
        else:
            text = ", ".join(f"X{n} {s if s is not None else r}" for n, s, r in drive)
            stage = "after synthesis" if drive[0][1] is not None else "after routing"
        rows.append(("drive strength", f"{text}  ({stage})"))

    for label, slack_key, violation_key in (
        ("setup slack", "timing__setup__ws", "timing__setup_vio__count"),
        ("hold slack", "timing__hold__ws", "timing__hold_vio__count"),
    ):
        slack = metrics.get(slack_key)
        if slack is not None:
            violations = metrics.get(violation_key, "?")
            rows.append((label, f"{slack:+.2f} ns  ({violations} violations)"))

    drv = drv_violations(metrics)
    if drv:
        counts = ", ".join(f"{n} {label}" for label, n, _ in drv)
        corners = sorted({c for _, _, cs in drv for c in cs})
        rows.append(("limit violations", counts + (f"  ({', '.join(corners)})" if corners else "")))

    # The default corner's power.rpt when the run left one: the bare
    # power__total names no corner, and in a real 3.0.14 run it is
    # max_ff_n40C_1v95's, not the default corner's.
    corner_power = default_power(path)
    if corner_power:
        corner, groups = corner_power
        total = next(g[4] for g in groups if g[0] == "Total")
        rows.append(("power", f"{site_page.milliwatts(total)}  ({corner})"))  # watts
    elif metrics.get("power__total") is not None:
        rows.append(("power", f"{site_page.milliwatts(metrics['power__total'])}  (corner not named)"))

    signoff = signoff_row(metrics)
    if signoff:
        rows.append(signoff)

    # Not fatal, and invisible everywhere else.
    warnings = metrics.get("design__lint_warning__count")
    if warnings is not None:
        rows.append(("lint warnings", str(warnings)))

    # Last because it is a pointer, not a measurement.
    render = find_render(path)
    if render:
        rows.append(("layout", render))

    return rows

def read_metrics(path):
    log_info(f"Reading metrics from {path}")
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        log_error(f"Could not read {path}: {e}")
        sys.exit(1)

def cmd_report(args, config):
    """
    Prints the handful of numbers that answer 'is my design any good' -- how big
    it is, whether it makes timing, what it burns. The flow computes all of this
    and then leaves it in a 300-key JSON file nobody opens.

    Informational only. It does not fail on a timing violation: closing timing
    is iterative, and LibreLane does not treat it as fatal either.
    """
    path = find_metrics(getattr(args, "metrics", None))
    rows = report_rows(read_metrics(path), path)

    if not rows:
        log_error(f"{path} carried none of the metrics this report reads.")
        sys.exit(1)

    label_width = max(len(label) for label, _ in rows)
    print()
    print(f"  {config_get(config, 'DESIGN_NAME', 'design')}")
    print()
    for label, value in rows:
        print(f"  {label.ljust(label_width)}   {value}")
    print()

# One page with what `report` prints, the layout and every
# cocotb verdict, for publishing on GitHub Pages. Everything it needs is copied
# into this directory, so the directory is the whole site. The markup is in
# site_page.py; this half finds the files.
SITE_DIR = "build/site"

COCOTB_RESULTS = [
    ("cocotb, RTL", "build/cocotb-results.xml"),
    ("cocotb, gate level", "build/cocotb-gl-results.xml"),
]

# The constraints the timing result depends on, as the STA step's config.json
# names them, with the unit LibreLane gives each.
CONSTRAINTS = [
    ("clock_period", "CLOCK_PERIOD"),
    ("uncertainty", "CLOCK_UNCERTAINTY_CONSTRAINT"),
    ("transition", "CLOCK_TRANSITION_CONSTRAINT"),
    ("derate", "TIME_DERATING_CONSTRAINT"),
    ("io_delay", "IO_DELAY_CONSTRAINT"),
]

def number(value):
    """A config value as a float, or None. LibreLane writes Decimals as numbers."""
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def run_details(metrics_path, metrics, config):
    """
    What the page shows beyond `report`'s rows, from the reports LibreLane
    leaves next to a run's metrics.json. Only when the file sits at
    <run>/final/metrics.json, for the reason find_render gives. Any part whose
    report is missing is left out.

    `config` is the design's config, which tells a constraint it set from one
    the flow defaulted.
    """
    details = {"signoff": signoff_checks(metrics)}
    final_dir = os.path.dirname(os.path.abspath(metrics_path))
    physical = details["physical"] = physical_details(metrics)
    if os.path.basename(final_dir) != "final":
        return details

    run_config = sta_config(metrics_path)
    constraints = {}
    for name, key in CONSTRAINTS:
        value = number(run_config.get(key))
        if value is not None:
            constraints[name] = (value, key in config)
    if constraints:
        physical["constraints"] = constraints
    corner = run_config.get("DEFAULT_CORNER")
    if corner:
        physical["corner"] = corner
    synthesized = synthesis_instances(metrics_path)
    if synthesized is not None:
        physical["synthesized"] = synthesized

    power = default_power(metrics_path)
    if power:
        details["power"] = power

    design = synthesis_design(metrics_path)
    drive = drive_table(metrics_path)
    if drive:
        details["drive"] = drive
    library = run_config.get("STD_CELL_LIBRARY")
    if isinstance(library, str) and library:
        physical["library"] = library
    # Two stages, not three peers: what synthesis produced (flip-flops and
    # logic), and the standard-cell total after routing, which contains them.
    area = {}
    if "area" in design and "sequential_area" in design:
        area["flip_flops"] = design["sequential_area"]
        area["logic"] = design["area"] - design["sequential_area"]
    if metrics.get("design__instance__area__stdcell") is not None:
        area["routed"] = metrics["design__instance__area__stdcell"]
    if metrics.get("design__instance__area__macros"):
        area["macros"] = metrics["design__instance__area__macros"]
    if area:
        details["area"] = area

    cells = [(CELL_CLASSES.get(name, name.replace("_", " ")), count,
              "synthesis" if name in FROM_SYNTHESIS
              else "flow" if name in ADDED_BY_FLOW else "other")
             for name, count in cell_classes(metrics)]
    if cells:
        details["cells"] = cells
    return details

# Violations of the cell library's limits after routing. The bare key is the
# worst over every corner; each corner has its own key with a suffix.
DRV_METRICS = (("max slew", "design__max_slew_violation__count"),
               ("max capacitance", "design__max_cap_violation__count"),
               ("max fanout", "design__max_fanout_violation__count"))

def drv_violations(metrics):
    """
    (limit, violations, corners with a violation) for each limit the run
    reported, in DRV_METRICS order. The flow does not fail on these, so the
    report and the page are where they show.
    """
    rows = []
    for label, metric in DRV_METRICS:
        if metrics.get(metric) is None:
            continue
        prefix = f"{metric}__corner:"
        corners = sorted(k[len(prefix):] for k, v in metrics.items() if k.startswith(prefix) and v)
        rows.append((label, metrics[metric], corners))
    return rows

def physical_details(metrics):
    """What a physical designer reads first, for the page; absent keys left out."""
    get = metrics.get
    out = {}
    if get("design__core__bbox"):
        x0, y0, x1, y1 = (float(v) for v in get("design__core__bbox").split())
        out["core"] = (x1 - x0, y1 - y0)
    for key, metric in (("taps", "design__instance__count__class:tap_cell"),
                        ("hold_buffers", "design__instance__count__hold_buffer"),
                        ("r2r_setup", "timing__setup_r2r__ws"),
                        ("r2r_hold", "timing__hold_r2r__ws"),
                        ("ir_worst", "ir__drop__worst")):
        if get(metric) is not None:
            out[key] = get(metric)
    # Worst slack over every corner (the bare key, see METRICS_GLOBS) and how
    # many paths miss, for the timing verdict.
    for key in ("setup", "hold"):
        if get(f"timing__{key}__ws") is not None:
            out[key] = (get(f"timing__{key}__ws"), get(f"timing__{key}_vio__count"))
    drv = drv_violations(metrics)
    if drv:
        out["drv"] = drv
    return out

# The files the page offers, with the section each belongs to. Each is copied
# only when it exists. The two summary.json are renamed so that they do not
# collide next to the page.
SITE_FILES = [
    ("tests", "build/cocotb-results.xml", "cocotb-results.xml"),
    ("tests", "build/cocotb-gl-results.xml", "cocotb-gl-results.xml"),
    ("regression", os.path.join(REGRESS_DIR, "summary.json"), "regress-summary.json"),
    ("coverage", os.path.join(COVERAGE_DIR, "summary.json"), "coverage-summary.json"),
]

# Every earlier run's numbers, in the order they were published. `report` fetches
# it from the live page before `site` runs (see actions/report).
HISTORY_FILE = "build/history.json"

def read_history(path=HISTORY_FILE):
    """
    The earlier rows of history.json, or [] when there is no file. The file is
    something an earlier run published, so one that is not a JSON list of
    objects is an error here and not a page that quietly starts over.
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            rows = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        log_error(f"Could not read {path}: {e}")
        sys.exit(1)
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        log_error(f"Could not read {path}: it is not a list of objects.")
        sys.exit(1)
    return rows

def c4o_version():
    """
    The c4o-core release, from version.txt at the root of the checkout or of
    /opt/c4o-core, or None. Found from this file, not from the working directory,
    which is the user's design.
    """
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    try:
        with open(os.path.join(root, "version.txt")) as f:
            return f.read().strip() or None
    except OSError:
        return None

def history_row(env, details, cocotb_runs, coverage, regression):
    """
    This run's numbers as one row of history.json, the same numbers the page
    shows. A number the run did not produce is None, which a chart draws as a
    gap. The names are the file's format: a later image reads rows an earlier
    one wrote.
    """
    physical = details.get("physical") or {}
    area = details.get("area") or {}
    cells = details.get("cells")
    power = details.get("power")
    count = lambda title: next(((sum(v == "PASS" for _, v, _ in cases), len(cases))
                                for t, _, cases in cocotb_runs if t == title), (None, None))
    runs = (regression or {}).get("runs")
    percent = lambda kind: (((coverage or {}).get("types") or {}).get(kind) or {}).get("percent")
    row = {
        "sha": env.get("GITHUB_SHA"),
        "built": site_page.build_time(env).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "c4o_version": c4o_version(),
        "clock_period": (physical.get("constraints") or {}).get("clock_period", (None,))[0],
        "regress_passed": sum(run["verdict"] == "pass" for run in runs) if runs else None,
        "regress_total": len(runs) if runs else None,
        "cov_block": percent("line"), "cov_branch": percent("branch"), "cov_toggle": percent("toggle"),
        "setup_ws": physical.get("setup", (None,))[0], "hold_ws": physical.get("hold", (None,))[0],
        "area_ff": area.get("flip_flops"), "area_logic": area.get("logic"), "area_routed": area.get("routed"),
        "inst_synth": physical.get("synthesized"),
        "inst_routed": sum(n for _, n, _ in cells) if cells else None,
        # The default corner's total, which is what the Power section shows.
        "power_w": next((r[4] for r in power[1] if r[0] == "Total"), None) if power else None,
        "ir_drop_v": physical.get("ir_worst"),
        "ir_drop_pct": site_page.ir_drop_share(physical),
    }
    row["rtl_passed"], row["rtl_total"] = count("cocotb, RTL")
    row["gl_passed"], row["gl_total"] = count("cocotb, gate level")
    return row

def merge_history(rows, row):
    """
    The rows with this run's added at the end. A row with the same commit is
    replaced where it stands: a re-run of the same commit is not a second
    commit.
    """
    same = [i for i, old in enumerate(rows) if old.get("sha") == row["sha"]]
    if not same:
        return rows + [row]
    merged = list(rows)
    merged[same[0]] = row
    for i in reversed(same[1:]):
        del merged[i]
    return merged

def cmd_site(args, config):
    """
    Writes build/site/index.html: the cocotb verdicts, code coverage, the timing
    verdict and the constraints behind it, area and instances, power and signoff, with the
    layout render beside the title. Each part is included when the file behind
    it exists, so it works after `make cocotb` alone as well as after the full
    flow. Each section also offers the files behind it, and gets a History fold
    from build/history.json, to which a run on GitHub Actions adds its own row.

    It reports; it does not judge. A failed test is shown as failed and the
    command still succeeds -- the command that ran the test is the gate.
    """
    if os.path.isdir(SITE_DIR):
        shutil.rmtree(SITE_DIR)  # never publish a previous run's picture
    os.makedirs(SITE_DIR)

    numbers, layout, details = [], None, {}
    files = []  # (section, name next to the page) of each file copied
    found = [path for pattern in METRICS_GLOBS for path in glob.glob(pattern)]
    if found:
        path = max(found, key=os.path.getmtime)
        metrics = read_metrics(path)
        rows = report_rows(metrics, path)
        details = run_details(path, metrics, config)
        # The clock the run used. Without a run directory to read it from, the
        # one the config asks for.
        constraints = details["physical"].setdefault("constraints", {})
        period = number(config_get(config, "CLOCK_PERIOD"))
        if "clock_period" not in constraints and period and period > 0:
            constraints["clock_period"] = (period, True)
        # Each has a section of their own on the page. Power only when that
        # section exists: its row is the bare metric, which names no corner
        # and would disagree with the table next to it.
        own = ({"layout", "signoff"} | ({"power"} if "power" in details else set())
               | ({"instance classes"} if "cells" in details else set())
               | {"drive strength"})
        numbers = [(label, value) for label, value in rows if label not in own]
        render = dict(rows).get("layout")
        if render:
            layout = "layout.png"
            shutil.copy(render, os.path.join(SITE_DIR, layout))
        # The layout itself, next to its picture: a download, and on a
        # published page a link that opens it in 3D.
        gds = find_gds(path)
        if gds:
            name = os.path.basename(gds)
            shutil.copy(gds, os.path.join(SITE_DIR, name))
            pdk = config_get(config, "PDK", "sky130A")
            details["gds"] = (name, pdk if pdk in GDS_VIEWER_PDKS else None,
                              os.path.getsize(gds))
        # The files of this run and no other: the netlist and the constraints
        # sit at the same <run>/final/ as the metrics.json the numbers come from.
        files.append(("summary", path, "metrics.json"))
        final_dir = os.path.dirname(os.path.abspath(path))
        if os.path.basename(final_dir) == "final":
            for section, pattern in (("timing", "sdc/*.sdc"), ("area", "nl/*.nl.v")):
                found_file = sorted(glob.glob(os.path.join(final_dir, pattern)))
                if found_file:
                    files.append((section, found_file[0], os.path.basename(found_file[0])))

    cocotb_runs = []
    for title, results in COCOTB_RESULTS:
        if not os.path.exists(results):
            continue
        try:
            seed, cases = site_page.cocotb_cases(results)
        except ElementTree.ParseError as e:
            log_error(f"Could not read {results}: {e}")
            sys.exit(1)
        cocotb_runs.append((title, seed, cases))

    files += [(section, src, name) for section, src, name in SITE_FILES if os.path.exists(src)]

    # From `make coverage`. Left out when it was not run, like every other part.
    coverage = None
    summary_path = os.path.join(COVERAGE_DIR, "summary.json")
    if os.path.exists(summary_path):
        try:
            with open(summary_path) as f:
                coverage = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            log_error(f"Could not read {summary_path}: {e}")
            sys.exit(1)

    # From `make regress`. Left out when it was not run, like every other part.
    regression = None
    regress_path = os.path.join(REGRESS_DIR, "summary.json")
    if os.path.exists(regress_path):
        try:
            with open(regress_path) as f:
                regression = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            log_error(f"Could not read {regress_path}: {e}")
            sys.exit(1)
        # The tests each entry holds, from the results file of each of its
        # runs, so the page can tie a module of the list to the tests in Tests.
        # A run with no readable results file adds no name: its verdict is
        # already a fail in the summary.
        tests = {}
        for run in regression.get("runs") or []:
            names = tests.setdefault(run["entry"], [])
            path = os.path.join(REGRESS_DIR, f"{run['entry']}-{run['seed']}.xml")
            try:
                _, cases = site_page.cocotb_cases(path)
            except (OSError, ElementTree.ParseError):
                continue
            names += [name for name, _, _ in cases if name not in names]
        regression["tests"] = tests

    if not (numbers or layout or cocotb_runs or details or coverage or regression):
        log_error(
            "Nothing to put on the page: no metrics.json under runs/ and no "
            "cocotb results. Run make cocotb or make gds first."
        )
        sys.exit(1)

    # The rows of the earlier runs, and this run's only on GitHub Actions: a
    # local `make site` is not a commit and must not leave a row behind.
    history = read_history()
    if os.environ.get("GITHUB_SHA"):
        history = merge_history(history, history_row(os.environ, details, cocotb_runs, coverage, regression))
    if history:
        with open(os.path.join(SITE_DIR, "history.json"), "w") as f:
            json.dump(history, f, separators=(",", ":"))
        files.append(("summary", os.path.join(SITE_DIR, "history.json"), "history.json"))

    offered = []
    for section, src, name in files:
        dest = os.path.join(SITE_DIR, name)
        if os.path.abspath(src) != os.path.abspath(dest):
            shutil.copy(src, dest)
        offered.append((section, name, os.path.getsize(dest)))

    design = config_get(config, "DESIGN_NAME", "design")
    index = os.path.join(SITE_DIR, "index.html")
    with open(index, "w") as f:
        f.write(site_page.render(design, numbers, layout, cocotb_runs, os.environ,
                                 description=config_get(config, "DESCRIPTION", None),
                                 coverage=coverage, regression=regression,
                                 history=history, files=offered, **details))
    log_info(f"Wrote {index}")

def cmd_pdk(args, config):
    # Same rule as the read path in gatesim_cell_models: PDK_ROOT wins, ./pdks
    # is the default. Installing to a fixed ./pdks while every reader honoured
    # PDK_ROOT meant the variable could only ever point at a PDK this command
    # had not installed -- so one 3GB copy per checkout was the only layout
    # that worked, and a shared read-only PDK was unreachable.
    pdk_root = os.environ.get("PDK_ROOT") or os.path.join(os.getcwd(), "pdks")
    if not os.path.exists(pdk_root):
        log_info(f"Creating PDK root directory: {pdk_root}")
        os.makedirs(pdk_root)

    # Commit hash from requirements
    commit_hash = "bdc9412b3e468c102d01b7cf6337be06ec6e9c9a"

    # Ciel is Volare's successor and takes the same arguments.
    cmd = [
        "ciel", "enable",
        "--pdk", "sky130",
        "--pdk-root", pdk_root,
        commit_hash
    ]
    run_command(cmd)

def build_parser():
    parser = argparse.ArgumentParser(description="c4o-core entrypoint script")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Lint command
    lint_parser = subparsers.add_parser("lint", help="Run Verilator lint")
    lint_parser.add_argument("--files", nargs="*", help="Verilog files to lint")
    lint_parser.set_defaults(func=cmd_lint)

    # Sim command
    sim_parser = subparsers.add_parser("sim", help="Run Icarus Verilog simulation")
    sim_parser.add_argument("--files", nargs="*", help="Verilog files to simulate")
    sim_parser.add_argument(
        "--if-configured", action="store_true",
        help="Skip, with a message, when TEST_FILES is not set (used by make all)",
    )
    sim_parser.set_defaults(func=cmd_sim)

    # Cocotb command
    cocotb_parser = subparsers.add_parser(
        "cocotb", help="Run cocotb (Python) tests against the RTL"
    )
    cocotb_parser.add_argument("--files", nargs="*", help="Verilog RTL files")
    # Bare --netlist means "the newest one", the same default gatesim takes.
    # Absent is RTL; present with no value is the empty string, which find_netlist
    # reads as "go and look".
    cocotb_parser.add_argument(
        "--netlist",
        nargs="?",
        const="",
        help="Drive the synthesised netlist instead of the RTL "
             "(default: the newest under runs/ or build/runs/)",
    )
    cocotb_parser.add_argument(
        "--if-configured", action="store_true",
        help="Skip, with a message, when COCOTB_TESTS is not set (used by make all)",
    )
    cocotb_parser.set_defaults(func=cmd_cocotb)

    # Regress command
    regress_parser = subparsers.add_parser(
        "regress", help="Run the cocotb tests listed in REGRESSION over many seeds"
    )
    regress_parser.add_argument(
        "--if-configured", action="store_true",
        help="Skip, with a message, when REGRESSION is not set",
    )
    regress_parser.set_defaults(func=cmd_regress)

    # Coverage command
    coverage_parser = subparsers.add_parser(
        "coverage", help="Measure code coverage of the cocotb tests on Verilator"
    )
    coverage_parser.add_argument("--files", nargs="*", help="Verilog RTL files")
    coverage_parser.add_argument(
        "--if-configured", action="store_true",
        help="Skip, with a message, when COCOTB_TESTS is not set",
    )
    coverage_parser.set_defaults(func=cmd_coverage)

    # Gate-level sim command
    gatesim_parser = subparsers.add_parser(
        "gatesim",
        help="Simulate the synthesised netlist against the PDK cell models "
             "(GATE_TESTS, else the COCOTB_TESTS)",
    )
    gatesim_parser.add_argument(
        "netlist",
        nargs="?",
        help="Path to the netlist (default: the newest under runs/ or build/runs/)",
    )
    gatesim_parser.set_defaults(func=cmd_gatesim)

    # Synth command
    synth_parser = subparsers.add_parser("synth", help="Run Yosys synthesis")
    synth_parser.add_argument("--files", nargs="*", help="Verilog files to synthesize")
    synth_parser.set_defaults(func=cmd_synth)

    # Check command. 'gds' is kept as an alias: it is what this command was
    # called before, and dropping it would break every pinned caller for a
    # rename.
    schematic_parser = subparsers.add_parser(
        "schematic",
        help="Draw the circuit as build/schematic.svg (RTL level, not the netlist)",
    )
    schematic_parser.add_argument("--files", nargs='*', help="Verilog files to draw")
    schematic_parser.set_defaults(func=cmd_schematic)

    check_parser = subparsers.add_parser(
        "check",
        aliases=["gds"],
        help="Validate the config for the physical design flow (pre-flight only)",
    )
    check_parser.set_defaults(func=cmd_check)

    # Report command
    report_parser = subparsers.add_parser(
        "report", help="Summarise a LibreLane run's metrics.json"
    )
    report_parser.add_argument(
        "metrics",
        nargs="?",
        help="Path to metrics.json (default: the newest under runs/ or build/runs/)",
    )
    report_parser.set_defaults(func=cmd_report)

    site_parser = subparsers.add_parser(
        "site", help="Write build/site/index.html: cocotb results, timing, area, power, signoff"
    )
    site_parser.set_defaults(func=cmd_site)

    # PDK command
    pdk_parser = subparsers.add_parser("pdk", help="Install/Enable Sky130 PDK via Ciel")
    pdk_parser.set_defaults(func=cmd_pdk)

    return parser

def main():
    parser = build_parser()

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    args.func(args, load_config())

if __name__ == "__main__":
    main()
