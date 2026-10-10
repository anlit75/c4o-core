import glob
import json
import os
import subprocess
import sys

import yaml

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

def load_config(quiet=False):
    """Loads the first configuration file found in the working directory."""
    for name in CONFIG_FILENAMES:
        config_path = os.path.join(os.getcwd(), name)
        if not os.path.exists(config_path):
            continue
        # The release rides on a line every command prints, so any pasted log
        # says which c4o-core produced it.
        version = c4o_version()
        if not quiet:
            log_info(f"Loading config from {config_path}" + (f" (c4o-core {version})" if version else ""))
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
