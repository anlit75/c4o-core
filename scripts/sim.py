import argparse
import os
import subprocess
import sys
from xml.etree import ElementTree

import progress
import stage_renders
import common
import report
import runs

def root_args(config, test_files, key):
    """
    The '-s <top>' Icarus needs, or nothing when there is only one candidate.

    Icarus elaborates every module nobody instantiates as its own root, and the
    first $finish ends the whole simulation -- so a second testbench runs
    partway and is cut off, with nothing in the exit code to show for it. -s
    names the one root, which is why it is required as soon as there is more
    than one file it could be hiding in.
    """
    top = common.config_get(config, key)
    if top:
        return ["-s", top]
    if len(test_files) > 1:
        common.log_error(
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
    if not common.config_get(config, other_key):
        common.log_error(
            f"No tests to run: set {key} (Verilog testbenches) or {other_key} "
            "(Python tests) in the config."
        )
        sys.exit(1)
    common.log_info(f"{command} skipped: {key} is not set.")

def cmd_sim(args, config):
    # Sim needs RTL + TEST

    # If CLI args are provided, they override the concept of keys completely.
    if getattr(args, "files", None):
        files = common.get_files(args, config) # key doesn't matter if args.files is set
        test_files = []
    else:
        rtl_files = common.get_files(args, config, key="VERILOG_FILES")
        test_files = common.get_files(args, config, key="TEST_FILES")
        if not test_files and getattr(args, "if_configured", False) is True:
            skip_unconfigured(config, "sim", "TEST_FILES", "COCOTB_TESTS")
            return
        if not test_files:
            common.log_error(
                "sim has no testbench: set TEST_FILES (or \"//TEST_FILES\") in the "
                "config, or pass --files."
            )
            sys.exit(1)
        files = rtl_files + test_files

    common.ensure_build_dir()
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
    for inc in common.get_include_dirs(config):
        compile_cmd.append(f"-I{inc}")

    compile_cmd += files
    common.run_command(compile_cmd)

    run_sim_cmd = ["vvp", "build/sim.vvp"]
    common.run_command(run_sim_cmd)

def cell_models(config):
    """
    The PDK's own Verilog models for the cells the netlist instantiates.

    Derived from PDK and STD_CELL_LIBRARY rather than a key of its own: the
    config already says which PDK and which library, and a third key that had
    to agree with both would only be somewhere else for them to disagree.
    """
    pdk = common.config_get(config, "PDK")
    library = common.config_get(config, "STD_CELL_LIBRARY")
    if not pdk or not library:
        common.log_error("gatesim needs PDK and STD_CELL_LIBRARY to find the cell models.")
        sys.exit(1)

    pdk_root = os.environ.get("PDK_ROOT") or os.path.join(os.getcwd(), "pdks")
    verilog = os.path.join(pdk_root, pdk, "libs.ref", library, "verilog")
    models = [
        os.path.join(verilog, "primitives.v"),
        os.path.join(verilog, f"{library}.v"),
    ]

    missing = [m for m in models if not os.path.exists(m)]
    if missing:
        common.log_error(
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
    tests = common.get_files(args, config, key="GATE_TESTS")
    if not tests:
        # No Verilog gate testbench: the cocotb tests, if there are any, are
        # the gate-level tests. That is what `cocotb --netlist` runs.
        if common.config_get(config, "COCOTB_TESTS"):
            args.netlist = getattr(args, "netlist", None) or ""
            cmd_cocotb(args, config)
            return
        common.log_error(
            "No gate-level tests: set GATE_TESTS (or \"//GATE_TESTS\") for a Verilog "
            "testbench, or COCOTB_TESTS (or \"//COCOTB_TESTS\") for Python tests."
        )
        sys.exit(1)

    netlist = runs.find_netlist(getattr(args, "netlist", None))
    common.log_info(f"Netlist: {netlist}")

    common.ensure_build_dir()
    vvp_file = "build/gatesim.vvp"

    # FUNCTIONAL drops the timing checks Icarus cannot run anyway; without
    # UNIT_DELAY the models leave every gate at zero delay and warn once per
    # cell. Both verified against sky130_fd_sc_hd: this pair compiles silently,
    # neither alone does.
    compile_cmd = ["iverilog", "-g2012", "-DFUNCTIONAL", "-DUNIT_DELAY=#1",
                   "-o", vvp_file]
    compile_cmd += root_args(config, tests, "GATE_TOP")
    compile_cmd += cell_models(config) + [netlist] + tests
    common.run_command(compile_cmd)

    common.run_command(["vvp", vvp_file])

def cocotb_config(*args):
    """Asks cocotb where its own files live rather than hardcoding paths."""
    try:
        return subprocess.run(
            ["cocotb-config", *args], check=True, capture_output=True, text=True
        ).stdout.strip()
    except subprocess.CalledProcessError as e:
        common.log_error(
            f"cocotb-config {' '.join(args)} failed: {e.stderr.strip() or e}"
        )
        sys.exit(1)
    except OSError as e:
        common.log_error(f"Could not run cocotb-config: {e}")
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
    test_files = common.get_files(args, config, key="COCOTB_TESTS")
    if not test_files and getattr(args, "if_configured", False) is True:
        skip_unconfigured(config, "cocotb", "COCOTB_TESTS", "TEST_FILES")
        return
    if not test_files:
        common.log_error(
            "No cocotb tests: set COCOTB_TESTS (or \"//COCOTB_TESTS\") to the "
            "Python test files in the config."
        )
        sys.exit(1)

    toplevel = common.config_get(config, "DESIGN_NAME")
    if not toplevel:
        common.log_error("cocotb needs DESIGN_NAME to know which module to drive.")
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

    common.ensure_build_dir()
    vvp_file = f"build/{stem}.vvp"
    results = os.path.join("build", f"{stem}-results.xml")
    if os.path.exists(results):
        os.remove(results)  # never report a previous run's verdict

    netlist = runs.find_netlist(args.netlist or None) if gate_level else None
    compile_cocotb(args, config, toplevel, vvp_file, netlist)

    env, lib_dir = cocotb_env(test_files, toplevel, results)
    if only:
        env["MODULE"] = only[0]
        env.pop("TESTCASE", None)
        if only[1]:
            env["TESTCASE"] = only[1]

    common.run_command(cocotb_vvp(vvp_file, lib_dir), env=env)

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
        common.log_info(f"Netlist: {netlist}")
        # FUNCTIONAL and UNIT_DELAY for the reason cmd_gatesim gives: that pair
        # compiles the cell models silently, neither of them alone does. The
        # include dirs are left out -- a netlist has no `include to resolve.
        compile_cmd = ["iverilog", "-g2012", "-DFUNCTIONAL", "-DUNIT_DELAY=#1",
                       "-s", toplevel, "-o", vvp_file]
        compile_cmd += cell_models(config) + [netlist]
    else:
        compile_cmd = ["iverilog", "-g2012", "-s", toplevel, "-o", vvp_file]
        compile_cmd += [f"-I{inc}" for inc in common.get_include_dirs(config)]
        sources = common.get_files(args, config, key="VERILOG_FILES")
        compile_cmd += sources
        # A debug VCD is opt-in: WAVES=1 in the environment, which `make
        # cocotb WAVES=1` passes into the container. Only the RTL run dumps.
        if os.environ.get("WAVES") == "1":
            compile_cmd += ["-s", "c4o_dump", write_dump_module(toplevel)]
        # Without a `timescale Icarus runs at 1 s precision, and the first
        # Clock(..., units="ns") dies with "Unable to accurately represent
        # 10(ns)" -- which names neither the cause nor the file. `make sim`
        # never shows it: the Verilog testbench carries its own `timescale.
        if not any("`timescale" in common.read_text(f) for f in sources):
            common.log_warn("None of VERILOG_FILES declares a `timescale. So the simulator runs at "
                     "1 s precision, and a cocotb Clock in ns fails with \"Unable to "
                     "accurately represent\". Put `timescale 1ns/1ps on the first line "
                     "of your RTL.")
    common.run_command(compile_cmd)

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
        common.log_error(f"'{spec}' names no module of COCOTB_TESTS. The modules are: {', '.join(modules)}.")
        sys.exit(1)
    if "." in spec and not function:
        common.log_error(f"'{spec}' ends in a dot. Write <module> or <module>.<function>.")
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
        common.log_error(
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

def cmd_progress(args, config):
    """
    Started by `make gds` beside LibreLane: follows the run directory and prints
    the ledger until the status file says LibreLane is done. The exit status is
    not LibreLane's. `make` has that, from the status file.
    """
    design = common.config_get(config, "DESIGN_NAME") or "design"
    try:
        sys.exit(progress.watch_flow(
            args.run_dir, args.status, args.log, args.plan,
            os.path.join("build", f"{design}.gds"), design, partial=args.partial,
            report=lambda: report.cmd_report(argparse.Namespace(metrics=None), config),
        ))
    except Exception as e:
        # A display that breaks must not take the flow with it: make waits for
        # LibreLane and returns its status.
        common.log_warn(f"The progress display stopped ({e}). LibreLane goes on. Its output: {args.log}")
        sys.exit(0)

def cmd_stages(args, config):
    """
    Started by `make gds` around the one KLayout call that draws each stage:
    `stages` decides what to draw (build/stages/jobs.json), `stages --collect`
    writes build/stages/stages.json from what was drawn. It never fails: a
    picture that is not drawn is a stage without one, and make goes on.
    """
    try:
        if args.collect:
            count = stage_renders.collect(args.run_dir)
            if count is not None and not args.quiet:
                print(f"  Stages      {stage_renders.OUT}/ ({count} render{'' if count == 1 else 's'})")
        else:
            stage_renders.plan(args.run_dir)
    except Exception as e:
        common.log_warn(f"No stage renders ({e}). make gds goes on.")
    sys.exit(0)

def check_cocotb_results(path):
    """Exits non-zero if the run recorded a failure. vvp will not."""
    if not os.path.exists(path):
        common.log_error(f"cocotb wrote no results to {path}. The run counts that as a failure.")
        sys.exit(1)
    try:
        cases = ElementTree.parse(path).getroot().iter("testcase")
    except ElementTree.ParseError as e:
        common.log_error(f"Could not read {path}: {e}")
        sys.exit(1)

    failed = [
        case.get("name")
        for case in cases
        if case.find("failure") is not None or case.find("error") is not None
    ]
    if failed:
        common.log_error(f"cocotb tests failed: {', '.join(failed)}")
        sys.exit(1)
    common.log_info("All cocotb tests passed.")
