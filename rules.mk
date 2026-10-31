# The commands of a repository made from the ChipForAll template.
#
# That repository's Makefile holds two image names and includes this file out
# of the c4o-core image it names (see stub.mk). So the commands are versioned
# with the image: a fix here reaches a repository without anybody copying it.
#
# What a repository may rely on -- the variables, the helper, the targets -- is
# written down in docs/makefile.md. Renaming one of them breaks the targets
# people have added to their own Makefile.

ifndef C4O_IMAGE
$(error C4O_IMAGE is not set. The Makefile that includes rules.mk has to name the c4o-core image first)
endif
ifndef LIBRELANE_IMAGE
$(error LIBRELANE_IMAGE is not set. The Makefile that includes rules.mk has to name the LibreLane image first)
endif

# A target a repository writes above its include must not become what a bare
# `make` runs. It checks the config and runs no tool.
.DEFAULT_GOAL := check

# Extra flags for the LibreLane run, passed through as they are.
LIBRELANE_ARGS ?=
DESIGN_NAME := $(shell grep -E '^DESIGN_NAME:' config.yaml | sed -e 's/^DESIGN_NAME:[[:space:]]*//' -e 's/["'"'"']//g')
PWD := $(shell pwd)

# A full run starts empty: --overwrite removes the previous run. LibreLane's
# default is to append to a run that exists, so a second `make gds` used to
# leave two of every step directory under the same tag.
#
# Not when LIBRELANE_ARGS names a step to start from. That is LibreLane's own
# resume, and it needs the previous run to still be there:
#
#   make gds LIBRELANE_ARGS="--from OpenROAD.Floorplan --with-initial-state <file>"
#
# where <file> is the state_in.json in that step's directory of the last run,
# runs/<tag>/13-openroad-floorplan/state_in.json for the template's example.
# The resumed steps are appended after the old ones, numbered on from the last.
#
# Most of what you change after the first flow -- FP_CORE_UTIL, the floorplan --
# does not need synthesis redone. CLOCK_PERIOD is not one of those changes: the
# clock is an input to synthesis, so resuming from floorplan measures the old
# gates under the new period.
#
# Measured on LibreLane 3.0.14: --last-run cannot be used here, because it and
# --run-tag are mutually exclusive; the step is 'OpenROAD.Floorplan', not
# 'floorplan'; and without --with-initial-state LibreLane starts from the state
# of the finished design, and CTS crashes on it.
ifeq ($(filter --from --from=% -F --only --only=%,$(LIBRELANE_ARGS)),)
LIBRELANE_OVERWRITE := --overwrite
endif

# What `make sim` and `make gds` print while they run. The tools' own output
# goes to build/log/ and the terminal gets one line for each command or stage:
#
#   make gds PROGRESS=raw     the tools' output as it is, nothing kept
#   make gds PROGRESS=plain   the lines as text: no colour, no redrawing (CI)
#   make gds PROGRESS=tty     the lines and, under them, what is running now
#
# Left out, it is tty on a terminal and plain anywhere else, also when CI is
# set. NO_COLOR removes the colour. The other commands print what they always did.
C4O_PROGRESS := $(or $(PROGRESS),$(C4O_PROGRESS))

# A run that is not the whole flow shows the number of the step, and no total.
ifneq ($(filter --from --from=% -F --to --to=% -T --skip --skip=% --only --only=%,$(LIBRELANE_ARGS)),)
LIBRELANE_PARTIAL := 1
endif

# Where the Sky130 PDK lives on the host. One copy is 1GB and every checkout
# needs the same one, so a machine with several -- a lab, a teaching account --
# can point them all at one directory instead of paying for it again each time:
#
#   make gds PDK_ROOT=/opt/sky130
#
# Both halves honour it: `make pdk` installs there and the LibreLane sidecar
# reads from there. Default is this checkout's own pdks/.
PDK_ROOT ?= $(PWD)/pdks

