# Ibex / PicoRV32 milestone — 2026-10-29

**Both processors passed the shared native UVM smoke contract in Vivado XSim
2025.2 / UVM 1.2.** The dual-processor matrix used seeds 20261029 and 20261030,
full-mode constrained-random memory timing and two workers. All six requested
matrix cases passed: four CPU UVM cases and two complementary Ibex component
cases. A CPU case contains two positive timing runs and its corruption control.

## Actual DUTs and configuration

Ibex remains pinned at `38c070939183cc10940b66c8e9e04eeca6b65470` with its
existing RV32IC-capable no-M/B/cache/security/writeback-stage smoke configuration.
Its first retirement is at `0x80` and its native RVFI order begins at 1.

PicoRV32 is the unmodified upstream source at
`ef203c2b0a3fb793280f5114941416c425c5b461`, retained with its ISC license and
per-file source lock. The tested native core has 32 registers, dual-port reads,
no compressed/M/PCPI/IRQ/counters/debug trace, `REGS_INIT_ZERO=1`, reset PC
`0x80`, and no automatic stack initialization (`STACKADDR=0xffffffff`). All
parameters are recorded in `config/picorv32.json` and the wrapper source.
`RISCV_FORMAL` enables RVFI. `FORMAL` and TESTBUG macros are not enabled; these
are simulation results, not formal proof. Native RVFI order begins at 0.

## Reuse implemented

Both DUTs use the exact same program/image object, delay items and sequences,
passive RVFI monitor/interface, TLM record types, `riscv_scoreboard`, private ISA
model and smoke covergroup. `riscv_env_base` supplies common checking; its Ibex
and Pico subclasses connect processor-specific physical agents. The old
`ibex_test.svh` include and `ibex_scoreboard` type alias remain available.

Pico's unified `mem_valid` / `mem_ready` interface completes atomically. Its
driver combines shared grant and response delay choices before asserting
ready; it does not fabricate an Ibex-like delayed response on the physical bus.
The independent native monitor publishes accepted instruction reads and data
request/response observations into the shared checker. `err=0` in these common
records reflects the lack of an error pin on this native bus; bus-error testing
is outside this smoke. Protocol-specific SVA checks held requests/write data,
known controls/read data, valid completions and the absence of unexpected traps.

## CPU results

Every positive run checked 14 retirements: arithmetic/LUI, one load, two stores,
a taken BEQ, an untaken BNE and a JAL. The terminal signature was `1` stored at
`0x1004`. All positive UVM warnings/errors/fatals were 0/0/0, simulator exits
were 0 and no assertion errors were detected.

| Processor | Seed | No-added-delay instruction / data stalls | Stalled instruction / data stalls | Positive runs | Corruption control |
| --- | ---: | --- | --- | ---: | --- |
| Ibex | 20261029 | 33 / 0 | 81 / 6 | 2 pass | Detected |
| Ibex | 20261030 | 33 / 0 | 80 / 5 | 2 pass | Detected |
| PicoRV32 | 20261029 | 0 / 0 | 39 / 13 | 2 pass | Detected |
| PicoRV32 | 20261030 | 0 / 0 | 47 / 9 | 2 pass | Detected |

The four observation corruption controls each produced exactly one intended
`RVFI_RD` UVM error, zero fatals and no pass marker. They change a sampled
writeback bit, not DUT RTL or reference state. They are not RTL mutation kills.

Full-mode positive runs executed successful SV randomization: Ibex reported
20/21 calls for no-added-delay/stalled, and Pico reported 19/19, at each seed.
Each smoke covergroup reported 87.50%; taken BNE and untaken BEQ remain cross
holes. The instruction skeleton is fixed and only one operand is seed-derived.
No random instruction generation, merged bin coverage or coverage closure is
claimed. Pico's initial seeded-procedural bring-up also passed its two profiles
and corruption control; its separate pre-matrix source identity remains in
`build/picorv32-bringup/results.json`.

## Cross-processor and preservation checks

The shared normalizer translates native origins to canonical order 0–13,
preserving `native_order`. For each seed, both processors emitted the same
program-image hash. All four cross-processor trace comparisons passed: both
timing profiles at both seeds, 14 retired records per comparison. Each
processor's two timing traces also matched architecturally at each seed.
Only meaningful register/memory effects and observed trap/halt/interrupt state
are compared; native order origins and fetch timing are not architectural
differences. This is DUT-to-DUT consistency plus independent UVM subset
prediction, not Spike execution or complete RISC-V compliance.

The preserved cocotb flow passed four actual Ibex register-file component tests
(32/16 registers at two seeds). The Python utility suite passed **42 tests**,
including new zero/one-origin normalization and cross-processor mismatch/missing
case controls. These utility fixtures are synthetic format tests, not CPU or
ISS simulation evidence.

## Reproduce and evidence

```powershell
.\scripts\run.ps1 --processor picorv32_rv32i --full
.\build\python-env\Scripts\python.exe scripts/run_regression.py --jobs 2 --include-cocotb
```

The default regression now selects both processors. Current results are in
`build/regressions/dual-processor-milestone/summary.json` and `report.md`.
Compact retained evidence is under `evidence/dual-processor/`, including raw
manifests, console logs, images, native/canonical traces, common case envelopes,
cross-processor results and pytest XML. Each manifest records source hashes,
processor identity/configuration, seed, simulator, scenarios, UVM counts and
corruption-control result. Both vendor locks are checked and source identities
are verified unchanged during execution. M0 and M1 evidence remains historical
and untouched.

The next independent-reference milestone is actual Spike execution. Broader ISA,
CSR/exception/IRQ behavior, reset scenarios, instruction randomization, RAL,
RTL mutations, licensed simulator CI and FPGA implementation remain outside
this accepted smoke scope.
