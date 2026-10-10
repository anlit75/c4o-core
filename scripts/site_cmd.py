import filecmp
import glob
import json
import os
import shutil
import sys
from datetime import timezone
from xml.etree import ElementTree

import site_page
import stage_renders
import common
import regress
import report
import runs

# One page with what `report` prints, the layout and every
# cocotb verdict, for publishing on GitHub Pages. Everything it needs is copied
# into this directory, so the directory is the whole site. The markup is in
# site_page.py; this half finds the files.
SITE_DIR = "build/site"

COCOTB_RESULTS = [
    ("cocotb, RTL", "build/cocotb-results.xml"),
    ("cocotb, gate level", "build/cocotb-gl-results.xml"),
]

# The constraints the timing result depends on, as the STA step's config.json
# names them, with the unit LibreLane gives each.
CONSTRAINTS = [
    ("clock_period", "CLOCK_PERIOD"),
    ("uncertainty", "CLOCK_UNCERTAINTY_CONSTRAINT"),
    ("transition", "CLOCK_TRANSITION_CONSTRAINT"),
    ("derate", "TIME_DERATING_CONSTRAINT"),
    ("io_delay", "IO_DELAY_CONSTRAINT"),
]

def number(value):
    """A config value as a float, or None. LibreLane writes Decimals as numbers."""
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def run_details(metrics_path, metrics, config):
    """
    What the page shows beyond `report`'s rows, from the reports LibreLane
    leaves next to a run's metrics.json. Only when the file sits at
    <run>/final/metrics.json, for the reason find_render gives. Any part whose
    report is missing is left out.

    `config` is the design's config, which tells a constraint it set from one
    the flow defaulted.
    """
    details = {"signoff": report.signoff_checks(metrics)}
    final_dir = os.path.dirname(os.path.abspath(metrics_path))
    physical = details["physical"] = physical_details(metrics)
    if os.path.basename(final_dir) != "final":
        return details

    run_config = report.sta_config(metrics_path)
    constraints = {}
    for name, key in CONSTRAINTS:
        value = number(run_config.get(key))
        if value is not None:
            constraints[name] = (value, key in config)
    if constraints:
        physical["constraints"] = constraints
    corner = run_config.get("DEFAULT_CORNER")
    if corner:
        physical["corner"] = corner
    synthesized = report.synthesis_instances(metrics_path)
    if synthesized is not None:
        physical["synthesized"] = synthesized

    power = report.default_power(metrics_path)
    if power:
        details["power"] = power

    design = report.synthesis_design(metrics_path)
    drive = report.drive_table(metrics_path)
    if drive:
        details["drive"] = drive
    library = run_config.get("STD_CELL_LIBRARY")
    if isinstance(library, str) and library:
        physical["library"] = library
    # Two stages, not three peers: what synthesis produced (flip-flops and
    # logic), and the standard-cell total after routing, which contains them.
    area = {}
    if "area" in design and "sequential_area" in design:
        area["flip_flops"] = design["sequential_area"]
        area["logic"] = design["area"] - design["sequential_area"]
    if metrics.get("design__instance__area__stdcell") is not None:
        area["routed"] = metrics["design__instance__area__stdcell"]
    if metrics.get("design__instance__area__macros"):
        area["macros"] = metrics["design__instance__area__macros"]
    if area:
        details["area"] = area

    cells = [(report.CELL_CLASSES.get(name, name.replace("_", " ")), count,
              "synthesis" if name in report.FROM_SYNTHESIS
              else "flow" if name in report.ADDED_BY_FLOW else "other")
             for name, count in report.cell_classes(metrics)]
    if cells:
        details["cells"] = cells
    return details

