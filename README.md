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
| `cocotb` | Runs cocotb tests — Python coroutines driving the RTL — on `VERILOG_FILES` + `COCOTB_TESTS`. |
| `gatesim` | Simulates the **synthesised netlist** against the PDK cell models, on `GATE_TESTS`. |
| `synth` | Performs logic synthesis using Yosys on `VERILOG_FILES` only. Generates `build/synthesis.json`. |
| `pdk` | Installs/Enables the Sky130 PDK via Ciel into `./pdks`. |
| `check` | Validates the configuration for the physical design flow. Produces no layout — LibreLane does that. Available as `gds` too, the name it had before. |
| `report` | Summarises a finished LibreLane run: area, utilization, cell count, timing slack, power. |

## ⚙️ Configuration

`c4o-core` looks for `config.yaml`, `config.yml`, or `config.json` in your workspace, in that order.

**This is a [LibreLane](https://github.com/librelane/librelane) configuration file.** The same file drives both this engine and the physical design flow, so the variable names are LibreLane's — not a parallel vocabulary of our own. `c4o-core` simply reads the subset it needs.

Simulation is outside LibreLane's scope, so testbenches are the one thing it has no variable for. That key is written with a `//` prefix, which LibreLane ignores outright, keeping the shared file valid under its validation:

```yaml
DESIGN_NAME: counter
VERILOG_FILES:
  - dir::src/**/*.v

# Simulation only. The '//' prefix is what makes LibreLane skip this key.
"//TEST_FILES":
  - dir::test/*.v
```

Glob patterns work (`**/*.v` matches recursively), as does LibreLane's `dir::` prefix, which marks a path as relative to the design directory.

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
DIE_AREA: [0, 0, 100, 100]
FP_CORE_UTIL: 40
FP_SIZING: absolute
```

### Key Configuration Options

*   **`VERILOG_FILES`**: List of synthesizable Verilog source files. Supports glob patterns.
*   **`//TEST_FILES`**: List of simulation testbench files (non-synthesizable). Plain `TEST_FILES` is also read, but only the prefixed spelling is silent under LibreLane's strict validation.
*   **`//SIM_TOP`**: Testbench module to elaborate as the simulation root. Required once `//TEST_FILES` resolves to more than one file — see below.
*   **`//COCOTB_TESTS`**: Python test files for the `cocotb` command. Supports globs.
*   **`//GATE_TESTS`**: Gate-level testbench files for `gatesim`. Supports globs.
*   **`//GATE_TOP`**: Gate-level testbench module to elaborate. Required once `//GATE_TESTS` resolves to more than one file.
*   **`VERILOG_INCLUDE_DIRS`**: List of directories containing Verilog include files (`.vh`, `.h`).
*   **`DESIGN_NAME`**: Top-level module name for synthesis.

### A pattern that matches nothing is an error

Every configured pattern must match at least one file. A renamed directory or a
typo used to be a warning, and `sim` would compile the RTL alone and exit 0 —
green CI, nothing verified. It now fails.

For the same reason, `sim` refuses to run without a testbench at all.

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

## 📊 Reading a finished run

LibreLane computes area, timing, power and much else, then writes all of it to a
single 300-key `metrics.json` that nobody opens. `report` pulls out the handful
that answer *is my design any good*:

```console
$ c4o-core report

  blinky

  die              100 x 100 um  (10000 um^2)
  utilization      29.2%
  standard cells   243
  setup slack      +4.69 ns  (0 violations)
  hold slack       +0.11 ns  (0 violations)
  power            0.292 mW
  lint warnings    441
```

With no argument it takes the newest `metrics.json` under `runs/` or
`build/runs/`; name a file to pick a different run. Two details worth knowing:

*   **Slack is the worst corner.** LibreLane writes every timing metric once per
    corner and again with no `__corner:` suffix; the bare key is already the
    worst of them, and that is what is shown.
*   **Cell count excludes filler.** `design__instance__count` counted 787 for the
    run above, but 544 of those were fill cells. The 243 is
    `design__instance__count__stdcell`.

It is informational and never fails: closing timing is iterative, and LibreLane
does not treat a violation as fatal either.

## 🏗 Architecture

*   **System Path**: The EDA tools and python scripts are installed in `/opt/c4o-core`.
*   **User Path**: Users should mount their workspace to `/workspace`.
*   **PDK Path**: The `pdk` command installs artifacts into the user's volume (`./pdks`), ensuring persistence across container runs.

## 📦 Included Tools

*   **Yosys**: Open Synthesis Suite
*   **Verilator**: High-performance Verilog simulator/linter
*   **Icarus Verilog**: Verilog simulation and synthesis tool
*   **Ciel**: PDK Version Manager
*   **Cocotb**: Coroutine based cosimulation library (see the `cocotb` command)

## License
This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

*Note: This framework invokes various third-party open-source EDA tools (Yosys, Verilator, LibreLane, etc.), which are distributed under their respective licenses.*
