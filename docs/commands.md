# c4o-core commands in detail

What each command does beyond the one-line table in the [README](../README.md#-command-reference), and why. `c4o-core <command>` is shorthand for the `docker run` line in the README's Quick Start.

## synth, and SystemVerilog in every command

**`synth` runs one fixed Yosys script**, and no variable replaces it: the reads,
then `synth -top <DESIGN_NAME>`, then `write_json`. Nothing hands Yosys a liberty
file, so the output is its own generic cells and not the PDK's -- `$_DFF_PP0_`,
`$_OR_`, `$_XOR_`, 94 of them for a design `report` later counts as 198 standard
cells. So this command answers "does it synthesise, and roughly how much logic",
which is the question worth a one-word command, and it is not a source of area or
timing: those come from the physical flow, which synthesises again against the
real library. Anything else -- your own passes, your own reports, a script you
wrote to explain line by line -- is Yosys' own interface, so open a shell in this
image and run `yosys` there.

**Every command reads SystemVerilog.** `sim` passes `iverilog -g2012`, `synth`
and `schematic` read with `read_verilog -sv`, `cocotb` and `gatesim` always did,
and LibreLane reads with `-sv` too -- so `logic`, `always_ff` and the rest of the
synthesisable subset behave the same whichever command opens the file. Before
2.8.3 they did not: the same file passed two of these commands and failed two.

What that costs, measured rather than assumed: `iverilog -g2012` rejects `bit`,
`do`, `final`, `soft`, `global`, `byte` and `type` as identifiers, which
Verilog-2005 allowed, so a design using one of those as a signal name has to
rename it. `read_verilog -sv` accepted all seven, so the yosys side costs
nothing. What `-sv` does not buy is an `interface` as a synthesisable module
boundary: yosys parses the declaration and then fails at `hierarchy`, which is
its own limitation rather than something a flag changes.

## Python testbenches (cocotb)

`sim` runs a Verilog testbench. `cocotb` runs the same design from Python
instead — useful when the stimulus is easier to express in a real programming
language than in Verilog:

```yaml
DESIGN_NAME: counter
VERILOG_FILES:
  - dir::src/counter.v
"//COCOTB_TESTS":
  - dir::test/*.py
```

```python
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

@cocotb.test()
async def reset_clears_the_count(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    assert dut.count.value == 0
```

`DESIGN_NAME` is the module cocotb drives, so no testbench wrapper is needed.

Two things worth knowing before you write one:

*   **A failing cocotb test does not fail the simulator.** `vvp` exits 0 whether
    the tests passed or not; the verdict is only in the results file. This
    command reads it and exits non-zero itself, which is the difference between
    a test suite and a decoration. The same silence hides a cocotb that could
    not start at all, so a run that writes no results is a failure too.
*   **Your design needs a `` `timescale ``.** Without one Icarus defaults to
    1-second precision and every cocotb test dies with
    `Unable to accurately represent 10(ns) with the simulator precision of 1e0`.
    Adding `` `timescale 1ns/1ps `` to the top of the file fixes it. `make sim`
    never shows this, because the Verilog testbench carries its own, so this
    command warns before compiling when no file in `VERILOG_FILES` declares one.

### The same tests, against the gates

```bash
cocotb                      # the RTL
cocotb --netlist            # what synthesis produced, same tests
cocotb --netlist path/to/x.nl.v
```

It takes the netlist and cell models exactly as `gatesim` does, and needs
`PDK` and `STD_CELL_LIBRARY` for the same reason. The tests do not change.

Which is the point. A testbench that only touches the top-level ports survives
synthesis; one that reaches inside the design does not, because the nets it
names are gone:

```
AttributeError: counter contains no object named c
```

That is not a bug to work around — it is the run telling you which of your
tests were checking the design and which were checking its internals. `gatesim`
cannot say it, because its testbench is a separate Verilog file written for the
netlist, so nothing is shared with the RTL run.

The two runs keep separate verdicts, `build/cocotb-results.xml` and
`build/cocotb-gl-results.xml`, so running both leaves both readable.

## Simulating the gates (gatesim)

`sim` shows the RTL behaves. `gatesim` shows the gates synthesis actually
produced still behave — a different claim, with latch inference, reset handling
and every ambiguous `always` block sitting between the two.

```yaml
PDK: sky130A
STD_CELL_LIBRARY: sky130_fd_sc_hd
"//GATE_TESTS":
  - dir::test/*_gl.v
```

It finds the newest netlist under `runs/` or `build/runs/`, and derives the cell
models from `PDK` and `STD_CELL_LIBRARY` — no third key to disagree with those
two. Set `PDK_ROOT` if the PDK lives outside `./pdks` -- the `pdk` command
installs where it points, so one copy can serve several checkouts.

**The gate-level testbench has to be a separate file from the RTL one.**
Synthesis resolves parameters, so a testbench that shrinks the design by
overriding one — the usual trick for keeping simulations short — has nothing
left to override. Drive the real ports at their real width.

### It can be slow, and how slow is your design's business

Gate-level cost scales with simulated cycles times cell count, and both can be
large. ChipForAll's blinky takes minutes, not seconds, because its clock divider
is 26 bits deep and one output toggle takes 2\*\*25 cycles. A deep divider is the
most common beginner design there is, so this is not an unusual case.

Two consequences worth planning for:

*   Put a `timeout-minutes` on the CI job. A runaway simulation should fail
    loudly rather than quietly spend an hour.
*   Bound the run in the testbench itself, so it reports what it got to rather
    than hanging with no output.

## Seeing the circuit (schematic)

```console
$ c4o-core schematic
[INFO] Wrote build/schematic.svg
[INFO] Wrote build/blocks/: 6 diagrams, top.svg first
```

An SVG of the design: flops, adders, muxes, carrying the names from your
source. Any browser or editor opens it, and GitHub renders it inline.

**It is not `synth`'s output.** That command runs a full synthesis and leaves
a Yosys JSON netlist — hundreds of technology cells, from which nobody has
ever learned anything about their own design. `schematic` stops after
`proc; opt`, which is where the design still looks like the code it came
from:

```
read_verilog <VERILOG_FILES>; hierarchy -top <DESIGN_NAME>; proc; opt;
show -format svg -viewer none -prefix build/schematic A:top
```

`hierarchy -auto-top` is used when `DESIGN_NAME` is absent. Testbenches are
not drawn — `schematic` reads `VERILOG_FILES` only, as `synth` and `lint` do.

**One module: the top.** `show` draws everything selected and yosys refuses SVG
for more than one module, so a design with a submodule needs the selection that
`A:top` provides. Submodules appear as boxes, not as their own drawings. To see
one of them instead, run yosys yourself and name it.

SVG rather than the JSON, deliberately: a file every browser and editor opens
beats one that needs a particular extension installed.

**The block diagrams.** In a design built from blocks, the schematic's muxes and
flops bury the blocks, and no single picture of a deep design stays readable.
So `schematic` also writes the netlist as `build/schematic.json` and, when the
top instantiates a module of the design, draws one level at a time into
`build/blocks/`:

*   `top.svg`: one box per instance, labelled with its instance and module
    names, one dashed box for the top's own logic, and an edge for every net two
    of them share. An input that reaches every block, such as a clock or a
    reset, becomes a caption rather than an edge into each.
*   Every block links to a file of its own: another block diagram for a module
    with submodules, with an "up to" link back, or that module's schematic
    for one without. Two parameterisations of one module are two files
    (`io_generic_fifo.svg`, `io_generic_fifo_2.svg`).

The links work when the SVG is opened directly, which is what clicking a
diagram on the `site` page does. A top with no submodule gets no block diagram.

## Before the physical flow (check)

`check` is the pre-flight for the physical design flow. It reads values, not
just key names, because the mistakes worth catching are all in the values:

```console
$ c4o-core check
[ERROR] DESIGN_NAME is 'my_cpu', but no module by that name is declared in
        VERILOG_FILES. Declared there: counter.
```

That is the first wall anyone hits after putting their own design into a
template. Without this it surfaces minutes later, as a Yosys error about a
module it cannot find, or as a LibreLane run that dies partway through.

Three checks, and the third is deliberately weaker than the other two:

| Check | On failure |
|---|---|
| `DESIGN_NAME` names a module declared in `VERILOG_FILES` | **error** |
| `DIE_AREA` is four numbers, second corner larger | **error** |
| `CLOCK_PORT` appears somewhere in `VERILOG_FILES` | **warning** |

Which floorplan key is *required* follows `FP_SIZING`: `absolute` needs
`DIE_AREA`, `relative` needs `FP_CORE_UTIL` and never reads `DIE_AREA`.
Demanding both refused a config LibreLane would have run. `DIE_AREA` is still
checked whenever it is present, since LibreLane validates its shape either way.

**A false alarm here is worse than no check**, because it blocks a design that
would have built. So only the two things decidable without parsing Verilog
properly are errors. Proving a name really *is* a port means reading a port
list — which spans lines, carries attributes, and can come out of a macro. What
can be said without a parser is that a name absent from the RTL entirely is not
a port of it, and that is the typo the warning catches:

```console
[WARN] CLOCK_PORT is 'wall_clock', which does not appear anywhere in
       VERILOG_FILES. The flow will not find a clock to constrain.
[INFO] Configuration verified for the physical design flow.
[INFO] This step builds no layout; LibreLane does that.
```

Module detection strips comments first, so a commented-out module does not
count as one.

## Reading a finished run

LibreLane computes area, timing, power and much else, then writes all of it to a
single 300-key `metrics.json` that nobody opens. `report` pulls out the handful
that answer *is my design any good*:

```console
$ c4o-core report

  blinky

  die              69.5 x 80.2 um  (5573 um^2)
  utilization      57.1%
  standard cells   198
  cell classes     57 logic, 46 well taps, 35 timing-repair buffers, 27 inverters, 26 sequential, 7 clock buffers
  setup slack      +4.70 ns  (0 violations)
  hold slack       +0.11 ns  (0 violations)
  power            0.248 mW  (nom_tt_025C_1v80)
  signoff          clean  (Magic DRC, KLayout DRC, LVS, antenna, XOR)
  lint warnings    0
  layout           runs/blinky_run/final/render/blinky.png
```

Those are one example design's numbers, from one PDK version; the lines are
what to read.

With no argument it takes the newest `metrics.json` under `runs/` or
`build/runs/`; name a file to pick a different run. A row it has no metric for
is left out rather than printed as a blank or a zero.

### Can it be made?

The numbers above answer *is my design any good*. The `signoff` row answers the
other half — *can it be manufactured* — by reading the checks LibreLane's
Classic flow runs after routing: Magic DRC, KLayout DRC, LVS, antenna and XOR.

Every one of those errors the flow by default (`ERROR_ON_MAGIC_DRC` and its
siblings all default to `True`), so a run that got as far as writing a
`metrics.json` has already passed them.

The metric keys are the ones a real run emits — antenna, for instance, comes
from `OpenROAD.CheckAntennas` rather than from a checker step the Classic flow
does not run. Without this row nothing states the result, and
the reader is left inferring it from the absence of a crash.

When something *is* wrong — a run stopped part-way, or the checks were turned
down to warnings — it names what, instead of printing a column of zeroes with
one non-zero buried in it:

```console
  signoff   2 Magic DRC, 1 LVS
```

`clean` lists the checks it actually saw, because the word is only as strong as
that list. A check the run never reported is not a check that passed.

### The layout it drew

`KLayout.Render` produces a PNG of the finished layout on every run and leaves
it in the run directory, where nobody goes looking. The `layout` row is its
path — `final/render/<design>.png`, falling back to the render step's own
directory. It appears only when the `metrics.json` sits where a run left it,
at `<run>/final/metrics.json`.

Three details worth knowing:

*   **Slack is the worst corner.** LibreLane writes every timing metric once per
    corner and again with no `__corner:` suffix; the bare key is already the
    worst of them, and that is what is shown.
*   **Cell count excludes filler.** `design__instance__count` includes the fill
    and tap cells the flow adds, which outnumber the design's own in a small
    chip. The row shows `design__instance__count__stdcell`.
*   **Cell classes say what those cells are.** LibreLane files every cell under
    a class (`design__instance__count__class:*`); the row lists them largest
    first, fill left out, and in a real run they add up to `standard cells`.
    It is how you see that 88 of blinky's 198 are buffers and taps the flow
    added, not logic the RTL asked for.

It is informational and never fails: closing timing is iterative, LibreLane does
not treat a violation as fatal either, and the checks that *are* fatal have
already had their say by the time this runs.

### One page to share (site)

`site` puts the rows above, the layout render, `build/schematic.svg` and the
cocotb results (`build/cocotb-results.xml`, and `build/cocotb-gl-results.xml`
from a `--netlist` run) on one page, `build/site/index.html`, with the images
copied next to it. The directory is the whole site: upload it with
`actions/upload-pages-artifact` and GitHub Pages serves it.

Each part appears when the file behind it exists, so the page works after
`cocotb` alone; until a run directory exists, the heading says what `make gds` adds. The directory is emptied first, so a render from an earlier run
cannot be published under a later one. Each cocotb table carries the run's seed,
which is what reproduces a failure the page shows. The heading says when the
page was built (`SOURCE_DATE_EPOCH` pins it), and on GitHub Actions also links
the commit and the run it came from -- provided `GITHUB_SERVER_URL`,
`GITHUB_REPOSITORY`, `GITHUB_SHA` and `GITHUB_RUN_ID` reach the container, which
`docker run` does only when asked with `-e`. The verdict chips are one per
thing that ran; "Timing met" needs both setup and hold slack non-negative.

The page is laid out to be shared -- a portfolio piece more than a CI log. The
layout render sits beside the title, captioned with the die size, the cell count
and the PDK. Under the title, on Actions, a byline names the repository's owner;
`"//DESCRIPTION"` from the config says what the design is, and the buttons are
what a visitor does with a chip, most wanted first: **Open in 3D**, **View
source** (on Actions), and the GDS with its size. The summary writes the die as
`69.5 × 80.2 µm`, groups thousands, and colours a non-negative slack green. It
adds what a physical designer asks next: the clock (config's `CLOCK_PERIOD`),
the core that utilization is a share of (`design__core__bbox` -- not the die
beside it), how many of the standard cells are well taps, and the reg-to-reg
setup and hold slack (`timing__*_r2r__ws`) beside the worst. The
sections then run summary, tests, block diagram, waveform, signoff, timing,
area and power. The RTL schematic is a link under the block diagram when there
is one, since past a few hundred cells it is a texture rather than a picture
and the blocks already click through to each module's own; without a block
diagram it is a section of its own, folded into a `<details>`. When both an RTL and a gate-level cocotb run exist they
share one table, a column each, which is what makes "the same tests still pass
after synthesis" visible. The page carries Open Graph tags for link previews;
`og:image` is the layout, as a `summary` card, and only on Actions, where the Pages URL it must be
absolute against is known (`https://<owner>.github.io/<repo>/`).

Every picture on the page zooms in place: the + / − / reset buttons, Ctrl +
wheel or a trackpad pinch to zoom around the pointer, drag to pan. A plain
wheel still scrolls the page. A click that did not drag opens the file itself. Each also has a **Download SVG** link, for a slide or a report.

Like `report`, it shows a failed test and still succeeds: the command that ran
the test is the gate, not the page.

From the run directory's own reports, when the `metrics.json` sits at
`<run>/final/`, it adds four more sections:

| Section | Read from | What to keep in mind |
|---|---|---|
| Signoff checks | `metrics.json` | One row per check, with its error count. Under it, the max slew, capacitance and fanout violations (`design__max_*_violation__count`) and the worst static IR drop (`ir__drop__worst`), which the flow reports without stopping on, so they never turn the "Signoff clean" chip red; and a line naming what it does not analyse: electromigration, crosstalk, dynamic IR. |
| Worst setup path | `*-openroad-stapostpnr/<corner>/max.rpt` | The corner whose `timing__setup__ws__corner:*` is lowest, and that report's first path. Read into one sentence (from where to where, the clock period and MHz, when the clock reaches the start point, how long logic and wires take, and when the data arrives against its deadline) and a bar from the launch edge to the capture clock in four parts, each a number in the report: launch clock latency (or input delay), logic and wires, slack, and what the capture side holds back (setup time or output delay, plus uncertainty). The corner is in words (`max_ss_100C_1v60` is maximum wire RC, slow transistors, 100 °C, 1.60 V). On an I/O path it says so and gives the reg-to-reg slack, and it gives the worst clock skew (`clock__skew__worst_setup`); the report as OpenSTA wrote it stays one click away. A path that cannot be read that way -- a field missing, or a launch edge off zero, where the gap to the capture edge is not the clock period -- shows the report alone. Left out if that corner has no `max.rpt`, rather than showing a path that is not the worst one. |
| Area | synthesis's `reports/stat.json` and `metrics.json` | One bar of the standard-cell area after routing, split into synthesis's flip-flops and logic and the difference place and route added (a difference, since routing also resizes cells); then one bar of the cell count by class, split into what synthesis produced, what the flow added (taps, timing-repair and clock buffers and inverters) and anything unclassified. Not per module: LibreLane's default `SYNTH_HIERARCHY_MODE` is `flatten`, so module boundaries are gone by then. |
| Power | `<DEFAULT_CORNER>/power.rpt` | OpenSTA's sequential / combinational / clock split, as internal, switching and leakage, with groups at zero (a design with no macros or pads) left out and each bar the group's share of the total, on a track that stands for the whole. The activity is OpenSTA's default, not a simulation's, so it shows where power goes, not what a workload draws. |

The power table reads `power.rpt` rather than the bare `power__*` metrics
because those carry one corner's numbers without naming it. `report`'s `power`
row does the same and names the corner. Without a run directory to find
`power.rpt` in, it falls back to the metric and says `(corner not named)`.
When the power table is on the page, the summary drops its `power` row.

The run's final GDS, `<run>/final/gds/*.gds`, is copied next to the page and
linked from the heading as a download. When config's `PDK` is one
[Tiny Tapeout's GDS viewer](https://github.com/TinyTapeout/tinytapeout_gds_viewer)
has layers for — `sky130A`, `ihp-sg13g2`, `gf180mcuD` — the page also links it
there, to open in 3D. The viewer fetches the GDS by URL, so that link appears
only once the page is served over HTTP(S), as on GitHub Pages; opened straight
from disk it stays hidden. Serving `build/site` with `python3 -m http.server`
works too: the viewer accepts `localhost` URLs.

Two more sections, when their files exist:

*   **Block diagram**: `build/blocks/top.svg`, with every file it links to
    copied next to it, so clicking through works once published.
*   **Waveform**: the signals `"//WAVE_SIGNALS"` names, drawn across the whole
    run from the newest `build/*.vcd` that declares all of them, so a second
    testbench's VCD being newer is no error. When no VCD declares them all,
    `site` fails, lists every name missing from the newest one, and lists up to 20
    names it does declare, since a typo is the usual cause. No VCD yet, as after `cocotb` alone,
    leaves the section out.

## Generated register blocks

None of the tools in this image read SystemVerilog with unpacked structs, which
is what `peakrdl regblock` emits:

```
yosys:     ERROR: Only PACKED supported at this time
iverilog:  sorry: Unpacked structs not supported.
```

`sv2v` is the step between. One `.rdl` file, through to gates and to a register
model that cannot drift from it:

```bash
peakrdl regblock regs.rdl -o rdl --cpuif apb3-flat
sv2v rdl/regs_pkg.sv rdl/regs.sv > rdl/regs.v      # now everything here reads it
peakrdl pyuvm    regs.rdl -o rdl/regs_ral.py       # the same source, as pyuvm
```

`sv2v` writes signed one-bit zeroes into wider assignments, which verilator
calls `WIDTHEXPAND`, so a config that lints generated Verilog wants
`LINTER_DISABLE_WARNINGS: [WIDTHEXPAND]`.