# The current directory is mounted at /workspace, so what the tools write lands
# in build/ and runs/ here, owned by the user who ran make.
DOCKER_RUN := docker run --rm -v $(PWD):/workspace -w /workspace -u $(shell id -u):$(shell id -g)

# The LibreLane container and the flags of the run.
LIBRELANE_RUN = docker run --rm \
		-v $(PWD):/workspace -w /workspace \
		-v $(PDK_ROOT):/pdks \
		-e PDK_ROOT=/pdks \
		-e HOME=/tmp \
		-u $(shell id -u):$(shell id -g) \
		$(LIBRELANE_IMAGE) \
		python3 -m librelane --manual-pdk --pdk-root /pdks \
			$(LIBRELANE_OVERWRITE) $(LIBRELANE_ARGS) \
			--run-tag $(DESIGN_NAME)_run config.yaml

# Which steps this config will run, before it does: the steps of the Classic
# flow, less those a switch of the config turns off. It is how the ledger can
# say "step 24 of 76". About a second, in the LibreLane image, and it uses
# gating_config_vars, an attribute of LibreLane's that is not a documented
# interface: when it fails, or after an upgrade changed it, the ledger counts
# steps without a total. Check it again when LIBRELANE_IMAGE moves.
LIBRELANE_PLAN_PY := import json,librelane;from librelane.flows import Flow;C=Flow.factory.get("Classic");f=C("config.yaml",pdk_root="/pdks");g={s for s,v in f.gating_config_vars.items() if any(not f.config[x] for x in v)};print(json.dumps({"version":librelane.__version__,"all":len(C.Steps),"steps":[[s.id,s.name] for s in C.Steps if s.id not in g]}))
LIBRELANE_PLAN = docker run --rm -v $(PWD):/workspace -w /workspace -v $(PDK_ROOT):/pdks -e PDK_ROOT=/pdks -e HOME=/tmp \
		-u $(shell id -u):$(shell id -g) $(LIBRELANE_IMAGE) python3 -c '$(LIBRELANE_PLAN_PY)'

# One picture per stage of the flow, for the results page. c4o-core decides
# which layout of the run each stage is drawn from (`stages`, in the c4o-core
# image), and the LibreLane image draws them with LibreLane's own render.py,
# as its KLayout.Render step does: this is the only part that needs KLayout.
# Every call is allowed to fail, and none changes the status of `make gds`: a
# picture that is not drawn is a stage without one. Run after a flow that
# failed as well, on what the run left. After an upgrade of LIBRELANE_IMAGE,
# check that scripts/klayout/render.py still takes the arguments c4o-core gives it.
STAGES_RUN := runs/$(DESIGN_NAME)_run
# The file in the run that records what it was made from. c4o-core's runs.py names it too.
INPUTS_FILE := c4o-inputs.sha256
LIBRELANE_RENDER_PY := import json,os,subprocess,sys,librelane;R=os.path.join(os.path.dirname(librelane.__file__),"scripts","klayout","render.py");ok=lambda j:subprocess.run([sys.executable,R]+j["args"],capture_output=True).returncode==0 and os.path.exists(j["png"]) and os.path.getsize(j["png"])>0;[os.path.exists(j["png"]) and os.remove(j["png"]) for j in json.load(open("build/stages/jobs.json")) if not ok(j)]
LIBRELANE_RENDER = docker run --rm -v $(PWD):/workspace -w /workspace -v $(PDK_ROOT):/pdks -e PDK_ROOT=/pdks -e HOME=/tmp \
		-u $(shell id -u):$(shell id -g) $(LIBRELANE_IMAGE) timeout 300 python3 -c '$(LIBRELANE_RENDER_PY)'
# $(1): flags for the call that lists the pictures (--quiet for PROGRESS=raw)
C4O_STAGES = ( $(C4O_CMD) stages --run-dir $(STAGES_RUN) || true ); \
	if [ -f build/stages/jobs.json ]; then ( $(LIBRELANE_RENDER) >/dev/null 2>&1 || true ); fi; \
	( $(C4O_CMD) stages --run-dir $(STAGES_RUN) --collect $(1) || true )

