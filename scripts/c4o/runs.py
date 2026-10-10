import glob
import hashlib
import json
import os
import sys

from c4o import common

# make gds runs LibreLane with --run-tag <DESIGN_NAME>_run, so that is the one
# directory every command reads. ChipForAll once moved the whole run into
# build/, so look in both places.
RUN_ROOTS = ["runs", "build/runs"]

# Written into the run directory by `make gds` after a whole flow succeeded:
# the hash of the inputs the run was made from.
INPUTS_FILE = "c4o-inputs.sha256"

def run_tag(config):
    """The tag `make gds` gives its run, or exits when there is no design name."""
    design = common.config_get(config, "DESIGN_NAME")
    if not design:
        common.log_error("DESIGN_NAME is not set in the config, so there is no run to look for.")
        sys.exit(1)
    return f"{design}_run"

def locate(config, pattern):
    """
    (run directory, first match of pattern inside it) for the run of this
    design, or (None, None). Looked up by tag, never by modification time: a
    git checkout changes that, and a run of another design is not this one.
    """
    tag = run_tag(config)
    for root in RUN_ROOTS:
        run_dir = os.path.join(root, tag)
        found = sorted(glob.glob(os.path.join(run_dir, pattern)))
        if found:
            return run_dir, found[0]
    return None, None

def dir_paths(value):
    """Every 'dir::' path inside a config value: a string, or lists and mappings of them."""
    if isinstance(value, str):
        return [common.strip_path_prefix(value)] if value.startswith("dir::") else []
    if isinstance(value, list):
        return [p for item in value for p in dir_paths(item)]
    if isinstance(value, dict):
        return [p for item in value.values() for p in dir_paths(item)]
    return []

def expand(pattern):
    """The files a path or glob names. A directory counts as the files under it."""
    files = set()
    for match in glob.glob(pattern, recursive=True):
        if os.path.isdir(match):
            files.update(os.path.join(root, name) for root, _, names in os.walk(match) for name in names)
        elif os.path.isfile(match):
            files.add(match)
    return files

def input_files(config):
    """
    The files a run is made from: the config file, VERILOG_FILES, the include
    directories, and every file a key of the config points at with 'dir::'.

    Keys that start with '//' are c4o-core's own (the tests, the regression
    list), and LibreLane ignores them. They stay out, so that editing a
    testbench does not make a layout stale.
    """
    patterns = common.config_get(config, "VERILOG_FILES") or []
    patterns = list(patterns) if isinstance(patterns, list) else []
    includes = common.config_get(config, "VERILOG_INCLUDE_DIRS", [])
    patterns += common.get_include_dirs(config) if isinstance(includes, list) else []
    patterns += dir_paths({k: v for k, v in config.items() if not str(k).startswith("//")})
    files = {f for p in patterns if isinstance(p, str) for f in expand(common.strip_path_prefix(p))}
    configs = [name for name in common.CONFIG_FILENAMES if os.path.isfile(name)]
    return sorted(files) + configs[:1]

def inputs_hash(config):
    """
    A hash of the contents of the RTL and the config, or None when there is
    nothing to hash. File names count too, so a renamed file is a change.
    """
    files = sorted(set(input_files(config)))
    if not files:
        return None
    digest = hashlib.sha256()
    for path in files:
        with open(path, "rb") as f:
            digest.update(f"{path}\0{hashlib.sha256(f.read()).hexdigest()}\n".encode())
    return digest.hexdigest()

def freshness(run_dir, config):
    """
    'fresh' when the run was made from the inputs that are here now, 'stale'
    when it was not, 'unknown' when it carries no hash (a run made before
    c4o-core wrote one) or there is nothing to compare it with.
    """
    try:
        with open(os.path.join(run_dir, INPUTS_FILE)) as f:
            recorded = f.readline().strip()
    except OSError:
        return "unknown"
    current = inputs_hash(config)
    if current is None:
        return "unknown"
    return "fresh" if recorded == current else "stale"

