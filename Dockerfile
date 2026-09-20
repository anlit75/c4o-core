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
# The EDA tools are pinned to the versions 24.04 ships. 22.04 carried Yosys 0.9
# (2019), Verilator 4.038 and Icarus 11.0; these are 0.33, 5.020 and 12.0.
# A pin that stops resolving fails the build loudly, which is the point -- an
# unpinned install drifts silently instead.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    libpython3.12t64 \
    make \
    git \
    yosys=0.33-5build2 \
    verilator=5.020-1 \
    iverilog=12.0-2build2 \
    && rm -rf /var/lib/apt/lists/*

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
RUN pip install --no-cache-dir \
    "cocotb==1.9.*" \
    "pytest==8.*" \
    "ciel==2.6.1" \
    "pyyaml==6.0.*"

# Create the application directory
WORKDIR /opt/c4o-core

# Copy the repository contents into the container
COPY . /opt/c4o-core

# Set the working directory for the user
WORKDIR /workspace

# Set the entrypoint to the Python wrapper script
ENTRYPOINT ["python3", "/opt/c4o-core/scripts/entrypoint.py"]