# The results page names the commit and CI run it was built from, which c4o-core
# reads from these. `-e NAME` with no value passes the host's value through, and
# passes nothing when the host has none, so a local `make site` is unaffected.
SITE_ENV := -e GITHUB_SERVER_URL -e GITHUB_REPOSITORY -e GITHUB_SHA -e GITHUB_RUN_ID

# Inside the image -- the Dev Container -- the tools are called directly. On a
# host each command is a container of C4O_IMAGE.
#
# C4O_COCOTB is C4O_CMD with a seed, the waves switch, a test name and the
# coverage switch threaded through.
# cocotb seeds Python's random module from the seed and logs the value it used,
# so
#
#   make cocotb SEED=1789965785
#
# replays a failed run exactly. SEED here, RANDOM_SEED inside: that is cocotb
# 1.9's name for it, and cocotb 2 renames it again. Translating at this line
# keeps `make cocotb SEED=...` the same command across that change.
#
#   make cocotb WAVES=1
#
# writes build/<DESIGN_NAME>.vcd. WAVES reaches the container as it is.
#
#   make cocotb TEST=<module>[.<function>]
#
# runs one module of COCOTB_TESTS, or one test of it. TEST reaches the container
# as it is. `make regress` prints this line, with the seed, for each run it lost.
#
#   make regress COVERAGE=0
#
# leaves out the coverage run that `make regress` ends with. make reads COVERAGE
# itself, and the container never sees it.
#
# C4O_COCOTB mounts PDK_ROOT when it is there, so a cocotb run on the netlist
# (`$(C4O_COCOTB) cocotb --netlist`, in a target of your own) finds the cell
# models wherever the PDK is. C4O_GATES mounts it always: `make gatesim` is the
# one command that cannot run without the PDK.
#
# c4o_tool runs one of the image's other programs the same two ways:
#
#   $(call c4o_tool,sv2v) rtl/a.sv
ENTRYPOINT_SCRIPT := /opt/c4o-core/scripts/entrypoint.py
ifneq ($(wildcard $(ENTRYPOINT_SCRIPT)),)
C4O_IN_CONTAINER := 1
C4O_CMD := python3 $(ENTRYPOINT_SCRIPT)
C4O_COCOTB = $(if $(or $(SEED),$(WAVES),$(TEST)),env $(strip $(if $(SEED),RANDOM_SEED=$(SEED)) $(if $(WAVES),WAVES=$(WAVES)) $(if $(TEST),TEST=$(TEST)))) $(C4O_CMD)
C4O_GATES = env $(strip PDK_ROOT=$(PDK_ROOT) $(if $(SEED),RANDOM_SEED=$(SEED)) $(if $(WAVES),WAVES=$(WAVES)) $(if $(TEST),TEST=$(TEST))) $(C4O_CMD)
C4O_SITE := $(C4O_CMD)
C4O_PDK = env PDK_ROOT=$(PDK_ROOT) $(C4O_QUIET_ENV)$(C4O_CMD)
C4O_QUIET_ENV = $(if $(C4O_QUIET),C4O_QUIET_INFO=1 )
C4O_CMDQ = $(if $(C4O_QUIET),env C4O_QUIET_INFO=1 )$(C4O_CMD)
C4O_FLOW := env LIBRELANE_IMAGE=$(LIBRELANE_IMAGE) $(C4O_CMD)
c4o_tool = $(1)
C4O_INFO = env C4O_IMAGE=$(C4O_IMAGE) LIBRELANE_IMAGE=$(LIBRELANE_IMAGE) C4O_RUNS_IN=image \
	C4O_HOST="$(INFO_OS)" C4O_DOCKER="$(INFO_DOCKER)" $(C4O_CMD)
