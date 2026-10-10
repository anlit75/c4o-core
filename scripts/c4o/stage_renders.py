"""
One picture per stage of a LibreLane run, for the "How it was built" section of
the results page.

`make gds` calls this twice, around one KLayout call in the LibreLane image
(the c4o-core image has no KLayout):

  plan     decides which DEF of the run each stage is drawn from and writes
           build/stages/jobs.json, the arguments of LibreLane's own render.py
  collect  after the render: writes build/stages/stages.json, which names the
           pictures that exist, with the stage's seconds and how it ended

A stage is drawn from the last top-level step of that stage that wrote a DEF.
Signoff is not drawn again: LibreLane's final/render/<design>.png is copied. A
stage with no DEF has no picture, and a step that never wrote its state_out.json
is not trusted to have finished its DEF. This runs after a flow that failed as
well, and draws what is there.
"""
import glob
import json
import os
import shutil

from c4o import progress
from c4o import stages

OUT = os.path.join("build", "stages")
RENDER_KEYS = (("KLAYOUT_RENDER_GRID_VISBLE", "--grid-visible", False),
               ("KLAYOUT_RENDER_SHOW_RULER", "--grid-show-ruler", False),
               ("KLAYOUT_RENDER_TEXT_VISIBLE", "--text-visible", False),
               ("KLAYOUT_RENDER_BACKGROUND_COLOR", "--background-color", "white"),
               ("KLAYOUT_RENDER_RESOLUTION", "--resolution", 1000),
               ("KLAYOUT_RENDER_OVERSAMPLING", "--oversampling", 0))

def png_name(k):
    return stages.slug(stages.STAGES[k].name) + ".png"

def read_run(run_dir):
    """The top-level steps of a run in order, each with its stage, whether it finished, its seconds and its DEF."""
    found = []
    for name in os.listdir(run_dir) if os.path.isdir(run_dir) else []:
        m = progress.TOP_STEP.match(name)
        if m and os.path.isdir(os.path.join(run_dir, name)):
            found.append((int(m.group(1)), name, m.group(2)))
    # A resume appends new directories after the old: the step run last is the one that counts.
    latest = {slug: (ordinal, name, slug) for ordinal, name, slug in sorted(found)}
    steps, current = [], None
    for ordinal, name, slug in sorted(latest.values()):
        current = stages.advance(current, slug)
        path = os.path.join(run_dir, name)
        try:
            with open(os.path.join(path, "state_out.json")) as f:
                json.load(f)
            ok = True
        except (OSError, ValueError):
            ok = False
        defs = sorted(glob.glob(os.path.join(path, "*.def")))
        steps.append({"ordinal": ordinal, "name": name, "stage": current, "ok": ok,
                      "seconds": progress.read_runtime(os.path.join(path, "runtime.txt")) or 0.0,
                      "def": defs[0] if defs and ok else None})
    return steps

def read_resolved(run_dir):
    try:
        with open(os.path.join(run_dir, "resolved.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}

def render_args(cfg, def_path, png):
    """What KLayout.Render passes to render.py, from the config the run resolved."""
    tech = cfg.get("TECH_LEFS") or {}
    tech_lef = next((v for k, v in tech.items() if k.startswith("nom_")), next(iter(tech.values()), None))
    args = [def_path, "--output", png]
    for key, flag, default in RENDER_KEYS:
        args += [flag, str(cfg.get(key, default))]
    args += ["--lyp", cfg["KLAYOUT_PROPERTIES"], "--lyt", cfg["KLAYOUT_TECH"], "--lym", cfg["KLAYOUT_DEF_LAYER_MAP"]]
    for lef in [tech_lef] + list(cfg.get("CELL_LEFS") or []) + list(cfg.get("EXTRA_LEFS") or []):
        if lef:
            args += ["--input-lef", lef]
    return args

def pictures(steps):
    """{stage: the step it is drawn from}: the last finished step of each stage with a DEF."""
    drawn = {}
    for s in steps:
        if s["def"]:
            drawn[s["stage"]] = s
    return drawn

def plan(run_dir, out=OUT):
    """
    Empties out, copies LibreLane's final render and writes jobs.json for the
    steps that need drawing. Returns the number of jobs.
    """
    shutil.rmtree(out, ignore_errors=True)
    steps = read_run(run_dir)
    if not steps:
        return 0
    os.makedirs(out)
    cfg = read_resolved(run_dir)
    last = len(stages.STAGES) - 1
    final = os.path.join(run_dir, "final", "render", f"{cfg.get('DESIGN_NAME')}.png")
    if any(s["stage"] == last for s in steps) and os.path.isfile(final):
        shutil.copy(final, os.path.join(out, png_name(last)))
    jobs = []
    for k, s in pictures(steps).items():
        if k != last:
            try:
                jobs.append({"png": os.path.join(out, png_name(k)), "args": render_args(cfg, s["def"], os.path.join(out, png_name(k)))})
            except KeyError:    # a run whose config says nothing of KLayout cannot be drawn
                pass
    with open(os.path.join(out, "jobs.json"), "w") as f:
        json.dump(jobs, f)
    return len(jobs)

def collect(run_dir, out=OUT):
    """Writes stages.json from what the run holds and what the render left. Returns the number of pictures, or None for a run with no steps."""
    steps = read_run(run_dir)
    if not steps:
        return None
    drawn = pictures(steps)
    rows = []
    for k, stage in enumerate(stages.STAGES):
        mine = [s for s in steps if s["stage"] == k]
        png = png_name(k)
        path = os.path.join(out, png)
        have = os.path.exists(path) and os.path.getsize(path) > 0
        # Signoff's picture is the flow's own, of the end; the others are of the step they came from.
        source = mine[-1] if k == len(stages.STAGES) - 1 and mine else drawn.get(k)
        bad = [s["name"] for s in mine if not s["ok"]]
        rows.append({
            "name": stage.name, "blurb": stage.blurb, "detail": stage.detail,
            "first_step": mine[0]["ordinal"] if mine else None, "last_step": mine[-1]["ordinal"] if mine else None,
            "seconds": round(sum(s["seconds"] for s in mine), 3),
            "png": png if have else None,
            "after_step": source["ordinal"] if have and source else None,
            "status": "not reached" if not mine else "failed" if bad else "ok",
            "failed": bad,
        })
    count = sum(1 for r in rows if r["png"])
    with open(os.path.join(out, "stages.json"), "w") as f:
        json.dump({"run": os.path.basename(os.path.normpath(run_dir)), "stages": rows}, f, indent=1)
    try:
        os.remove(os.path.join(out, "jobs.json"))
    except OSError:
        pass
    return count
