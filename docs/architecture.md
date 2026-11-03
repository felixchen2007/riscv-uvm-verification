# RISC-V verification architecture

The project has three responsibilities. Implementation status is explicit:

| Layer | Responsibility | Current status |
| --- | --- | --- |
| 1 — SystemVerilog UVM | Drive and monitor both CPUs; check protocols, architectural state, scenarios, assertions and functional coverage | Implemented; a private SV predictor currently checks architectural state |
| 2 — Spike reference checking | Supply independent architectural expectations through the pinned C++ reference | Offline comparison plus optional live DPI-C/WSL stepping for normal smoke/corners/random programs |
| 3 — Python automation | Builds, seeds/configurations, regressions, trace audits, mutations, coverage export and reports; unittest checks these utilities | Standard-library automation and unit checks |

Python launches UVM and the reference tools. With `--spike-live`, a UVM
subscriber calls a C++ comparator through DPI-C; a persistent WSL process
executes Spike on demand. The private SV predictor remains active. Reset/IRQ
events are outside this live contract. See [spike-dpi.md](spike-dpi.md) for the
process boundary, controls, reproduction commands and exact limits.
SoC/RAL and new component-test environments are outside this scope.

## Shared contracts and processor adapters

`config/processors/` contains common ISA, entry, memory-signature, retirement
and capability profiles. `ibex_smoke` and `picorv32_rv32i` have executable
physical adapters. Both use locked upstream RTL and the same smoke program,
scoreboard and architectural coverage model. Profiles currently describe one RV32 hart;
supporting multiple processor implementations does not claim simultaneous
multi-hart verification.

Program profiles are selected separately through `config/programs/` and
`--program`. The original smoke and the extended directed corners share the
same UVM agents, independent predictor and Spike bridge. Their structural
counts, terminal PCs and branch goals are explicit. Regression comparisons
include program identity in addition to processor and seed; see [programs.md](programs.md).
The separate random profile uses native SV constrained instruction items and
shuffled schedules to add 64 random body instructions. Python audits only input
legality/distributions/replay, while the independent UVM ISA model and actual
Spike execution continue to own architectural checking. Body-only coverage
is separate from the directed prologue; see [random-programs.md](random-programs.md).

The original `config/smoke.json` remains the authoritative Ibex parameter
configuration; `config/picorv32.json` records the Pico wrapper configuration.
Existing RTL/UVM include paths and commands stay in place. Reuse the
program image format and common architectural records; put incompatible bus,
reset, interrupt and retirement semantics behind processor-specific adapters.

The v1 retirement contract uses zero-based contiguous `order`, hart, PC,
instruction, architectural destination write, memory effect and trap/halt/
interrupt observations. The Ibex adapter preserves `native_order` while
translating the pinned core's one-based order. PicoRV32's RVFI starts at zero.
The shared normalizer translates the configured native origin. It excludes stale RVFI memory
fields for non-memory instructions and rejects incomplete or unknown records.
It does not infer absent trap flags in historical CSVs. JSON Schemas live in
`schemas/`, with executable semantic validators in `verification/`.

The common comparator checks every retirement and rejects missing, extra or
reordered records. It checks timing invariance within each CPU and consistency
between Ibex and PicoRV32. Its synthetic synthetic fixtures are not Spike execution evidence.
An actual Spike adapter must identify its build, ISA, initial state and program
window before any ISS-comparison pass can be claimed.

## Minimal repository organization

```text
vendor/                 immutable synthesizable upstream RTL and source locks
tb/uvm/                 Layer 1: existing UVM environment and DUT harness
verification/           Layer 3: shared config, traces, results and utility code
verification/reference/ independent targeted models and pinned Spike adapter
scripts/                executable simulation and regression entry points
config/processors/      processor contracts; capability status is explicit
config/regressions/     reproducible processor / seed / mode matrices
schemas/                shared trace and result formats
tests/                  unittest automation and checker tests
evidence/               versioned, scoped execution evidence
build/                  isolated outputs, dependencies and simulator databases
```

The shared `riscv_env_base` and `riscv_smoke_test` live in `riscv_test.svh`.
`ibex_test.svh` preserves its old include path. The ISA checker is now
`riscv_scoreboard`, with a legacy `ibex_scoreboard` type alias. Existing program,
delay-sequence and RVFI monitor/interface names remain compatible. Ibex retains
its split-port agents; Pico uses a native unified valid/ready driver and passive
monitor. Both publish the same TLM transaction types. See
[the reuse matrix](reuse-plan.md).

## Regression and coverage ownership

Layer 3 launches `scripts/run_uvm_tests.py` for native CPU cases. Each case gets
its own simulator libraries, program, logs, traces and coverage database.
`scripts/run_regression.py` validates requested seeds/configurations, runs a
bounded worker pool, preserves failed artifacts and emits JSON/Markdown reports
with replay commands. Missing tests, changed sources, compilation-only output
and unexpected corruption diagnostics cannot be counted as passing cases.

SV covergroups remain the CPU functional-coverage authority. Python collects
per-run coverage observations and points to databases; it does not average
percentages into a fictitious merged coverage figure. Native databases are merged
by the coverage exporter. SoC and RAL are outside the accepted scope.

## Current Ibex UVM implementation