def physical_details(metrics):
    """What a physical designer reads first, for the page; absent keys left out."""
    get = metrics.get
    out = {}
    if get("design__core__bbox"):
        x0, y0, x1, y1 = (float(v) for v in get("design__core__bbox").split())
        out["core"] = (x1 - x0, y1 - y0)
    for key, metric in (("taps", "design__instance__count__class:tap_cell"),
                        ("hold_buffers", "design__instance__count__hold_buffer"),
                        ("r2r_setup", "timing__setup_r2r__ws"),
                        ("r2r_hold", "timing__hold_r2r__ws"),
                        ("ir_worst", "ir__drop__worst")):
        if get(metric) is not None:
            out[key] = get(metric)
    # Worst slack over every corner (the bare key, see METRICS_GLOBS) and how
    # many paths miss, for the timing verdict.
    for key in ("setup", "hold"):
        if get(f"timing__{key}__ws") is not None:
            out[key] = (get(f"timing__{key}__ws"), get(f"timing__{key}_vio__count"))
    drv = report.drv_violations(metrics)
    if drv:
        out["drv"] = drv
    return out

# The files the page offers, with the section each belongs to. Each is copied
# only when it exists. The two summary.json are renamed so that they do not
# collide next to the page.
SITE_FILES = [
    ("tests", "build/cocotb-results.xml", "cocotb-results.xml"),
    ("tests", "build/cocotb-gl-results.xml", "cocotb-gl-results.xml"),
    ("regression", os.path.join(regress.REGRESS_DIR, "summary.json"), "regress-summary.json"),
    ("coverage", os.path.join(regress.COVERAGE_DIR, "summary.json"), "coverage-summary.json"),
]

# Every earlier run's numbers, in the order they were published. `report` fetches
# it from the live page before `site` runs (see actions/report).
HISTORY_FILE = "build/history.json"

