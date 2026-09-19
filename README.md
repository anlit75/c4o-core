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
| `synth` | Performs logic synthesis using Yosys on `VERILOG_FILES` only. Generates `build/synthesis.json`. |
| `pdk` | Installs/Enables the Sky130 PDK via Ciel into `./pdks`. |
| `gds` | Validates configuration for the physical design flow (pre-flight check). Requires valid `VERILOG_FILES`. |

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
*   **`VERILOG_INCLUDE_DIRS`**: List of directories containing Verilog include files (`.vh`, `.h`).
*   **`DESIGN_NAME`**: Top-level module name for synthesis.

Everything else in the file belongs to LibreLane; see its documentation for the full list.

## 🏗 Architecture

*   **System Path**: The EDA tools and python scripts are installed in `/opt/c4o-core`.
*   **User Path**: Users should mount their workspace to `/workspace`.
*   **PDK Path**: The `pdk` command installs artifacts into the user's volume (`./pdks`), ensuring persistence across container runs.

## 📦 Included Tools

*   **Yosys**: Open Synthesis Suite
*   **Verilator**: High-performance Verilog simulator/linter
*   **Icarus Verilog**: Verilog simulation and synthesis tool
*   **Ciel**: PDK Version Manager
*   **Cocotb**: Coroutine based cosimulation library

## License
This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

*Note: This framework invokes various third-party open-source EDA tools (Yosys, Verilator, OpenLane, etc.), which are distributed under their respective licenses.*
