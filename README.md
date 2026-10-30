# RISC-V CPU Verification with SystemVerilog UVM

Independent UVM 1.2 verification of pinned **lowRISC Ibex** and **PicoRV32** processors, with reusable agents, constrained-random stimulus, an architectural scoreboard, assertions, native functional coverage, and independent Spike comparisons.

**Bounded CPU v1 is complete.** This is a single-hart verification environment reused across two processor implementations. SoC peripherals and RAL are outside the accepted scope.

## Verified results

| Executed check | v1 result |
| --- | ---: |
| Clean positive native UVM profiles | 41 passed |
| CPU regression cases | 16 passed |
| Reset, factory and Ibex interrupt scenarios | 5 passed |
| Full retirement traces matched against Spike | 40 |
| Actual pinned Spike executions | 22 |
| Selected RTL mutations detected | 8 / 8 |
| Declared functional-coverage bins | 60 / 60 closed |
| Python utility tests | 171 passed |
| Complementary cocotb register-file variants | 4 passed |

All clean UVM profiles reported zero errors and fatals. The release also detected 23 native observation-corruption controls and 22 reference-comparison controls. These controls are separate from the eight actual RTL mutations.

The 60 bins cover the declared opcode/branch, directed corner, random-body instruction-family, ALU-operation and scratch-word goals. Native XCRG database merges closed those goals per CPU and combined. These results do not claim full ISA compliance, RTL code-coverage closure or a broad mutation score.

[Detailed measured results](docs/v1-results.md) · [Architecture and demonstration guide](docs/v1.md) · [Archived v1 evidence](evidence/v1/README.md)

## Verification architecture

Exactly two primary layers:

1. **SystemVerilog UVM** owns CPU acceptance: sequences, sequencers, drivers, passive monitors, TLM observations, independent prediction, assertions and covergroups.
2. **Python verification and automation** combines targeted cocotb component tests, pytest utilities, seeded regression scheduling, input/trace audits, the pinned Spike reference, mutation orchestration and reports.

Ibex uses split instruction/data memory agents. PicoRV32 uses a native valid/ready adapter. Both publish common transaction types to the same architectural scoreboard. Expected register, memory and PC state is computed independently; observed DUT results never become expected values.

A virtual sequencer coordinates memory-policy and reset/IRQ agents. Executed factory overrides select a maximum-delay sequence. Reset tests abort pending work and check a complete restart; an Ibex-only interrupt program checks the external event, cause, saved PC, handler and MRET.

## Reproduce v1

Tested tools: Windows, Vivado/XSim 2025.2 with UVM 1.2, Questa Intel FPGA Starter 2024.3 for cocotb VPI, Python 3.12, cocotb 2.0.1 and pytest 8.4.2. The independent Spike executable runs in Ubuntu WSL.

From this repository in PowerShell:

```powershell
.\scripts\v1.ps1
```

This runs utility tests, both processor matrices, advanced native scenarios, both RTL mutation campaigns and native coverage export/merging. Every run uses fresh output folders and writes a fail-closed release manifest and report under `build/releases/`.

For a first setup, install the simulators and WSL build prerequisites, then build the pinned reference with `./scripts/v1.ps1 -BuildSpike`. The launcher creates a local Python environment if needed. See [setup and replay details](docs/v1.md) and [the Spike build contract](docs/spike.md).

Run an individual UVM test:

```powershell
.\scripts\run.ps1 --full
.\scripts\run.ps1 --processor picorv32_rv32i --program corners --full
.\scripts\run.ps1 --program random --full --seed 20261031
.\scripts\run.ps1 --program corners --scenario reset --full
.\scripts\run.ps1 --program irq --scenario irq --full
```

The `random` program executes 64 actual SV-constrained-random body instructions and eight randomized schedules after a directed prologue. Control flow remains directed and bounded. The four seeds are 20261029-20261032; same-seed replay and cross-CPU input equality are checked separately from cross-seed diversity.

The installed Questa Starter license denies SV randomize and covergroups. Its explicit procedural UVM alternative is available for the original smoke; it is not the full-mode v1 evidence. CPU acceptance above uses XSim.

## Source and evidence integrity

- Ibex v2.1.0: `38c070939183cc10940b66c8e9e04eeca6b65470`.
- PicoRV32: `ef203c2b0a3fb793280f5114941416c425c5b461`.
- Official Spike v1.1.0: `530af85d83781a3dae31a4ace84a573ec255fefa`.

Vendor sources remain unchanged and are checked against source locks. Each mutant replaces one compiled RTL file with an isolated checked copy; its patch, first intended diagnostic and independent retirement divergence are retained. Compile-invalid and infrastructure failures never count as detections.

The local v1 release verified 275 source/configuration identities. Its archive hashes 2,200 artifacts, including tested verification sources, raw traces, native UVM transcripts, Spike records, mutations and coverage reports. Historical milestones retain their original scopes. Archived commands retain machine-specific execution paths; current launchers discover installed tools or accept path overrides. Exact source/evidence bytes are preserved by Git attributes.

## Scope and limits

The tested programs cover a bounded RV32I subset. Ibex compressed/M/B features, broader exceptions, debug, randomized control flow, multi-hart execution and SoC/RAL verification are outside v1. The Ibex IRQ scenario is checked natively; asynchronous interrupt synchronization with Spike is not implemented. PicoRV32's custom IRQ ISA is excluded.

This is host simulation. No FPGA is required. The optional DE10-Lite implementation would use Quartus.

The manual GitHub Actions configuration separates hosted utility checks from a native job requiring a self-hosted Windows runner with the installed simulators and WSL reference. Local results are not relabelled as CI execution.

## Repository layout

```text
vendor/                 pinned upstream RTL and locks
 tb/uvm/                native CPU acceptance environment
 tb/cocotb/             targeted register-file tests
verification/           shared contracts, audits and reference helpers
scripts/                simulation, regression, mutation and release entry points
config/                 processor, program and campaign configurations
tests/                  utility and targeted-model tests
docs/                   architecture, scope, setup and measured results
evidence/               immutable historical execution evidence
build/                  ignored local tools, environments and fresh run outputs
```

Project code is Apache-2.0. Vendored sources retain their original licenses and notices; see [THIRD_PARTY.md](THIRD_PARTY.md).
