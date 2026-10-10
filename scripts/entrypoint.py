#!/usr/bin/env python3
import argparse
import os
import sys

from c4o import progress
from c4o import check
from c4o import common
from c4o import regress
from c4o import report
from c4o import rtl
from c4o import sim
from c4o import site

def cmd_all(args, config):
    """
    lint, sim, cocotb and synth, one line each, and the reason when one fails.
    Their own output is in build/log/<command>.log; PROGRESS=raw streams it.
    """
    design = common.config_get(config, "DESIGN_NAME") or "design"
    try:
        sys.exit(progress.run_all(os.path.abspath(__file__), design, common.c4o_version()))
    except KeyboardInterrupt:
        print("interrupted")
        sys.exit(130)

def cmd_pdk(args, config):
    # Same rule as the read path in gatesim_cell_models: PDK_ROOT wins, ./pdks
    # is the default. Installing to a fixed ./pdks while every reader honoured
    # PDK_ROOT meant the variable could only ever point at a PDK this command
    # had not installed -- so one 3GB copy per checkout was the only layout
    # that worked, and a shared read-only PDK was unreachable.
    pdk_root = os.environ.get("PDK_ROOT") or os.path.join(os.getcwd(), "pdks")
    if not os.path.exists(pdk_root):
        common.log_info(f"Creating PDK root directory: {pdk_root}")
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
    common.run_command(cmd)

def build_parser():
    parser = argparse.ArgumentParser(description="c4o-core entrypoint script")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Lint command
    lint_parser = subparsers.add_parser("lint", help="Run Verilator lint")
    lint_parser.add_argument("--files", nargs="*", help="Verilog files to lint")
    lint_parser.set_defaults(func=rtl.cmd_lint)

    # Sim command
    sim_parser = subparsers.add_parser("sim", help="Run Icarus Verilog simulation")
    sim_parser.add_argument("--files", nargs="*", help="Verilog files to simulate")
    sim_parser.add_argument(
        "--if-configured", action="store_true",
        help="Skip, with a message, when TEST_FILES is not set (used by make all)",
    )
    sim_parser.set_defaults(func=sim.cmd_sim)

    # All command
    all_parser = subparsers.add_parser(
        "all", help="Run lint, sim, cocotb and synth and print one line for each"
    )
    all_parser.set_defaults(func=cmd_all)

    # Progress command: what `make gds` runs beside LibreLane
    progress_parser = subparsers.add_parser(
        "progress", help="Follow a LibreLane run and print its ledger (started by make gds)"
    )
    progress_parser.add_argument("--run-dir", required=True, help="runs/<tag>")
    progress_parser.add_argument("--status", required=True, help="File that holds LibreLane's exit status when it is done")
    progress_parser.add_argument("--log", required=True, help="LibreLane's output, kept as it is")
    progress_parser.add_argument("--plan", required=True, help="The steps this run will take (JSON)")
    progress_parser.add_argument("--partial", action="store_true", help="Not a whole flow: do not count steps")
    progress_parser.set_defaults(func=sim.cmd_progress)

    # Stages command: what `make gds` runs to put a picture on each stage
    stages_parser = subparsers.add_parser(
        "stages", help="Decide which layouts of a LibreLane run to draw, and list the pictures (started by make gds)"
    )
    stages_parser.add_argument("--run-dir", required=True, help="runs/<tag>")
    stages_parser.add_argument("--collect", action="store_true", help="After the render: write build/stages/stages.json")
    stages_parser.add_argument("--quiet", action="store_true", help="Print nothing (PROGRESS=raw)")
    stages_parser.set_defaults(func=sim.cmd_stages)

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
    cocotb_parser.set_defaults(func=sim.cmd_cocotb)

    # Regress command
    regress_parser = subparsers.add_parser(
        "regress", help="Run the cocotb tests listed in REGRESSION over many seeds"
    )
    regress_parser.add_argument(
        "--if-configured", action="store_true",
        help="Skip, with a message, when REGRESSION is not set",
    )
    regress_parser.set_defaults(func=regress.cmd_regress)

    # Coverage command
    coverage_parser = subparsers.add_parser(
        "coverage", help="Measure code coverage of the cocotb tests on Verilator"
    )
    coverage_parser.add_argument("--files", nargs="*", help="Verilog RTL files")
    coverage_parser.add_argument(
        "--if-configured", action="store_true",
        help="Skip, with a message, when COCOTB_TESTS is not set",
    )
    coverage_parser.set_defaults(func=regress.cmd_coverage)

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
    gatesim_parser.set_defaults(func=sim.cmd_gatesim)

    # Synth command
    synth_parser = subparsers.add_parser("synth", help="Run Yosys synthesis")
    synth_parser.add_argument("--files", nargs="*", help="Verilog files to synthesize")
    synth_parser.set_defaults(func=rtl.cmd_synth)

    # Check command. 'gds' is kept as an alias: it is what this command was
    # called before, and dropping it would break every pinned caller for a
    # rename.
    schematic_parser = subparsers.add_parser(
        "schematic",
        help="Draw the circuit as build/schematic.svg (RTL level, not the netlist)",
    )
    schematic_parser.add_argument("--files", nargs='*', help="Verilog files to draw")
    schematic_parser.set_defaults(func=rtl.cmd_schematic)

    check_parser = subparsers.add_parser(
        "check",
        aliases=["gds"],
        help="Validate the config for the physical design flow (pre-flight only)",
    )
    check_parser.set_defaults(func=check.cmd_check)

    # Report command
    report_parser = subparsers.add_parser(
        "report", help="Summarise a LibreLane run's metrics.json"
    )
    report_parser.add_argument(
        "metrics",
        nargs="?",
        help="Path to metrics.json (default: the newest under runs/ or build/runs/)",
    )
    report_parser.set_defaults(func=report.cmd_report)

    site_parser = subparsers.add_parser(
        "site", help="Write build/site/index.html: cocotb results, timing, area, power, signoff"
    )
    site_parser.set_defaults(func=site.cmd_site)

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
    # The ledger opens with the release and the design, so it does not need the
    # line that says which config was read.
    args.func(args, common.load_config(quiet=args.command in ("all", "progress", "stages")))

if __name__ == "__main__":
    main()