C4O_LEDGER = env $(strip C4O_PROGRESS=$(C4O_PROGRESS) $(if $(SEED),RANDOM_SEED=$(SEED)) $(if $(WAVES),WAVES=$(WAVES)) $(if $(TEST),TEST=$(TEST))) python3 $(ENTRYPOINT_SCRIPT)
else
C4O_IN_CONTAINER :=
C4O_CMD := $(DOCKER_RUN) $(C4O_IMAGE)
C4O_COCOTB = $(DOCKER_RUN) $(if $(wildcard $(PDK_ROOT)),-v $(PDK_ROOT):/pdks -e PDK_ROOT=/pdks) $(strip $(if $(SEED),-e RANDOM_SEED=$(SEED)) $(if $(WAVES),-e WAVES=$(WAVES)) $(if $(TEST),-e TEST=$(TEST))) $(C4O_IMAGE)
C4O_GATES = $(DOCKER_RUN) -v $(PDK_ROOT):/pdks -e PDK_ROOT=/pdks $(strip $(if $(SEED),-e RANDOM_SEED=$(SEED)) $(if $(WAVES),-e WAVES=$(WAVES)) $(if $(TEST),-e TEST=$(TEST))) $(C4O_IMAGE)
C4O_SITE := $(DOCKER_RUN) $(SITE_ENV) $(C4O_IMAGE)
C4O_PDK = $(DOCKER_RUN) -v $(PDK_ROOT):/pdks -e PDK_ROOT=/pdks $(C4O_QUIET_ENV)$(C4O_IMAGE)
C4O_QUIET_ENV = $(if $(C4O_QUIET),-e C4O_QUIET_INFO=1 )
C4O_CMDQ = $(DOCKER_RUN) $(C4O_QUIET_ENV)$(C4O_IMAGE)
C4O_FLOW := $(DOCKER_RUN) -e LIBRELANE_IMAGE=$(LIBRELANE_IMAGE) $(C4O_IMAGE)
c4o_tool = $(DOCKER_RUN) --entrypoint $(1) $(C4O_IMAGE)
C4O_INFO = $(DOCKER_RUN) -e C4O_IMAGE=$(C4O_IMAGE) -e LIBRELANE_IMAGE=$(LIBRELANE_IMAGE) -e C4O_RUNS_IN=host \
	-e C4O_HOST="$(INFO_OS)" -e C4O_DOCKER="$(INFO_DOCKER)" -e GITHUB_ACTIONS -e CODESPACES $(C4O_IMAGE)
# The ledger redraws, so on a host its container gets a terminal exactly when
# make's output is one. A recipe sets $$T for that: `[ -t 1 ]` has to run in the
# recipe's own shell, where $(shell) would be asking about a pipe.
C4O_LEDGER = $(DOCKER_RUN) $$T $(PROGRESS_ENV) $(strip $(if $(SEED),-e RANDOM_SEED=$(SEED)) $(if $(WAVES),-e WAVES=$(WAVES)) $(if $(TEST),-e TEST=$(TEST))) $(C4O_IMAGE)
endif
# What `make gds` and `make pdk` print is their own lines and the tools'. The
# [INFO] lines of c4o-core that say what it is about to do -- the config it
# loaded, the command it runs, the file it reads -- would be a second voice
# above the progress ledger, so these targets set C4O_QUIET and c4o-core is
# called with C4O_QUIET_INFO=1 (common.py). Warnings, errors and everything a
# tool prints stay. They also stop echoing their commands. PROGRESS=raw is for
# debugging and sets neither: it shows the commands and the whole [INFO] output.
#
# Set for the targets that use it, not here, so that `make report` and
# `make check` on their own print what they always did. `make gds` hands it to
# the `report` it runs, which is a make of its own and does not inherit it.
pdk gds gds-flow: C4O_QUIET := $(if $(filter raw,$(C4O_PROGRESS)),,1)
C4O_Q = $(if $(C4O_QUIET),@)

