# Regression report

Status: **pass**. 6/6 cases passed.

| Case | Layer / scope | Result | Failure class |
| --- | --- | --- | --- |
| ibex_smoke_python_regfile_seed20261029 | python / component | pass |  |
| ibex_smoke_python_regfile_seed20261030 | python / component | pass |  |
| ibex_smoke_uvm_full_seed20261029 | uvm / cpu | pass |  |
| ibex_smoke_uvm_full_seed20261030 | uvm / cpu | pass |  |
| picorv32_rv32i_uvm_full_seed20261029 | uvm / cpu | pass |  |
| picorv32_rv32i_uvm_full_seed20261030 | uvm / cpu | pass |  |

One UVM case includes two positive timing profiles and its corruption control.
One Python component case includes the 32-register and 16-register configurations.
Coverage percentages are per-run observations; simulator bins have not been merged.
RTL mutation campaigns were not executed. See summary.json for replay commands and artifacts.

Spike: requested=True; successful executions=4; profile matches=8; comparison corruption controls=4.

Cross-processor trace matches: 4.
