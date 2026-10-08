"""
LibreLane's steps, grouped into the seven stages that the terminal ledger shows.

One table, so that whatever else wants to say "which stage is this step in" --
the terminal today, the results page next -- reads the same one.

A stage begins at its first step id and runs until the next stage's first id.
An id this table has never seen belongs to the stage that is running, so a
LibreLane that adds or renames a step does not break the grouping. The ids are
those of LibreLane 3.0.14's Classic flow.
"""
import re
from collections import namedtuple

Stage = namedtuple("Stage", "name first blurb")

STAGES = (
    Stage("Synthesis", "Verilator.Lint", "RTL becomes gates; lint and a first timing check"),
    Stage("Floorplan", "OpenROAD.Floorplan", "pick the die size, power grid and tap cells"),
    Stage("Placement", "OpenROAD.GlobalPlacementSkipIO", "give every gate a place on the die"),
    Stage("Clock tree", "OpenROAD.CTS", "build the clock distribution and fix its timing"),
    Stage("Routing", "OpenROAD.GlobalRouting", "draw the wires; repair antenna violations"),
    Stage("Finish & GDS", "Checker.TrDRC", "fill, extract parasitics, final timing, write the GDS"),
    Stage("Signoff", "Odb.CheckDesignAntennaProperties", "DRC, LVS, antenna, XOR: can it be made?"),
)


def slug(step):
    """
    The form in which an id and a directory name can be compared:
    'OpenROAD.CTS' and the 'openroad-cts' of runs/<tag>/35-openroad-cts are the same.
    """
    return re.sub(r"[^a-z0-9]+", "-", step.lower()).strip("-")


STAGE_OF_FIRST = {slug(s.first): k for k, s in enumerate(STAGES)}


def advance(current, step):
    """The stage of a step, given the stage of the one before it (None for the first)."""
    k = STAGE_OF_FIRST.get(slug(step))
    if k is not None:
        return k
    return 0 if current is None else current


def group(steps):
    """The stage index of each step of an ordered list of ids or directory slugs."""
    out, current = [], None
    for step in steps:
        current = advance(current, step)
        out.append(current)
    return out


def step_counts(steps):
    """How many of an ordered list of steps each stage holds."""
    counts = [0] * len(STAGES)
    for k in group(steps):
        counts[k] += 1
    return counts
