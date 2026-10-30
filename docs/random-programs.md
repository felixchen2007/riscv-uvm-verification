# Bounded constrained-random instruction programs

`--program random --full` builds a program with **64 actual SV-constrained-
random instructions**, a directed corner prologue and a fixed terminal store.
It executes through the existing native UVM CPU environment and independent
scoreboard. Spike supplies a separate architectural reference. Python audits
input legality, schedules runs and compares traces; it does not generate a
second CPU environment or predict instruction results.

## Scope and termination

The program starts at `0x80`. It reuses the first 46 retirements of the corner
program, then executes the random body at `[0x13c, 0x23c)`. The final store at
`0x23c` writes `1` to `0x1004`. Total retirement count is 111: 46 directed
prologue instructions, 64 random instructions and the terminal store.

The prologue supplies bounded branches, a two-iteration backward loop, known
register initialization and directed corner goals. Control flow is not random.
The body is straight-line, so random data cannot change its execution count.
Destinations exclude x6 (the RAM base) and x27 (the terminal value). Word loads
and stores use x6 with aligned offsets 32–60, restricting them to
`0x1020`–`0x103c`, away from code and the signature. Unwritten data RAM is zero
in the UVM responders, private scoreboard and Spike.

## What is randomized

`riscv_instruction_item` contains SV `rand` fields with legal range and dependency
constraints. It selects among all ten register-register RV32I ALU operations,
destination/source registers, signed ADDI immediates, LUI values and scratch-word
addresses. Dependency modes can force rs1 or rs2 to use the previous destination
when legal. x0 remains a permitted destination; its architectural discard
behavior stays checked.

Eight calls to a constrained permutation object shuffle eight slots per block.
Each block contains four register ALUs, one ADDI, one LUI, one LW and one SW.
The complete body therefore has 32 register ALUs and eight of each other class.
The quota bounds memory traffic and ensures every instruction class is exercised;
the order and encoded instruction choices vary. This is a constrained subset,
not a uniform distribution over all legal RV32I programs.

The generator records **64 successful instruction `randomize()` calls and eight
successful schedule `randomize()` calls per test**. Those counts are separate
from memory timing randomization. Failed constraints are fatal. The random
profile requires full mode and has no procedural-PRNG fallback. The directed
smoke/corner profiles continue to report zero instruction-randomization calls.

Instruction and schedule objects use separate, explicitly seeded local RNG
streams. CPU topology and randomized bus timing cannot consume those streams.
Same-seed image/body hashes must match across processors and timing profiles;
distinct seeds must produce distinct **body** hashes, so a changed prologue
operand alone cannot qualify as instruction diversity. Exact replay is scoped
to the tested XSim version/source/configuration; emitted images are retained
for replay without regenerating them.

## Checking and coverage boundaries

`program-generation.json` records the seed, successful call counts and the 64
emitted items, including PC, encoding, class and dependency metadata. The shared
Python legality audit independently decodes each input encoding, rejects
unsupported operations/protected-register writes/memory escapes, checks the
block quotas and verifies that metadata matches the actual image. It contains
no arithmetic, memory-state or PC-result predictor.

The native UVM scoreboard still independently computes private architectural
state from the input image and checks actual RVFI plus passive memory
observations. The unchanged pinned Spike implementation executes the same
image. Every positive timing profile must match every retirement, including
register results, memory effects and the bounded branch paths.

The directed `retire_cg` and `corner_cg` remain required at 100% for this profile,
but the prologue can satisfy those goals. Two separate groups sample **only the
random body**: `random_kind_cg` covers its five instruction classes and is
required at 100%; `random_alu_cg` reports actual coverage of the ten random ALU
choices without assuming closure. Scratch-slot/register distributions and forced
dependency counts are procedural observations, reported separately from SV
covergroups. Every percentage belongs to one run; no averages or merged-bin
closure claims are made.

## Run and replay

```powershell
.\scripts\run.ps1 --program random --full --seed 20261029
.\scripts\run.ps1 --processor picorv32_rv32i --program random --full --seed 20261030
.\build\python-env\Scripts\python.exe scripts/run_regression.py --config config/regressions/random.json
```

The matrix preserves smoke and corners and adds random, across both processors
and two seeds: twelve CPU cases plus two complementary component cases. A CPU
case includes two positive timing profiles and its UVM corruption control.
Spike runs once per processor/seed/program image and compares both positive
profiles. Program generation artifacts, source hashes, corpus identities,
coverage observations and replay commands accompany the case manifests.

Standalone reference replay uses `run_spike_tests.py --program-profile random
--program <saved-image> --rvfi <saved-trace> --output <fresh-folder>`; it does not
claim new UVM execution or new randomization. See [random-program-results.md](random-program-results.md)
for measured execution evidence and limitations.
