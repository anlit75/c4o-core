# Use Ubuntu 22.04 LTS as the base image
FROM ubuntu:22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Update package lists and install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    make \
    git \
    yosys \
    verilator \
    iverilog \
    && rm -rf /var/lib/apt/lists/*

# Install Python libraries
# Pin cocotb to major version 1.8 to prevent breaking changes
RUN pip3 install --no-cache-dir \
    "cocotb==1.8.*" \
    pytest \
    volare

# Create the application directory
WORKDIR /c4o

# Copy the repository contents into the container
COPY . /c4o

# Set the entrypoint to the Python wrapper script
ENTRYPOINT ["python3", "/c4o/scripts/entrypoint.py"]
