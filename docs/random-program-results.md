# Bounded random instruction results

**All 14 final regression cases passed.** The native UVM environment executed
smoke, directed corners and the new random profile on Ibex and PicoRV32, at
seeds 20261029 and 20261030. Actual SV instruction/schedule randomization,
same-seed replay, cross-seed diversity, independent Spike comparisons and
complementary component checks were verified on one stable source snapshot.

| Measured result | Outcome |
| --- | --- |
| CPU cases | 12 pass: two cores × three programs × two seeds |
| Positive UVM timing profiles | 24 pass |
| Positive warnings / errors / fatals / assertion failures | 0 / 0 / 0 / 0 in every profile |
| Actual Spike executions / profile comparisons | 12 successful executions / 24 matches |
| Native UVM corruption controls | 12 detected, each with the intended `RVFI_RD` error and zero fatals |
| Independent comparison corruption controls | 12 intended `rd_data` mismatches detected |
| Cross-processor comparisons | 12 matches, indexed by program, seed and timing |
| Complementary component tests | 4 actual cocotb register-file tests passed |
| Utility tests | 123 pytest tests passed; synthetic fixtures are separate from RTL/ISS execution |
| Source identities | 254 recorded SHA-256 entries stable across the final matrix |
| Preserved baseline inputs | 16 smoke/corner positive images unchanged byte for byte |
| Preserved random prologue | All eight positive random images retain the earlier directed prefix |

## Actual generation and replay

Each random-profile simulation performed **64 successful instruction
`randomize()` calls and eight successful schedule `randomize()` calls**. These
are separate from the memory-delay randomization counter. The 64-instruction
body contains 32 register ALUs and eight each of ADDI, LUI, LW and SW, arranged
in eight constrained shuffled blocks. ALU kinds, registers, immediates, LUI
values, word addresses and legal forced dependencies vary.

Each complete random program retires 111 instructions: 46 directed prologue
instructions, 64 random body instructions and a final signature store. The
body occupies `[0x13c, 0x23c)` and cannot branch, overwrite x6/x27, access code or
touch the signature address. Aligned scratch RAM is `0x1020`–`0x103c`. The fixed
store at `0x23c` writes `1` to `0x1004`. Branches and the bounded backward loop
belong to the directed prologue; random control flow is not claimed.

All four processor/timing replays of a seed produced the same emitted image
and body hash. The two seeds produced different bodies at **all 64 instruction
positions**. Diversity was checked on body-only hashes, independently of the
seed-derived prologue operand. The full hashes, encodings and actual generation
metadata are retained in the case manifests and `summary.json`'s `random_corpora`.

The independent input auditor decoded each emitted body, checked class quotas,
protected-register and scratch-memory rules, and matched the item/dependency
metadata to the encodings. It predicts no instruction results. The UVM
scoreboard continues to compute private architectural state and check actual
RVFI plus passive bus observations; unchanged upstream Spike separately executes
the identical input image. Every positive random run matched all 111 retirements.

## Coverage and observed limits

The directed opcode/branch and corner groups reached 100% in every random run.
Those groups can be satisfied by the prologue. Separate SV groups sample only
the random body, preventing the directed instructions from hiding random gaps.

| Seed | Random-body class group | Random-body ALU group | Missing random ALU kind | Forced dependencies | Scratch slots visited |
| --- | --- | --- | --- | ---: | --- |
| 20261029 | 100% (5/5 classes) | 100% (10/10 kinds) | None | 20 | 6 of 8 |
| 20261030 | 100% (5/5 classes) | 90% (9/10 kinds) | SLL | 26 | 7 of 8 |

These observations agree across both processors and timing profiles. The scratch
slot and dependency columns are procedural input-distribution observations,
not SV covergroup closure. Slot 11 (`0x102c`) was not selected by either tested
corpus; seed 20261029 also did not select slot 13 (`0x1034`). These are useful
targets for a later coverage-driven campaign.

Eight individual native XCRG 2025.2 text/HTML reports confirm the body-only
measurements, including the uncovered SLL bin in seed 20261030. Each report
contains 19 coverpoints/crosses across the directed and random groups. The
directed groups and five-class body group have no uncovered bins; random ALU
coverage remains an observation rather than a required 100% gate. No runs or
bin databases were merged, and percentages were not averaged. Two seed corpora
do not establish full ISA, register, dependency or address-space closure.

## Configuration, artifact checks and reproduction

The DUT snapshots remain unmodified: Ibex
`38c070939183cc10940b66c8e9e04eeca6b65470` and PicoRV32
`ef203c2b0a3fb793280f5114941416c425c5b461`. CPU acceptance used Vivado XSim
2025.2 / UVM 1.2, with full constrained randomization and covergroups. Component
tests used Questa Intel FPGA Starter 2024.3 VPI and cocotb 2.0.1; the scheduler
serializes those cases for the installed single-session license.

Spike v1.1.0 remains pinned at
`530af85d83781a3dae31a4ace84a573ec255fefa`, using the same verified WSL build
and unchanged bridge. It supports this program through the selected count and
terminal contract. There is no procedural fallback for the random instruction
profile: missing `--full`, failed constraints or missing execution counters fail.

The artifact audit caught padding in the directed smoke generation label. The
SV formatter was corrected, exact metadata identity/count checks were added,
and the entire final matrix was rerun on the corrected frozen sources. Tests
also reject padded identifiers, noninteger metadata and incorrect call/item
counts. Earlier bring-up runs remain separate in the build folder.

```powershell
.\scripts\run.ps1 --program random --full --seed 20261029
.\scripts\run.ps1 --processor picorv32_rv32i --program random --full --seed 20261030
.\build\python-env\Scripts\python.exe scripts/run_regression.py --config config/regressions/random.json
.\build\python-env\Scripts\python.exe -m pytest -q
```

The accepted matrix is `build/regressions/random-program-verified/`. Its
`summary.json`, `report.md`, `audit.json` and `coverage-exports.json` record the
results, native export commands, hashes and replay arguments. The 681 retained
artifacts in `evidence/random-programs/` include raw UVM/RVFI/Spike logs, emitted
images and generation items, normalized traces, controls, component/utility XML,
positive coverage databases and all eight native random-coverage reports.
`artifact-sha256.json` indexes the retained files; original paths and executor
timestamps are preserved. [random-programs.md](random-programs.md) defines the
generator's legality and termination policy.

This result covers bounded random data/instruction choices with directed control
flow. Broader ISA/control-flow generation, larger seed campaigns, SoC events/RAL,
live DPI and RTL mutation testing remain later work. Corruption controls qualify
observation/checking paths and are not RTL mutant kills. No FPGA result is claimed.
