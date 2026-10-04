# c4o-core (ChipForAll Engine)

![CI Status](https://github.com/anlit75/c4o-core/actions/workflows/ci.yml/badge.svg)
![Docker Image Version](https://img.shields.io/github/v/release/anlit75/c4o-core?label=version)
[![License](https://img.shields.io/github/license/anlit75/c4o-core)](LICENSE)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/anlit75/c4o-core)

**c4o-core** is the underlying EDA toolchain engine for the [ChipForAll](https://github.com/anlit75/ChipForAll) project.
It packages open-source silicon tools into a unified, Python-driven Docker container.

> **Note**: This is an internal component of [ChipForAll](https://github.com/anlit75/ChipForAll), documented for the people who maintain it and for anyone reading an error it printed. To use it, start from the ChipForAll template; its `Makefile` is the reference for how this image is meant to be called.

## 🚀 Quick Start

You can run `c4o-core` directly via Docker.
Mount your current directory to `/workspace` (or any workspace path) to persist artifacts, and run as yourself so they are not owned by root:

```bash
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/workspace -w /workspace ghcr.io/anlit75/c4o-core:latest <command>
```

The examples below shorten that line to `c4o-core <command>`. The image is built for `amd64` only; on an `arm64` machine Docker runs it emulated.

Every release publishes four tags:

| tag | for |
|---|---|
| `X.Y.Z` | a build that will never change under you |
| `X.Y` | **what a repository should pin.** Patches arrive without editing anything while `X.Y` is the newest minor (see below); new behaviour only arrives with a new minor |
| `X` | the current major |
| `latest` | one-off runs like the line above. Nothing should pin it |

**Only the newest minor gets fixes.** Releases come from `main` alone, with no
maintenance branches, so once `X.Y+1` is out `X.Y` stops moving: a fix made
after that reaches you only when you move your pin up.

The current numbers are on the [releases page](https://github.com/anlit75/c4o-core/releases).

## 🛠 Command Reference

The engine supports the following commands via its Python entrypoint:

| Command | Description |
|---|---|
| `lint` | Runs Verilator linting checks on `VERILOG_FILES`. |
| `sim` | Compiles and runs simulation using Icarus Verilog on `VERILOG_FILES` + `TEST_FILES`. |
| `cocotb` | Runs cocotb tests — Python coroutines driving the RTL — on `VERILOG_FILES` + `COCOTB_TESTS`. `--netlist` runs the same tests against the synthesised gates. |
| `gatesim` | Simulates the **synthesised netlist** against the PDK cell models, on `GATE_TESTS`. |
| `synth` | Performs logic synthesis using Yosys on `VERILOG_FILES` only. Generates `build/synthesis.json`. One fixed script -- see [docs/commands.md](docs/commands.md#synth-and-systemverilog-in-every-command). |
| `schematic` | Draws the circuit as `build/schematic.svg` — the RTL as written, not the synthesised netlist. |
| `pdk` | Installs/Enables the Sky130 PDK via Ciel into `$PDK_ROOT`, or `./pdks` when that is unset. |
| `check` | Validates the configuration for the physical design flow, values included. Produces no layout — LibreLane does that. `gds` is an alias. |
| `report` | Summarises a finished LibreLane run: area, utilization, cell count, timing slack, power, and the DRC/LVS/antenna signoff result. |
| `site` | Writes `build/site/`, one page for GitHub Pages: what `report` prints, signoff checks, the worst setup path, area and power breakdowns, the layout render, the schematic and every cocotb verdict. |

What each one does beyond this line, and why, is in [docs/commands.md](docs/commands.md).

The CI of a repository made from the ChipForAll template is here too, as actions that its workflow calls: [docs/actions.md](docs/actions.md).

## ⚙️ Configuration

`c4o-core` looks for `config.yaml`, `config.yml`, or `config.json` in your workspace, in that order.

**This is a [LibreLane](https://github.com/librelane/librelane) configuration file.** The same file drives both this engine and the physical design flow, so the variable names are LibreLane's — not a parallel vocabulary of our own. `c4o-core` simply reads the subset it needs.

Simulation is outside LibreLane's scope, so testbenches are the one thing it has no variable for. Those keys are written with a `//` prefix, which LibreLane ignores outright, keeping the shared file valid under its validation.

LibreLane's `dir::` prefix marks a path as relative to the design directory, and works on any key.

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

### The keys this engine reads

| Key | What it is |
|---|---|
| `DESIGN_NAME` | the top module's name |
| `VERILOG_FILES` | synthesisable sources, one literal path per entry |
| `VERILOG_INCLUDE_DIRS` | directories holding `.vh` / `.h` includes |
| `"//TEST_FILES"` | Verilog testbenches for `sim`. Globs work. Plain `TEST_FILES` is read too, but only the prefixed spelling is silent under LibreLane's validation |
| `"//SIM_TOP"` | which testbench module to elaborate. Required once `"//TEST_FILES"` matches more than one file |
| `"//COCOTB_TESTS"` | Python testbenches for `cocotb`. Globs work |
| `"//GATE_TESTS"` / `"//GATE_TOP"` | the same two, for `gatesim` |
| `CLOCK_PORT` / `CLOCK_PERIOD` | the clock to constrain, and its period in ns |
| `PDK` / `STD_CELL_LIBRARY` | needed by `gatesim`, `cocotb --netlist` and `pdk` |
| `"//DESCRIPTION"` | one line saying what the design is, under the title of `site`'s page and in its link preview |
| `"//WAVE_SIGNALS"` | signals `site` draws from `sim`'s VCD, dotted from the testbench top (`tb_blinky.uut.count`). A name the VCD does not declare fails `site` |

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
*   **pyuvm**: the UVM in Python, on top of cocotb — `import pyuvm` in a `COCOTB_TESTS` file and it works
*   **sv2v**: SystemVerilog to Verilog-2005, for sources the tools above will not read
*   **PeakRDL**: `regblock` generates a register block from SystemRDL, `pyuvm` generates the matching register model ([how the three fit together](docs/commands.md#generated-register-blocks))

## Releasing

Nobody pushes a tag. Merging anything to `main` updates a **Release PR** holding
the next version and its CHANGELOG entry, both computed from the commit titles
— which is why this repository writes them as
[Conventional Commits](https://www.conventionalcommits.org/): `feat:` moves the
minor, `fix:` the patch.

Merging that Release PR is the release. The tag, the GitHub release and the
four images above all follow from it.

The PR in the middle is deliberate. A version and a changelog derived from
commit messages are worth reading before they are permanent, and a wrong one is
a pull request to close rather than a release to yank.

It needs `RELEASE_PLEASE_TOKEN`: a fine-grained PAT scoped to this repository
with **Contents: read and write** and **Pull requests: read and write**. The
automatic `GITHUB_TOKEN` will not do, because a tag pushed with it does not
trigger other workflows — the tag would appear and no image would ever be
built.

## License
This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

*Note: This framework invokes various third-party open-source EDA tools (Yosys, Verilator, LibreLane, etc.), which are distributed under their respective licenses.*
