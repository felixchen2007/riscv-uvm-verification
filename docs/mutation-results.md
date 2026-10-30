# First actual RTL mutation results

**All four targeted Ibex RTL defects were detected in the final campaign.** A
clean native UVM/Spike baseline passed before mutant execution. Each mutant was
compiled from one isolated changed RTL file, with the original vendor snapshot,
testbench, stimulus and independent expected-state logic preserved.

| Actual RTL mutation | First UVM checker | UVM errors / fatals | First Spike divergence, zero-based record | Outcome |
| --- | --- | --- | --- | --- |
| Flip bit 0 of `ALU_ADD` result | `RVFI_RD` | 115 / 0 | 0: writeback `fffffffe` instead of `ffffffff` | Killed |
| Invert the EQ branch comparison | `RVFI_PC` | 42 / 0 | 36: PC `0x110` instead of `0x114` | Killed |
| Flip bit 0 of SLL result | `RVFI_RD` | 2 / 0 | 19: writeback `80000001` instead of `80000000` | Killed |
| Flip bit 0 of non-ECC store output | `MEM_STORE_DATA` | 29 / 0 | 28: loaded value 21 instead of 20 | Killed |

Counts are the complete reported error counts, including propagated failures.
Qualification requires the intended **first** error, all errors counted and
retained, zero fatals, successful compilation/elaboration and actual simulation,
no simulator error, no UVM pass marker and no observation-corruption injection.
The architectural mutants also require an independently observed Spike
divergence. The separate physical bus check is sufficient to qualify its
store-output defect, and this run additionally observed a later load divergence.

The store result demonstrates complementary checking: the passive request
monitor exposed the incorrect physical write data first. The independent
retirement reference later exposed the loaded corruption. The shared
`ALU_ADD` path serves several instructions, including ADDI/LUI, so corrupting
it naturally produced many downstream source-register, result and path errors.

## Executed configuration

The DUT was pinned Ibex v2.1.0 at
`38c070939183cc10940b66c8e9e04eeca6b65470`, using its existing RV32IC-capable
no-M/B/cache/security/writeback-stage configuration and the 47-retirement
`corners` program. Seed was 20261029. XSim 2025.2 / UVM 1.2 used full mode;
mutants ran the stalled profile with maximum memory delay 3 and the ordinary
UVM test, drivers, passive monitors, scoreboard and assertions.

The clean baseline ran both positive timing profiles. Each checked all 47
retirements with zero UVM errors/fatals and zero simulator/assertion errors,
then passed the expected observation-corruption control. One actual pinned
Spike v1.1.0 execution at commit
`530af85d83781a3dae31a4ace84a573ec255fefa` supplied the independent reference;
both full baseline traces matched it. The comparator's separate observation
control also detected its intended mismatch. These two controls are retained
as checker qualifications, distinct from the four actual RTL mutations.

Each mutant compiled and elaborated successfully and completed its observed
simulation with simulator exit code 0. UVM errors prevented ordinary verification
passes. Every run used an input image identical to the clean baseline, allowing
the same actually executed Spike reference to be reused. This is **one ISS
execution, two full baseline comparisons and four mutant diagnostic-prefix
comparisons**, rather than five separate ISS executions.

All four retained mutant traces contain 47 observed records, but remain
explicitly `complete: false`: failed UVM/model completion is not a clean
architectural completion. Their actual first divergences are listed above.
The prefix adapter also supports genuinely shortened traces and does not let
them enter the normal full-pass comparator.

## Isolation, qualification and limits

The audit verified 258 unchanged repository source hashes across the clean
baseline and final mutant executions. Those hashes describe the common
pristine inputs; each mutant's **effective compiled RTL intentionally differs**
in exactly one isolated file. Per-mutant manifests record the original and
modified source hashes, saved source contents, exact patch and actual resolved
compiler list. The original Ibex and PicoRV32 source locks were rechecked after
the campaign. No testbench or predictor source was mutated, and the runtime
RVFI observation-flip plusarg was absent in mutant runs.

The first qualification attempt used an overly strict single-error rule. The
actual UVM error action allowed continued execution and cascaded diagnostics,
so that attempt retained four unqualified detections. The policy was corrected
to qualify the intended first error with complete error accounting and reference
evidence, unit-tested, and the clean baseline plus all four mutants were rerun
on a fresh frozen snapshot. The initial summary/report remain separately
retained; they were not relabeled.

Final outcome counts are **4 killed, 0 survived, 0 compile-invalid, 0
infrastructure-failed and 0 unqualified detections**. The executed denominator
is four; invalid builds and infrastructure failures never count as kills.
This is evidence for four specific faults at one Ibex configuration/program/seed,
not a broad mutation score, full verification closure or PicoRV32 mutation
coverage. The 148 passing pytest tests qualify isolation, prefix handling,
tamper rejection and classification; synthetic fixtures are not RTL kills.

## Reproduce and inspect

```powershell
.\build\python-env\Scripts\python.exe scripts/run_mutation_tests.py --output build/mutations/a-fresh-run
.\build\python-env\Scripts\python.exe -m pytest -q --basetemp build/python-tests/mutation-check
```

The accepted campaign is `build/mutations/ibex-verified/`, with `summary.json`,
`report.md` and the checked `audit.json`. Its 131 retained artifacts under
`evidence/rtl-mutations/` include originals, mutant sources, unified patches,
compiler commands/lists, raw UVM/RVFI/Spike data, input images, prefix comparisons,
source identities, baseline controls and pytest XML. `artifact-sha256.json`
indexes the retained files. Original paths and executor timestamps are preserved.

[mutations.md](mutations.md) defines the policy and outcome taxonomy. Broader
operators, programs/seeds, surviving/equivalent-mutant triage and PicoRV32
campaigns remain later work. No FPGA/hardware result is part of this campaign.
