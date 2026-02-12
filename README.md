# c4o-core (ChipForAll Engine)

![CI Status](https://github.com/anlit75/c4o-core/actions/workflows/ci.yml/badge.svg)
![Docker Pulls](https://img.shields.io/badge/docker-pull-blue)

**c4o-core** is the underlying EDA toolchain engine for the [ChipForAll](https://github.com/anlit75/ChipForAll) project.
It packages open-source silicon tools into a unified, Python-driven Docker container.

> **Note**: If you are a beginner, please use the [ChipForAll Template](https://github.com/anlit75/ChipForAll) instead of using this engine directly.

## 🚀 Quick Start

You can run `c4o-core` directly via Docker.
Mount your current directory (`$(PWD)`) to `/c4o` (or any workspace path) to persist artifacts.

```bash
docker run --rm -v $(PWD):/c4o -w /c4o ghcr.io/anlit75/c4o-core:latest <command>
```

## 🛠 Command Reference

The engine supports the following commands via its Python entrypoint:

| Command | Description |
|---|---|
| `lint` | Runs Verilator linting checks on the source files. |
| `sim` | Compiles and runs simulation using Icarus Verilog. |
| `synth` | Performs logic synthesis using Yosys. Generates `build/synthesis.json`. |
| `pdk` | Installs/Enables the Sky130 PDK via Volare into `./pdks`. |
| `gds` | Validates configuration for OpenLane flow (pre-flight check). |

## ⚙️ Configuration (config.json)

`c4o-core` looks for a `config.json` file in your workspace to understand your design structure.

### Minimal Example (RTL Only)

```json
{
  "DESIGN_NAME": "counter",
  "VERILOG_FILES": ["src/counter.v", "src/alu.v"]
}
```

### Full Example (RTL + GDS)

Required for `make gds` / OpenLane flow.

```json
{
  "DESIGN_NAME": "counter",
  "VERILOG_FILES": ["src/counter.v"],
  "PDK": "sky130A",
  "STD_CELL_LIBRARY": "sky130_fd_sc_hd",
  "DIE_AREA": "0 0 100 100",
  "FP_CORE_UTIL": 40,
  "FP_SIZING": "absolute",
  "CLOCK_PORT": "clk",
  "CLOCK_PERIOD": 10.0
}
```

## 🏗 Architecture

*   **System Path**: The EDA tools and python scripts are installed in `/opt/c4o-core`.
*   **User Path**: Users should mount their workspace to `/c4o` (or `/workspace`).
*   **PDK Path**: The `pdk` command installs artifacts into the user's volume (`./pdks`), ensuring persistence across container runs.

## 📦 Included Tools

*   **Yosys**: Open Synthesis Suite
*   **Verilator**: High-performance Verilog simulator/linter
*   **Icarus Verilog**: Verilog simulation and synthesis tool
*   **Volare**: PDK Version Manager
*   **Cocotb**: Coroutine based cosimulation library
