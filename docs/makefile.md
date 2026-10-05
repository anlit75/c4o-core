# The Makefile rules

The `Makefile` of a repository made from the [ChipForAll](https://github.com/anlit75/ChipForAll) template is short. It names two images and includes the rules from the c4o-core image. Thus a fix to a command reaches that repository with the image, and nobody copies it.

## What the Makefile of a repository contains

```make
C4O_IMAGE := ghcr.io/anlit75/c4o-core:2.17
LIBRELANE_IMAGE := ghcr.io/librelane/librelane:3.0.14

# ... the text of stub.mk, unchanged ...

# your own targets
```

- Keep the two image lines in this form. The [actions](actions.md) read them.
- Do not edit the text of `stub.mk`. It finds the rules and includes them.
- Put your own targets below it.

## Where the rules come from

| Where `make` runs | The rules |
|---|---|
| Inside the image (the Dev Container) | `/opt/c4o-core/rules.mk`, read directly. |
| On a host | Copied out of the image into `.c4o/<image id>.mk`, one time for each image. |
| With `C4O_RULES=<file>` | That file. No Docker is necessary. |

The file name is the id of the image on your machine. Thus the rules are always the rules of the image that runs. When `docker pull` gets a newer image for the same tag, the next `make` copies its rules and removes the old copy.

Put `.c4o/` in `.gitignore`. `make distclean` removes it.

If the image is not on your machine, `make` pulls it first. If Docker does not answer, or the image has no `rules.mk`, `make` stops and tells you why. An image older than c4o-core 2.17 has no `rules.mk`.

## What your own targets can use

These names stay the same in all 2.x releases.

| Name | Meaning |
|---|---|
| `C4O_IMAGE`, `LIBRELANE_IMAGE` | The two images. You set them. |
| `C4O_CMD` | Runs a c4o-core command: `$(C4O_CMD) lint`. |
| `C4O_COCOTB` | The same, with `SEED`, `WAVES` and `TEST` passed on: `$(C4O_COCOTB) cocotb --netlist`. |
| `$(call c4o_tool,<program>)` | Runs a different program of the image: `$(call c4o_tool,sv2v) rtl/a.sv`. |
| `DOCKER_RUN` | `docker run` with the repository mounted at `/workspace` and your user id. |
| `C4O_IN_CONTAINER` | Not empty when `make` runs inside the image. |
| `DESIGN_NAME` | Read from `config.yaml`. |
| `PDK_ROOT` | Where the PDK is on the host. Default: `pdks/` in the repository. |
| `LIBRELANE_ARGS` | More flags for LibreLane. With `--from`, `-F` or `--only`, `make gds` keeps the previous run. |
| `SEED` | The seed for `make cocotb` and for `make gatesim` with Python tests. For `make regress` it is the base seed of the list. |
| `TEST` | `make cocotb TEST=<module>[.<function>]` runs one module or one test of `"//COCOTB_TESTS"`. |
| `WAVES` | `make cocotb WAVES=1` writes `build/<DESIGN_NAME>.vcd`. `make gatesim` passes it on and writes no VCD. |

`C4O_CMD`, `C4O_COCOTB` and `c4o_tool` call the program directly inside the image, and start a container on a host. You write the target one time and it works in the two places.

`help` has two colons. To add a line for your target:

```make
help::
	@echo "  make ral     - Regenerate test/uart_ral.py"

ral:
	$(call c4o_tool,peakrdl) pyuvm regs/apb_uart.rdl -o test/uart_ral.py
```

A bare `make` runs `all`, also when one of your targets is above the include.

## The targets

`all`, `help`, `lint`, `sim`, `cocotb`, `regress`, `coverage`, `gatesim`, `synth`, `schematic`, `pdk`, `gds`, `report`, `site`, `shell`, `clean`, `distclean`. `make help` gives one line for each. [commands.md](commands.md) tells you what the c4o-core command behind each one does.

### Which tests run

`config.yaml` has two keys for tests. `"//TEST_FILES"` names Verilog testbenches. `"//COCOTB_TESTS"` names Python tests.

| Target | With its key | Without its key |
|---|---|---|
| `make sim` | Runs the testbenches. | Fails. |
| `make cocotb` | Runs the Python tests. | Fails. |
| `make all` | Runs `lint`, `sim`, `cocotb` and `synth` in this order. | `sim` and `cocotb` each print a skip message and the rest runs. |

`make all` fails when neither key is set. A repository with no test does not pass.

`make regress` runs the test list that `"//REGRESSION"` names, each entry over its seeds. `make all` does not run it, and it fails without the key. `make regress SEED=<n>` reruns the whole list with the same seeds. `make cocotb SEED=<n> TEST=<entry>` replays one run. See [commands.md](commands.md#many-seeds-regress).

`make coverage` runs the Python tests of `"//COCOTB_TESTS"` again on Verilator and writes `build/coverage/`. `make all` does not run it. It does not decide whether the tests pass. `make cocotb` decides that. `make coverage SEED=<n>` sets the seed. With `"//REGRESSION"` it runs the list of `make regress` and merges the runs. See [commands.md](commands.md#code-coverage-coverage).

`make gatesim` runs the Verilog testbench of `"//GATE_TESTS"`. Without that key, it runs the Python tests of `"//COCOTB_TESTS"` on the netlist. With neither key it fails. `make gatesim SEED=<n>` sets the seed in the same way as `make cocotb SEED=<n>`.

`make gds` starts LibreLane as a second container, from the place where `make` runs. Thus that place needs a Docker daemon: your host, or the Dev Container, which has its own.
