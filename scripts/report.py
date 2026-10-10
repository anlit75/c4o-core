import glob
import json
import os
import re
import sys

import site_page
import common
import runs

# The manufacturability checks LibreLane's Classic flow runs after routing.
# Every one of them errors the flow by default (ERROR_ON_MAGIC_DRC and friends
# all default to True), so a run that produced a metrics.json has already
# passed them -- which is exactly why they are worth printing. The other rows
# answer 'is my design any good'; without these, nothing answers 'can it be
# made', and the reader is left inferring it from the absence of a crash.
#
# The two DRC decks are one check, "DRC": two independent tools asked the same
# question. Antenna is its own row because in this flow neither deck checks it.
DRC_TOOLS = [("Magic", "magic__drc_error__count"), ("KLayout", "klayout__drc_error__count")]

SIGNOFF_CHECKS = [
    ("LVS", "design__lvs_error__count"),
    ("antenna", "route__antenna_violation__count"),
    ("XOR", "design__xor_difference__count"),
]

def signoff_checks(metrics):
    """
    (check, errors, tools, failed) per check the run reported, DRC first.

    `tools` names the DRC tools that reported, `failed` the ones with errors
    and their counts: "KLayout", or "Magic 2, KLayout 3" when both. Both are
    empty for the other checks. A key present but null is not a check that
    ran, so it is left out.
    """
    out = []
    drc = [(tool, metrics[key]) for tool, key in DRC_TOOLS if metrics.get(key) is not None]
    if drc:
        bad = [(tool, count) for tool, count in drc if count]
        failed = (bad[0][0] if len(bad) == 1 else ", ".join(f"{t} {c}" for t, c in bad)) if bad else ""
        out.append(("DRC", sum(count for _, count in drc), " and ".join(t for t, _ in drc), failed))
    out += [(label, metrics[key], "", "") for label, key in SIGNOFF_CHECKS
            if metrics.get(key) is not None]
    return out

def signoff_row(metrics):
    """
    One line summarising the checks above, or None when the run reported none.

    Named rather than counted when something is wrong -- '3 DRC (KLayout), 1 LVS'
    is the sentence you want; a column of zeroes with one non-zero hidden in it
    is not.
    """
    present = signoff_checks(metrics)
    if not present:
        return None

    failed, ran = site_page.signoff_words(present)
    if failed:
        return ("signoff", failed)
    # Name the checks that actually ran: 'clean' is only as strong as its list.
    # DRC says its tools, since one of the two may be all that reported.
    return ("signoff", f"clean  ({ran})")

# The PDKs Tiny Tapeout's GDS viewer has layer maps for (its src/pdk_layers.js).
# Any other and the page offers the GDS as a download only.
GDS_VIEWER_PDKS = {"sky130A", "ihp-sg13g2", "gf180mcuD"}

def sta_step(metrics_path):
    """
    The newest post-PnR STA step directory of the run a metrics.json belongs
    to, or None -- including when the file does not sit at <run>/final/, for
    the reason find_render gives.
    """
    final_dir = os.path.dirname(os.path.abspath(metrics_path))
    if os.path.basename(final_dir) != "final":
        return None
    return runs.newest_step(os.path.dirname(final_dir), "*-openroad-stapostpnr")

def sta_config(metrics_path):
    """
    The config.json the newest post-PnR STA step ran with, as a dict, or {}.
    It holds the whole resolved config, so it states the constraints the
    result depends on whether config.yaml set them or the flow defaulted them.
    """
    sta = sta_step(metrics_path)
    path = os.path.join(sta, "config.json") if sta else None
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except ValueError:
        return {}

def default_power(metrics_path):
    """(DEFAULT_CORNER, power_groups rows) from that corner's power.rpt, or None."""
    sta = sta_step(metrics_path)
    corner = sta_config(metrics_path).get("DEFAULT_CORNER")
    if not sta or not corner:
        return None
    report = os.path.join(sta, corner, "power.rpt")
    if not os.path.exists(report):
        return None
    with open(report) as f:
        rows = site_page.power_groups(f.read())
    return (corner, rows) if any(r[0] == "Total" for r in rows) else None

def synthesis_design(metrics_path):
    """
    The `design` object of the stat.json Yosys.Synthesis wrote, or {}. Read
    from the run's own step directory, for the reason find_render gives, and
    from the steps of the run final/ describes.
    """
    final_dir = os.path.dirname(os.path.abspath(metrics_path))
    if os.path.basename(final_dir) != "final":
        return {}
    stat = runs.newest_step(os.path.dirname(final_dir), "*-yosys-synthesis/reports/stat.json")
    if not stat:
        return {}
    try:
        with open(stat) as f:
            design = json.load(f).get("design", {})
    except (OSError, ValueError):
        return {}
    return design if isinstance(design, dict) else {}

def synthesis_instances(metrics_path):
    """The cell count Yosys.Synthesis reported (design.num_cells), or None."""
    count = synthesis_design(metrics_path).get("num_cells")
    return count if isinstance(count, int) else None

