#!/usr/bin/env python3
import argparse
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

def get_files(args):
    # args.files is a list of strings. If passed from GitHub Action, it might be ["file1 file2"].
    # We need to split any strings containing spaces and flatten the list.
    raw_files = args.files
    files = []
    for f in raw_files:
        files.extend(f.strip().split())

    if not files:
        log_error("No files provided.")
        sys.exit(1)
    return files

def cmd_lint(args):
    files = get_files(args)
    cmd = ["verilator", "--lint-only"] + files
    run_command(cmd)

def cmd_synth(args):
    files = get_files(args)
    ensure_build_dir()

    # Generate read_verilog commands for each file
    read_cmds = [f"read_verilog {f}" for f in files]
    read_cmd_str = "; ".join(read_cmds)

    # read_verilog <file1>; read_verilog <file2>; ...; synth -auto-top; write_json build/synthesis.json
    yosys_cmd = f"{read_cmd_str}; synth -auto-top; write_json build/synthesis.json"
    cmd = ["yosys", "-p", yosys_cmd]
    run_command(cmd)

def cmd_test(args):
    files = get_files(args)
    ensure_build_dir()
    # iverilog -o build/sim.vvp <files> && vvp build/sim.vvp
    compile_cmd = ["iverilog", "-o", "build/sim.vvp"] + files
    run_command(compile_cmd)

    run_sim_cmd = ["vvp", "build/sim.vvp"]
    run_command(run_sim_cmd)

def main():
    parser = argparse.ArgumentParser(description="c4o-core entrypoint script")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Lint command
    lint_parser = subparsers.add_parser("lint", help="Run Verilator lint")
    lint_parser.add_argument("--files", nargs="+", required=True, help="Verilog files to lint")
    lint_parser.set_defaults(func=cmd_lint)

    # Synth command
    synth_parser = subparsers.add_parser("synth", help="Run Yosys synthesis")
    synth_parser.add_argument("--files", nargs="+", required=True, help="Verilog files to synthesize")
    synth_parser.set_defaults(func=cmd_synth)

    # Test command
    test_parser = subparsers.add_parser("test", help="Run Icarus Verilog simulation")
    test_parser.add_argument("--files", nargs="+", required=True, help="Verilog files to test")
    test_parser.set_defaults(func=cmd_test)

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
