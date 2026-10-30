# Configurable RISC-V framework verification plan

This plan uses the two-layer architecture in [architecture.md](architecture.md).
Layer 1 is the primary SystemVerilog UVM CPU/SoC environment. Layer 2 combines
cocotb, Python automation, pytest and the shared offline Spike integration.
The [roadmap](roadmap.md) separates implemented milestones from planned work;
the [reuse matrix](reuse-plan.md) identifies common and processor-specific code.
The Ibex acceptance contract below remains required and is preserved.

The same bounded ISA predictor and scenario contract now also apply to the
PicoRV32 adapter. The default matrix selects both cores and two seeds. Each
processor must pass both timing profiles and its independent corruption control;
normalized traces must additionally match across processors for each seed and
profile. Cross-processor consistency checks remain distinct from the additional
independent reference executions required by the regression's `--spike` option.

This project starts with an independent UVM environment around the unmodified
lowRISC Ibex processor. It is a verification project with a small memory-system
harness; it is not yet a complete peripheral SoC or an FPGA implementation.
The initial milestone is deliberately bounded. A passing smoke test establishes
that the selected program, checks and configuration ran; it does not establish
RISC-V compliance or full Ibex verification closure.

## Preferred simulator and optional FPGA

The requested host simulator is AMD Vivado Simulator (XSim), using UVM 1.2.
The DE10-Lite remains the optional physical FPGA target; use Intel Quartus for
that board. Host simulation does not require the simulated RTL to target an AMD
FPGA. The reusable environment should stay portable across simulators.

AMD documents a precompiled UVM 1.2 library for XSim and the standalone
`xvlog`/`xelab` option `-L uvm`. This establishes documented tool support, not a
successful local run. Vivado 2025.2 was found under
`D:/AMDDesignTools/2025.2/Vivado/bin` after checking the user's D: installation.
See the recorded results for actual compilation, elaboration, smoke and control
execution. Record missing tools as unavailable. Do not silently substitute
Questa and label its results as XSim evidence.

Questa Intel FPGA Starter provides a separately identified UVM capability
probe and an explicit alternative runner. Keep its results and feature
limitations separate from the user's preferred XSim milestone.

## Configuration and provenance

- Fetch a fixed upstream Git commit and record it in the project source lock.
  Never accept a moving branch name as sufficient run provenance.
- Use the configuration recorded by the simulation harness and result manifest.
  The first program uses 32-bit RV32I instructions only. Hardware support for
  other extensions does not imply those extensions have been exercised.
- Run native UVM 1.2 components under `tb/uvm`. Keep this project's evidence
  separate from the surrounding Tensor Memory Accelerator project.
- Record simulator identity, UVM version, configuration, seed, source hashes,
  test name, status, UVM error/fatal counts, scenario counters, assertion results
  and the corruption-control outcome. Compilation alone is never a pass.

## Execution modes

| Mode | Stimulus | Coverage | Acceptance language |
| --- | --- | --- | --- |
| Default, XSim or Questa | Explicit seeded PRNG for memory timing; fixed instruction skeleton with seed-derived operand | Procedural scenario counters | Native UVM simulation with seeded procedural stimulus |
| `--full`, supported simulator required | SystemVerilog `randomize()` and constraints for memory timing; same fixed program skeleton | SystemVerilog smoke covergroup and branch cross | Constrained-random timing/covergroup execution only after a successful run |

The installed Questa Intel FPGA Starter can run UVM base classes but denies the
`svverification` feature used by randomization and covergroups. An attempted
`--full` run that fails the license checkout must be recorded as unavailable or
failed, never silently downgraded or counted as constrained-random execution.
Scenario counters measure exercised cases; they are not covergroup closure.

## Initial acceptance contract

The smoke program uses ADDI, ADD, SUB, XOR, LUI, SW, LW, a taken BEQ, an
untaken BNE and JAL. The expected execution contains 14 retired instructions
and finishes with a signature store of `1` to address `0x1004`. The checked-in
sequence and scoreboard define the exact program and checks. The first
acceptance run must demonstrate all of the following:

1. Reset releases, the processor fetches from the configured boot entry, and
   memory requests receive legal responses.
2. An active instruction responder and an active data responder use reusable
   transaction/driver interfaces. Independent passive monitors observe the bus
   and RVFI rather than treating driver intent as proof of DUT behavior.
3. An independent architectural model predicts register values, next PC and
   supported memory effects from its own state and the loaded program. The
   next retired PC is compared with the independently predicted next PC;
   the pinned Ibex `rvfi_pc_wdata` can reflect fetch-ahead behavior and is not
   used as an architectural oracle. DUT
   writeback values and DUT load responses must not seed expected values.
