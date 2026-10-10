"""
LibreLane's steps, grouped into the seven stages that the terminal ledger shows.

One table, so that whatever else wants to say "which stage is this step in" --
the terminal today, the results page next -- reads the same one. `blurb` is the
line of the terminal and the subtitle of the page; `detail` is what the page says
when a stage is opened, for a reader who has never seen a layout.

A stage begins at its first step id and runs until the next stage's first id.
An id this table has never seen belongs to the stage that is running, so a
LibreLane that adds or renames a step does not break the grouping. The ids are
those of LibreLane 3.0.14's Classic flow.
"""
import re
from collections import namedtuple

Stage = namedtuple("Stage", "name first blurb detail")

STAGES = (
    Stage("Synthesis", "Verilator.Lint", "RTL becomes gates; lint and a first timing check",
          "Your Verilog is checked, then turned into logic gates from the Sky130 cell library. "
          "There is no layout yet, so this stage has no picture."),
    Stage("Floorplan", "OpenROAD.Floorplan", "pick the die size, power grid and tap cells",
          "The die is the outline of the chip. The empty rows are where gates will sit, "
          "and the stripes are the metal rails that bring power to them."),
    Stage("Placement", "OpenROAD.GlobalPlacementSkipIO", "give every gate a place on the die",
          "Every gate now has a place on the die. The small colored blocks are the cells, packed into the rows."),
    Stage("Clock tree", "OpenROAD.CTS", "build the clock distribution and fix its timing",
          "Extra buffers now carry the clock to every flip-flop at nearly the same moment. "
          "They are small cells added among the others."),
    Stage("Routing", "OpenROAD.GlobalRouting", "draw the wires; repair antenna violations",
          "Metal wires now connect the gates. The colored lines drawn over the cells are wires on different metal layers."),
    Stage("Finish & GDS", "Checker.TrDRC", "fill, extract parasitics, final timing, write the GDS",
          "Filler cells close the gaps between the gates, and timing is measured again from the real wires. "
          "The picture is the layout that is written to the GDS file."),
    Stage("Signoff", "Odb.CheckDesignAntennaProperties", "DRC, LVS, antenna, XOR: can it be made?",
          "The checks a fab would run on the finished layout. This is the picture of that layout, "
          "the one that is handed over."),
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
