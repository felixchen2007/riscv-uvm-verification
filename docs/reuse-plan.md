# Reuse across Ibex, PicoRV32 and future RISC-V implementations

The goal is reuse across processor implementations; the current harness is
single-hart. Ibex and PicoRV32 now have implemented physical adapters. They
share one bounded architectural checker, program generator, timing policy and
coverage model. Exact executed scopes are in `dual-processor-results.md`.

| Component | Reuse boundary | Ibex today | PicoRV32 today / remaining work |
| --- | --- | --- | --- |
| Program artifacts | RV32I encodings, image hashes, word-address convention, signature contract | Shared SV-generated image and manifest | Same generator/image, reset entry 0x80; per-seed hashes compared |
| Architectural transaction | RVFI-style retirement and normalized v1 JSON | Shared passive RVFI monitor; order begins at 1 | Same monitor/normalizer; native order begins at 0 |
| Architectural scoreboard | Private ISA state, instruction semantics, expected PC and memory | Shared `riscv_scoreboard` | Same class and expected-state logic; adapter configures order origin |
| Memory timing policy | Delay sequence items, constraints, seeded procedural alternative | Shared sequence drives split responders | Same sequence items; request/response delays sum before native completion |
| Passive memory observations | Accepted request/response and semantic memory transaction | Split request/grant/response monitors | Native monitor publishes atomic completion as common request/response observations |
| Reset and interrupts | Shared control agent and passive events; adapter-specific request boundaries | Accepted-request reset; vectored machine-external IRQ/CSR/MRET scenario | Pending-request reset; custom PicoRV32 IRQ semantics remain outside this release |
| SVA | Common semantic rules plus protocol-specific properties | Held requests, grant legality, known values, DUT alerts | Held valid/address/strobes, write-data stability, completion/known controls, no-trap assertion |
| SV functional coverage | ISA classes and branches | Shared smoke covergroup and branch cross | Same instance type; protocol counters remain processor-specific |
| UVM TLM and factory | Analysis ports, configured environments, sequencer policies | Split-port environment and executed maximum-delay factory override | Same registered sequence override through the unified-port environment |
| Virtual sequences | Shared virtual sequencer and scenario sequence | Coordinates instruction/data policy sequences and control agent | Coordinates native-memory policy and control agent; bus-error scenarios remain future work |
| UVM RAL | Peripheral register model, bus predictor and frontdoor adapter | No peripheral block/RAL yet | Reuse only with the same real peripheral map; adapt the bus frontdoor |
| cocotb tests/models | Targeted behavioral contracts and edge vectors | Actual FF register-file tests; independent register model | Add component harnesses for available implementation boundaries; do not duplicate CPU UVM |
| Spike | One pinned execution adapter and canonical comparator | Shared offline bridge, `rv32ic` reference configuration, RV32I program scope | Same bridge, `rv32i` reference configuration, same input/initial state and per-retirement checks; see `spike-results.md` |
| Regression/reporting | Configs, seeds, scheduling, failure classes, artifacts, replay | Multi-seed UVM + targeted Ibex cocotb | Multi-seed UVM; cross-processor comparisons fail the aggregate on divergence |
| Mutation infrastructure | Baseline, isolated mutant copies, kill taxonomy and reports | Four actual ADD/BEQ/SLL/store RTL mutations | Four corresponding implementation-specific RTL mutations; compile-invalid cases cannot count as kills |

PicoRV32 is pinned at `ef203c2b0a3fb793280f5114941416c425c5b461` with an ISC
source lock. `RISCV_FORMAL` enables its RVFI instrumentation; `FORMAL` and
upstream TESTBUG macros are not enabled. No simulation acceptance result is
described as formal proof. Its native bus and interrupt semantics differ from
Ibex, so the physical bus agent is separate and IRQs remain disabled in this
milestone. Shared smoke/corners/random programs exercise a bounded RV32I
intersection; PicoRV32 compressed/M, CSRs, exceptions and interrupts remain
outside the tested scope. The Ibex-only IRQ profile has its own bounded CSR
and event contract; see [the v1 guide](v1.md).

Reference: [PicoRV32 upstream documentation](https://github.com/YosysHQ/picorv32).
