"""Complementary cocotb tests of the actual upstream Ibex FF register file."""
import os
import random
import cocotb
from cocotb.triggers import Timer

from verification.reference.register_file import RegisterFileModel


@cocotb.test()
async def register_file_contract(dut):
    seed = int(os.environ["RF_TEST_SEED"])
    count = 16 if int(os.environ["RF_RV32E"]) else 32
    model = RegisterFileModel(count)
    rng = random.Random(seed)
    dut.clk.value = 0
    dut.rst_n.value = 0
    dut.write_enable.value = 0
    dut.read_a.value = 0
    dut.read_b.value = 0
    dut.write_address.value = 0
    dut.write_data.value = 0

    async def tick():
        dut.clk.value = 0
        await Timer(5, unit="ns")
        dut.clk.value = 1
        await Timer(5, unit="ns")
        dut.clk.value = 0

    async def check(a, b):
        dut.read_a.value, dut.read_b.value = a, b
        await Timer(1, unit="ns")
        assert int(dut.data_a.value) == model.read(a), f"seed={seed} read_a={a}"
        assert int(dut.data_b.value) == model.read(b), f"seed={seed} read_b={b}"
        assert int(dut.error.value) == 0

    await tick()
    dut.rst_n.value = 1
    for a in range(count):
        await check(a, count - a - 1)
    # Every legal register gets a directed write; x0 must remain zero.
    for a in range(count):
        dut.write_enable.value = 1
        dut.write_address.value = a
        dut.write_data.value = 0xa5a50000 | a
        await tick()
        model.write(a, 0xa5a50000 | a)
        await check(a, 0)
    for _ in range(128):
        address = rng.randrange(count)
        value = rng.getrandbits(32)
        enable = bool(rng.randrange(4))
        a, b = rng.randrange(count), rng.randrange(count)
        dut.write_enable.value = int(enable)
        dut.write_address.value = address
        dut.write_data.value = value
        await check(a, b)  # Before the clock: old architectural values.
        await tick()
        model.write(address, value, enable)
        await check(address, b)  # After the clock: committed values.
    dut.write_enable.value = 0
    for a in range(count):
        await check(a, count - a - 1)
    dut.rst_n.value = 0
    await tick()
    model.reset()
    dut.rst_n.value = 1
    for a in range(count):
        await check(a, 0)
    dut._log.info("RF_COMPONENT_PASS seed=%d registers=%d random_cycles=128", seed, count)