# `docker pull` and ciel print nothing while they download when their output is
# not a terminal, and ciel's is never one here: rich draws its bars only on a
# terminal. The first `make gds` would be minutes of silence. c4o_beat runs a
# command and, every C4O_BEAT_EVERY seconds until it ends, prints a line saying
# what is still going on. Elapsed time only: neither tool reports bytes in a
# pipe, and the tarballs ciel fetches land in the container's /tmp.
#
#   $(C4O_BEAT) c4o_beat "what it is doing" <command...>
#
# The command runs in the foreground, so its status and Ctrl-C work as they did.
# The ticker is the background part, and it is stopped when the command ends.
C4O_BEAT_EVERY ?= 30
C4O_BEAT = c4o_beat() { what=$$1; shift; \
	( t=0; while sleep $(C4O_BEAT_EVERY); do t=$$((t + $(C4O_BEAT_EVERY))); echo "  ... still $$what ($$t s)"; done ) & tick=$$!; \
	trap 'kill $$tick 2>/dev/null; exit 130' INT TERM; \
	"$$@"; rc=$$?; kill $$tick 2>/dev/null; wait $$tick 2>/dev/null; return $$rc; }; \

# What `make info` cannot see from inside the image: the system make runs on and
# its Docker. `=`, not `:=`, so that only `make info` asks Docker.
INFO_OS = $(shell uname -sm)
INFO_DOCKER = $(shell docker version --format '{{.Server.Version}}' 2>/dev/null)

# What the ledger decides its mode from, passed on as the host has it.
PROGRESS_ENV := -e C4O_PROGRESS=$(C4O_PROGRESS) -e NO_COLOR -e CI -e TERM -e GITHUB_ACTIONS

.PHONY: check rtl sim regress gatesim schematic gds gds-flow pdk report site info clean distclean shell help cocotb coverage

# The config and the files it names, for every part of the flow the config
# asks for. No tool runs, so it takes a second. `make rtl`, `make sim` and
# `make gds` each run the part of it that is theirs first.
check:
	$(C4O_CMD) check

# Checks the RTL: its config, an Icarus compile, Verilator lint, Yosys generic
# synthesis. Four commands in one container, and no tests.
rtl:
	$(C4O_CMD) rtl

# `rtl`, then the config of the tests, then each kind of test that config.yaml
# lists: Verilog testbenches and cocotb. The kind it does not list is skipped,
# and neither kind is an error. SEED, WAVES and TEST apply to the cocotb run.
#
# One line for each of the four, with their own output in build/log/. With
# PROGRESS=raw it is the tools' output as it is.
sim:
	@if [ -t 1 ]; then T=-t; else T=; fi; $(C4O_LEDGER) all
	@echo
	@echo "Next:"
	@echo "  make gds"
	@echo "      builds the chip layout. It takes minutes, and the first run also"
	@echo "      downloads about 2 GB."
	@echo "  or change rtl/ or tb/ and run make sim again"

