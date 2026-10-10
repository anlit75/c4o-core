import sys

from c4o import common

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
    codes = common.config_get(config, "LINTER_DISABLE_WARNINGS", [])
    if isinstance(codes, str):
        # One code without the brackets is the easy YAML mistake to make, and
        # iterating it would spell out -Wno-W -Wno-I -Wno-D. Say so instead.
        common.log_error(
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
    if common.config_get(config, "LINTER_DISABLE_WARNINGS") is None:
        config = dict(config, LINTER_DISABLE_WARNINGS=LINTER_DEFAULT_WAIVERS)
    waived = disable_warnings(config)
    flags = ["--Wall", "--Wno-fatal"] + waived
    for code, key in (("LATCH", "LINTER_ERROR_ON_LATCH"), ("MULTIDRIVEN", "LINTER_ERROR_ON_MULTIDRIVEN")):
        if common.config_get(config, key, True) and f"-Wno-{code}" not in waived:
            flags.append(f"--Werror-{code}")
    top = common.config_get(config, "DESIGN_NAME")
    if top:
        flags += ["--top-module", top]
    return flags

def cmd_lint(args, config):
    # Lint only checks RTL
    files = common.get_files(args, config, key="VERILOG_FILES")
    cmd = ["verilator", "--lint-only"]

    cmd += lint_flags(config)

    # Add include directories
    for inc in common.get_include_dirs(config):
        cmd.append(f"-I{inc}")

    cmd += files
    common.run_command(cmd)

def cmd_synth(args, config):
    # Synth only checks RTL
    files = common.get_files(args, config, key="VERILOG_FILES")
    common.ensure_build_dir()

    # Generate include commands
    include_cmds = []
    for inc in common.get_include_dirs(config):
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
        common.log_info(f"Using design name from config: {design_name}")
        synth_cmd = f"synth -top {design_name}"

    parts.append(synth_cmd)
    parts.append("write_json build/synthesis.json")

    yosys_cmd = "; ".join(parts)
    cmd = ["yosys", "-p", yosys_cmd]
    common.run_command(cmd)

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
    files = common.get_files(args, config, key="VERILOG_FILES")
    common.ensure_build_dir()

    parts = [f"verilog_defaults -add -I{inc}" for inc in common.get_include_dirs(config)]
    parts += [f"read_verilog -sv {f}" for f in files]

    design_name = common.config_get(config, "DESIGN_NAME")
    if design_name:
        common.log_info(f"Using design name from config: {design_name}")
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

    common.run_command(["yosys", "-p", "; ".join(parts)])
    common.log_info(f"Wrote {SCHEMATIC_PREFIX}.svg")
