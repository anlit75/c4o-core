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

`sim` and `cocotb` both accept `--if-configured`. The command then skips, with a message, when its own key is not set. `make all` uses it. It fails when neither `"//TEST_FILES"` nor `"//COCOTB_TESTS"` is set. Without the flag, a missing key is always an error.

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

### The waveform of a cocotb run

`make cocotb WAVES=1` writes `build/<DESIGN_NAME>.vcd` from the RTL run. The signal names start at the design: `counter.count`. Without `WAVES=1` nothing is dumped. The `--netlist` run never dumps. `site` does not read the file.

## Code coverage (coverage)

`coverage` shows how much of the RTL the Python tests run. It runs the `"//COCOTB_TESTS"` again on Verilator, with coverage counters in the model. Icarus has no code coverage.

It reads the same config as `cocotb`. It also applies `LINTER_DISABLE_WARNINGS`, because Verilator stops at a warning when it builds the design. It accepts `--if-configured`, as `cocotb` does. `make all` does not run it.

| Kind | What it counts |
|---|---|
| Block | Each block of code that ran. |
| Branch | Each side of an `if` or a `case`. |
| Toggle | Each signal bit that changed value. |
| User | Each `cover property`. It appears only when the design has one. |

Expression coverage and FSM coverage are not measured. The Verilator in the image does not have them.

The verdict stays with `cocotb`, which runs on Icarus. Verilator is 2-state, so a signal that reads `x` on Icarus before reset reads 0 here. A test can pass on one and fail on the other. A test that fails on Verilator does not fail `coverage`, because the run still wrote its numbers. A design that Verilator cannot build fails it.

A line counts as not reached when a line point or a branch point on it was not hit. A signal that never toggled does not add a line. The Toggle row and the module table show it.

`make coverage SEED=<n>` sets the seed, as `make cocotb SEED=<n>` does. The `report` action passes the seed of the RTL run, and the page says which seed the coverage run used.

Verilator overwrites `coverage.dat` on each run. The command renames it and merges the files with `verilator_coverage --write`. The numbers count the points of each kind in that file. They do not come from the lcov export, which mixes the three kinds.

| In `build/coverage/` | What it holds |
|---|---|
| `coverage.dat` | The merged counts. |
| `summary.json` | The numbers for each kind and each module, the files they cover, the seed, and the lines no test reached. |
| `results.xml` | The cocotb results of the Verilator run. `build/cocotb-results.xml` is not changed. |
| `build.log` | The Verilator build output. |

The numbers are for the files in `VERILOG_FILES`.

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

Without `"//GATE_TESTS"`, `gatesim` runs the `"//COCOTB_TESTS"` on the netlist. That is the run of `cocotb --netlist`, with the same verdict file. With neither key it fails and names both.

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

  die                56.375 x 67.095 um  (3782.48 um^2)
  utilization        56.6%
  instances          65 after synthesis, 113 after routing
  instance classes   32 logic, 27 well taps, 18 timing-repair buffers, 17 inverters, 16 sequential, 3 clock buffers
  drive strength     X1 0->18, X2 65->65, X16 0->3  (synthesis->routing)
  setup slack        +5.52 ns  (0 violations)
  hold slack         +0.11 ns  (0 violations)
  power              0.143 mW  (nom_tt_025C_1v80)
  signoff            clean  (DRC, LVS, antenna, XOR)
  lint warnings      0
  layout             runs/blinky_run/final/render/blinky.png
```

Those are one example design's numbers, from one PDK version; the lines are
what to read.

With no argument it takes the newest `metrics.json` under `runs/` or
`build/runs/`; name a file to pick a different run. A row it has no metric for
is left out rather than printed as a blank or a zero.

### Can it be made?

The numbers above answer *is my design any good*. The `signoff` row answers the
other half — *can it be manufactured* — by reading the checks LibreLane's
Classic flow runs after routing: DRC, LVS, antenna and XOR. DRC is Magic and KLayout together, and its count is their sum.

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
  signoff   2 DRC (Magic), 1 LVS
```

`clean` lists the checks it actually saw, because the word is only as strong as
that list. If only one DRC tool reported, it says `Magic DRC` or `KLayout DRC`. A check the run never reported is not a check that passed.

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
*   **Instances are counted twice.** The first number is `num_cells` from
    synthesis's `reports/stat.json`. The second is
    `design__instance__count__stdcell` after routing. Fill is not in it,
    because `design__instance__count` includes the fill and tap instances.
    Without a run directory, only the second number is shown.
*   **Instance classes say what the routed instances are.** LibreLane files
    every instance under a class (`design__instance__count__class:*`). The row
    lists them largest first, fill left out. They add up to the routed count.
    In one real run, 88 of 198 were buffers and taps that the flow added.
*   **Drive strength is the number that ends a cell's name.** `dfrtp_2` is X2. The row counts the cells at each strength after synthesis, then after routing. Synthesis's count comes from `reports/stat.json`. The routed count comes from the netlist in `final/nl/`, which lists every instance. Taps, decap, fill and antenna diodes have no logic function and are left out. A stage with no source is left out, not shown as zero.

It is informational and never fails: closing timing is iterative, LibreLane does
not treat a violation as fatal either, and the checks that *are* fatal have
already had their say by the time this runs.

### One page to share (site)

