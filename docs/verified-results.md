# Verified initial milestone — 2026-10-29

This is the retained M0 historical record. The subsequent architecture and
multi-seed/component milestone is documented in
[two-layer-results.md](two-layer-results.md), with separate source hashes and
evidence. The results below are not relabeled as later framework runs.

The initial Ibex UVM suite **passed in Vivado XSim 2025.2**, using the installed
precompiled UVM 1.2 library. Both the default seeded mode and `--full` mode ran
two positive profiles and an independent expected-failure corruption control.
This is execution evidence, not a compilation-only result.

## Configuration

- DUT: upstream `ibex_core` and `ibex_register_file_ff`, unmodified selected
  snapshot of v2.1.0 commit `38c070939183cc10940b66c8e9e04eeca6b65470`.
- RV32E=0, RV32MNone, RV32BNone, ICache=0, ICacheECC=0, SecureIbex=0,
  WritebackStage=0, BranchPredictor=0, PMPEnable=0, ResetAll=1.
- 100 MHz simulation clock; reset held for eight clocks; boot address 0;
  first expected PC `0x80`. This revision's RVFI order starts at 1.
- Seed: **20261029** for every case in this milestone.
- `no_added_delay`: zero additional randomized delays, with the responder's
  fixed minimum response latency. `stalled`: grant/response delays in 0–3 clocks.
- Full mode randomizes **memory timing only**. Instruction ordering is a fixed
  skeleton, with one operand deterministically derived from the seed.
- XSim compatibility wrapper suppresses unused no-cache DPI exports while
  preserving standard RTL assertion macros. See xsim.md.

## Executed cases

| Mode | Profile | Retired | UVM errors / fatals | Instruction / data grant stalls | Result |
| --- | --- | ---: | --- | --- | --- |
| Seeded PRNG | no_added_delay | 14 | 0 / 0 | 33 / 0 | Pass |
| Seeded PRNG | stalled | 14 | 0 / 0 | 85 / 5 | Pass |
| SV constrained-random timing | no_added_delay | 14 | 0 / 0 | 33 / 0 | Pass |
| SV constrained-random timing | stalled | 14 | 0 / 0 | 81 / 6 | Pass |

Every positive case checked one load, two stores, one taken branch, one untaken
branch and one jump. The checked signature was `1` stored at `0x1004`.
All positive simulations exited with code 0, UVM warnings=0, and no detected
simulator or assertion errors. Retirement traces were checked for the exact
14-PC path and orders 1–14. No physical board or JTAG was accessed.

Each mode's corruption control flipped bit 0 of the first sampled nonzero
RVFI register write. Both controls produced the intended `RVFI_RD` diagnostic,
exactly **1 UVM error, 0 UVM fatals**, and no pass marker. No DUT source or
reference-model state was changed. These are checker qualification results,
not RTL mutant kills.

## Functional coverage and randomization

The XSim full-mode positive cases executed **20** and **21** successful
`randomize()` calls respectively. The smoke covergroup reported **87.50%** in
each case. It includes seven opcode-family bins, branch direction, BEQ/BNE kind
and the kind/direction cross. Taken BEQ and untaken BNE were exercised; untaken
BEQ and taken BNE remain cross holes. No ISA or project coverage closure is
claimed. XSim coverage databases are retained under `build/xsim/full/coverage`.

Default mode executed the explicit seeded PRNG and procedural counters. It did
not execute SV `randomize()` or covergroups. The full-mode statements above
apply to XSim; they do not change the Questa Starter license findings.

## Tools and reproducibility

Vivado's tested executable directory is
`D:/AMDDesignTools/2025.2/Vivado/bin`. Python 3.12.14 and Git 2.55.0 were used.
Quartus Prime Lite 24.1std.0 Build 1077 was found and version-checked.

Questa Intel Starter 2024.3 separately executed the UVM class/factory/phase
probe with UVM errors/fatals=0/0. Its randomize and covergroup probes compiled
but simulation was denied the `svverification` license feature. Compilation of
those probes is not counted as feature execution. These are capability probes,
not Ibex DUT smoke passes.

The standard `spike`, `riscv32-unknown-elf-gcc` and `riscv64-unknown-elf-gcc`
commands were not found on PATH. The smoke uses directly encoded instruction
words and does not require GCC. Spike comparison has not run; other compiler
installations bundled with Vivado were not used for this milestone.

The two XSim manifests record the full tested configuration, seed, simulator
identity, exact compile list, source hashes, scenario results, UVM counts and
corruption-control outcome. Source hashes were checked again against the final
simulation sources. The upstream lock verifies each vendored file before build.
Retained evidence lives under `evidence/initial/`; current local logs, argument
files, program images and retirement traces live under `build/xsim/`.

The compile log contains one benign `DV_FCOV_DISABLE` macro redefinition warning
caused by the scoped compatibility wrapper. No assertion/coverage suppression
command-line flags are used. AMD's precompiled UVM library reports `UVM_NO_DPI`,
so DPI-based UVM component-name checking is unavailable; native UVM components
and the supported SV features above executed successfully.

## Remaining milestones

Spike retirement comparisons, random instruction generation, broader RV32I/C/M
and CSR/exception coverage, reset/interrupt agents and actual RTL mutation
campaigns remain planned work. No FPGA bitstream, timing closure, hardware
self-test, ASIC readiness or full RISC-V compliance is claimed.
