# Verified bounded CPU v1 results

The complete one-command release passed on 2026-10-30 UTC.

Execution root: `build/releases/v1-verified`. Archived evidence: `evidence/v1`.
The release used the source identities recorded in `release.json` and retained all earlier milestones separately.

| Executed evidence | Count |
| --- | ---: |
| pytest passed | 171 |
| cpu matrix cases | 16 |
| component cases | 2 |
| component variants | 4 |
| advanced cases | 5 |
| positive uvm profiles | 41 |
| uvm corruption controls | 23 |
| spike executions | 22 |
| spike full trace matches | 40 |
| spike comparison controls | 22 |
| rtl mutants killed | 8 |
| rtl mutants survived | 0 |
| rtl mutants invalid or unqualified | 0 |

All clean positive profiles had zero UVM errors/fatals and zero reported simulator/assertion failures.
Expected negative-control errors and actual mutant errors are separate evidence.

## Configuration

Windows host; Vivado XSim 2025.2 / UVM 1.2; Questa Starter 2024.3 for cocotb VPI only; Python 3.12 / cocotb 2.0.1 / pytest 8.4.2.
Pinned Ibex v2.1.0 `38c070939183cc10940b66c8e9e04eeca6b65470` and PicoRV32 `ef203c2b0a3fb793280f5114941416c425c5b461`.
Pinned official Spike v1.1.0 `530af85d83781a3dae31a4ace84a573ec255fefa` executed under Ubuntu WSL.
The release checked 275 source/configuration/dependency identities. Vendor snapshots remained unchanged.
Baseline seeds: 20261029/20261030; random seeds: 20261029–20261032; advanced and mutation seed: 20261029.
Each random profile executed 64 SV instruction randomizations and eight SV schedule randomizations, separately from randomized memory timing.

## Advanced native scenarios

| CPU | Scenario | Native observations | Independent reference |
| --- | --- | --- | --- |
| ibex_smoke | factory | factory calls=59; virtual completed=1 | Full final trace matched Spike |
| ibex_smoke | irq | factory calls=19; virtual completed=1; IRQ entry=1, deassertion=1, MRET=1; mcause=0x8000000b, mepc=0x9c | Native independent CSR/event checks; no asynchronous Spike comparison |
| ibex_smoke | reset | factory calls=89; virtual completed=1; resets=1; pending=1; accepted=1; prefix=27; final=47 | Full final trace matched Spike |
| picorv32_rv32i | factory | factory calls=58; virtual completed=1 | Full final trace matched Spike |
| picorv32_rv32i | reset | factory calls=88; virtual completed=1; resets=1; pending=1; accepted=0; prefix=27; final=47 | Full final trace matched Spike |

Ibex resets an accepted outstanding transaction; Pico resets a pending unaccepted valid/ready transaction.
Both aborted prefixes matched their reference prefixes without being accepted as complete executions.
Raw all-epoch traces remain alongside final-epoch traces. Pico custom IRQ instructions are excluded.

## Native coverage closure

| Covergroup | Native merged covered / declared bins |
| --- | ---: |
| retire_cg | 15 / 15 |
| corner_cg | 22 / 22 |
| random_kind_cg | 5 / 5 |
| random_alu_cg | 10 / 10 |
| random_memory_cg | 8 / 8 |

All 20 coverpoints/crosses and 60 scoped bins closed separately for each CPU and in the combined native merge.
XCRG restored four stalled-profile databases per CPU and eight in the combined merge; individual reports also preserve both timing profiles.
Random-body coverage excludes the directed prefix. No percentages were averaged. This is not complete ISA or RTL code coverage.