`site` puts the cocotb results, the run's numbers and the layout render on one page, `build/site/index.html`. The cocotb results are `build/cocotb-results.xml`, and `build/cocotb-gl-results.xml` from a `--netlist` run. The directory is the whole site. Upload it with `actions/upload-pages-artifact` and GitHub Pages serves it.

Each part appears when the file behind it exists, so the page works after `cocotb` alone. Until a run directory exists, the heading says what `make gds` adds. The directory is emptied first, so a render from an earlier run cannot be published under a later one. Each cocotb table carries the run's seed, which reproduces a failure the page shows. The heading says when the page was built (`SOURCE_DATE_EPOCH` pins it). On GitHub Actions it also links the commit and the run. That needs `GITHUB_SERVER_URL`, `GITHUB_REPOSITORY`, `GITHUB_SHA` and `GITHUB_RUN_ID` in the container, which `docker run` passes only with `-e`.

The page is laid out to be shared. The layout render sits beside the title, captioned with the die size, the instance count and the PDK. Under the title, on Actions, a byline names the repository's owner. `"//DESCRIPTION"` says what the design is. The buttons are **Open in 3D**, **View source** (on Actions) and the GDS with its size. The verdict chips are one per thing that ran. "Timing met" needs both setup and hold slack to be non-negative.

The sections run in this order:

| Section | Read from | What to keep in mind |
|---|---|---|
| Tests | the cocotb results | When an RTL and a gate-level run exist, they share one table with a column each. |
| Coverage | `build/coverage/summary.json` | A row for each kind with the points hit and the total. Then the numbers for each module in a collapsed list, the seed and the files covered. The lines no test reached are in `summary.json` only. The Summary gets a code coverage card with one stat for each kind. The card has no total across the kinds. Pass and fail stay with the Tests section. Without `make coverage`, the page has no Coverage section and no card. |
| Timing | `metrics.json`, and `config.json` of the newest `*-openroad-stapostpnr` step | Says whether timing is met. Gives the worst setup and hold slack over all corners, the violation count and the reg-to-reg slack. Then lists the constraints the run used: clock period, clock uncertainty, clock transition, timing derate and I/O delay. Each says whether `config.yaml` set it or the flow defaulted it. A constraint the run does not state is left out. |
| Area and instances | `metrics.json`, synthesis's `reports/stat.json` and `final/nl/*.nl.v` | Cards for die, core utilization and instances. One bar of the area after routing, split into synthesis's flip-flops and logic and the difference that place and route added. One bar of the instance count by class, split into what synthesis produced, what the flow added and anything unclassified. The headline is the count after synthesis. The count after routing comes second. A table of instances by drive strength follows, after synthesis and after routing, with a line saying what place and route added. The section names the standard cell library from the run's `config.json`. For a `sky130_fd_sc_*` library it adds that the library has a single threshold voltage. |
| Power | `<DEFAULT_CORNER>/power.rpt` | OpenSTA's sequential, combinational and clock split. States the corner, the clock frequency from `CLOCK_PERIOD` and the activity, which is OpenSTA's default and not a simulation's. |
| Signoff checks | `metrics.json` | DRC is one row, the sum of Magic and KLayout, and a failure names the tool: `3 (KLayout)`. LVS, antenna and XOR have rows of their own. Antenna says that OpenROAD checks it in this flow, not the DRC decks. |

The Summary holds three cards to a row. The first row is die, core utilization and instances. The second is the clock and one timing card, with the worst setup slack and the worst hold slack side by side. Each slack is green when it is not negative and red when it is. The third row is code coverage, total power and signoff. A card whose data is missing is left out.

Static IR drop (`ir__drop__worst`) sits under the signoff table when the run reports it, as mV and as a share of the supply. A run without the key gets no IR line. The page takes the supply from the voltage in `DEFAULT_CORNER`, as in `nom_tt_025C_1v80`, because the run's config holds no supply. Without a readable corner it shows mV alone. LibreLane sets no IR limit, so the page claims none.

The slack comes from the bare timing metrics, which hold the worst corner. The constraints come from the run, not from `config.yaml`, so an edit made after the run does not change what the page says.

The power table reads `power.rpt` rather than the bare `power__*` metrics because those carry one corner's numbers without naming it. `report`'s `power` row does the same and names the corner. Without a run directory to find `power.rpt` in, it falls back to the metric and says `(corner not named)`. When the power table is on the page, the summary drops its `power` row.

The page has no block diagram, no waveform and no schematic. `make schematic` writes `build/schematic.svg` for you to open. `make cocotb WAVES=1` writes the VCD. A `"//WAVE_SIGNALS"` key in an older config is ignored.

The run's final GDS, `<run>/final/gds/*.gds`, is copied next to the page and linked from the heading as a download. When config's `PDK` is one [Tiny Tapeout's GDS viewer](https://github.com/TinyTapeout/tinytapeout_gds_viewer) has layers for (`sky130A`, `ihp-sg13g2`, `gf180mcuD`), the page also links it there, to open in 3D. The viewer fetches the GDS by URL, so that link appears only once the page is served over HTTP(S), as on GitHub Pages. Serving `build/site` with `python3 -m http.server` works too.

Like `report`, `site` shows a failed test and still succeeds. The command that ran the test is the gate, not the page. The page carries Open Graph tags for link previews. `og:image` is the layout, and only on Actions, where the Pages URL is known.

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