This document describes the intended component boundaries for the initial
environment and its expansion. The checked-in source and recorded test results
define which parts are implemented and executed at each milestone.
The preferred host simulator is Vivado Simulator (XSim), while optional hardware
work retains the Intel DE10-Lite and Quartus. These are independent choices:
UVM simulation on the host does not require an AMD FPGA. Vivado XSim 2025.2 is
installed under `D:/AMDDesignTools/2025.2/Vivado/bin`. Actual run evidence is
recorded separately from the Questa Starter capability probes. A board
implementation is not a prerequisite for the UVM milestones.

```text
UVM test / virtual sequence
  | program and initial memory       | timing/response sequence items
  v                                  v
program image                   instruction/data memory agents
  |                                  | active drivers
  |                                  v
  |                         SystemVerilog interfaces <-> Ibex DUT
  |                                  |
  |                      passive bus and RVFI monitors
  |                                  |
  v                                  v
private reference state ------> independent scoreboard
                                     |
                              scenario/coverage subscriber

interface assertions ---------> UVM/simulator failure + result manifest
RVFI trace -------------------> offline Spike comparison adapter
```

## DUT boundary and configuration

Use the actual lowRISC Ibex RTL at an immutable revision. Local UVM components
must not replace the processor with a behavioral stand-in. Keep wrapper wiring,
primitive selection and configuration visible in the file list/harness. The
small initial harness supplies clock, reset, instruction memory and data memory
responses and ties unused interrupt/debug inputs to documented inactive values.

Ibex's documented boot entry is `boot_addr_i + 0x80`; record the actual entry
chosen by the pinned source and harness. RVFI must be enabled for architectural
observation. Only use RVFI signals as actual observations, not as expected-state
input. Extension and microarchitecture parameter changes create distinct tested
configurations and require fresh evidence.

## Reusable agents

Memory agents own the active response behavior. Their transactions describe
timing choices; the UVM sequencer/driver boundary keeps
the policy separate from pin driving. Instruction and data interfaces can share
transaction types and responder machinery while retaining distinct instances
and configuration. Agent configuration controls activity, delays, address map,
image initialization and response policy. Unsupported stimulus is rejected.

Passive monitors sample accepted requests and responses independently of the
drivers. Transactions sent to analysis ports are snapshots so later driver or
monitor updates cannot change a record already checked. Observed handshakes,
addresses, byte enables and data support protocol diagnostics. A passive RVFI
monitor emits one immutable retirement transaction per valid retirement.

The initial program sequence may be a fixed scaffold with explicitly seeded
parameter choices. Under the full mode, constraints and `randomize()`
select bounded memory timing. Program generation, responder timing and
coverage must report which mode ran. The initial full mode randomizes memory
timing only; program operands remain seed-derived. Using UVM alone does not make stimulus
constrained random.

## Independent scoreboard

The reference model starts from the known program image, known memory contents,
reset architectural state and expected boot PC. It decodes supported
instructions and maintains private registers, memory and next-PC state. These
values are separate from the active memory agent's storage and from the DUT's
register file. Check x0 invariance and compare only architecturally meaningful
fields for each instruction.

The initial program retires 14 instructions covering ADDI, ADD, SUB, XOR, LUI,
SW, LW, taken BEQ, untaken BNE and JAL, ending with a checked signature store
of `1` to `0x1004`. The model predicts the next retirement PC and checks it
against the following RVFI record. It does not use `rvfi_pc_wdata` as the
architectural next-PC oracle because that field can reflect fetch-ahead
behavior in the pinned Ibex implementation.

For a load, the expected result comes from the reference memory; for a store,
the model computes the expected address and data from reference registers.
Expected register results must not be copied from RVFI `rd_wdata`, observed
load response data or DUT internal signals. Observed instruction bits are
checked against the reference program before execution. Unsupported opcodes,
unexpected traps, incorrect retirement ordering or an unexpected PC fail.

A negative control changes an actual observation without changing the private
reference state. The scoreboard must report the expected mismatch. This checks
the comparison path; expanding into an RTL mutation campaign is a separate
milestone.

## Assertions and coverage

Interface assertions and passive checks enforce the defined request/response
contract and detect unknown controls, unsolicited responses and unstable held
requests where the Ibex protocol requires stability. A watchdog bounds progress.
Document which checks are implemented rather than assuming all upstream
assertions are enabled or supported by the local simulator.

Procedural counters in Starter mode show which opcode families, dependency
patterns, paths and response-delay choices occurred. The full mode adds
covergroups and legal crosses. Every reported coverage value identifies its
mode, denominator and configuration; scenario counts are not a substitute for
covergroup closure.

## Result pipeline and future extensions

The Python runner locates tools, builds UVM and DUT sources, runs the requested
cases, validates completion/error diagnostics and writes a machine-readable
manifest. It records source hashes before execution and checks that they remain
unchanged afterward. Failed or unavailable runs must not leave an older passing
result appearing current.

Retirement trace output feeds the shared offline Spike adapter described in
[spike.md](spike.md). It executes the same input image and initial state in the
pinned upstream library and rejects incomplete traces. The optional live DPI-C subscriber is described in [spike-dpi.md](spike-dpi.md). Later reset/interrupt/debug agents can reuse analysis
and configuration patterns, but their event timing must become part of the
reference-model contract before claiming trap or interrupt coverage.

See [the verification plan](verification-plan.md) for staged acceptance and
[the upstream integration contract](https://ibex-core.readthedocs.io/en/latest/02_user/integration.html)
for DUT integration details. The pinned revision's RTL and documentation govern
the actual wrapper.
