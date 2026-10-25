"""
`make info`: what a bug report needs, as one block to paste. The images, where
make ran and the version of every tool the commands call. It reads no config
and runs no flow, so it works in a repository that does not build.

make passes in what only the host knows: the two image names, where it runs,
the host's system and its Docker. The rest is read here, in the image.
"""
import os
import platform
import subprocess
from importlib import metadata

from c4o import common

# The tools the commands call, and the flag each prints its version for.
TOOLS = [
    ("Verilator", ["verilator", "--version"]),
    ("Icarus Verilog", ["iverilog", "-V"]),
    ("Yosys", ["yosys", "-V"]),
    ("sv2v", ["sv2v", "--numeric-version"]),
]
PACKAGES = ["cocotb", "pyuvm"]


def tool_version(cmd):
    """The first line a tool prints for its version flag, or "not found"."""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return "not found"
    for line in (out.stdout + out.stderr).splitlines():
        if line.strip():
            return line.strip()
    return "not found"


def package_version(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not found"


def runs_on(env):
    """The same four places the bug report form offers."""
    if env.get("GITHUB_ACTIONS") == "true":
        return "GitHub Actions"
    if env.get("CODESPACES") == "true":
        return "Codespace"
    if env.get("C4O_RUNS_IN") == "image":
        return "Dev Container"
    return "Docker on this machine"


def collect(env=None):
    """The lines of the block, as (name, value) pairs."""
    env = os.environ if env is None else env
    rows = [
        ("c4o-core", common.c4o_version() or "unknown"),
        ("C4O_IMAGE", env.get("C4O_IMAGE") or "unknown"),
        ("LIBRELANE_IMAGE", env.get("LIBRELANE_IMAGE") or "unknown"),
        ("Runs on", runs_on(env)),
        ("Host", env.get("C4O_HOST") or "unknown"),
        ("Docker", env.get("C4O_DOCKER") or "not found"),
        ("Python", platform.python_version()),
    ]
    rows += [(name, tool_version(cmd)) for name, cmd in TOOLS]
    rows += [(name, package_version(name)) for name in PACKAGES]
    return rows


def cmd_info(args, config):
    rows = collect()
    width = max(len(name) for name, _ in rows)
    for name, value in rows:
        print(f"{name.ljust(width)}  {value}")