4. The scoreboard compares every supported retired instruction, including
   instruction identity, PC, register result and relevant memory effects. It
   rejects unexpected opcodes or traps instead of skipping them.
5. Assertions/procedural protocol checks detect invalid responses, unstable
   requests where prohibited, unknown control values and watchdog expiry within
   the explicitly checked protocol scope.
6. Completion follows a checked architectural terminal condition. A timeout,
   missing completion, UVM error/fatal, assertion failure or simulator error
   fails the positive test.
7. A separate negative run corrupts an observed result and must fail with the
   intended scoreboard diagnostic. A negative run passing, timing out, or
   failing for an unrelated reason does not validate the checker.

Exact counts and instruction classes belong in the run manifest and verified
results document. This plan does not claim a run has passed.

## Traceability and staged expansion

| ID | Feature / risk | Stimulus and checker | Required evidence | Stage |
| --- | --- | --- | --- | --- |
| BOOT-01 | Reset and boot address | Reset sequence, passive fetch observation, expected initial PC | Correct first retirement, bounded completion | Initial smoke |
| ISA-01 | Integer arithmetic and dependency chains | RV32I subset sequence, independent register model | Every retirement checked; exercised opcode counters | Initial smoke |
| MEM-01 | Word loads and stores | Memory agents, private expected memory, RVFI/bus checks | Address, data, masks and returned architectural value | Initial smoke |
| CTRL-01 | Taken/untaken control flow | Taken BEQ, untaken BNE and JAL | Next retirement matches predicted PC; path counters | Initial smoke |
| PROTO-01 | Fetch/data response timing | Seeded responder delays, passive protocol monitors | Legal handshakes, no timeout/assertion errors | Initial smoke then expand |
| CHECK-01 | Scoreboard sensitivity | Corruption control on observed transaction | Expected failure ID and nonzero UVM error count | Initial smoke |
| RAND-01 | Distribution and corner combinations | Licensed constrained-random sequences with reproducible seeds | Actual successful `randomize()` execution and constraint settings | Later licensed milestone |
| COV-01 | Functional coverage completeness | Opcode, dependency, delay, branch and memory covergroups | Per-bin report, reviewed exclusions and legal crosses | Later licensed milestone |
| ISA-02 | Remaining integer, subword, compressed and M extension cases | Directed corners plus generated programs | ISA/configuration-specific coverage and architectural matches | Later expansion |
| TRAP-01 | Exceptions, interrupts and debug | Reusable interrupt/reset agent and trap-aware predictor | Cause/EPC/privilege checks, event timing record | Later expansion |
| CSR-01 | Machine CSRs and counters | CSR sequences and explicit non-deterministic-field policy | Legal access, masks, side effects, trap checks | Later expansion |
| SPIKE-01 | Independent ISS comparison | Same program/initial state in pinned Spike, normalized retirement traces | Matched PC/instruction/register/memory effects, tool/build identity, intended comparison corruption diagnostic | Implemented offline smoke adapter; see `spike-results.md` for executed evidence |
| REG-01 | Reproducible regressions | Test/seed/configuration matrix | One result per requested case, failures retained, aggregate fails closed | Initial runner then expand |
| PY-01 | Independent targeted component checking | cocotb on actual FF register file, software register semantics, RV32E parameter variants | Executed tests and XML results; do not label as CPU UVM acceptance | Two-layer milestone |
| DATA-01 | Shared retirement/result contracts | Normalize actual RVFI, compare timing profiles, reject corrupt/truncated synthetic records with pytest | Program hashes, contiguous records, strict comparator and schema versions | Two-layer milestone |
| REG-02 | Multi-seed and parallel isolation | Two seeds, separate work libraries, bounded workers, both layers | Case manifests, replay commands, no lost cases or source drift | Two-layer milestone |
| CPU-02 | PicoRV32 physical and retirement adapters | Pinned native core, unified memory UVM agent, shared RVFI checker and program | Correct native order origin, clean smoke/control results and cross-processor trace matches | Dual-processor milestone |
| MUT-01 | Verification quality against injected bugs | One controlled mutation at a time | Baseline passes; intended checker kills each non-equivalent mutant | Corruption control first; RTL campaign later |

The initial corruption control validates the observation/checking path. It is
not an RTL mutation campaign. A later campaign should mutate arithmetic,
branch selection, byte enables and response timing in isolated DUT copies;
record killed, survived, equivalent, compile-invalid and infrastructure-failed
mutants separately. Keep original source hashes and run an unmutated baseline
before accepting a mutation score. Never inflate the score by counting invalid
mutants as detected functional defects.

