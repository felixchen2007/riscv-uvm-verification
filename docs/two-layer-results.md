# Two-layer milestone results — 2026-10-29

The existing Ibex UVM environment was preserved and the architecture was
consolidated into two layers. The next milestone adds common processor, trace
and result contracts; complementary cocotb component tests; pytest utility/model
tests; and isolated, bounded parallel multi-seed scheduling.

## Executed matrix

The combined regression ran with **two workers** and seeds **20261029** and
**20261030**. Its four requested cases all passed:

| Case scope | Simulator | Cases | Executed checks |
| --- | --- | ---: | --- |
| Layer 1 CPU UVM, full mode | Vivado XSim 2025.2, UVM 1.2 | 2 seeds | Four positive timing-profile runs, 14 retirements each, UVM errors/fatals 0/0 |
| Layer 1 checker controls | Same XSim runs | 2 controls | Intended `RVFI_RD`, exactly one UVM error, no UVM fatal, no pass marker |
| Layer 2 targeted component | Questa Starter 2024.3 VPI, cocotb 2.0.1 | 2 seeds | Four component tests: RV32E=0/1 at each seed, 32/16 registers, 128 Python-random cycles each plus directed/reset checks |
| Layer 2 utilities and model | pytest 8.4.2 | 38 tests | All passed; no skips or failures in the final utility run |

Each UVM case invoked the native `scripts/run_uvm_tests.py --full` suite with
its own output directory. Each component case compiled the actual locked
upstream `ibex_register_file_ff`, using a small cocotb harness and an independent
register-semantics model. Component results are not CPU UVM acceptance results.
The original seed's full-mode CPU scenarios remain identical to M0.

The original default seeded UVM entry point was also rerun after the update:
both timing profiles passed with 14 retirements and UVM errors/fatals 0/0,
and its corruption control produced the intended error. That preservation run
used procedural PRNG timing and did not execute SV randomize or covergroups.

Full-mode UVM executed SV constrained-random **memory timing**, not random
instruction generation. Its smoke covergroup remained 87.50% in each positive
profile. Untaken BEQ and taken BNE are still unexercised cross combinations.
No coverage percentages were averaged or treated as merged bin coverage.

## Shared trace and result checks

Four actual UVM positive retirement traces were normalized into the v1 common
format. Both seeds' no-added-delay and stalled traces matched architecturally
for all 14 retirements. This establishes timing invariance for those runs; it
is not a Spike comparison.

The adapter translates Ibex's native order 1–14 to canonical order 0–13 and
preserves the native order separately. It uses observed trap/halt/interrupt
flags appended to the CSV, omits stale RVFI memory fields on non-memory
instructions, checks the program image hash, and requires the terminal store.
Historical CSVs lacking flags are rejected by the new adapter rather than
having flags invented. Existing historical evidence remains unchanged.

The 38 utility tests exercise dropped, duplicate, reordered, unknown and
incomplete traces; architectural mismatches; seed validation; planned-core
rejection; register semantics; missing cases; failure classification; and
coverage aggregation rules. Their small synthetic `producer=spike` fixtures
test only comparator behavior and are not claimed as ISS execution evidence.

## Compatibility findings

- **UVM:** the installed XSim 2025.2 flow remains the primary CPU verification
  flow. Its existing narrow upstream DPI compatibility wrapper is unchanged.
- **cocotb:** actual VPI execution on Questa Starter passed. The selected
  cocotb 2.0.1 package does not provide an XSim runner. No common-simulator or
  simultaneous-execution requirement was imposed.
- **Windows paths:** the generic cocotb Python runner escaped source paths
  incorrectly for this workspace. The component runner uses native structured
  `vlog`/`vsim` arguments and passes `-pli` as one Tcl list element pointing at
  the original wheel DLL. It does not copy/patch the installed simulator or
  rely on duplicate runtime DLL instances.
- The component simulator reports the expected PLI/access optimization warnings;
  its executed tests pass without simulator errors. These are not UVM warnings.
- Python dependencies were installed only in `build/python-env`. The final
  pytest run used a fresh temporary directory inside the workspace because
  the restricted process could not create pytest's default external temp folder.

## Evidence and reproducibility

The current matrix report is
`build/regressions/two-layer-milestone/report.md`, with a detailed `summary.json`.
Each case retains raw simulator output, a common `case-result-v1.json`, source
hashes and replay arguments. CPU cases also retain normalized traces, program
manifests and individual coverage databases. The common result envelope keeps
CPU/component scope and simulator-specific evidence distinct.

Retained compact evidence is saved under `evidence/two-layer/`, alongside the
final pytest XML and resolved Python package list. The original
`evidence/initial/` artifacts are preserved.

PicoRV32 has a planned profile only and is rejected for execution. No PicoRV32
RTL, Spike run, full CPU cocotb environment, RTL mutation campaign, SoC RAL,
virtual-sequence scenario, random instruction generator, CI execution, ISA
closure or hardware result is claimed. Their concrete acceptance gates are in
[roadmap.md](roadmap.md) and [reuse-plan.md](reuse-plan.md).

Primary compatibility reference:
[cocotb 2.0.1 simulator support](https://docs.cocotb.org/en/v2.0.1/simulator_support.html).
