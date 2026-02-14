#!/usr/bin/env python3
import argparse
import glob
import json
import os
import subprocess
import sys

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

def run_command(cmd, shell=False):
    """Runs a command and exits if it fails."""
    # Convert list to string for logging if it's a list
    cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
    log_info(f"Running: {cmd_str}")
    try:
        subprocess.run(cmd, shell=shell, check=True)
    except subprocess.CalledProcessError as e:
        log_error(f"Command failed with exit code {e.returncode}")
        sys.exit(e.returncode)

def ensure_build_dir():
    if not os.path.exists("build"):
        os.makedirs("build")
        log_info("Created build/ directory")

def load_config():
    """Loads configuration from config.json if it exists."""
    config_path = os.path.join(os.getcwd(), "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                log_info(f"Loading config from {config_path}")
                return json.load(f)
        except json.JSONDecodeError as e:
            log_error(f"Failed to parse {config_path}: {e}")
            sys.exit(1)
    return {}

def get_files(args, config, key="RTL_FILES"):
    """
    Returns a list of files to process.
    Prioritizes CLI arguments. If empty, falls back to config.json.
    Supports globbing (e.g. src/**/*.v).

    Args:
        args: Parsed arguments (may contain .files)
        config: Config dictionary
        key: The config key to look up (default: RTL_FILES)
    """
    initial_files = []

    # Check CLI args first - if present, they override config
    # Use getattr because not all parsers have 'files' argument (e.g., cmd_gds)
    cli_files = getattr(args, "files", None)
    if cli_files:
        for f in cli_files:
            if f.strip(): # Ignore empty strings
                initial_files.extend(f.strip().split())
        # If args provided, we return just them, no config lookup.
        # But we need to handle globbing on them too.
        # Logic below handles globbing.
        pass

    # Fallback to config
    elif key in config:
        config_files = config[key]
        if isinstance(config_files, list):
            # Standard relative paths supported. Removed legacy :: replacement logic.
            initial_files = config_files
        else:
            log_error(f"{key} in config.json must be a list.")
            sys.exit(1)

    # Backwards compatibility: if looking for RTL_FILES but not found, check VERILOG_FILES
    elif key == "RTL_FILES" and "VERILOG_FILES" in config:
        log_warn("RTL_FILES not found in config.json. Falling back to VERILOG_FILES.")
        config_files = config["VERILOG_FILES"]
        if isinstance(config_files, list):
            initial_files = config_files
        else:
            log_error("VERILOG_FILES in config.json must be a list.")
            sys.exit(1)

    # If asking for TEST_FILES and not found, return empty list (unless CLI args were expected but not present?)

    if not initial_files:
        # Check if we failed to find RTL files when explicitly requested via key or fallback
        # Note: if CLI args were empty but attribute existed, we fall here too if config was also empty.

        # If the user intended to provide files via CLI but didn't, or config was missing...
        if key == "RTL_FILES" and not cli_files:
             log_error("No RTL files provided via CLI or config.json (RTL_FILES or VERILOG_FILES).")
             sys.exit(1)
        # If TEST_FILES is empty, that's fine
        return []

    # Expand globs and deduplicate
    final_files = set()
    for pattern in initial_files:
        # Use recursive globbing
        matched = glob.glob(pattern, recursive=True)
        if matched:
            final_files.update(matched)
        else:
            # Optional: warn if a pattern matched nothing?
            pass

    sorted_files = sorted(list(final_files))

    if not sorted_files and key == "RTL_FILES":
        log_warn("No files found after glob expansion for RTL_FILES.")

    return sorted_files

def cmd_lint(args, config):
    # Lint only checks RTL
    files = get_files(args, config, key="RTL_FILES")
    cmd = ["verilator", "--lint-only"]

    # Add include directories
    include_dirs = config.get("INCLUDE_DIRS", [])
    for inc in include_dirs:
        cmd.append(f"-I{inc}")

    cmd += files
    run_command(cmd)

def cmd_sim(args, config):
    # Sim needs RTL + TEST

    # If CLI args are provided, they override the concept of keys completely.
    if getattr(args, "files", None):
        files = get_files(args, config, key="RTL_FILES") # key doesn't matter if args.files is set
    else:
        rtl_files = get_files(args, config, key="RTL_FILES")
        test_files = get_files(args, config, key="TEST_FILES")
        files = rtl_files + test_files

    ensure_build_dir()
    # iverilog -o build/sim.vvp <files> && vvp build/sim.vvp
    compile_cmd = ["iverilog", "-o", "build/sim.vvp"]

    # Add include directories
    include_dirs = config.get("INCLUDE_DIRS", [])
    for inc in include_dirs:
        compile_cmd.append(f"-I{inc}")

    compile_cmd += files
    run_command(compile_cmd)

    run_sim_cmd = ["vvp", "build/sim.vvp"]
    run_command(run_sim_cmd)

def cmd_synth(args, config):
    # Synth only checks RTL
    files = get_files(args, config, key="RTL_FILES")
    ensure_build_dir()

    # Generate include commands
    include_cmds = []
    include_dirs = config.get("INCLUDE_DIRS", [])
    for inc in include_dirs:
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

def cmd_gds(args, config):
    """
    Validates the configuration for GDS generation.
    """
    required_keys = [
        "PDK", "STD_CELL_LIBRARY", "DIE_AREA", "FP_CORE_UTIL",
        "FP_SIZING", "CLOCK_PORT", "CLOCK_PERIOD"
    ]

    missing_keys = [key for key in required_keys if key not in config]

    if missing_keys:
        log_error(f"Missing required keys in config.json for GDS generation: {', '.join(missing_keys)}")
        sys.exit(1)

    # Validate that we have RTL files
    files = get_files(args, config, key="RTL_FILES")
    if not files:
        log_error("No RTL files found. GDS generation requires valid RTL.")
        sys.exit(1)

    log_info("GDS configuration verified successfully.")

def cmd_pdk(args, config):
    pdk_root = os.path.join(os.getcwd(), "pdks")
    if not os.path.exists(pdk_root):
        log_info(f"Creating PDK root directory: {pdk_root}")
        os.makedirs(pdk_root)

    # Commit hash from requirements
    commit_hash = "bdc9412b3e468c102d01b7cf6337be06ec6e9c9a"

    cmd = [
        "volare", "enable",
        "--pdk", "sky130",
        "--pdk-root", pdk_root,
        commit_hash
    ]
    run_command(cmd)

def main():
    parser = argparse.ArgumentParser(description="c4o-core entrypoint script")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Load config once
    config = load_config()

    # Lint command
    lint_parser = subparsers.add_parser("lint", help="Run Verilator lint")
    lint_parser.add_argument("--files", nargs="*", help="Verilog files to lint")
    lint_parser.set_defaults(func=cmd_lint)

    # Sim command
    sim_parser = subparsers.add_parser("sim", help="Run Icarus Verilog simulation")
    sim_parser.add_argument("--files", nargs="*", help="Verilog files to simulate")
    sim_parser.set_defaults(func=cmd_sim)

    # Synth command
    synth_parser = subparsers.add_parser("synth", help="Run Yosys synthesis")
    synth_parser.add_argument("--files", nargs="*", help="Verilog files to synthesize")
    synth_parser.set_defaults(func=cmd_synth)

    # GDS command
    gds_parser = subparsers.add_parser("gds", help="Run GDS generation (OpenLane)")
    gds_parser.set_defaults(func=cmd_gds)

    # PDK command
    pdk_parser = subparsers.add_parser("pdk", help="Install/Enable Sky130 PDK via volare")
    pdk_parser.set_defaults(func=cmd_pdk)

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    args.func(args, config)

if __name__ == "__main__":
    main()
