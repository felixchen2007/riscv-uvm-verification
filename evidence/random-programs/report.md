# Regression report

Status: **pass**. 14/14 cases passed.

| Case | Layer / scope | Result | Failure class |
| --- | --- | --- | --- |
| ibex_smoke_python_regfile_seed20261029 | python / component | pass |  |
| ibex_smoke_python_regfile_seed20261030 | python / component | pass |  |
| ibex_smoke_uvm_full_seed20261029 | uvm / cpu | pass |  |
| ibex_smoke_uvm_full_seed20261029_corners | uvm / cpu | pass |  |
| ibex_smoke_uvm_full_seed20261029_random | uvm / cpu | pass |  |
| ibex_smoke_uvm_full_seed20261030 | uvm / cpu | pass |  |
| ibex_smoke_uvm_full_seed20261030_corners | uvm / cpu | pass |  |
| ibex_smoke_uvm_full_seed20261030_random | uvm / cpu | pass |  |
| picorv32_rv32i_uvm_full_seed20261029 | uvm / cpu | pass |  |
| picorv32_rv32i_uvm_full_seed20261029_corners | uvm / cpu | pass |  |
| picorv32_rv32i_uvm_full_seed20261029_random | uvm / cpu | pass |  |
| picorv32_rv32i_uvm_full_seed20261030 | uvm / cpu | pass |  |
| picorv32_rv32i_uvm_full_seed20261030_corners | uvm / cpu | pass |  |
| picorv32_rv32i_uvm_full_seed20261030_random | uvm / cpu | pass |  |

One UVM case includes two positive timing profiles and its corruption control.
One Python component case includes the 32-register and 16-register configurations.
Coverage percentages are per-run observations; simulator bins have not been merged.
RTL mutation campaigns were not executed. See summary.json for replay commands and artifacts.

Spike: requested=True; successful executions=12; profile matches=24; comparison corruption controls=12.

Cross-processor trace matches: 12.

Distinct constrained-random instruction corpora: 2.
