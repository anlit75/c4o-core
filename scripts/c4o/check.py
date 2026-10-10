import re
import sys

from c4o import common
from c4o import regress

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

# What a scope stands for in the line that says it passed, and which scopes it
# is built on. A scope runs the checks of the ones it needs first, so the
# problem of a lower scope is the one that is reported.
SCOPES = {
    "rtl": ("the RTL", []),
    "sim": ("the tests", ["rtl"]),
    "regress": ("the regression", ["sim"]),
    "gatesim": ("the gate-level tests", []),
    "gds": ("the physical design flow", ["rtl"]),
}

# The keys that only the physical design flow reads. A config with none of them
# is a design that is simulated and never built, and `check` does not ask it
# for a PDK.
GDS_KEYS = ("PDK", "STD_CELL_LIBRARY", "FP_SIZING", "CLOCK_PERIOD", "DIE_AREA", "FP_CORE_UTIL")

def needs_of(scope):
    """The scope and the scopes under it, the lowest first."""
    order = []
    for needed in SCOPES[scope][1]:
        order += [n for n in needs_of(needed) if n not in order]
    return order + [scope]

def skip_reason(config, scope):
    """Why a bare `check` leaves a scope out, or None when the config asks for it."""
    if scope == "regress" and not common.config_get(config, "REGRESSION"):
        return "REGRESSION is not set"
    if scope == "gatesim" and not (common.config_get(config, "GATE_TESTS") or common.config_get(config, "COCOTB_TESTS")):
        return "GATE_TESTS and COCOTB_TESTS are not set"
    if scope == "gds" and not any(key in config or f"//{key}" in config for key in GDS_KEYS):
        return "the config has none of the keys of the physical design flow"
    return None

def check_rtl(args, config):
    files = common.get_files(args, config, key="VERILOG_FILES")

    design_name = common.config_get(config, "DESIGN_NAME")
    if not design_name:
        common.log_error("DESIGN_NAME is not set. It names the top module of VERILOG_FILES.")
        sys.exit(1)
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
            common.read_text(f) for f in files)):
        common.log_warn(
            f"CLOCK_PORT is '{clock_port}', which does not appear anywhere in "
            "VERILOG_FILES. The flow will not find a clock to constrain."
        )

def check_sim(args, config):
    # get_files stops on a pattern that matches no file, so a test file that
    # is named and not there is found here and not by the simulator.
    testbenches = common.get_files(args, config, key="TEST_FILES")
    cocotb = common.get_files(args, config, key="COCOTB_TESTS")
    if not testbenches and not cocotb:
        common.log_error(
            "No tests to run: set TEST_FILES (Verilog testbenches) or "
            "COCOTB_TESTS (Python tests) in the config."
        )
        sys.exit(1)

def check_regress(args, config):
    value = common.config_get(config, "REGRESSION")
    if not value:
        common.log_error("No test list: set REGRESSION (or \"//REGRESSION\") to a YAML file of tests and seeds.")
        sys.exit(1)
    test_files = common.get_files(args, config, key="COCOTB_TESTS")
    if not test_files:
        common.log_error("REGRESSION runs tests of COCOTB_TESTS, and the config sets none.")
        sys.exit(1)
    # Reads the list, and stops on a file that is not there, a list that does
    # not parse and an entry that names no test.
    regress.load_regression(config, test_files)

def check_gatesim(args, config):
    gate = common.get_files(args, config, key="GATE_TESTS")
    cocotb = common.get_files(args, config, key="COCOTB_TESTS")
    if not gate and not cocotb:
        common.log_error(
            "No gate-level tests: set GATE_TESTS (or \"//GATE_TESTS\") for a Verilog "
            "testbench, or COCOTB_TESTS (or \"//COCOTB_TESTS\") for Python tests."
        )
        sys.exit(1)

def check_gds(args, config):
    """
    Validates that the configuration is complete enough for the physical design
    flow. It produces no layout of its own -- LibreLane does that -- so this is
    a pre-flight check.

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

    # Checked whenever it is there, not only when it is the sizing variable:
    # LibreLane validates DIE_AREA's shape either way, so a malformed one is an
    # error it would raise too, three minutes later.
    if common.config_get(config, "DIE_AREA") is not None:
        error = die_area_error(common.config_get(config, "DIE_AREA"))
        if error:
            common.log_error(error)
            sys.exit(1)

CHECKS = {
    "rtl": check_rtl,
    "sim": check_sim,
    "regress": check_regress,
    "gatesim": check_gatesim,
    "gds": check_gds,
}

def cmd_check(args, config):
    """
    Validates the config for one scope (`check --for gds`) or, without one, for
    every scope whose feature the config asks for. `make rtl`, `make sim` and
    `make gds` run their own scope first. It builds nothing and runs no tool.
    """
    scope = getattr(args, "scope", None)
    if scope:
        asked = [scope]
    else:
        asked = []
        for name in SCOPES:
            why = skip_reason(config, name)
            if why:
                common.log_info(f"{name} skipped: {why}.")
            else:
                asked.append(name)

    done = []
    for name in asked:
        for needed in needs_of(name):
            if needed not in done:
                CHECKS[needed](args, config)
                done.append(needed)

    for name in asked:
        common.log_info(f"Configuration verified for {SCOPES[name][0]}.")
    if "gds" in asked:
        common.log_info("This step builds no layout. LibreLane does that.")