## Spike comparison milestone

Spike is one shared Layer 2 reference resource for UVM and cocotb. Do not
implement separate ISS wrappers with divergent ISA or trace policies. Prefer
RVFI for each processor where available and translate implementation-specific
interfaces through its adapter. The common comparator is implemented; invoking
it on timing-profile traces or synthetic fixtures does not constitute a Spike run.

The current offline adapter emits normalized RVFI retirement records, runs the
same shared image and initial state in a pinned Spike build, and compares PCs,
instruction encodings, architectural register writes and memory effects. Match
the ISA string, reset/entry behavior, memory map, endianness, terminal condition
and trap policy. Compare only the program execution window, and explain how any
reset ROM instructions are excluded. Reject missing, duplicate and reordered
records, rather than accepting a matching final signature alone.

Move to live DPI co-simulation only after that contract is tested. Interrupts,
debug, bus errors and non-deterministic CSRs need explicit synchronization and
checking policies. The upstream Ibex co-simulation path documents a specialized
lowRISC Spike branch and VCS flow; porting it to XSim or Questa requires
separate build and runtime evidence. A missing Spike executable is recorded as
not run, never as a comparison pass.

## Regression and closure policy

The bounded v1 acceptance flow is `scripts/v1.ps1`, documented in
[v1.md](v1.md). It requires the baseline and four-seed random matrices, five
advanced native scenarios, both CPU mutation campaigns and native coverage
merges. Its release manifest fails closed if any stage or source-identity check
fails. The checked-in CI configuration requires a suitable self-hosted native
runner; a local release is not evidence of CI execution.

Advanced acceptance adds a real UVM virtual sequencer and executed sequence
factory override. Reset must be observed at the adapter's actual pending or
accepted boundary, preserve raw retirement epochs, abort unfinished memory
work and complete a checked restart. The reset program writes registers before
reading them; it does not claim PicoRV32 register-array reset or retention.
The Ibex IRQ scenario requires the physical external event, independent
enable/vector/cause/return checks, MRET and mainline completion. Its bounded
native event contract is separate from the offline Spike contract.

Random-body memory coverage has eight scratch-word bins, separately sampled
from the directed prologue. Together with the other four groups, the model
declares 20 coverpoints/crosses and 60 bins. XCRG must restore the actual native
databases, preserve their hashes and close the declared bins per processor and
in the combined merge. Individual ALU/memory gaps remain visible in per-seed
reports. Closure of this model does not imply full ISA, code or protocol-state
coverage.

The `corners` directed profile adds all ten register-register RV32I ALU
operations, bounded backward control flow, all four BEQ/BNE outcomes and
specific arithmetic/dependency/memory goals. Each full positive corner run
must hit 100% of the existing opcode/branch group and the separate bounded
corner group, with exact branch counts checked against successive observed
PCs. This closes those named directed goals only. The original smoke remains
separate; no per-run percentages are averaged into a merged-coverage claim.
See [programs.md](programs.md) and [the measured results](directed-corners-results.md).

- Every positive test needs clean UVM error/fatal counts, intended completion,
  all mandatory scenario counters, clean protocol checks and stable source
  hashes. Preserve simulator logs when a run fails.
- Every negative test needs the intended diagnostic. An arbitrary nonzero
  process exit is insufficient.
- Use multiple fixed seeds before increasing random program length. Keep each
  failure seed and configuration for replay. Report case counts and coverage
  denominators; do not extrapolate from one smoke case.
- A coverage hole is either exercised or justified against the selected DUT
  configuration and program generator. Exclusions need review and explanation.
- FPGA synthesis/self-tests and JTAG are optional later milestones. The user
  retains the Intel DE10-Lite, so any implementation for that board uses
  Quartus. Vivado/XSim is the preferred host UVM simulator. Hardware results
  are separate evidence and do not substitute for native UVM simulation.

## Primary references

- [Ibex source and license](https://github.com/lowRISC/ibex)
- [Ibex core integration](https://ibex-core.readthedocs.io/en/latest/02_user/integration.html)
- [Ibex co-simulation and RVFI contract](https://ibex-core.readthedocs.io/en/latest/03_reference/cosim.html)
- [Spike source and build documentation](https://github.com/riscv-software-src/riscv-isa-sim)
- [AMD UG900: XSim UVM 1.2 support and standalone options](https://docs.amd.com/r/en-US/ug900-vivado-logic-simulation/Universal-Verification-Methodology-UVM-Support)

The fetched commit's own documentation and RTL take precedence over changing
online `latest` documentation when integrating the pinned DUT.
