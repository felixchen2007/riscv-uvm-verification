# Spike comparison milestone

**The accepted matrix passed all six requested cases.** Fresh native UVM
acceptance for Ibex and PicoRV32 matched an independently executed, pinned
Spike reference at every retirement in both positive timing profiles, at seeds
20261029 and 20261030. Complementary component and utility checks also passed.

| Measured result | Count / outcome |
| --- | --- |
| CPU UVM cases | 4 pass: two processors × two seeds |
| Positive UVM timing profiles | 8 pass, each with 14 checked retirements |
| Positive UVM errors / fatals / assertion failures | 0 / 0 / 0 in every profile |
| Native UVM observation corruption controls | 4 detected; each has exactly one intended `RVFI_RD` error and zero fatals |
| Actual Spike executions | 4 pass, one independent execution per processor/seed image |
| DUT-to-Spike profile comparisons | 8 matches, 14 retirement records per match |
| Spike comparison corruption controls | 4 detected at record 0, specifically in `rd_data` |
| Cross-processor consistency comparisons | 4 matches, distinct from independent ISS checking |
| Actual cocotb component tests | 4 pass: 32/16-register Ibex FF register files at two seeds |
| pytest utility/adapter tests | 75 pass; synthetic format/gating tests are separate from RTL/ISS execution |
| Recorded source identities audited | 245 unchanged SHA-256 entries across all six cases |

## Executed configuration and independence

The DUTs retain their unmodified, locked snapshots: Ibex
`38c070939183cc10940b66c8e9e04eeca6b65470` and PicoRV32
`ef203c2b0a3fb793280f5114941416c425c5b461`. Their parameter profiles and native
UVM environment remain those described in [dual-processor-results.md](dual-processor-results.md).
The primary simulator was Vivado XSim 2025.2 with UVM 1.2. Targeted component
tests used cocotb 2.0.1 and Questa Intel FPGA Starter 2024.3 VPI.

The reference is official Spike v1.1.0 at
`530af85d83781a3dae31a4ace84a573ec255fefa`, built locally under Ubuntu WSL2
with GCC 15.2.0. The unchanged upstream implementation executes through
`processor_t::step(1)`; the thin project bridge records its actual commit state.
The bridge takes the shared input image and configuration, without any DUT
retirement values or UVM-predicted results. Input-image identity is checked for
every comparison. Both positive profiles use the same reference execution
because their architectural input and initial state are identical.

The shared execution window begins directly at PC `0x80` in machine mode with
zero registers and RAM before image loading. It contains 14 aligned 32-bit RV32I
instructions and ends with a store of `1` to `0x1004`. The reference ISA is
`rv32ic` for Ibex and `rv32i` for PicoRV32; compressed execution is not exercised.
The strict comparator checks order, hart, PC, instruction, register writes,
word-memory effects and trap/halt/interrupt state. It rejects missing or
reordered records and requires the reference completion marker and terminal
signature. [spike.md](spike.md) defines the bounded event and memory policy.

The accepted bridge executable SHA-256 is
`9448ea50cf31964a81b03e3e0fdf98d350b16eba9ef619e9feeb32eaf4257ab1`.
Its bridge source SHA-256 is
`def829bb43cd4c67667e59303cfe86190fbf60a8f4d0607e63e63a95d590708d`.
The source archive SHA-256 is
`07c879a3b2ab0b0d5631fdc91265f252607eb9c3e38ea1eaa9354d420c43fcfa`.
Build manifests retain the compiler, options, upstream revision and all other
reference hashes; each reference verifies its artifacts before and after running.

## Coverage and controls

Every positive UVM profile exercised one load, two stores, one taken branch,
one untaken branch and one jump. SV constrained-random **memory timing** executed
in XSim: Ibex reported 20/21 randomization calls for no-added-delay/stalled,
and PicoRV32 reported 19/19, at both seeds. Each smoke covergroup reported
87.50%; taken BNE and untaken BEQ remain holes. These per-run values have not
been averaged or merged. The instruction skeleton remains fixed, with one
seed-derived operand; random instruction generation and ISA closure remain work.

The UVM control corrupts a sampled RVFI writeback and requires the intended
scoreboard error. The independent comparison control corrupts a copy of one
normalized DUT writeback while keeping Spike's result unchanged. It requires
the specific `rd_data` mismatch. These eight controls qualify observation and
comparison paths; they are not RTL mutations or mutation-score evidence.

One earlier full attempt finished at 5/6 because two complementary Questa
sessions overlapped and its node-locked Starter license rejected one session.
All its CPU/Spike cases passed, but the aggregate remains recorded as failed.
The scheduler now serializes Questa component cases while permitting concurrent
XSim workers. The accepted matrix was rerun from fresh output directories with
that scheduler; none of the failed attempt was relabeled as passing.

## Reproduce and inspect

From the project folder in PowerShell:

```powershell
.\build\python-env\Scripts\python.exe scripts/build_spike.py --jobs 8
.\build\python-env\Scripts\python.exe scripts/run_regression.py --config config/regressions/spike-smoke.json
.\build\python-env\Scripts\python.exe -m pytest -q
```

The accepted output is `build/regressions/spike-milestone-verified/`, including
`summary.json`, `report.md` and the checked `audit.json`. Retained compact copies
are in `evidence/spike/`: raw UVM logs and RVFI, shared images, normalized DUT
and Spike records, raw Spike JSONL/commit logs, corruption controls, source/build
identities and the pytest XML. `artifact-sha256.json` indexes the retained files.
Coverage databases and executables remain in the ignored build folder.
Original manifest paths and executor timestamps are preserved.

Raw UVM-only `results.json` correctly reports that its command did not execute
Spike; the enclosing case and separate reference artifacts record that later
execution. Standalone `run_spike_tests.py` replays an image/comparison without
claiming a fresh UVM run. Missing or stale builds and failed/incomplete reference
executions cannot become a requested `--spike` acceptance pass.

This milestone verifies the existing bounded smoke against an independent ISS.
Live DPI integration, exceptions, interrupts, debug, CSRs, broader instruction
programs, SoC peripherals/RAL, RTL mutation campaigns and optional FPGA work
remain outside this result. The next useful step is broader legal programs and
directed branch cases, checked through the same UVM and Spike contracts.