def check_fresh(run_dir, config):
    """A stale run is an error; one with no hash is a warning, since it may be fine."""
    state = freshness(run_dir, config)
    if state == "stale":
        common.log_error(
            f"{run_dir} was made from different RTL or config than this directory "
            "has now, so its results describe an older design. Run make gds to "
            "update it, or name the file to skip this check."
        )
        sys.exit(1)
    if state == "unknown":
        common.log_warn(
            f"{run_dir} does not record the inputs it was made from, so it cannot "
            "be checked against the RTL. Run make gds to record them."
        )

def find_netlist(explicit, config):
    """The gate-level netlist of this design's run, unless named."""
    if explicit:
        return explicit
    run_dir, found = locate(config, "final/nl/*.v")
    if not found:
        common.log_error(
            f"No netlist found in runs/{run_tag(config)} or build/runs/{run_tag(config)}. "
            "Run make gds first, or name the file: gatesim <path>, "
            "cocotb --netlist <path>."
        )
        sys.exit(1)
    check_fresh(run_dir, config)
    return found

# LibreLane writes each timing metric once per corner and again with no
# '__corner:' suffix. The bare key already holds the worst value across every
# corner -- verified against a real run, where timing__setup__ws equalled the
# minimum of its nine per-corner values -- so the bare key is the one to report.
def find_metrics(explicit, config):
    """The metrics.json of this design's run, unless named."""
    if explicit:
        return explicit
    run_dir, found = locate(config, "final/metrics.json")
    if not found:
        common.log_error(
            f"No metrics.json found in runs/{run_tag(config)} or build/runs/{run_tag(config)}. "
            "Run make gds first, or name the file: report <path>."
        )
        sys.exit(1)
    check_fresh(run_dir, config)
    return found

def flow_identity():
    """What besides the inputs decides the result: the LibreLane image and this release."""
    return {"librelane_image": os.environ.get("LIBRELANE_IMAGE"), "c4o_core": common.c4o_version()}

def recorded_identity(run_dir):
    """The identity lines of the stamp. A stamp of one line has none."""
    try:
        with open(os.path.join(run_dir, INPUTS_FILE)) as f:
            lines = f.read().splitlines()[1:]
    except OSError:
        return {}
    return dict(line.split("=", 1) for line in lines if "=" in line)

def cmd_stamp(args, config):
    """
    Record the inputs of the run `make gds` just finished, and the flow that
    made it (started by make gds). The first line is the hash of the inputs,
    which is all that report and gatesim compare.
    """
    run_dir, _ = locate(config, "final/metrics.json")
    digest = inputs_hash(config)
    if not run_dir or not digest:
        common.log_warn("Could not record the inputs of the run.")
        return
    identity = "".join(f"{k}={v}\n" for k, v in flow_identity().items() if v)
    with open(os.path.join(run_dir, INPUTS_FILE), "w") as f:
        f.write(digest + "\n" + identity)

def cmd_fresh(args, config):
    """
    Exit 0 when `make gds` has nothing to redo: the run was made from these
    inputs by this LibreLane image and this release, and its GDS was copied to
    build/. Exit 1 otherwise (started by make gds).

    The image is only known here, from the environment, so report and gatesim
    cannot compare it. A stamp that records no image or release is not held
    against the run.
    """
    run_dir, _ = locate(config, "final/metrics.json")
    gds = os.path.join("build", f"{common.config_get(config, 'DESIGN_NAME')}.gds")
    if run_dir and os.path.isfile(gds) and freshness(run_dir, config) == "fresh":
        recorded, now = recorded_identity(run_dir), flow_identity()
        changed = [k for k, v in recorded.items() if now.get(k) and now[k] != v]
        if not changed:
            common.log_info(f"{run_dir} was made from these inputs by the same flow.")
            return
        common.log_info(f"{run_dir} was made by another {' and '.join(changed)}: running the flow.")
    sys.exit(1)

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