# A standard cell as the netlists and stat.json name it: sky130_fd_sc_hd__dfrtp_2
# is library sky130_fd_sc_hd, function dfrtp, drive strength 2. The `_sc_` and
# the double underscore are the sky130 naming; a macro or a Yosys-internal
# type does not match and is not counted.
STD_CELL = re.compile(r"\w+?_sc_\w+?__(?P<function>\w+)_(?P<drive>\d+)$")

# Cells with no logic function, which have no drive strength to choose: well
# taps, decap, fill and antenna diodes. LibreLane files the first three under
# tap_cell and fill_cell (decap is fill's). A diode's _2 is its size, not a
# driver's strength, and the flow places it, not the design.
PHYSICAL_ONLY = ("tap", "decap", "fill", "diode")

def drive_strengths(cells):
    """{drive strength: count} of the logic cells in a {cell name: count} map."""
    out = {}
    for name, count in cells.items():
        m = STD_CELL.match(name)
        if m and not m["function"].startswith(PHYSICAL_ONLY):
            out[int(m["drive"])] = out.get(int(m["drive"]), 0) + count
    return out

def routed_cells(metrics_path):
    """
    {cell name: instances} of the routed design, or None. From the netlist
    LibreLane copies to final/nl/, the one list of instances that is plain
    text and needs no tool to open: one line per instance, `<cell> <name> (`.
    Measured on 3.0.14 it holds every instance -- the 274 of a run whose
    metrics count 113 standard cells, 161 fill and decap, and 27 taps -- and
    so does final/pnl/. 53-odb-cellfrequencytables's cell.rpt has the same
    counts, but as a terminal table that the next LibreLane may redraw.
    """
    final_dir = os.path.dirname(os.path.abspath(metrics_path))
    if os.path.basename(final_dir) != "final":
        return None
    found = sorted(glob.glob(os.path.join(final_dir, "nl", "*.nl.v")))
    if not found:
        return None
    counts = {}
    try:
        with open(found[0]) as f:
            for line in f:
                m = re.match(r"\s*(\w+_sc_\w+__\w+)\s+\S+\s*\(", line)
                if m:
                    counts[m[1]] = counts.get(m[1], 0) + 1
    except OSError:
        return None
    return counts

def drive_table(metrics_path):
    """
    [(drive strength, after synthesis, after routing)] by strength, smallest
    first. A stage whose source is missing is None in every row, never a zero;
    [] when neither stage is known.
    """
    synthesized = synthesis_design(metrics_path).get("num_cells_by_type")
    synthesized = drive_strengths(synthesized) if isinstance(synthesized, dict) else None
    routed = routed_cells(metrics_path)
    routed = drive_strengths(routed) if routed is not None else None
    if synthesized is None and routed is None:
        return []
    count = lambda stage, n: None if stage is None else stage.get(n, 0)
    sizes = sorted(set(synthesized or ()) | set(routed or ()))
    return [(n, count(synthesized, n), count(routed, n)) for n in sizes]

# LibreLane's names for the classes a real 3.0.14 run reported, in words. A
# class not listed here is printed under its own name, underscores spaced.
CELL_CLASSES = {
    "multi_input_combinational_cell": "logic",
    "sequential_cell": "sequential",
    "inverter": "inverters",
    "timing_repair_buffer": "timing-repair buffers",
    "clock_buffer": "clock buffers",
    "clock_inverter": "clock inverters",
    "tap_cell": "well taps",
}

# Which classes the flow adds rather than synthesis producing them. Counted
# against a real run: its 198 instances were synthesis's 110 plus 42
# clock-tree, hold and fanout buffers and 46 well taps. A class in neither set
# is shown as "other" rather than guessed at.
FROM_SYNTHESIS = {"multi_input_combinational_cell", "sequential_cell", "inverter"}

ADDED_BY_FLOW = {"timing_repair_buffer", "clock_buffer", "clock_inverter", "tap_cell"}

def cell_classes(metrics):
    """(class, count) per class LibreLane filed cells under, largest first, fill left out."""
    return sorted(
        ((key.split(":", 1)[1], count) for key, count in metrics.items()
         if key.startswith("design__instance__count__class:")
         and not key.endswith(":fill_cell") and count),
        key=lambda c: -c[1])

