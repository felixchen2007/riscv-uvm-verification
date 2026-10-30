# Isolated RTL mutation campaign

`scripts/run_mutation_tests.py` qualifies checker behavior against actual changes
to Ibex RTL. It is separate from the earlier testbench observation-corruption
controls. Native SystemVerilog UVM remains the primary acceptance/checking
environment; Python owns isolation, scheduling, classification and reports.

## Current bounded campaign

The versioned configuration `config/mutations/ibex-small.json` selects the pinned
Ibex configuration, `corners`, seed 20261029, full XSim mode and two workers.
It first runs a clean native UVM suite: both positive timing profiles and its
observation-corruption control, followed by actual independent Spike execution
and both full retirement comparisons. A failed baseline prevents mutant launch.

| Mutation | Isolated RTL location | Changed behavior | Intended checker |
| --- | --- | --- | --- |
| `add_flip_bit0` | `ibex_alu.sv` | XOR bit 0 of the shared ALU_ADD result, preserving the separate address-adder output | `RVFI_RD` |
| `beq_inverted` | `ibex_alu.sv` | Reverse the EQ branch comparison | `RVFI_PC` |
| `sll_flip_bit0` | `ibex_alu.sv` | XOR bit 0 of SLL writeback | `RVFI_RD` |
| `store_flip_bit0` | `ibex_load_store_unit.sv` | XOR bit 0 of the non-ECC memory write-data output | `MEM_STORE_DATA` |

Each mutant changes one intended behavior in one owned source copy under
`build/`. A saved original, mutated source, unified patch and manifest record
the before/after hashes and exact substitution. The original vendor snapshot
and lock stay intact. Preparation rejects missing/ambiguous anchors, original
hash drift, unknown definitions, path escapes and altered mutant contents.

## Native execution and evidence

Mutant workers invoke `scripts/run_uvm_tests.py --rtl-mutation <manifest>` with
an explicit isolated output. This observation mode requires full Ibex XSim and
substitutes exactly one compiled file. Remaining RTL, the testbench, predictor,
agents, assertions, program and seed stay shared with the clean baseline.
Logical and resolved compilation lists plus the actual compiler command are
recorded, making the effective DUT source substitution reviewable.

Each mutant executes the stalled profile through the same UVM test, drivers,
passive bus/RVFI monitors and independent scoreboard. The observation-flip
plusarg is absent. Early-stopped mutant runs retain their actual UVM errors,
fatal counts, exit codes, raw traces and images; they never become ordinary
`verification_pass` results. Compilation alone cannot qualify a detection.

The runner reuses the clean Spike reference only after checking the mutant's
input-image hash against the clean baseline. A stopped trace is explicitly
marked `complete: false` and compared only as a diagnostic prefix. A mismatching
retirement is reported as an architectural divergence. A matching prefix
means the observed prefix agrees; it does not turn the stopped run into a full
architectural pass. A physical store-data defect can be caught by the passive
bus checker before it appears as a differing architectural retirement.

## Outcome policy

- **Killed:** compiled/elaborated and simulated, intact source identity, the
  expected first UVM checker error, every subsequent error counted and retained,
  zero fatals, no pass marker, no simulator error
  and no observation-corruption injection or watchdog substitution.
  Architectural mutations additionally require an independent Spike retirement
  divergence. A bus-output mutation can instead qualify through its specific
  passive-bus error, with the reference prefix observation recorded separately.
- **Survived:** clean complete UVM completion with all expected case/scenario
  fields, complete retirement count and no disagreement with the independent
  reference. Survival requires investigation rather than relabeling as a kill.
- **Compile-invalid:** code-related compile/elaboration failure, excluded from
  the executed detection denominator.
- **Infrastructure-failed:** unavailable tools/licenses, timeouts, integrity
  failures, simulator failures or unusable/missing execution evidence.
- **Unqualified detection:** an unexpected checker/fatal/completion pattern;
  retained for triage and excluded from qualified kills.

The summary reports raw counts. Its detection fraction uses only killed plus
survived mutants; invalid and infrastructure results do not inflate it. This
four-mutant, one-core/program/seed campaign is not a broad mutation-score or
RISC-V compliance claim. PicoRV32 mutation coverage is not established here.

## Run

```powershell
.\build\python-env\Scripts\python.exe scripts/run_mutation_tests.py --output build/mutations/a-fresh-run
.\build\python-env\Scripts\python.exe -m pytest -q --basetemp build/python-tests/mutation-check
```

Use a fresh output under this project's `build/` folder. `summary.json` and
`report.md` contain the baseline, per-mutant classifications, actual commands,
source identities and reference observations. Each `mutants/<id>/` folder holds
the source/patch manifest, native simulation artifacts and diagnostic prefix.
See [mutation-results.md](mutation-results.md) for actual executed outcomes.
The mutation-isolation unit fixtures also need their pytest temporary directory
inside `build/`, as in the tested command above, to exercise the same path guard.
