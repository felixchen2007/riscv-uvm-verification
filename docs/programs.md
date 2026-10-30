# Shared program profiles

Program selection is independent of processor selection. Both native UVM CPU
adapters use `ibex_program`, the same memory sequences, passive monitors and
independent `riscv_scoreboard`. Program contracts live in `config/programs/`;
`--program smoke` remains the default. Existing processor IDs and RTL locks are
preserved. No second CPU environment or Python instruction-result model is added.

| Profile | Retirements | Terminal PC | Loads / stores | Taken / untaken branches | Purpose |
| --- | ---: | --- | --- | --- | --- |
| `smoke` | 14 | `0xbc` | 1 / 2 | 1 / 1 | Original image, including its existing coverage holes |
| `corners` | 47 | `0x13c` | 3 / 4 | 3 / 3 | Directed ALU boundaries, dependencies, memory offsets, all four BEQ/BNE outcomes and a bounded backward loop |
| `random` | 111 | `0x23c` | 11 / 12 | 3 / 3 | Directed prologue plus 64 actual SV-constrained-random instructions; [generation policy](random-programs.md) |
| `irq` | 15 minimum; bounded variable parking | `0xa4` | 0 / 1 | At least 1 / 1 | Ibex-only machine-external interrupt, handler CSR reads and MRET; requires `--scenario irq --full`; [event contract](v1.md) |

All profiles start at `0x80`, use one RV32 hart in machine mode and finish with a
checked store of `1` to `0x1004`. Smoke and corners use fixed instruction
skeletons with one seed-derived operand and randomize memory timing in full
mode. The separate random profile also executes actual SV instruction/schedule
randomization; its directed prologue and straight-line body bound termination.
The separate IRQ program has no random instructions and receives native
independent UVM checking and a passive event/path audit. It is excluded from
the current offline Spike comparator because that bridge has no synchronized
external interrupt input.

## Corner program

The new program exercises all ten register-register RV32I ALU operations:
ADD, SUB, XOR, AND, OR, SLT, SLTU, SLL, SRL and SRA. It contrasts signed and
unsigned comparisons of `0x80000000` against `1`, and logical/arithmetic shifts
of a negative operand. Shift sources include 31 and 32, checking that only the
low five bits select the shift amount. Other cases include addition wrap to
zero, crossing `0x7fffffff` to `0x80000000`, subtraction underflow, ADDI's signed
immediate limits, a nonzero attempted x0 write, source/destination aliases,
x31 dependencies, an immediate load-use dependency, negative word offsets,
store overwrite/readback and JAL's link value with a skipped poison path.

The branch plan is explicit:

| Outcome | Smoke hits | Corners hits |
| --- | ---: | ---: |
| BEQ taken | 1 | 1 |
| BEQ not taken | 0 | 1 |
| BNE taken | 0 | 2 |
| BNE not taken | 1 | 2 |

The last two BNE observations come from a two-iteration decrementing loop, so
both a negative branch displacement and loop exit are checked. Taken forward
branches skip poison instructions. Unexpected paths fail PC/instruction checks;
merely reaching the final store does not pass acceptance.

## Checking and coverage

The UVM scoreboard independently decodes the expected input image and updates
private registers/memory/PC. It checks RVFI operands/results and separately
observed memory requests/responses. The new ALU semantics are in that model;
Spike executes its own unchanged upstream instruction implementation. Neither
reference copies a DUT result into expected state.

The existing `retire_cg` retains its opcode-family goals and BEQ/BNE direction
cross. Full-mode corner acceptance requires 100% of that existing group in each
positive run. A new `corner_cg` has twelve named hit goals (wrap, sign boundary,
underflow, immediate minimum/maximum, x0 discard, two alias forms, load-use,
negative memory offset, high register and masked shift count), plus ten ALU-kind
bins. Full-mode corner acceptance also requires 100% of this scoped group.
These are finite directed goals, not full RV32I or processor coverage closure.

The scoreboard reports four separate branch counters. Python independently
derives outcomes from each observed retirement's next PC, checks that it is the
encoded target or fallthrough, and requires exact agreement with the program
contract and SV counters. These observations complement the actual SV covergroup;
they do not replace it. Coverage percentages remain per instance/run, without
averaging or claiming a merged database.

Normalized traces carry `program_profile` in addition to image SHA-256 and CPU
identity. Cross-processor comparisons are indexed by processor, seed **and
program**; missing one requested program cannot be hidden by another. Spike
uses the selected profile's entry, count and terminal signature, with a strict
terminal-PC check during normalization. Both timing profiles compare against
the actual reference execution of their identical image.

## Run

From the project folder in PowerShell:

```powershell
.\scripts\run.ps1 --processor ibex_smoke --program corners --full
.\scripts\run.ps1 --processor picorv32_rv32i --program corners --full
.\build\python-env\Scripts\python.exe scripts/run_regression.py --config config/regressions/corners.json
```

The corners matrix requests smoke and corners, both processors and two seeds, with full UVM,
actual Spike comparisons and the two complementary component cases. Native UVM
still owns CPU acceptance. Questa component cases share one licensed session;
the bounded worker pool permits concurrent XSim cases. Use fresh output folders.
The standalone reference replay tool accepts `--program-profile corners` alongside
its `--program <image-path>` argument. Extended CPU program acceptance currently
uses XSim; Questa retains its separately supported original smoke mode.