# Two colons, so a repository can add lines for its own targets with a
# `help::` rule below its include.
help::
	@echo "Available targets:"
	@echo "  make check   - Check config.yaml and the files it names (takes a second)"
	@echo "  make rtl     - Check the RTL: compile, Verilator lint, Yosys synthesis"
	@echo "  make sim     - Run rtl, then every test config.yaml lists (Verilog and cocotb)"
	@echo "                 (repeat a random failure: make sim SEED=<n>)"
	@echo "                 (write build/<DESIGN_NAME>.vcd: make sim WAVES=1)"
	@echo "                 (run one module or test: make sim SEED=<n> TEST=<entry>)"
	@echo "  make regress - Run the tests listed in //REGRESSION over many seeds (build/regress/),"
	@echo "                 then measure code coverage (build/coverage/)"
	@echo "                 (repeat the whole list: make regress SEED=<n>)"
	@echo "                 (leave out coverage: make regress COVERAGE=0)"
	@echo "  make gatesim - Re-simulate the synthesised netlist (after make gds)"
	@echo "  make schematic - Draw the circuit as build/schematic.svg"
	@echo "  make pdk     - Install/Enable Sky130 PDK via Ciel, LibreLane's PDK manager"
	@echo "  make gds     - Check the physical design config, then run LibreLane GDSII flow"
	@echo "                 (skipped when its inputs are unchanged since the last one;"
	@echo "                 make gds FORCE=1 runs it anyway)"
	@echo "  make report  - Show area, timing and power from the last GDS run"
	@echo "  make site    - Put tests, timing, area, power and signoff on one page (build/site/)"
	@echo "  make info    - Print the versions a bug report needs"
	@echo "  make shell   - Enter c4o-core interactive shell"
	@echo "  make clean     - Remove build/ (keeps runs/, which report and gatesim read)"
	@echo "  make distclean - Remove build/, runs/ and the copied rules in .c4o/"
	@echo ""
	@echo "  Re-run part of the flow after the first full one:"
	@echo "    make gds LIBRELANE_ARGS=\"--from OpenROAD.Floorplan --with-initial-state <state_in.json>\""

# `cocotb` and `coverage` are not in `make help`, and they stay: a failed run
# prints `make cocotb SEED=<n> TEST=<entry>` as the command that replays it,
# and the report action calls `make coverage`. `all`, `lint` and `synth`, the
# old names of `sim` and `rtl`, are gone.

# The Python (cocotb) tests alone, without rtl and the Verilog testbenches. A
# failed `make regress` run is replayed with it.
cocotb:
	$(C4O_COCOTB) cocotb

# The coverage run alone: the cocotb tests again on Verilator with coverage
# counters, or the REGRESSION list when the key is there. Not a verdict.
# C4O_COCOTB so that SEED reaches it. `make regress` ends with the same run.
coverage:
	$(C4O_COCOTB) coverage

# The test list of REGRESSION, each test over its seeds, from one compile, and
# then the same list on Verilator for the coverage numbers that Icarus cannot
# give. The verdict is the first part's and stays on Icarus: the second part
# runs only when every run passed, and measures. The summaries are
# build/regress/summary.json and build/coverage/summary.json. C4O_COCOTB so that
# SEED, the base seed every run's seed comes from, reaches both. Named by itself
# it fails without the key.
regress:
	$(C4O_COCOTB) regress $(if $(filter 0,$(COVERAGE)),,--coverage)

# Simulates runs/<tag>/final/nl/, which `make gds` leaves behind, against the
# PDK's own cell models. `make sim` says the RTL behaves; this says the gates
# synthesis produced still behave, which is a different claim.
#
# The testbench is the Verilog one of GATE_TESTS. Without that key it is the
# cocotb tests of COCOTB_TESTS, as `cocotb --netlist` runs them. C4O_GATES so
# that `make gatesim SEED=n` replays a random cocotb test like `make cocotb`.
#
# PDK_ROOT is mounted whether it is in this checkout or not, and made first: a
# bind mount of a path that does not exist is created by the daemon, owned by
# root, and `make pdk` could not write into it.
gatesim:
	mkdir -p $(PDK_ROOT)
	$(C4O_GATES) gatesim

# A picture of the RTL, not of the netlist. `make rtl` runs a full synthesis
# and leaves a wall of generic gates; this stops after `proc; opt`, where the
# design still looks like the code you wrote.
schematic:
	$(C4O_CMD) schematic

pdk:
	@echo "▸ Installing the Sky130 PDK. The first run downloads about 170 MB."
	@# Created here, not by the mount below: a bind mount of a path that does
	@# not exist yet is made by the daemon and owned by root, which the
	@# --user container then cannot write into.
	$(C4O_Q)mkdir -p $(PDK_ROOT)
	$(C4O_Q)$(C4O_BEAT) c4o_beat "installing the Sky130 PDK" $(C4O_PDK) pdk