def report_rows(metrics, path):
    """The (label, value) rows `report` prints, in the order it prints them."""
    rows = []

    bbox = metrics.get("design__die__bbox")
    area = metrics.get("design__die__area")
    if bbox and area is not None:
        x0, y0, x1, y1 = (float(v) for v in bbox.split())
        rows.append(("die", f"{x1 - x0:g} x {y1 - y0:g} um  ({area:g} um^2)"))

    utilization = metrics.get("design__instance__utilization")
    if utilization is not None:
        rows.append(("utilization", f"{utilization * 100:.1f}%"))

    # Instances, not "cells": the count after synthesis is what the design is,
    # and the count after routing adds what the flow put in.
    # Not design__instance__count: that one counts fill instances too, which
    # say nothing about the design -- 544 of this run's 787 were fill. Well
    # taps are in the stdcell count: 46 of this run's 198.
    routed = metrics.get("design__instance__count__stdcell")
    synthesized = synthesis_instances(path)
    if synthesized is not None and routed is not None:
        rows.append(("instances", f"{synthesized} after synthesis, {routed} after routing"))
    elif routed is not None:
        rows.append(("instances", f"{routed} after routing"))
    elif synthesized is not None:
        rows.append(("instances", f"{synthesized} after synthesis"))

    # What the routed instances are, by the class LibreLane files each one
    # under, largest first. Fill is left out for the reason above; in a real
    # run the rest add up to the routed count -- 198, of which 88 are buffers
    # and taps the flow added, not logic the RTL asked for.
    classes = cell_classes(metrics)
    if classes:
        rows.append(("instance classes", ", ".join(
            f"{count} {CELL_CLASSES.get(name, name.replace('_', ' '))}"
            for name, count in classes)))

    # What drive strength the cells have, before and after the flow. Taps, decap
    # and fill have none and are left out. Only the stages that are known.
    drive = drive_table(path)
    if drive:
        if all(s is not None and r is not None for _, s, r in drive):
            text = ", ".join(f"X{n} {s}->{r}" for n, s, r in drive)
            stage = "synthesis->routing"
        else:
            text = ", ".join(f"X{n} {s if s is not None else r}" for n, s, r in drive)
            stage = "after synthesis" if drive[0][1] is not None else "after routing"
        rows.append(("drive strength", f"{text}  ({stage})"))

    for label, slack_key, violation_key in (
        ("setup slack", "timing__setup__ws", "timing__setup_vio__count"),
        ("hold slack", "timing__hold__ws", "timing__hold_vio__count"),
    ):
        slack = metrics.get(slack_key)
        if slack is not None:
            violations = metrics.get(violation_key, "?")
            rows.append((label, f"{slack:+.2f} ns  ({violations} violations)"))

    drv = drv_violations(metrics)
    if drv:
        counts = ", ".join(f"{n} {label}" for label, n, _ in drv)
        corners = sorted({c for _, _, cs in drv for c in cs})
        rows.append(("limit violations", counts + (f"  ({', '.join(corners)})" if corners else "")))

    # The default corner's power.rpt when the run left one: the bare
    # power__total names no corner, and in a real 3.0.14 run it is
    # max_ff_n40C_1v95's, not the default corner's.
    corner_power = default_power(path)
    if corner_power:
        corner, groups = corner_power
        total = next(g[4] for g in groups if g[0] == "Total")
        rows.append(("power", f"{site_page.milliwatts(total)}  ({corner})"))  # watts
    elif metrics.get("power__total") is not None:
        rows.append(("power", f"{site_page.milliwatts(metrics['power__total'])}  (corner not named)"))

    signoff = signoff_row(metrics)
    if signoff:
        rows.append(signoff)

    # Not fatal, and invisible everywhere else.
    warnings = metrics.get("design__lint_warning__count")
    if warnings is not None:
        rows.append(("lint warnings", str(warnings)))

    # Last because it is a pointer, not a measurement.
    render = runs.find_render(path)
    if render:
        rows.append(("layout", render))

    return rows

def read_metrics(path):
    common.log_info(f"Reading metrics from {path}")
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        common.log_error(f"Could not read {path}: {e}")
        sys.exit(1)

def cmd_report(args, config):
    """
    Prints the handful of numbers that answer 'is my design any good' -- how big
    it is, whether it makes timing, what it burns. The flow computes all of this
    and then leaves it in a 300-key JSON file nobody opens.

    Informational only. It does not fail on a timing violation: closing timing
    is iterative, and LibreLane does not treat it as fatal either.
    """
    path = runs.find_metrics(getattr(args, "metrics", None))
    rows = report_rows(read_metrics(path), path)

    if not rows:
        common.log_error(f"{path} carried none of the metrics this report reads.")
        sys.exit(1)

    label_width = max(len(label) for label, _ in rows)
    print()
    print(f"  {common.config_get(config, 'DESIGN_NAME', 'design')}")
    print()
    for label, value in rows:
        print(f"  {label.ljust(label_width)}   {value}")
    print()

# Violations of the cell library's limits after routing. The bare key is the
# worst over every corner; each corner has its own key with a suffix.
DRV_METRICS = (("max slew", "design__max_slew_violation__count"),
               ("max capacitance", "design__max_cap_violation__count"),
               ("max fanout", "design__max_fanout_violation__count"))

def drv_violations(metrics):
    """
    (limit, violations, corners with a violation) for each limit the run
    reported, in DRV_METRICS order. The flow does not fail on these, so the
    report and the page are where they show.
    """
    rows = []
    for label, metric in DRV_METRICS:
        if metrics.get(metric) is None:
            continue
        prefix = f"{metric}__corner:"
        corners = sorted(k[len(prefix):] for k, v in metrics.items() if k.startswith(prefix) and v)
        rows.append((label, metrics[metric], corners))
    return rows
