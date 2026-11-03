# RISC-V CPU Verification

A SystemVerilog UVM environment verifies the pinned Ibex and PicoRV32 cores.
A C++ DPI-C bridge steps Spike during simulation and checks each retirement.
Python orchestrates the builds, regressions, trace comparisons, and coverage
reports using its standard library.

| Qualification | Result |
| --- | ---: |
| Python automation checks | 175 passed |
| CPU, program and seed cases | 12 passed |
| Positive UVM runs | 24 passed |
| Live Spike retirement matches | 2,020 |
| Injected live checker mismatches detected | 36/36 |
| Declared functional bins hit | 60/60 |

The qualification exercises smoke, directed corners, and constrained-random
programs, with four random seeds across both CPUs. Each case runs with and
without added memory stalls. The live path checks bounded RV32I retirement
behavior. The native UVM scenarios separately cover reset and Ibex interrupts.
See the [qualification report](evidence/qualification/report.md).

## Run the qualification

```powershell
.\scripts\verify.ps1
```

The launcher builds pinned Spike and its live adapter, runs the checks, and
writes a report and machine-readable manifest under `build/releases/`.
Setup requires Git, Python 3.12 or later, Vivado XSim with UVM 1.2, and an
Ubuntu WSL build environment. See the [setup guide](docs/setup.md).

- [Architecture](docs/architecture.md) explains the UVM agents, shared scoreboard, and processor adapters.
- [Live Spike guide](docs/spike-dpi.md) describes the Windows DPI-C transport and WSL reference process.
- [Verification plan](docs/verification-plan.md) describes coverage, controls, and the supported scenarios.
- [RTL mutation runner](docs/mutations.md) describes the separate mutation campaigns.

The project targets CPU simulation. The vendored sources retain their
upstream licenses and pinned revision records. See [third-party sources](THIRD_PARTY.md).
