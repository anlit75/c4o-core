# Ubuntu 24.04 LTS, pinned by digest so every rebuild resolves to this exact base
FROM ubuntu:24.04@sha256:008173c23f95b170204355c12626cb5a965d779a7e1283b09e9cffbb1bf33ca3

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Update package lists and install dependencies
# libpython3.12t64 carries libpython3.12.so.1.0, which the python3 package does
# not pull in: nothing in a plain Python install embeds the interpreter. cocotb
# does -- its GPI dlopens libpython at runtime -- so without this, cocotb-config
# --libpython finds nothing and the simulator runs no tests while exiting 0.
# Left unpinned so apt matches whatever python3 it resolves; the 't64' is the
# 64-bit time_t transition, not a typo.
# graphviz supplies the `dot` that yosys's `show` shells out to for the
# `schematic` command. Unpinned, like libpython above and unlike the EDA
# tools: it renders a picture of the design rather than deciding anything
# about it, so a newer dot draws the same circuit with slightly different
# splines. Pinning it would buy reproducibility nobody is checking.
# The EDA tools are pinned to the versions 24.04 ships. 22.04 carried Yosys 0.9
# (2019), Verilator 4.038 and Icarus 11.0; these are 0.33, 5.020 and 12.0.
# A pin that stops resolving fails the build loudly, which is the point -- an
# unpinned install drifts silently instead.
# libgmp10 is sv2v's only interesting shared dependency, and nothing else here
# drags it in -- yosys, verilator and iverilog all link without it, checked with
# apt-cache depends rather than assumed. Unpinned for the reason graphviz is.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    libpython3.12t64 \
    make \
    git \
    yosys=0.33-5build2 \
    verilator=5.020-1 \
    iverilog=12.0-2build2 \
    graphviz \
    libgmp10 \
    && rm -rf /var/lib/apt/lists/*

# sv2v turns SystemVerilog into the Verilog-2005 the rest of this image reads.
# Generated register blocks are why it is here: PeakRDL emits SystemVerilog with
# unpacked structs, and both of the tools that matter refuse them --
#
#   yosys 0.33:   ERROR: Only PACKED supported at this time
#   iverilog 12:  sorry: Unpacked structs not supported.
#
# -- while sv2v's output synthesises and simulates clean. It ships as one
# static-ish binary, so there is no build to do and nothing to pin but the
# release itself.
#
# ADD fetches it without needing curl in the image; the checksum is verified
# and the archive unpacked with the python3 that is already here, rather than
# adding ca-certificates and unzip for two lines of Dockerfile.
ADD https://github.com/zachjs/sv2v/releases/download/v0.0.13/sv2v-Linux.zip /tmp/sv2v.zip
RUN python3 -c "\
import hashlib, sys; \
want = '552799a1d76cd177b9b4cc63a3e77823a3d2a6eb4ec006569288abeff28e1ff8'; \
got = hashlib.sha256(open('/tmp/sv2v.zip','rb').read()).hexdigest(); \
sys.exit(0) if got == want else sys.exit(f'sv2v.zip is {got}, expected {want}')" \
    && python3 -m zipfile -e /tmp/sv2v.zip /tmp/sv2v \
    && install -m 0755 /tmp/sv2v/sv2v-Linux/sv2v /usr/local/bin/sv2v \
    && rm -rf /tmp/sv2v /tmp/sv2v.zip \
    && sv2v --version

# 24.04 marks its Python installation as externally managed (PEP 668), so the
# Python tooling lives in a venv rather than fighting apt over site-packages.
# Putting the venv first on PATH also keeps `ciel` resolvable for `c4o-core pdk`.
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python libraries
# cocotb 1.8 predates Python 3.12 support; 1.9 is the first line that carries it.
# Ciel supersedes Volare as the PDK manager and is what LibreLane itself uses.
# pyyaml arrives transitively via Ciel, but the entrypoint imports it directly,
# so it is pinned here rather than left to another package's dependency tree.
#
# pyuvm is the UVM in Python. It sits on cocotb rather than replacing it, and
# declares cocotb>=1.6,<3.0, so it costs nothing at the pin above.
#
# The PeakRDL trio generates a register block and its pyuvm register model from
# one SystemRDL file, which is the only way those two stay in step: a hand-
# written RAL that drifts from the RTL is a bug no testbench can catch, because
# both sides agree with each other and neither agrees with the design. They
# bring numpy and systemrdl-compiler with them, which is most of the ~84MB this
# block adds -- paid once, in an image that already carries three EDA tools.
RUN pip install --no-cache-dir \
    "cocotb==1.9.*" \
    "pytest==8.*" \
    "ciel==2.6.1" \
    "pyyaml==6.0.*" \
    "pyuvm==5.0.*" \
    "peakrdl==1.5.*" \
    "peakrdl-regblock==1.3.*" \
    "peakrdl-pyuvm==0.9.*"

# Create the application directory
WORKDIR /opt/c4o-core

# Copy the repository contents into the container
COPY . /opt/c4o-core

# Set the working directory for the user
WORKDIR /workspace

# Set the entrypoint to the Python wrapper script
ENTRYPOINT ["python3", "/opt/c4o-core/scripts/entrypoint.py"]
