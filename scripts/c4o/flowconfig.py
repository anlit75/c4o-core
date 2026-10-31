"""
The config LibreLane reads: c4o-core's defaults with config.yaml over them.

LibreLane takes several config files and lets a later one replace an earlier
one, but it loads the PDK and the standard cell library from the first file
only. A defaults file in front would load sky130A and its default library
whatever config.yaml says, and config.yaml's PDK and STD_CELL_LIBRARY would be
read too late to matter. So one file is written, the merge done here, and
LibreLane gets exactly what it would get if config.yaml had these keys in it.
"""
import os

import yaml

from c4o import common

DEFAULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "librelane-defaults.yaml")
OUT = os.path.join("build", "librelane-config.yaml")

HEADER = (
    "# Written by `make gds` (c4o-core flow-config): the defaults of c4o-core's\n"
    "# librelane-defaults.yaml with the keys of config.yaml over them. Edit config.yaml.\n"
)

def merged(config):
    """The defaults, with every top-level key of the config replacing its default."""
    with open(DEFAULTS) as f:
        result = yaml.safe_load(f) or {}
    result.update(config)
    return result

def cmd_flow_config(args, config):
    """Write build/librelane-config.yaml (started by make gds)."""
    if not config:
        common.log_error("No config.yaml, config.yml or config.json to read.")
        raise SystemExit(1)
    common.ensure_build_dir()
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        f.write(HEADER)
        yaml.safe_dump(merged(config), f, sort_keys=False, allow_unicode=True)
    os.replace(tmp, OUT)
