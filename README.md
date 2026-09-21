# c4o-core (ChipForAll Engine)

![CI Status](https://github.com/anlit75/c4o-core/actions/workflows/ci.yml/badge.svg)
![Docker Image Version](https://img.shields.io/github/v/release/anlit75/c4o-core?label=version)
[![License](https://img.shields.io/github/license/anlit75/c4o-core)](LICENSE)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/anlit75/c4o-core)

**c4o-core** is the underlying EDA toolchain engine for the [ChipForAll](https://github.com/anlit75/ChipForAll) project.
It packages open-source silicon tools into a unified, Python-driven Docker container.

> **Note**: If you are a beginner, please use the [ChipForAll Template](https://github.com/anlit75/ChipForAll) instead of using this engine directly.

## 🚀 Quick Start

You can run `c4o-core` directly via Docker.
Mount your current directory (`$(PWD)`) to `/workspace` (or any workspace path) to persist artifacts.

```bash
docker run --rm -v $(PWD):/workspace -w /workspace ghcr.io/anlit75/c4o-core:latest <command>
```

## 🛠 Command Reference

The engine supports the following commands via its Python entrypoint:

| Command | Description |
|---|---|
| `lint` | Runs Verilator linting checks on `VERILOG_FILES`. |
| `sim` | Compiles and runs simulation using Icarus Verilog on `VERILOG_FILES` + `TEST_FILES`. |
| `cocotb` | Runs cocotb tests — Python coroutines driving the RTL — on `VERILOG_FILES` + `COCOTB_TESTS`. `--netlist` runs the same tests against the synthesised gates. |
| `gatesim` | Simulates the **synthesised netlist** against the PDK cell models, on `GATE_TESTS`. |
| `synth` | Performs logic synthesis using Yosys on `VERILOG_FILES` only. Generates `build/synthesis.json`. |
| `schematic` | Draws the circuit as `build/schematic.svg` — the RTL as written, not the synthesised netlist. |
| `pdk` | Installs/Enables the Sky130 PDK via Ciel into `./pdks`. |
| `check` | Validates the configuration for the physical design flow, values included. Produces no layout — LibreLane does that. Available as `gds` too, the name it had before. |
| `report` | Summarises a finished LibreLane run: area, utilization, cell count, timing slack, power, and the DRC/LVS/antenna signoff result. |

## ⚙️ Configuration

`c4o-core` looks for `config.yaml`, `config.yml`, or `config.json` in your workspace, in that order.

**This is a [LibreLane](https://github.com/librelane/librelane) configuration file.** The same file drives both this engine and the physical design flow, so the variable names are LibreLane's — not a parallel vocabulary of our own. `c4o-core` simply reads the subset it needs.

Simulation is outside LibreLane's scope, so testbenches are the one thing it has no variable for. That key is written with a `//` prefix, which LibreLane ignores outright, keeping the shared file valid under its validation:

```yaml
DESIGN_NAME: counter
VERILOG_FILES:
  - dir::src/counter.v

# Simulation only. The '//' prefix is what makes LibreLane skip this key.
"//TEST_FILES":
  - dir::test/*.v
```

LibreLane's `dir::` prefix marks a path as relative to the design directory, and works on any of these keys.

**Globs work on the `//` keys, not on `VERILOG_FILES`.** This engine expands them everywhere, but `VERILOG_FILES` belongs to LibreLane, which validates each entry as a literal path and does not expand `**`. A config with `dir::src/**/*.v` therefore lints, simulates and synthesises here, and then fails in the physical flow:

```console
ERROR  Path provided for variable 'VERILOG_FILES[0]' is invalid:
       '/workspace/src/**/*.v' does not exist
```

List source files one per line. The `//` keys are this engine's own, so `dir::test/*.v` and `dir::test/**/*.py` are fine there.

### Full Example (RTL + GDS)

Everything the physical design flow needs. YAML is preferred because it takes comments; JSON works too, with the same keys.

```yaml
# ---- what you normally change ----
DESIGN_NAME: counter
VERILOG_FILES:
  - dir::src/counter.v
  - dir::src/alu.v
"//TEST_FILES":
  - dir::test/tb_counter.v
VERILOG_INCLUDE_DIRS:
  - dir::src/include
CLOCK_PORT: clk
CLOCK_PERIOD: 10.0

# ---- keep these unless you know what you are doing ----
PDK: sky130A
STD_CELL_LIBRARY: sky130_fd_sc_hd
FP_CORE_UTIL: 40
FP_SIZING: relative
```

`FP_SIZING: relative` sizes the die from `FP_CORE_UTIL`, so it grows with the design. For a fixed die, set `FP_SIZING: absolute` and add `DIE_AREA: [0, 0, w, h]` instead.

### Key Configuration Options

*   **`VERILOG_FILES`**: List of synthesizable Verilog source files, one path per entry — see the note above on globs.
*   **`//TEST_FILES`**: List of simulation testbench files (non-synthesizable). Plain `TEST_FILES` is also read, but only the prefixed spelling is silent under LibreLane's strict validation.
*   **`//SIM_TOP`**: Testbench module to elaborate as the simulation root. Required once `//TEST_FILES` resolves to more than one file — see below.
*   **`//COCOTB_TESTS`**: Python test files for the `cocotb` command. Supports globs.
*   **`//GATE_TESTS`**: Gate-level testbench files for `gatesim`. Supports globs.
*   **`//GATE_TOP`**: Gate-level testbench module to elaborate. Required once `//GATE_TESTS` resolves to more than one file.
*   **`VERILOG_INCLUDE_DIRS`**: List of directories containing Verilog include files (`.vh`, `.h`).
*   **`DESIGN_NAME`**: Top-level module name for synthesis.

### A pattern that matches nothing is an error

Every configured pattern must match at least one file, and `sim` refuses to run
without a testbench at all. A renamed directory or a typo would otherwise leave
`sim` compiling the RTL alone and exiting 0 — green CI, nothing verified.

### More than one testbench

Icarus elaborates every module nobody instantiates as its own root, and the
first `$finish` ends the whole simulation — so a second testbench ran partway
and was cut off, with nothing in the exit code to show for it. Name the one to
run and it is passed to `iverilog -s`:

```yaml
"//TEST_FILES":
  - dir::test/*.v
"//SIM_TOP": tb_counter
```

With a single testbench file, `//SIM_TOP` is optional.

Everything else in the file belongs to LibreLane; see its documentation for the full list.

## 🐍 Python testbenches (cocotb)

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
    Adding `` `timescale 1ns/1ps `` to the top of the file fixes it.

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

## 🔬 Simulating the gates (gatesim)

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
two. Set `PDK_ROOT` if the PDK lives outside `./pdks`.

**The gate-level testbench has to be a separate file from the RTL one.**
Synthesis resolves parameters, so a testbench that shrinks the design by
overriding one — the usual trick for keeping simulations short — has nothing
left to override. Drive the real ports at their real width.

### It can be slow, and how slow is your design's business

Gate-level cost scales with simulated cycles times cell count, and both can be
large. Measured on ChipForAll's blinky: **281 seconds**, because its clock
divider is 26 bits deep and one output toggle takes 2\*\*25 cycles. A deep
divider is the most common beginner design there is, so this is not an unusual
case.

Two consequences worth planning for:

*   Put a `timeout-minutes` on the CI job. A runaway simulation should fail
    loudly rather than quietly spend an hour.
*   Bound the run in the testbench itself, so it reports what it got to rather
    than hanging with no output.

## 🖼 Seeing the circuit (schematic)

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
show -format svg -viewer none -prefix build/schematic
```

`hierarchy -auto-top` is used when `DESIGN_NAME` is absent. Testbenches are
not drawn — `schematic` reads `VERILOG_FILES` only, as `synth` and `lint` do.

SVG rather than the JSON, deliberately: a file every browser and editor opens
beats one that needs a particular extension installed.

## ✈️ Before the three-minute run (check)

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
```

Module detection strips comments first, so a commented-out module does not
count as one.

## 📊 Reading a finished run

LibreLane computes area, timing, power and much else, then writes all of it to a
single 300-key `metrics.json` that nobody opens. `report` pulls out the handful
that answer *is my design any good*:

```console
$ c4o-core report

  blinky

  die              69.485 x 80.205 um  (5573.04 um^2)
  utilization      57.1%
  standard cells   198
  setup slack      +4.70 ns  (0 violations)
  hold slack       +0.11 ns  (0 violations)
  power            0.290 mW
  signoff          clean  (Magic DRC, KLayout DRC, LVS, antenna, XOR)
  lint warnings    0
  layout           runs/blinky_run/final/render/blinky.png
```

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

The metric keys are the ones a real LibreLane 3.0.14 run emits — antenna, for
instance, comes from `OpenROAD.CheckAntennas` rather than from a checker step
the Classic flow does not run. Without this row nothing states the result, and
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

Two details worth knowing:

*   **Slack is the worst corner.** LibreLane writes every timing metric once per
    corner and again with no `__corner:` suffix; the bare key is already the
    worst of them, and that is what is shown.
*   **Cell count excludes filler.** `design__instance__count` includes the fill
    and tap cells the flow adds, which outnumber the design's own in a small
    chip. The row shows `design__instance__count__stdcell`.

It is informational and never fails: closing timing is iterative, LibreLane does
not treat a violation as fatal either, and the checks that *are* fatal have
already had their say by the time this runs.

## 🏗 Architecture

*   **System Path**: The EDA tools and python scripts are installed in `/opt/c4o-core`.
*   **User Path**: Users should mount their workspace to `/workspace`.
*   **PDK Path**: The `pdk` command installs artifacts into the user's volume (`./pdks`), ensuring persistence across container runs.

## 📦 Included Tools

*   **Yosys**: Open Synthesis Suite
*   **Verilator**: High-performance Verilog simulator/linter
*   **Icarus Verilog**: Verilog simulation and synthesis tool
*   **Graphviz**: renders the `schematic` command's SVG (yosys `show` shells out to `dot`)
*   **Ciel**: PDK Version Manager
*   **Cocotb**: Coroutine based cosimulation library (see the `cocotb` command)

## License
This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

*Note: This framework invokes various third-party open-source EDA tools (Yosys, Verilator, LibreLane, etc.), which are distributed under their respective licenses.*