def read_history(path=HISTORY_FILE):
    """
    The earlier rows of history.json, or [] when there is no file. The file is
    something an earlier run published, so one that is not a JSON list of
    objects is an error here and not a page that quietly starts over.
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            rows = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        common.log_error(f"Could not read {path}: {e}")
        sys.exit(1)
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        common.log_error(f"Could not read {path}: it is not a list of objects.")
        sys.exit(1)
    return rows

def history_row(env, details, cocotb_runs, coverage, regression):
    """
    This run's numbers as one row of history.json, the same numbers the page
    shows. A number the run did not produce is None, which a chart draws as a
    gap. The names are the file's format: a later image reads rows an earlier
    one wrote.
    """
    physical = details.get("physical") or {}
    area = details.get("area") or {}
    cells = details.get("cells")
    power = details.get("power")
    count = lambda title: next(((sum(v == "PASS" for _, v, _ in cases), len(cases))
                                for t, _, cases in cocotb_runs if t == title), (None, None))
    runs = (regression or {}).get("runs")
    percent = lambda kind: (((coverage or {}).get("types") or {}).get(kind) or {}).get("percent")
    row = {
        "sha": env.get("GITHUB_SHA"),
        "built": site_page.build_time(env).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "c4o_version": common.c4o_version(),
        "clock_period": (physical.get("constraints") or {}).get("clock_period", (None,))[0],
        "regress_passed": sum(run["verdict"] == "pass" for run in runs) if runs else None,
        "regress_total": len(runs) if runs else None,
        "cov_block": percent("line"), "cov_branch": percent("branch"), "cov_toggle": percent("toggle"),
        "setup_ws": physical.get("setup", (None,))[0], "hold_ws": physical.get("hold", (None,))[0],
        "area_ff": area.get("flip_flops"), "area_logic": area.get("logic"), "area_routed": area.get("routed"),
        "inst_synth": physical.get("synthesized"),
        "inst_routed": sum(n for _, n, _ in cells) if cells else None,
        # The default corner's total, which is what the Power section shows.
        "power_w": next((r[4] for r in power[1] if r[0] == "Total"), None) if power else None,
        "ir_drop_v": physical.get("ir_worst"),
        "ir_drop_pct": site_page.ir_drop_share(physical),
    }
    row["rtl_passed"], row["rtl_total"] = count("cocotb, RTL")
    row["gl_passed"], row["gl_total"] = count("cocotb, gate level")
    return row

def merge_history(rows, row):
    """
    The rows with this run's added at the end. A row with the same commit is
    replaced where it stands: a re-run of the same commit is not a second
    commit.
    """
    same = [i for i, old in enumerate(rows) if old.get("sha") == row["sha"]]
    if not same:
        return rows + [row]
    merged = list(rows)
    merged[same[0]] = row
    for i in reversed(same[1:]):
        del merged[i]
    return merged

def cmd_site(args, config):
    """
    Writes build/site/index.html: the cocotb verdicts, code coverage, the timing
    verdict and the constraints behind it, area and instances, power and signoff, with the
    layout render beside the title. Each part is included when the file behind
    it exists, so it works after `make cocotb` alone as well as after the full
    flow. Each section also offers the files behind it, and gets a History fold
    from build/history.json, to which a run on GitHub Actions adds its own row.

    It reports; it does not judge. A failed test is shown as failed and the
    command still succeeds -- the command that ran the test is the gate.
    """
    if os.path.isdir(SITE_DIR):
        shutil.rmtree(SITE_DIR)  # never publish a previous run's picture
    os.makedirs(SITE_DIR)

    numbers, layout, details = [], None, {}
    render = None  # the flow's own render of the layout, when there is a run
    files = []  # (section, name next to the page) of each file copied
    found = [path for pattern in runs.METRICS_GLOBS for path in glob.glob(pattern)]
    if found:
        path = max(found, key=os.path.getmtime)
        metrics = report.read_metrics(path)
        rows = report.report_rows(metrics, path)
        details = run_details(path, metrics, config)
        # The clock the run used. Without a run directory to read it from, the
        # one the config asks for.
        constraints = details["physical"].setdefault("constraints", {})
        period = number(common.config_get(config, "CLOCK_PERIOD"))
        if "clock_period" not in constraints and period and period > 0:
            constraints["clock_period"] = (period, True)
        # Each has a section of their own on the page. Power only when that
        # section exists: its row is the bare metric, which names no corner
        # and would disagree with the table next to it.
        own = ({"layout", "signoff"} | ({"power"} if "power" in details else set())
               | ({"instance classes"} if "cells" in details else set())
               | {"drive strength"})
        numbers = [(label, value) for label, value in rows if label not in own]
        render = dict(rows).get("layout")
        if render:
            layout = "layout.png"
            shutil.copy(render, os.path.join(SITE_DIR, layout))
        # The layout itself, next to its picture: a download, and on a
        # published page a link that opens it in 3D.
        gds = runs.find_gds(path)
        if gds:
            name = os.path.basename(gds)
            shutil.copy(gds, os.path.join(SITE_DIR, name))
            pdk = common.config_get(config, "PDK", "sky130A")
            details["gds"] = (name, pdk if pdk in report.GDS_VIEWER_PDKS else None,
                              os.path.getsize(gds))
        # The files of this run and no other: the netlist and the constraints
        # sit at the same <run>/final/ as the metrics.json the numbers come from.
        files.append(("summary", path, "metrics.json"))
        final_dir = os.path.dirname(os.path.abspath(path))
        if os.path.basename(final_dir) == "final":
            for section, pattern in (("timing", "sdc/*.sdc"), ("area", "nl/*.nl.v")):
                found_file = sorted(glob.glob(os.path.join(final_dir, pattern)))
                if found_file:
                    files.append((section, found_file[0], os.path.basename(found_file[0])))

    cocotb_runs = []
    for title, results in COCOTB_RESULTS:
        if not os.path.exists(results):
            continue
        try:
            seed, cases = site_page.cocotb_cases(results)
        except ElementTree.ParseError as e:
            common.log_error(f"Could not read {results}: {e}")
            sys.exit(1)
        cocotb_runs.append((title, seed, cases))

    files += [(section, src, name) for section, src, name in SITE_FILES if os.path.exists(src)]

    # From `make coverage`. Left out when it was not run, like every other part.
    coverage = None
    summary_path = os.path.join(regress.COVERAGE_DIR, "summary.json")
    if os.path.exists(summary_path):
        try:
            with open(summary_path) as f:
                coverage = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            common.log_error(f"Could not read {summary_path}: {e}")
            sys.exit(1)

    # From `make regress`. Left out when it was not run, like every other part.
    regression = None
    regress_path = os.path.join(regress.REGRESS_DIR, "summary.json")
    if os.path.exists(regress_path):
        try:
            with open(regress_path) as f:
                regression = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            common.log_error(f"Could not read {regress_path}: {e}")
            sys.exit(1)
        # The tests each entry holds, from the results file of each of its
        # runs, so the page can tie a module of the list to the tests in Tests.
        # A run with no readable results file adds no name: its verdict is
        # already a fail in the summary.
        tests = {}
        for run in regression.get("runs") or []:
            names = tests.setdefault(run["entry"], [])
            path = os.path.join(regress.REGRESS_DIR, f"{run['entry']}-{run['seed']}.xml")
            try:
                _, cases = site_page.cocotb_cases(path)
            except (OSError, ElementTree.ParseError):
                continue
            names += [name for name, _, _ in cases if name not in names]
        regression["tests"] = tests

    # From `make gds`: the render of each stage. Left out when there is none,
    # and when the file cannot be read, since the page does not need it.
    built = None
    stages_path = os.path.join(stage_renders.OUT, "stages.json")
    if os.path.exists(stages_path):
        try:
            with open(stages_path) as f:
                built = json.load(f)
            for row in built["stages"]:
                name = os.path.basename(row["png"] or "")
                png = os.path.join(stage_renders.OUT, name)
                if row["png"] and os.path.isfile(png):
                    if layout and render and filecmp.cmp(png, render, shallow=False):
                        # The picture the page already publishes as the layout: not a second copy.
                        row["png"] = layout     # offered as a download elsewhere on the page
                    else:
                        row["png"] = "stages/" + name
                        files.append(("stages", png, row["png"]))
                else:
                    row["png"] = None
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            common.log_warn(f"Not showing {stages_path} ({e}).")
            built = None

    if not (numbers or layout or cocotb_runs or details or coverage or regression):
        common.log_error(
            "Nothing to put on the page: no metrics.json under runs/ and no "
            "cocotb results. Run make cocotb or make gds first."
        )
        sys.exit(1)

    # The rows of the earlier runs, and this run's only on GitHub Actions: a
    # local `make site` is not a commit and must not leave a row behind.
    history = read_history()
    if os.environ.get("GITHUB_SHA"):
        history = merge_history(history, history_row(os.environ, details, cocotb_runs, coverage, regression))
    if history:
        with open(os.path.join(SITE_DIR, "history.json"), "w") as f:
            json.dump(history, f, separators=(",", ":"))
        files.append(("summary", os.path.join(SITE_DIR, "history.json"), "history.json"))

    offered = []
    for section, src, name in files:
        dest = os.path.join(SITE_DIR, name)
        if os.path.abspath(src) != os.path.abspath(dest):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy(src, dest)
        offered.append((section, name, os.path.getsize(dest)))

    design = common.config_get(config, "DESIGN_NAME", "design")
    index = os.path.join(SITE_DIR, "index.html")
    with open(index, "w") as f:
        f.write(site_page.render(design, numbers, layout, cocotb_runs, os.environ,
                                 description=common.config_get(config, "DESCRIPTION", None),
                                 coverage=coverage, regression=regression,
                                 history=history, files=offered, stages=built, **details))
    common.log_info(f"Wrote {index}")
