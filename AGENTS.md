# Configurable RISC-V verification framework

The project has three responsibilities.
1. SystemVerilog UVM owns CPU acceptance and protocol/scenario/coverage checking.
2. Spike supplies independent architectural checking. The optional live DPI-C
   subscriber uses a native Windows C++ transport and persistent WSL Spike
   service for normal smoke/corners/random programs. Reset/IRQ events remain
   outside the live contract; retain scoped native and offline evidence.
3. Python owns automation: builds, regressions, seeds, mutations and reports.
   Built-in unittest checks that automation and its checking utilities. Do not add cocotb
   component tests or a second Python CPU environment.
Ibex and PicoRV32 have physical adapters and share the UVM architectural
checker. Future planned profiles must not be reported as verified without
actual DUT execution. Cross-processor consistency is not Spike execution.

Keep this independent project separate from the surrounding Tensor Memory
Accelerator repository. Use native UVM 1.2 under `tb/uvm` for RTL acceptance.
The user prefers Vivado XSim for host simulation and retains the DE10-Lite as
an optional FPGA target. Any DE10-Lite implementation uses Quartus.

Run `scripts/run_uvm_tests.py` (default XSim), or `scripts/run.ps1` on Windows.
`--full` enables constrained-random **memory timing** and the smoke covergroup.
Do not call the fixed program skeleton a random instruction generator.
The separate `random` profile requires `--full` and executes 64 SV-constrained-
random instructions after a directed prologue. Record its 64 instruction and 8
schedule randomization calls separately from memory timing. It has no Starter
PRNG fallback. Its control flow is directed/bounded, not randomized. Check the
emitted body's legality, same-seed replay and cross-seed diversity; report body-
only ALU coverage separately from the directed prologue's coverage.
Questa is an explicit `--sim questa` alternative. Its installed Starter license
supports UVM base classes but denies randomize and covergroups; use seeded
procedural mode there. Never silently downgrade a failed full run.

Preserve the unmodified vendor snapshots and their `vendor/*.lock.json` files. Record
configuration, seed, source hashes, UVM counts, scenarios, simulator/assertion
errors and intended corruption-control diagnostic. A compile is not a pass.
The observation corruption control is not an RTL mutation campaign. Spike,
ISA coverage closure and optional FPGA results need separate execution evidence.

Use `scripts/run_regression.py` for isolated multi-seed scheduling. Its worker
cases must invoke the native UVM suite. Use unittest for automation and shared
checking utilities. Preserve qualification evidence and its original scope. Keep
common processor/program/retirement/result contracts versioned, reject missing
or partial traces, and never average coverage percentages across seeds.
The common comparator and synthetic fixtures do not prove Spike execution.
