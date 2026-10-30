# Directed programs and branch coverage results

**All 10 requested regression cases passed.** Ibex and PicoRV32 each executed
the preserved smoke and the new directed-corner program at seeds 20261029 and
20261030. Every positive timing profile passed native UVM and matched an actual
independent Spike execution. The targeted branch and corner groups reached 100%
in every positive corner run, confirmed by individual native bin reports.

| Measured result | Outcome |
| --- | --- |
| CPU cases | 8 pass: two processors × two programs × two seeds |
| Positive UVM profiles | 16 pass: no-added-delay and stalled per CPU case |
| Positive UVM warnings / errors / fatals / assertion failures | 0 / 0 / 0 / 0 in every profile |
| Actual Spike executions / profile comparisons | 8 successful executions / 16 matches |
| Native UVM corruption controls | 8 intended `RVFI_RD` errors detected, each with one error and zero fatals |
| Independent comparison corruption controls | 8 intended `rd_data` mismatches detected |
| Cross-processor comparisons | 8 matches, indexed separately by program, seed and timing profile |
| Complementary component tests | 4 actual cocotb register-file tests passed |
| Utility tests | 97 pytest tests passed; synthetic fixtures remain separate from RTL/ISS execution |
| Source identity | 249 recorded SHA-256 entries stable across all 10 cases |
| Preserved smoke inputs | All eight positive smoke images match the earlier Spike evidence byte for byte |

## New program and measured coverage

The new `corners` profile retires 47 instructions, with three loads, four
stores, three taken branches, three untaken branches and one JAL. It starts at
`0x80` and ends at `0x13c` with the checked signature store to `0x1004`.
Its ten register ALU operations include signed/unsigned comparisons and shifts;
the independent scoreboard and Spike agree on wraparound, sign boundaries,
immediate limits, x0 discard, register aliases, x31, load-use behavior, negative
word offsets and overwrite/readback. The audit also checks the intended corner
result values directly in the recorded retirements.

Each corner run has these observed branch outcomes, independently checked from
successive retirement PCs and matched against the SV counters:

| Outcome | Hits per corner run |
| --- | ---: |
| BEQ taken | 1 |
| BEQ not taken | 1 |
| BNE taken | 2 |
| BNE not taken | 2 |

The BNE count includes a bounded backward loop and its exit. These observations
close the two holes in the earlier BEQ/BNE cross for the new program.

| Program | Positive runs | Existing opcode/branch `retire_cg` | New `corner_cg` |
| --- | ---: | --- | --- |
| Original smoke | 8 | 87.50% per run, retaining its original holes | Partial; full corner goals are not required for this profile |
| Directed corners | 8 | 100% per run | 100% per run |

Vivado XCRG 2025.2 exported each of the eight positive corner databases
**separately** to text/CSV and HTML. Each report confirms zero uncovered bins
across 17 coverpoints/crosses: seven opcode-family bins, two direction bins, two
branch-kind bins, all four branch-cross bins, twelve named corner-hit bins and
ten register ALU-kind bins. The actual bin hit counts, original positive
databases and export commands/hashes are retained. No seed or timing profiles
were merged, and no percentages were averaged.

The instruction skeletons are directed, with one seed-derived operand. Full
mode executed SV constrained-random **memory timing**, with successful
randomization counts retained per run. These results close the specified finite
groups; they do not establish full RV32I, all branch instructions or processor
coverage closure. Random instruction generation remains future work.

## Configuration and reuse

The DUTs remain unmodified at Ibex
`38c070939183cc10940b66c8e9e04eeca6b65470` and PicoRV32
`ef203c2b0a3fb793280f5114941416c425c5b461`. Their hardware parameter profiles
and physical memory agents are unchanged. Native CPU acceptance used Vivado
XSim 2025.2 / UVM 1.2. Complementary register-file tests used Questa Intel FPGA
Starter 2024.3 VPI and cocotb 2.0.1, with component cases serialized for its
single-session license.

Both programs share the same UVM test, memory sequences/drivers, passive
monitors and independent architectural scoreboard. Program contracts are
separate from CPU profiles and specify counts, terminal PCs and coverage goals.
Normalized traces and regression comparisons include program identity, so a
missing corner case cannot be replaced by a passing smoke case.

Spike v1.1.0 remains pinned to
`530af85d83781a3dae31a4ace84a573ec255fefa`, using the previously verified WSL
build and unchanged bridge executable. Its actual execution window comes from
the selected program contract. Every UVM profile compares all meaningful
retirements against the independent reference; DUT results never initialize
expected state. The earlier [Spike milestone](spike-results.md) remains a
separate historical record.

## Reproduce and evidence

```powershell
.\scripts\run.ps1 --program corners --full
.\scripts\run.ps1 --processor picorv32_rv32i --program corners --full
.\build\python-env\Scripts\python.exe scripts/run_regression.py --config config/regressions/corners.json
.\build\python-env\Scripts\python.exe -m pytest -q
```

The accepted output is `build/regressions/directed-corners-milestone/`.
`summary.json`, `report.md`, `audit.json` and `coverage-exports.json` record the
matrix, checks and native coverage exports. The 525 retained artifacts under
`evidence/directed-corners/` include raw UVM/RVFI/Spike logs, program images,
normalized traces, controls, component/utility XML, positive XSim coverage
databases and native text/HTML reports. `artifact-sha256.json` indexes them.
Original paths and executor timestamps remain in the manifests. For example,
the first Ibex corner report is under its case's
`coverage-reports/no_added_delay/functionalCoverageReport/` folder.

[programs.md](programs.md) defines the program and goal details. Live DPI,
compressed instructions, additional immediate/branch operations, exceptions,
interrupts, debug, SoC RAL and RTL mutation campaigns remain later work. The
corruption controls in this run qualify observation/checking paths and are not
RTL mutant kills. No FPGA implementation result is included.
