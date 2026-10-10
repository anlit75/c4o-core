import glob
import json
import os
import sys

import common

# LibreLane writes the synthesised netlist under final/nl/. ChipForAll then
# moves the whole run into build/, so look in both places.
NETLIST_GLOBS = ["runs/*/final/nl/*.v", "build/runs/*/final/nl/*.v"]

def find_netlist(explicit):
    """The newest gate-level netlist a run left behind, unless named."""
    if explicit:
        return explicit
    found = [path for pattern in NETLIST_GLOBS for path in glob.glob(pattern)]
    if not found:
        common.log_error(
            "No netlist found under runs/ or build/runs/. Run the physical "
            "design flow first, or name the file: gatesim <path>, "
            "cocotb --netlist <path>."
        )
        sys.exit(1)
    return max(found, key=os.path.getmtime)

# LibreLane writes each timing metric once per corner and again with no
# '__corner:' suffix. The bare key already holds the worst value across every
# corner -- verified against a real run, where timing__setup__ws equalled the
# minimum of its nine per-corner values -- so the bare key is the one to report.
METRICS_GLOBS = ["runs/*/final/metrics.json", "build/runs/*/final/metrics.json"]

def find_metrics(explicit):
    """The newest metrics.json a LibreLane run left behind, unless named."""
    if explicit:
        return explicit
    found = [path for pattern in METRICS_GLOBS for path in glob.glob(pattern)]
    if not found:
        common.log_error(
            "No metrics.json found under runs/ or build/runs/. Run the physical "
            "design flow first, or name the file: report <path>."
        )
        sys.exit(1)
    return max(found, key=os.path.getmtime)

# KLAYOUT_RENDER is registered with extension "png" and folder "render", so the
# file is <design>.png -- not <design>.klayout.png, which is what the format's
# name suggests and what this first looked for. Confirmed against a real
# LibreLane 3.0.14 run, not inferred from the step's f-string.
RENDER_GLOBS = ["final/render/*.png", "*-klayout-render/*.png"]

def step_ordinal(path, run_dir):
    """The number LibreLane gave the step directory a path is under, or -1."""
    head = os.path.relpath(path, run_dir).split("-", 1)[0]
    return int(head) if head.isdigit() else -1

def last_finished_step(run_dir):
    """
    The number of the last step of the run final/metrics.json describes, or
    None when no step directory says.

    LibreLane writes final/ only when a flow reaches its end. A resume that is
    interrupted -- a crash, a kill, Ctrl-C -- leaves step directories newer
    than final/, and reading those puts the timing of a run that never
    finished under the summary of the one that did. Measured on 3.0.14: the
    last step of a finished flow carries exactly final/'s metrics in its
    state_out.json, and no step of a later, different run does.

    Compared as text, so that a NaN in the metrics still equals itself.
    """
    def text(metrics):
        return json.dumps(metrics, sort_keys=True)

    try:
        with open(os.path.join(run_dir, "final", "metrics.json")) as f:
            final = text(json.load(f))
    except (OSError, ValueError):
        return None
    states = glob.glob(os.path.join(run_dir, "*-*", "state_out.json"))
    for state in sorted(states, key=lambda p: -step_ordinal(p, run_dir)):
        try:
            with open(state) as f:
                metrics = json.load(f).get("metrics")
        except (OSError, ValueError):
            continue
        if metrics is not None and text(metrics) == final:
            return step_ordinal(state, run_dir)
    return None

def newest_step(run_dir, pattern):
    """
    The newest match of a pattern that starts with a step directory, among the
    steps of the run final/ describes, or None.

    LibreLane numbers the step directories, and a resumed run adds its steps
    after the ones already there. So 119-openroad-stapostpnr is newer than
    55-openroad-stapostpnr -- and sorts before it as a string, which is how
    the page once showed the timing of the run before the resume.

    Steps after last_finished_step() are left out. When it has no answer --
    a run directory copied without its state files -- every step counts.
    """
    last = last_finished_step(run_dir)
    found = [path for path in sorted(glob.glob(os.path.join(run_dir, pattern)))
             if last is None or step_ordinal(path, run_dir) <= last]
    return max(found, key=lambda p: step_ordinal(p, run_dir)) if found else None

def find_render(metrics_path):
    """
    The PNG KLayout.Render drew of the finished layout.

    The Classic flow renders one on every run and leaves it in the run
    directory, where nobody goes looking. It lands twice: in the step's own
    directory, and again under final/ in the folder KLAYOUT_RENDER is
    registered with. final/ is the copy worth pointing at, so it is tried
    first.

    Both patterns name the directory rather than globbing the whole run for
    *.png, so an unrelated image a step happens to write cannot be reported as
    the layout.

    Only looked for when the file sits where a run leaves it, at
    <run>/final/metrics.json. A metrics.json named on the command line can be
    anywhere, and globbing two directories up from an arbitrary path is how a
    report ends up pointing at a PNG from an unrelated run -- or walking
    someone's entire home directory to find one.
    """
    final_dir = os.path.dirname(os.path.abspath(metrics_path))
    if os.path.basename(final_dir) != "final":
        return None

    run_dir = os.path.dirname(final_dir)
    for pattern in RENDER_GLOBS:
        found = newest_step(run_dir, pattern)
        if not found:
            continue
        # Printed for a human to open, so spell it the way they would type it.
        relative = os.path.relpath(found)
        return found if relative.startswith(os.pardir) else relative
    return None

def find_gds(metrics_path):
    """
    The run's final GDS, at <run>/final/gds/, or None -- including when the
    metrics.json does not sit at <run>/final/, for the reason find_render gives.
    """
    final_dir = os.path.dirname(os.path.abspath(metrics_path))
    if os.path.basename(final_dir) != "final":
        return None
    found = sorted(glob.glob(os.path.join(final_dir, "gds", "*.gds")))
    return found[0] if found else None
