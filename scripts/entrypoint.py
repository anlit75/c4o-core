#!/usr/bin/env python3
import argparse
import glob
import json
import os
import re
import subprocess
import sys
from xml.etree import ElementTree

import yaml

# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def log_info(msg):
    print(f"{GREEN}[INFO] {msg}{RESET}")

def log_error(msg):
    print(f"{RED}[ERROR] {msg}{RESET}")

def log_warn(msg):
    print(f"{YELLOW}[WARN] {msg}{RESET}")

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
    Supports globbing (e.g. src/**/*.v).

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
    with no default on purpose: LibreLane defaults it to DECLFILENAME and
    EOFNEWLINE, and neither of those fires in verilator 5.020 unless asked for,
    so copying the default would only add flags that change nothing.
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

def cmd_lint(args, config):
    # Lint only checks RTL
    files = get_files(args, config, key="VERILOG_FILES")
    cmd = ["verilator", "--lint-only"]

    cmd += disable_warnings(config)

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

def cmd_sim(args, config):
    # Sim needs RTL + TEST

    # If CLI args are provided, they override the concept of keys completely.
    if getattr(args, "files", None):
        files = get_files(args, config) # key doesn't matter if args.files is set
        test_files = []
    else:
        rtl_files = get_files(args, config, key="VERILOG_FILES")
        test_files = get_files(args, config, key="TEST_FILES")
        if not test_files:
            log_error(
                "sim has no testbench: set TEST_FILES (or \"//TEST_FILES\") in the "
                "config, or pass --files."
            )
            sys.exit(1)
        files = rtl_files + test_files

    ensure_build_dir()
    # iverilog -o build/sim.vvp <files> && vvp build/sim.vvp
    compile_cmd = ["iverilog", "-o", "build/sim.vvp"]

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
            "design flow first, or name the file: gatesim <path>."
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
    """
    netlist = find_netlist(getattr(args, "netlist", None))
    log_info(f"Netlist: {netlist}")

    tests = get_files(args, config, key="GATE_TESTS")
    if not tests:
        log_error(
            "No gate-level testbench: set GATE_TESTS (or \"//GATE_TESTS\") in "
            "the config."
        )
        sys.exit(1)

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

def cmd_cocotb(args, config):
    """
    Runs cocotb tests: Python coroutines driving the RTL, rather than a Verilog
    testbench. Same simulator underneath, so this is an alternative to `sim`,
    not a replacement for it.
    """
    rtl_files = get_files(args, config, key="VERILOG_FILES")

    test_files = get_files(args, config, key="COCOTB_TESTS")
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

    ensure_build_dir()
    vvp_file = "build/cocotb.vvp"
    results = os.path.join("build", "cocotb-results.xml")
    if os.path.exists(results):
        os.remove(results)  # never report a previous run's verdict

    # -s names the DUT as the root: there is no Verilog testbench to elaborate.
    run_command(["iverilog", "-g2012", "-s", toplevel, "-o", vvp_file] +
                [f"-I{inc}" for inc in get_include_dirs(config)] + rtl_files)

    # cocotb finds tests by module name on PYTHONPATH, so hand it both.
    modules = [os.path.splitext(os.path.basename(f))[0] for f in test_files]
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

    run_command(
        ["vvp", "-M", lib_dir,
         "-m", cocotb_config("--lib-name", "vpi", "icarus"), vvp_file],
        env=env,
    )

    # vvp exits 0 even when every test failed -- verified against cocotb 1.9.
    # The verdict only exists in the results file, so that is what decides here.
    check_cocotb_results(results)

def check_cocotb_results(path):
    """Exits non-zero if the run recorded a failure. vvp will not."""
    if not os.path.exists(path):
        log_error(f"cocotb wrote no results to {path}; treating that as a failure.")
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

def cmd_synth(args, config):
    # Synth only checks RTL
    files = get_files(args, config, key="VERILOG_FILES")
    ensure_build_dir()

    # Generate include commands
    include_cmds = []
    for inc in get_include_dirs(config):
        include_cmds.append(f"verilog_defaults -add -I{inc}")

    # Generate read_verilog commands for each file
    read_cmds = [f"read_verilog {f}" for f in files]

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
    parts += [f"read_verilog {f}" for f in files]

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
    parts.append(f"show -format svg -viewer none -prefix {SCHEMATIC_PREFIX}")

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
        log_error(f"Missing required keys in the config file for GDS generation: {', '.join(missing_keys)}")
        sys.exit(1)

    # Validate that we have RTL files
    files = get_files(args, config, key="VERILOG_FILES")
    if not files:
        log_error("No RTL files found. GDS generation requires valid RTL.")
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
SIGNOFF_CHECKS = [
    ("Magic DRC", "magic__drc_error__count"),
    ("KLayout DRC", "klayout__drc_error__count"),
    ("LVS", "design__lvs_error__count"),
    ("antenna", "route__antenna_violation__count"),
    ("XOR", "design__xor_difference__count"),
]

def signoff_row(metrics):
    """
    One line summarising the checks above, or None when the run reported none.

    Named rather than counted when something is wrong -- '2 Magic DRC, 1 LVS'
    is the sentence you want; a column of zeroes with one non-zero hidden in it
    is not.

    A key present but null is not a check that passed, so it does not count
    towards 'clean' either.
    """
    present = [
        (label, metrics[key])
        for label, key in SIGNOFF_CHECKS
        if metrics.get(key) is not None
    ]
    if not present:
        return None

    failed = [f"{count} {label}" for label, count in present if count]
    if failed:
        return ("signoff", ", ".join(failed))
    # Name the checks that actually ran: 'clean' is only as strong as its list.
    return ("signoff", "clean  (" + ", ".join(label for label, _ in present) + ")")

# KLAYOUT_RENDER is registered with extension "png" and folder "render", so the
# file is <design>.png -- not <design>.klayout.png, which is what the format's
# name suggests and what this first looked for. Confirmed against a real
# LibreLane 3.0.14 run, not inferred from the step's f-string.
RENDER_GLOBS = ["final/render/*.png", "*-klayout-render/*.png"]

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
        found = sorted(glob.glob(os.path.join(run_dir, pattern)))
        if not found:
            continue
        # Printed for a human to open, so spell it the way they would type it.
        relative = os.path.relpath(found[0])
        return found[0] if relative.startswith(os.pardir) else relative
    return None

def cmd_report(args, config):
    """
    Prints the handful of numbers that answer 'is my design any good' -- how big
    it is, whether it makes timing, what it burns. The flow computes all of this
    and then leaves it in a 300-key JSON file nobody opens.

    Informational only. It does not fail on a timing violation: closing timing
    is iterative, and LibreLane does not treat it as fatal either.
    """
    path = find_metrics(getattr(args, "metrics", None))
    log_info(f"Reading metrics from {path}")
    try:
        with open(path) as f:
            metrics = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        log_error(f"Failed to read {path}: {e}")
        sys.exit(1)

    rows = []

    bbox = metrics.get("design__die__bbox")
    area = metrics.get("design__die__area")
    if bbox and area is not None:
        x0, y0, x1, y1 = (float(v) for v in bbox.split())
        rows.append(("die", f"{x1 - x0:g} x {y1 - y0:g} um  ({area:g} um^2)"))

    utilization = metrics.get("design__instance__utilization")
    if utilization is not None:
        rows.append(("utilization", f"{utilization * 100:.1f}%"))

    # Not design__instance__count: that one counts fill and tap cells, which say
    # nothing about the design -- 544 of this run's 787 instances were fill.
    cells = metrics.get("design__instance__count__stdcell")
    if cells is not None:
        rows.append(("standard cells", str(cells)))

    for label, slack_key, violation_key in (
        ("setup slack", "timing__setup__ws", "timing__setup_vio__count"),
        ("hold slack", "timing__hold__ws", "timing__hold_vio__count"),
    ):
        slack = metrics.get(slack_key)
        if slack is not None:
            violations = metrics.get(violation_key, "?")
            rows.append((label, f"{slack:+.2f} ns  ({violations} violations)"))

    power = metrics.get("power__total")
    if power is not None:
        rows.append(("power", f"{power * 1e3:.3f} mW"))  # OpenSTA reports watts

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

def cmd_pdk(args, config):
    pdk_root = os.path.join(os.getcwd(), "pdks")
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
    sim_parser.set_defaults(func=cmd_sim)

    # Cocotb command
    cocotb_parser = subparsers.add_parser(
        "cocotb", help="Run cocotb (Python) tests against the RTL"
    )
    cocotb_parser.add_argument("--files", nargs="*", help="Verilog RTL files")
    cocotb_parser.set_defaults(func=cmd_cocotb)

    # Gate-level sim command
    gatesim_parser = subparsers.add_parser(
        "gatesim", help="Simulate the synthesised netlist against the PDK cell models"
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
