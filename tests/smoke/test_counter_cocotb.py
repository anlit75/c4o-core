"""cocotb equivalent of tb_counter.v: the same design, driven from Python."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge


async def start(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0


@cocotb.test()
async def reset_clears_the_count(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    assert dut.count.value == 0, f"count was {dut.count.value} while rst asserted"


@cocotb.test()
async def counts_up_by_one(dut):
    await start(dut)
    await RisingEdge(dut.clk)
    previous = int(dut.count.value)
    for _ in range(5):
        await RisingEdge(dut.clk)
        expected = (previous + 1) % 16
        assert int(dut.count.value) == expected, (
            f"count went {previous} -> {int(dut.count.value)}, expected {expected}"
        )
        previous = expected


@cocotb.test()
async def spans_exactly_four_bits(dut):
    # Two weaker versions of this test were caught by mutating the design:
    #   - "repeats after 16 cycles" passes on a 3-bit counter, which repeats twice
    #   - "0..15 all appear within 16 cycles" passes on a 5-bit counter, whose
    #     first 16 values are also 0..15
    # Running two full periods and requiring the set to be exactly 0..15 rules
    # out both: a narrower counter misses values, a wider one adds them.
    await start(dut)
    seen = set()
    for _ in range(32):
        await RisingEdge(dut.clk)
        seen.add(int(dut.count.value))
    assert seen == set(range(16)), f"counter covered {sorted(seen)}, expected 0..15"
