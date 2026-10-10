import re
import sys

from c4o import common

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
            common.log_error(f"Could not read {path}: {e}")
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
    sized_by = "FP_CORE_UTIL" if common.config_get(config, "FP_SIZING") == "relative" else "DIE_AREA"

    required_keys = [
        "PDK", "STD_CELL_LIBRARY", sized_by,
        "FP_SIZING", "CLOCK_PORT", "CLOCK_PERIOD"
    ]

    missing_keys = [key for key in required_keys if key not in config]

    if missing_keys:
        common.log_error(f"Missing required keys in the config file for the physical design flow: {', '.join(missing_keys)}")
        sys.exit(1)

    # Validate that we have RTL files
    files = common.get_files(args, config, key="VERILOG_FILES")
    if not files:
        common.log_error("No RTL files found. The physical design flow requires valid RTL.")
        sys.exit(1)

    # Checked whenever it is there, not only when it is the sizing variable:
    # LibreLane validates DIE_AREA's shape either way, so a malformed one is an
    # error it would raise too, three minutes later.
    if common.config_get(config, "DIE_AREA") is not None:
        error = die_area_error(common.config_get(config, "DIE_AREA"))
        if error:
            common.log_error(error)
            sys.exit(1)

    design_name = common.config_get(config, "DESIGN_NAME")
    modules = declared_modules(files)
    if design_name not in modules:
        common.log_error(
            f"DESIGN_NAME is '{design_name}', but no module by that name is "
            f"declared in VERILOG_FILES. Declared there: "
            f"{', '.join(sorted(modules)) or 'nothing'}."
        )
        sys.exit(1)

    # A warning, not an error: finding a port properly means parsing a port
    # list, which spans lines, carries attributes and can come from a macro.
    # What is safe to say is that a name absent from the RTL entirely is not a
    # port of it -- which is the typo this catches.
    clock_port = common.config_get(config, "CLOCK_PORT")
    if clock_port and not re.search(rf"\b{re.escape(str(clock_port))}\b", "\n".join(
            open(f, errors="replace").read() for f in files)):
        common.log_warn(
            f"CLOCK_PORT is '{clock_port}', which does not appear anywhere in "
            "VERILOG_FILES. The flow will not find a clock to constrain."
        )

    common.log_info("Configuration verified for the physical design flow.")
    # `gds` is an alias of this command, and it exits 0 -- so say outright
    # that nothing was built, or "make gds" reads as a finished layout. Worded
    # to hold both run alone and as the step before LibreLane in a template's
    # `make gds`, where "no layout was produced" read like a failure.
    common.log_info("This step builds no layout. LibreLane does that.")
