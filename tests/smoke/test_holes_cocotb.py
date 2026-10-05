"""Drives holes.v with sel always high, so its else branch is never run."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge


@cocotb.test()
async def counts_while_selected(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.sel.value = 1
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    for _ in range(8):
        await RisingEdge(dut.clk)
    assert dut.hole_marker.value == 0