# --- Physical design, LibreLane as a sidecar container ---
# 1. Stop unless a Docker daemon answers.
# 2. c4o-core validates the config. Before the PDK, not after: `check --for gds`
#    reads config.yaml and the RTL and needs no PDK, so a DESIGN_NAME that names
#    no module costs a second instead of arriving behind a download.
# 3. The PDK.
# 4. LibreLane, on the PDK the step before installed.
#
# The container command mirrors what `librelane --dockerized` runs itself:
# `python3 -m librelane` with the flags, and --user to keep artifacts owned by
# the host user. --manual-pdk stops Ciel from re-resolving the PDK, since the
# `pdk` target already pinned and enabled it.
gds:
	@# LibreLane runs as a sidecar container, so this needs a daemon it can
	@# talk to. Ask the daemon rather than guessing from where we are, so a
	@# container without one and a host without Docker both get the same clear
	@# answer instead of a wall of client error.
	@if ! docker info >/dev/null 2>&1; then \
		echo "❌ [ERROR] 'make gds' needs a working Docker daemon to run LibreLane."; \
		echo "👉 On your host: start Docker Desktop, or check 'docker info'."; \
		echo "👉 In the Dev Container: rebuild it so the docker-in-docker feature installs."; \
		exit 1; \
	fi

	@# Quiet: c4o-core prints this line itself, with its release.
	@$(if $(C4O_QUIET),:,echo "▸ Checking config.yaml and the RTL")
	$(C4O_Q)$(C4O_CMDQ) check --for gds

	@# A run made from these inputs by this LibreLane image has nothing to redo: print its
	@# report instead of waiting minutes for the same numbers. FORCE=1 reruns it,
	@# and so does a partial run, which exists to run a part of the flow again.
	@# What the run was made from is written by `stamp` below, after a whole
	@# flow succeeded and not before.
	@if $(if $(or $(FORCE),$(LIBRELANE_PARTIAL)),false,$(C4O_FLOW) fresh); then \
		echo "▸ LibreLane skipped: the inputs are unchanged since the last run. make gds FORCE=1 runs it again."; \
		$(MAKE) --no-print-directory report C4O_QUIET=$(C4O_QUIET); \
		$(if $(filter raw,$(C4O_PROGRESS)),,if [ -f build/$(DESIGN_NAME).gds ]; then echo "  GDS         build/$(DESIGN_NAME).gds"; fi;) \
	else \
		$(MAKE) --no-print-directory gds-flow; \
	fi
	@# Say what comes after the layout, since a new user does not know. A failed
	@# flow stops the recipe above, so this prints only after a layout.
	@echo
	@echo "Next:"
	@echo "  make site"
	@echo "      puts the results on one page: build/site/index.html"
	@echo "  or push, and CI publishes the page when GitHub Pages is on"

# The part of `make gds` that runs LibreLane.
gds-flow:
	$(C4O_Q)$(MAKE) --no-print-directory pdk
	$(C4O_Q)mkdir -p build
	@# The run about to start is not the one that was stamped. A partial run or a
	@# failed one leaves no stamp, so the next command says it cannot be checked.
	@rm -f $(STAGES_RUN)/$(INPUTS_FILE)
	@# The plan below runs in the LibreLane image with stderr hidden, so docker's
	@# pull of a missing image (1.5 GB) would be minutes of silence. Pull it here,
	@# in the open, with a line every 30 s: docker pull -q prints nothing until it
	@# is done, and its own bars would be a mess in a CI log. A failed pull stops make.
	@if ! docker image inspect $(LIBRELANE_IMAGE) >/dev/null 2>&1; then \
		echo "▸ Downloading the LibreLane image, 1.5 GB, first run only..."; \
		$(C4O_BEAT) c4o_beat "downloading the LibreLane image" sh -c 'docker pull -q "$$0" >/dev/null' $(LIBRELANE_IMAGE) || exit 1; \
	fi
