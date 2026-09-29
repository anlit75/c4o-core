#!/usr/bin/env python3
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from xml.etree import ElementTree

import yaml

import diagrams
import site_page

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

    # Separate names so a gate-level run and an RTL run do not overwrite each
    # other's verdict. `make cocotb` keeps the names it always had.
    gate_level = getattr(args, "netlist", None) is not None
    stem = "cocotb-gl" if gate_level else "cocotb"

    ensure_build_dir()
    vvp_file = f"build/{stem}.vvp"
    results = os.path.join("build", f"{stem}-results.xml")
    if os.path.exists(results):
        os.remove(results)  # never report a previous run's verdict

    # -s names the DUT as the root: there is no Verilog testbench to elaborate.
    if gate_level:
        netlist = find_netlist(args.netlist or None)
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
        compile_cmd += get_files(args, config, key="VERILOG_FILES")
    run_command(compile_cmd)

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
BLOCKS_DIR = "build/blocks"

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
    parts.append(f"write_json {SCHEMATIC_PREFIX}.json")

    # Never draw a previous design's blocks.
    if os.path.exists(SCHEMATIC_PREFIX + ".json"):
        os.remove(SCHEMATIC_PREFIX + ".json")
    if os.path.isdir(BLOCKS_DIR):
        shutil.rmtree(BLOCKS_DIR)
    prepare = parts[:parts.index("opt") + 1]
    run_command(["yosys", "-p", "; ".join(parts)])
    log_info(f"Wrote {SCHEMATIC_PREFIX}.svg")
    draw_blocks(SCHEMATIC_PREFIX + ".json", prepare)

def draw_blocks(netlist_path, prepare):
    """
    build/blocks/: top.svg draws the top module as its submodules and the
    wiring between them, and each block links to a file of its own -- another
    block diagram for a module with submodules, that module's schematic for
    one without. A design of any depth is then read one level at a time; the
    single schematic of the top buries the blocks of anything built from them.

    `prepare` is the yosys script up to `opt`, reused to draw the leaves.
    Skipped for a top with no submodule, where it would be one box.
    """
    if not os.path.exists(netlist_path):
        return
    with open(netlist_path) as f:
        netlist = json.load(f)
    top = next((name for name, mod in netlist["modules"].items()
                if mod.get("attributes", {}).get("top")), None)
    if not top or not diagrams.has_submodules(netlist, top):
        log_info("The top module instantiates no submodule; no block diagram to draw.")
        return
    os.makedirs(BLOCKS_DIR, exist_ok=True)
    plan = diagrams.diagram_plan(netlist, top)
    links = {name: f"{stem}.svg" for name, stem in plan.items()}
    parents = {}
    for name in plan:  # plan lists the top first, so each child gets its nearest parent
        for cell in netlist["modules"][name].get("cells", {}).values():
            parents.setdefault(cell["type"], (diagrams.module_label(name), links[name]))

    leaves = []
    for name, stem in plan.items():
        if not diagrams.has_submodules(netlist, name):
            leaves.append(f"show -format svg -viewer none -prefix {BLOCKS_DIR}/{stem} {name}")
            continue
        dot_path = os.path.join(BLOCKS_DIR, f"{stem}.dot")
        with open(dot_path, "w") as f:
            f.write(diagrams.block_diagram_dot(netlist, name, links, parents.get(name)))
        run_command(["dot", "-Tsvg", dot_path, "-o", os.path.join(BLOCKS_DIR, f"{stem}.svg")])
    if leaves:
        run_command(["yosys", "-p", "; ".join(prepare + leaves)])
    log_info(f"Wrote {BLOCKS_DIR}/: {len(plan)} diagrams, top.svg first")

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

def sta_step(metrics_path):
    """
    The newest post-PnR STA step directory of the run a metrics.json belongs
    to, or None -- including when the file does not sit at <run>/final/, for
    the reason find_render gives.
    """
    final_dir = os.path.dirname(os.path.abspath(metrics_path))
    if os.path.basename(final_dir) != "final":
        return None
    found = sorted(glob.glob(os.path.join(os.path.dirname(final_dir), "*-openroad-stapostpnr")))
    return found[-1] if found else None

