#!/usr/bin/env python3
import argparse
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
    """Loads configuration from src/config.json if it exists."""
    config_path = os.path.join(os.getcwd(), "src", "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                log_info(f"Loading config from {config_path}")
                return json.load(f)
        except json.JSONDecodeError as e:
            log_error(f"Failed to parse {config_path}: {e}")
            sys.exit(1)
    return {}

def get_files(args, config):
    """
    Returns a list of files to process.
    Prioritizes CLI arguments. If empty, falls back to config.json.
    """
    files = []

    # Check CLI args first
    if args.files:
        for f in args.files:
            if f.strip(): # Ignore empty strings
                files.extend(f.strip().split())

    if files:
        return files

    # Fallback to config
    if "VERILOG_FILES" in config:
        verilog_files = config["VERILOG_FILES"]
        if isinstance(verilog_files, list):
            # Handle possible "dir::file.v" convention by replacing "::" with "/"
            # and verify paths relative to project root (CWD)
            return [f.replace("::", "/") for f in verilog_files]
        else:
            log_error("VERILOG_FILES in config.json must be a list.")
            sys.exit(1)

    log_error("No files provided via CLI or config.json.")
    sys.exit(1)

def cmd_lint(args, config):
    files = get_files(args, config)
    cmd = ["verilator", "--lint-only"] + files
    run_command(cmd)

def cmd_sim(args, config):
    files = get_files(args, config)
    ensure_build_dir()
    # iverilog -o build/sim.vvp <files> && vvp build/sim.vvp
    compile_cmd = ["iverilog", "-o", "build/sim.vvp"] + files
    run_command(compile_cmd)

    run_sim_cmd = ["vvp", "build/sim.vvp"]
    run_command(run_sim_cmd)

def cmd_synth(args, config):
    files = get_files(args, config)
    ensure_build_dir()

    # Generate read_verilog commands for each file
    read_cmds = [f"read_verilog {f}" for f in files]
    read_cmd_str = "; ".join(read_cmds)

    # Determine top module
    synth_cmd = "synth -auto-top"
    if "DESIGN_NAME" in config:
        design_name = config["DESIGN_NAME"]
        log_info(f"Using design name from config: {design_name}")
        synth_cmd = f"synth -top {design_name}"

    # read_verilog <file1>; ...; synth -top <design>; write_json build/synthesis.json
    yosys_cmd = f"{read_cmd_str}; {synth_cmd}; write_json build/synthesis.json"
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

    # Optional: Check types/values if needed, but existence is a good start.
    log_info("GDS configuration verified successfully.")

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

    # Keeping 'test' as a hidden alias or just not supporting it?
    # Since I will update CI, I can remove it. But for safety, I can alias it.
    # The prompt explicitly asked for `sim`. I'll stick to `sim`.

    # Synth command
    synth_parser = subparsers.add_parser("synth", help="Run Yosys synthesis")
    synth_parser.add_argument("--files", nargs="*", help="Verilog files to synthesize")
    synth_parser.set_defaults(func=cmd_synth)

    # GDS command
    gds_parser = subparsers.add_parser("gds", help="Run GDS generation (OpenLane)")
    gds_parser.set_defaults(func=cmd_gds)

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    args.func(args, config)

if __name__ == "__main__":
    main()
