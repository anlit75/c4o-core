# c4o-core (ChipForAll Engine)

![CI Status](https://github.com/anlit75/c4o-core/actions/workflows/ci.yml/badge.svg)
![Docker Image Version](https://img.shields.io/github/v/release/anlit75/c4o-core?label=version)
[![License](https://img.shields.io/github/license/anlit75/c4o-core)](LICENSE)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/anlit75/c4o-core)

**c4o-core** is the EDA toolchain engine of the [ChipForAll](https://github.com/anlit75/ChipForAll) project. It puts open-source silicon tools into one Docker image, with a Python program that runs them.

> **Note**: This is a component of [ChipForAll](https://github.com/anlit75/ChipForAll). To use it, start from the ChipForAll template. This page is for when you must know what a command or a configuration key does, or what an error from the engine means.

## 🚀 Quick Start

You can run `c4o-core` directly with Docker. Mount your current directory at `/workspace` (or a different workspace path) to keep the files that it writes. Run it as yourself, so that root does not own those files:

```bash
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/workspace -w /workspace ghcr.io/anlit75/c4o-core:latest <command>
```

The examples below write that line as `c4o-core <command>`. The image is built for `amd64` only. On an `arm64` machine, Docker runs it emulated.

Each release publishes four tags:

| tag | for |
|---|---|
| `X.Y.Z` | A build that never changes. |
| `X.Y` | **The tag that a repository pins.** Patches arrive with no edit while `X.Y` is the newest minor (see below). New behaviour arrives only with a new minor. |
| `X` | The current major. |
| `latest` | One-time runs such as the line above. Do not pin it. |

**Only the newest minor gets fixes.** Releases come from `main` only, and there are no maintenance branches. Thus `X.Y` stops when `X.Y+1` is released. A later fix reaches you only when you move your pin up.

The current numbers are on the [releases page](https://github.com/anlit75/c4o-core/releases).

## 🛠 Command Reference

The Python entrypoint of the engine has these commands:

| Command | Description |
|---|---|
| `lint` | Runs the Verilator lint checks on `VERILOG_FILES` with the flags of LibreLane's lint step, so both report the same warnings. A warning does not fail it. A latch or a signal with more than one driver does. |
| `sim` | Compiles `VERILOG_FILES` and `TEST_FILES` with Icarus Verilog and runs the simulation. |
| `cocotb` | Runs cocotb tests on `VERILOG_FILES` and `COCOTB_TESTS`. The tests are Python coroutines that drive the RTL. `--netlist` runs the same tests on the synthesised gates. `WAVES=1` also writes `build/<DESIGN_NAME>.vcd`. |
| `regress` | Runs the tests of the `//REGRESSION` list over many seeds. Prints the command that replays each failed run. Writes `build/regress/`. `--coverage` then runs `coverage` on the same list, when every run passed. |
| `coverage` | Runs the `COCOTB_TESTS` again on Verilator and measures block, branch and toggle coverage. Writes `build/coverage/`. It does not decide pass or fail. |
| `gatesim` | Simulates the **synthesised netlist** with the PDK cell models, on `GATE_TESTS`. Without `GATE_TESTS`, it runs the `COCOTB_TESTS` on the netlist. |
| `synth` | Runs logic synthesis with Yosys on `VERILOG_FILES` only. Writes `build/synthesis.json`. The script is fixed: see [docs/commands.md](docs/commands.md#synth-and-systemverilog-in-every-command). |
| `schematic` | Draws the circuit as `build/schematic.svg`. It shows the RTL as written, not the synthesised netlist. |
| `pdk` | Installs and enables the Sky130 PDK with Ciel, into `$PDK_ROOT`. Without `$PDK_ROOT`, it uses `./pdks`. |
| `rtl` | Checks the RTL. It runs `check --for rtl`, an Icarus compile, `lint` and `synth`, in that order. Writes `build/rtl.vvp` and `build/synthesis.json`. |
| `check` | Checks the configuration, values included. It builds nothing and runs no tool. `--for rtl`, `sim`, `regress`, `gatesim` or `gds` checks one part. Without `--for`, it checks every part that the config asks for. |
| `report` | Prints a summary of the last LibreLane run: area, timing, power and the signoff result. |
| `site` | Writes `build/site/`, one results page for GitHub Pages. The page shows the tests, timing, area, power and signoff of what was run before it. |

[docs/commands.md](docs/commands.md) tells you more about each command, and the reasons.

A repository made from the template calls them through `make`: `make check`, `make rtl`, `make sim`, `make regress` and `make gds`. [docs/makefile.md](docs/makefile.md) lists the targets and the older names that still work.

The CI of a repository made from the ChipForAll template is here too, as actions that its workflow calls: [docs/actions.md](docs/actions.md). The rules of its Makefile are here too: [docs/makefile.md](docs/makefile.md).

## ⚙️ Configuration

`c4o-core` looks for `config.yaml`, `config.yml` or `config.json` in your workspace, in that sequence.

**This is a [LibreLane](https://github.com/librelane/librelane) configuration file.** The same file controls this engine and the physical design flow. Thus the variable names are the LibreLane names, and this engine has no second vocabulary. `c4o-core` reads only the keys that it needs.

Simulation is not a part of LibreLane, so LibreLane has no variable for testbenches. Those keys have a `//` prefix. LibreLane ignores a key with that prefix, so the shared file stays valid for it.

The LibreLane prefix `dir::` makes a path relative to the design directory. It works on all keys.

**Globs work on the `//` keys, not on `VERILOG_FILES`.** This engine expands globs on all keys. But `VERILOG_FILES` belongs to LibreLane, which checks each entry as a literal path and does not expand `**`. A configuration with `dir::src/**/*.v` thus passes lint, simulation and synthesis here, and then fails in the physical flow:

```console
ERROR  Path provided for variable 'VERILOG_FILES[0]' is invalid:
       '/workspace/src/**/*.v' does not exist
```

Write one source file on each line. The `//` keys belong to this engine, so `dir::test/*.v` and `dir::test/**/*.py` are correct there.

### The keys this engine reads

| Key | What it is |
|---|---|
| `DESIGN_NAME` | The name of the top module. |
| `VERILOG_FILES` | Synthesisable sources. Each entry is one literal path. |
| `VERILOG_INCLUDE_DIRS` | Directories that contain `.vh` / `.h` includes. |
| `"//TEST_FILES"` | Verilog testbenches for `sim`. Globs work. The engine also reads `TEST_FILES` with no prefix, but only the name with the prefix passes the LibreLane validation with no message. |
| `"//SIM_TOP"` | The testbench module to elaborate. Necessary when `"//TEST_FILES"` matches more than one file. |
| `"//COCOTB_TESTS"` | Python testbenches for `cocotb`. Globs work. |
| `"//REGRESSION"` | A YAML list of `test` and `seeds` for `regress`. See [docs/commands.md](docs/commands.md#many-seeds-regress). |
| `"//GATE_TESTS"` / `"//GATE_TOP"` | The same two keys, for `gatesim`. |
| `CLOCK_PORT` / `CLOCK_PERIOD` | The clock to constrain, and its period in ns. |
| `PDK` / `STD_CELL_LIBRARY` | Necessary for `gatesim`, `cocotb --netlist`, `pdk` and `check`. |
| `FP_SIZING` | `relative` or `absolute`. `check` needs it. |
| `FP_CORE_UTIL` / `DIE_AREA` | `check` needs `FP_CORE_UTIL` with `relative` sizing and `DIE_AREA` with `absolute` sizing. |
| `LINTER_DISABLE_WARNINGS` | A list of Verilator warning codes that `lint` does not report. It is a LibreLane key with the same meaning there. |
| `"//DESCRIPTION"` | One line that tells what the design is. It appears below the title of the `site` page and in its link preview. |

### A pattern that matches nothing is an error

Each configured pattern must match one file or more. `sim` does not run without a testbench. Without these two rules, a renamed directory or a typing error has a bad result: `sim` compiles only the RTL and exits 0. CI is then green, and nothing was verified.

### More than one testbench

Icarus makes each module that no other module instantiates a separate root, and the first `$finish` stops the full simulation. Thus `sim` runs one testbench module. When `"//TEST_FILES"` matches more than one file, give the name of the module to run. Without the name, `sim` stops with an error. The engine passes the name to `iverilog -s`:

```yaml
"//TEST_FILES":
  - dir::test/*.v
"//SIM_TOP": tb_counter
```

With only one testbench file, `//SIM_TOP` is optional.

All other keys in the file belong to LibreLane. See its documentation for the full list.

## 📦 Included Tools

*   **Yosys**: Open Synthesis Suite
*   **Verilator**: High-performance Verilog simulator and linter
*   **Icarus Verilog**: Verilog simulation and synthesis tool
*   **Graphviz**: Renders the SVG of the `schematic` command (yosys `show` calls `dot`)
*   **Ciel**: PDK version manager
*   **Cocotb**: Coroutine-based cosimulation library (see the `cocotb` command)
*   **pyuvm**: The UVM in Python, on top of cocotb. `import pyuvm` works in a `COCOTB_TESTS` file.
*   **sv2v**: SystemVerilog to Verilog-2005, for sources that the tools above cannot read
*   **PeakRDL**: `regblock` generates a register block from SystemRDL, and `pyuvm` generates the matching register model ([how the three fit together](docs/commands.md#generated-register-blocks))

## License
This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

*Note: This framework invokes various third-party open-source EDA tools (Yosys, Verilator, LibreLane, etc.), which are distributed under their respective licenses.*