ifeq ($(C4O_PROGRESS),raw)
	$(LIBRELANE_RUN) || { code=$$?; $(call C4O_STAGES,--quiet); exit $$code; }
	@echo "🟢 Post-processing..."
	# Copy the final GDS to the build folder
	cp runs/$(DESIGN_NAME)_run/final/gds/$(DESIGN_NAME).gds build/$(DESIGN_NAME).gds
	@$(call C4O_STAGES,--quiet)
	@$(if $(LIBRELANE_PARTIAL),,$(C4O_FLOW) stamp)
	# runs/ stays where LibreLane put it: a resume looks for the run there, and
	# c4o-core's report and gatesim search it too.
else
	@# LibreLane runs in the background with its whole output in
	@# build/log/librelane.log, and its exit status in build/log/status once it is
	@# done. `c4o progress` follows runs/<tag>/ meanwhile and prints the ledger.
	@# A pipe would lose the status: sh has no pipefail, and the pipe returns 0.
	@#
	@# Ctrl-C: the shell and everything it starts ignore it, and docker passes it
	@# on to the container, so LibreLane stops by itself, the ledger says where,
	@# and this recipe returns after that and not before. Measured: without the
	@# trap, make returned while the container still ran for seconds.
	@#
	@# A full run deletes the previous run first. LibreLane clears it too, with the
	@# flag above, but later than the watcher looks, which then reads the old steps.
	@trap '' INT; \
	mkdir -p build/log; \
	rm -f build/log/status build/log/status.tmp build/log/plan.json build/log/plan.tmp; \
	$(LIBRELANE_PLAN) > build/log/plan.tmp 2>/dev/null \
		&& mv build/log/plan.tmp build/log/plan.json || rm -f build/log/plan.tmp; \
	$(if $(LIBRELANE_OVERWRITE),rm -rf runs/$(DESIGN_NAME)_run;) \
	if [ -t 1 ]; then T=-t; else T=; fi; \
	( $(LIBRELANE_RUN) > build/log/librelane.log 2>&1; echo $$? > build/log/status.tmp; \
	  mv build/log/status.tmp build/log/status ) & \
	$(C4O_LEDGER) progress --run-dir runs/$(DESIGN_NAME)_run --status build/log/status \
		--log build/log/librelane.log --plan build/log/plan.json $(if $(LIBRELANE_PARTIAL),--partial); \
	wait; \
	code=`cat build/log/status`; \
	if [ "$$code" != 0 ]; then $(call C4O_STAGES,); fi; \
	exit $$code
	@cp runs/$(DESIGN_NAME)_run/final/gds/$(DESIGN_NAME).gds build/$(DESIGN_NAME).gds
	@$(if $(LIBRELANE_PARTIAL),,$(C4O_FLOW) stamp)
endif

	@# The flow just measured area, timing and power. Show them rather than
	@# leaving them in a 300-key metrics.json under runs/.
	@$(MAKE) --no-print-directory report C4O_QUIET=$(C4O_QUIET)
ifneq ($(C4O_PROGRESS),raw)
	@echo "  GDS         build/$(DESIGN_NAME).gds"
	@$(call C4O_STAGES,)
endif

# Reads runs/<tag>/final/metrics.json, which `make gds` leaves behind.
report:
	$(C4O_Q)$(C4O_CMDQ) report

# build/site/index.html: the cocotb verdicts, timing, area, power, signoff and the
# layout render, on one page. Shows whatever has been run so far.
site:
	$(C4O_SITE) site

# The images, where this runs and the version of every tool, to paste into a bug
# report. It reads no config, so it works in a repository that does not build.
info:
	@$(C4O_INFO) info

shell:
	$(DOCKER_RUN) -it --entrypoint /bin/bash $(C4O_IMAGE)

# runs/ is deliberately not in here. `make report` and `make gatesim` both read
# the last flow out of it, so wiping it on every clean costs you the ability to
# look at a finished run again. `distclean` is there for when you do mean it.
clean:
	rm -rf build/

distclean: clean
	rm -rf runs/ .c4o/
