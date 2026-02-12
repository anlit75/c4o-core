# c4o-core

c4o-core is the unified engine for the c4o open-source chip design workflow. It combines the Docker environment and execution logic into a single repository.

## Directory Structure

```
.
├── Dockerfile                  # The single source of truth for the environment
├── action.yml                  # The GitHub Action interface
├── scripts/
│   └── entrypoint.py           # The "Glue Logic" wrapper script (Python)
├── tests/
│   └── smoke/                  # Smoke tests to verify the env works
│       ├── counter.v           # Simple Verilog counter
│       └── tb_counter.v        # Testbench for the counter
└── README.md                   # Minimal documentation
```

## Usage

### Local Development

1.  Build the Docker image:
    ```bash
    docker build -t c4o-core .
    ```

2.  Run the smoke test:
    ```bash
    docker run --rm -v $(pwd):/workspace -w /workspace c4o-core test --files tests/smoke/counter.v tests/smoke/tb_counter.v
    ```

### GitHub Action

Use the `c4o-core` action in your workflow:

```yaml
steps:
  - uses: c4o/c4o-core@main
    with:
      command: test
      files: src/my_design.v tests/my_test.v
```

## Supported Commands

*   `lint`: Run Verilator lint.
*   `synth`: Run Yosys synthesis.
*   `test`: Run Icarus Verilog simulation.
