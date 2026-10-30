# Two-layer verification roadmap

Each milestone requires actual execution evidence, checked source identities
and an explicit feature/configuration scope. Planned items are not completion
claims. The owner has accepted bounded CPU v1 as the finished project scope.
SoC peripherals and RAL are not planned or required. FPGA/ASIC implementation
is also outside this completed scope.

| Milestone | Deliverable | Status / acceptance |
| --- | --- | --- |
| M0 — Preserve baseline | Actual Ibex RTL, native UVM agents/driver/sequencer/passive monitors, independent scoreboard, SVA, bounded SV coverage and corruption control | Verified initial milestone retained in `evidence/initial`; two modes with explicit tool limits |
| M1 — Two layers and shared contracts | Common processor profiles, trace/result schemas, targeted cocotb, pytest, multi-seed scheduling, isolated parallel outputs and reports | Implemented in this update; new run evidence is recorded separately from M0 |
| M2 — PicoRV32 baseline | Pin source/license; native memory adapter; reset/ISA configuration; RVFI adapter; same common RV32I smoke and reference contract | Implemented; `dual-processor-results.md` records both cores' positive/control runs and cross-processor comparisons |
| M3 — Advanced UVM scenarios | Reusable CPU config/adapter, virtual sequencer, coordinated reset/interrupt scenarios, demonstrated factory overrides and TLM subscribers | Verified bounded v1: reset and factory override on both CPUs; machine-external IRQ/CSR/MRET on Ibex. Five native scenarios passed, with four full Spike matches and separately scoped native IRQ checks. Bus-error stimulus and broader events remain future work |
| M4 — Program generation and coverage | Legal constrained-random instruction sequences, directed ISA corners, dependency/memory goals and targeted coverage holes | Verified both cores across four random seeds; actual 64-instruction/8-schedule randomization calls, replay/diversity checks and independent Spike matches. Native per-CPU and combined merges close the 20 declared coverpoints/crosses and 60 scoped bins. Random control flow, broader ISA and richer crosses remain extensions |
| M5 — Shared Spike checking | One pinned Spike build/execution adapter, same program/initial state, normalized reference records and strict per-retirement comparison | The v1 release has 22 actual Spike executions and 40 full trace matches, plus separately reported incomplete diagnostic prefixes. Earlier milestones remain separately recorded. Asynchronous IRQ comparisons and live/event-rich co-simulation remain future work |
| M6 — SoC verification and RAL | Real peripheral RTL/register map, bus agents, RAL prediction/frontdoor/backdoor tests, CPU/peripheral virtual sequences | Out of scope by owner decision; not planned and not required for v1 completion |
| M7 — RTL mutation quality | Isolated mutated RTL, clean baseline, intended checker kills, survival triage and reproducible campaign reports | Verified v1: four actual RTL defects per CPU, eight intended detections, zero survivors/invalid/infrastructure/unqualified targets; fresh pristine UVM/Spike baselines. Broader mutation classes and survival/equivalence triage remain extensions. Observation controls remain separate |
| M8 — Scale and CI | Larger seed/config matrix, bounded parallelism, replay/triage, simulator bin merging, automated reports and appropriate CI | One-command v1 release verified locally: 171 utility tests, 16 CPU matrix cases, five advanced cases, two component cases, both mutation campaigns and real native bin merging. Manual hosted-utility/self-hosted-native CI configuration is checked in; CI execution and large-scale campaigns are not claimed |

The complete bounded CPU v1 release passed; see [v1-results.md](v1-results.md)
for measured counts and [v1.md](v1.md) for reproduction and demonstration.
No SoC or RAL follow-up is planned. Other extensions below are optional ideas,
not unfinished v1 requirements. Earlier evidence retains its original scope.

## Layer 1 acceptance

Keep UVM the primary professional CPU/SoC verification environment. Require real
sequences, drivers, passive monitors, independent prediction, TLM checking,
SVA and explicit SV coverage goals. Expand the present fixed smoke skeleton
into constrained-random instruction generation only with a legal program and
termination policy. Virtual sequences should coordinate existing agents; RAL
should model actual SoC peripherals. A factory registration macro alone is not
evidence of a tested override scenario.

## Layer 2 acceptance

cocotb is for focused RTL components and Python-driven corners, using the same
upstream RTL. Python/pytest owns utility/model tests, matrix scheduling,
configuration, program tooling, failure classification, evidence and reports.
Spike is a shared independent reference service within this layer. Tests may
run in separate simulators and at separate times. Do not build a second complete
Python CPU environment just to mirror the UVM environment.

## Mutation and closure policy

One mutant changes one intended RTL behavior in a disposable build copy.
Record killed, survived, equivalent, compile-invalid and infrastructure-failed
separately. Preserve the original source lock, mutation patch, baseline seed,
failure diagnostic and replay command. Broaden cocotb component mutations and
UVM architectural mutations where each checker has a justified scope.

Collect actual per-bin coverage databases before merging coverage across seeds.
Never average percentages or replace SV covergroup goals with Python scenario
counts. Feed observed gaps back into targeted UVM sequences or component tests.
