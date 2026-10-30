# Verified v1 release

Status: **pass**.

| Stage | Result |
| --- | --- |
| python-tests | pass |
| baseline | pass |
| random | pass |
| advanced | pass |
| mutations-ibex | pass |
| mutations-pico | pass |
| coverage | pass |

| Executed evidence | Count |
| --- | --- |
| pytest_passed | 171 |
| cpu_matrix_cases | 16 |
| component_cases | 2 |
| component_variants | 4 |
| advanced_cases | 5 |
| positive_uvm_profiles | 41 |
| uvm_corruption_controls | 23 |
| spike_executions | 22 |
| spike_full_trace_matches | 40 |
| spike_comparison_controls | 22 |
| rtl_mutants_killed | 8 |
| rtl_mutants_survived | 0 |
| rtl_mutants_invalid_or_unqualified | 0 |

Coverage closure applies only to the declared scoped coverpoints and crosses.
Mutants are eight targeted RTL changes, not a broad mutation score.

No full RV32I ISA closure
No asynchronous interrupt comparison with Spike
Ibex external IRQ only; PicoRV32 custom IRQ excluded
No SoC peripherals/RAL or FPGA implementation claimed