| CPU | Seed | Profile | Body ALU bins | Scratch word bins |
| --- | ---: | --- | ---: | ---: |
| ibex_smoke | 20261029 | no_added_delay | 10/10 | 6/8 |
| ibex_smoke | 20261029 | stalled | 10/10 | 6/8 |
| ibex_smoke | 20261030 | no_added_delay | 9/10 | 7/8 |
| ibex_smoke | 20261030 | stalled | 9/10 | 7/8 |
| ibex_smoke | 20261031 | no_added_delay | 10/10 | 8/8 |
| ibex_smoke | 20261031 | stalled | 10/10 | 8/8 |
| ibex_smoke | 20261032 | no_added_delay | 10/10 | 8/8 |
| ibex_smoke | 20261032 | stalled | 10/10 | 8/8 |
| picorv32_rv32i | 20261029 | no_added_delay | 10/10 | 6/8 |
| picorv32_rv32i | 20261029 | stalled | 10/10 | 6/8 |
| picorv32_rv32i | 20261030 | no_added_delay | 9/10 | 7/8 |
| picorv32_rv32i | 20261030 | stalled | 9/10 | 7/8 |
| picorv32_rv32i | 20261031 | no_added_delay | 10/10 | 8/8 |
| picorv32_rv32i | 20261031 | stalled | 10/10 | 8/8 |
| picorv32_rv32i | 20261032 | no_added_delay | 10/10 | 8/8 |
| picorv32_rv32i | 20261032 | stalled | 10/10 | 8/8 |

## Actual RTL mutation observations

| CPU | Mutation | First UVM diagnostic | Errors / fatals | Spike prefix result | Outcome |
| --- | --- | --- | ---: | --- | --- |
| ibex_smoke | add_flip_bit0 | RVFI_RD | 115 / 0 | Architectural mismatch at record 0: rd_data: 4294967294 != 4294967295 | killed |
| ibex_smoke | beq_inverted | RVFI_PC | 42 / 0 | Architectural mismatch at record 36: pc: 272 != 276 | killed |
| ibex_smoke | sll_flip_bit0 | RVFI_RD | 2 / 0 | Architectural mismatch at record 19: rd_data: 2147483649 != 2147483648 | killed |
| ibex_smoke | store_flip_bit0 | MEM_STORE_DATA | 29 / 0 | Architectural mismatch at record 28: rd_data: 21 != 20 | killed |
| picorv32_rv32i | pico_add_flip_bit0 | RVFI_RD | 39 / 0 | Architectural mismatch at record 2: rd_data: 1 != 0 | killed |
| picorv32_rv32i | pico_beq_inverted | RVFI_PC | 42 / 0 | Architectural mismatch at record 36: pc: 272 != 276 | killed |
| picorv32_rv32i | pico_sll_flip_bit0 | RVFI_RD | 2 / 0 | Architectural mismatch at record 19: rd_data: 2147483649 != 2147483648 | killed |
| picorv32_rv32i | pico_store_flip_bit0 | MEM_STORE_DATA | 31 / 0 | Architectural mismatch at record 27: memory: {'kind': 'store', 'address': 4096, 'mask': 15, 'data': 21} != {'kind': 'store', 'address': 4096, 'mask': 15, 'data': 20} | killed |

Each campaign first passed a fresh pristine UVM/Spike baseline. Architectural mutations require an independent retirement divergence; the physical store-data checker separately qualifies bus corruption.
Mutant traces remain explicit incomplete diagnostic prefixes, including those that reach the ordinary terminal length. Cascaded errors are retained.
No compile-invalid, infrastructure-failed, unqualified or surviving target was counted as a kill. These eight targets are not a broad mutation score.

## Reproduce and extend

```powershell
.\scripts\v1.ps1
```

See [the v1 guide](v1.md) for per-stage commands, demonstration steps and architecture.
The manual self-hosted CI workflow is checked in but has not been published or executed in CI.
The owner has accepted v1 as the completed project scope. SoC peripherals and RAL are not planned or required. Broader ISA/control-flow generation, synchronized asynchronous Spike events and Quartus/DE10-Lite implementation are optional extensions.