def default_power(metrics_path):
    """(DEFAULT_CORNER, power_groups rows) from that corner's power.rpt, or None."""
    sta = sta_step(metrics_path)
    config_path = os.path.join(sta, "config.json") if sta else None
    if not config_path or not os.path.exists(config_path):
        return None
    with open(config_path) as f:
        corner = json.load(f).get("DEFAULT_CORNER")
    report = os.path.join(sta, corner or "", "power.rpt")
    if not corner or not os.path.exists(report):
        return None
    with open(report) as f:
        rows = site_page.power_groups(f.read())
    return (corner, rows) if any(r[0] == "Total" for r in rows) else None

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

    # The default corner's power.rpt when the run left one: the bare
    # power__total names no corner, and in a real 3.0.14 run it is
    # max_ff_n40C_1v95's, not the default corner's.
    corner_power = default_power(path)
    if corner_power:
        corner, groups = corner_power
        total = next(g[4] for g in groups if g[0] == "Total")
        rows.append(("power", f"{total * 1e3:.3f} mW  ({corner})"))  # watts
    elif metrics.get("power__total") is not None:
        rows.append(("power", f"{metrics['power__total'] * 1e3:.3f} mW  (corner not named)"))

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
        log_error(f"Failed to read {path}: {e}")
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

# One page with what `report` prints, the layout, the schematic and every
# cocotb verdict, for publishing on GitHub Pages. Everything it needs is copied
# into this directory, so the directory is the whole site. The markup is in
# site_page.py; this half finds the files.
SITE_DIR = "build/site"

COCOTB_RESULTS = [
    ("cocotb, RTL", "build/cocotb-results.xml"),
    ("cocotb, gate level", "build/cocotb-gl-results.xml"),
]

def run_details(metrics_path, metrics):
    """
    What the page shows beyond `report`'s rows, from the reports LibreLane
    leaves next to a run's metrics.json. Only when the file sits at
    <run>/final/metrics.json, for the reason find_render gives. Any part whose
    report is missing is left out.

    """
    details = {"signoff": [(label, metrics[key]) for label, key in SIGNOFF_CHECKS
                           if metrics.get(key) is not None]}
    final_dir = os.path.dirname(os.path.abspath(metrics_path))
    if os.path.basename(final_dir) != "final":
        return details
    run_dir = os.path.dirname(final_dir)

    def newest(pattern):
        found = sorted(glob.glob(os.path.join(run_dir, pattern)))
        return found[-1] if found else None

    def read(path):
        with open(path) as f:
            return f.read()

    sta = sta_step(metrics_path)
    corners = {key.split(":", 1)[1]: value for key, value in metrics.items()
               if key.startswith("timing__setup__ws__corner:") and value is not None}
    if sta and corners:
        worst = min(corners, key=corners.get)
        report = os.path.join(sta, worst, "max.rpt")
        path = site_page.first_path(read(report)) if os.path.exists(report) else None
        if path:
            details["timing"] = (worst, path)

    power = default_power(metrics_path)
    if power:
        details["power"] = power

    stat = newest("*-yosys-synthesis/reports/stat.json")
    design = json.loads(read(stat)).get("design", {}) if stat else {}
    area = []
    if "area" in design and "sequential_area" in design:
        area += [("flip-flops, after synthesis", design["sequential_area"]),
                 ("combinational logic, after synthesis",
                  design["area"] - design["sequential_area"])]
    # Counted against a real run: its 198 standard cells were synthesis's 110
    # plus 42 clock-tree, hold and fanout buffers and 46 well taps.
    if metrics.get("design__instance__area__stdcell") is not None:
        area.append(("standard cells after routing, with the clock tree, buffers "
                     "and well taps the flow added", metrics["design__instance__area__stdcell"]))
    if metrics.get("design__instance__area__macros") is not None:
        area.append(("macros (memories, hard blocks)", metrics["design__instance__area__macros"]))
    if area:
        details["area"] = area
    return details

def cmd_site(args, config):
    """
    Writes build/site/index.html: the numbers `report` prints, the layout
    render, the schematic and the cocotb verdicts, on one page. Each part is
    included when the file behind it exists, so it works after `make cocotb`
    alone as well as after the full flow.

    It reports; it does not judge. A failed test is shown as failed and the
    command still succeeds -- the command that ran the test is the gate.
    """
    if os.path.isdir(SITE_DIR):
        shutil.rmtree(SITE_DIR)  # never publish a previous run's picture
    os.makedirs(SITE_DIR)

    numbers, layout, details = [], None, {}
    found = [path for pattern in METRICS_GLOBS for path in glob.glob(pattern)]
    if found:
        path = max(found, key=os.path.getmtime)
        metrics = read_metrics(path)
        rows = report_rows(metrics, path)
        details = run_details(path, metrics)
        # Each has a section of their own on the page. Power only when that
        # section exists: its row is the bare metric, which names no corner
        # and would disagree with the table next to it.
        own = {"layout", "signoff"} | ({"power"} if "power" in details else set())
        numbers = [(label, value) for label, value in rows if label not in own]
        render = dict(rows).get("layout")
        if render:
            layout = "layout.png"
            shutil.copy(render, os.path.join(SITE_DIR, layout))

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

    if os.path.exists(os.path.join(BLOCKS_DIR, "top.svg")):
        os.makedirs(os.path.join(SITE_DIR, "blocks"))
        for svg in glob.glob(os.path.join(BLOCKS_DIR, "*.svg")):
            shutil.copy(svg, os.path.join(SITE_DIR, "blocks"))
        details["blocks"] = "blocks/top.svg"

    # Opt-in: which signals are worth a picture is the designer's call, not
    # something to guess from a VCD that may hold hundreds.
    wanted = config_get(config, "WAVE_SIGNALS")
    if wanted:
        vcds = sorted(glob.glob("build/*.vcd"), key=os.path.getmtime)
        if not vcds:
            log_warn("WAVE_SIGNALS is set but build/ holds no VCD; run sim first.")
        else:
            # The newest VCD that declares every signal: with two testbenches
            # the newest file may be the other one's, which is no error.
            svg = source = first_error = None
            for vcd in reversed(vcds):
                with open(vcd) as f:
                    text = f.read()
                try:
                    svg, source = diagrams.waveform_svg(text, wanted), vcd
                    break
                except KeyError as e:
                    first_error = first_error or f"{vcd} does not declare {e.args[0]}"
            if svg is None:
                log_error(
                    f"No VCD in build/ declares every WAVE_SIGNALS name; {first_error}. "
                    "Names are dotted from the testbench top, e.g. tb_blinky.uut.count."
                )
                sys.exit(1)
            with open(os.path.join(SITE_DIR, "wave.svg"), "w") as f:
                f.write(svg)
            details["wave"] = ("wave.svg", source)

    schematic = None
    if os.path.exists(SCHEMATIC_PREFIX + ".svg"):
        schematic = "schematic.svg"
        shutil.copy(SCHEMATIC_PREFIX + ".svg", os.path.join(SITE_DIR, schematic))

    if not (numbers or layout or cocotb_runs or schematic or details):
        log_error(
            "Nothing to put on the page: no metrics.json under runs/, no cocotb "
            f"results, no {SCHEMATIC_PREFIX}.svg. Run make cocotb, make schematic "
            "or make gds first."
        )
        sys.exit(1)

    design = config_get(config, "DESIGN_NAME", "design")
    index = os.path.join(SITE_DIR, "index.html")
    with open(index, "w") as f:
        f.write(site_page.render(design, numbers, layout, cocotb_runs, schematic, os.environ,
                                 **details))
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

    site_parser = subparsers.add_parser(
        "site", help="Write build/site/index.html: report, layout, schematic, cocotb results"
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
