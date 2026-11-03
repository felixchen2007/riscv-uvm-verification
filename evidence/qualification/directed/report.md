# Regression report

Status: **pass**. 4/4 cases passed.

| Case | Layer / scope | Result | Failure class |
| --- | --- | --- | --- |
| ibex_smoke_uvm_full_seed20261029 | uvm / cpu | pass |  |
| ibex_smoke_uvm_full_seed20261029_corners | uvm / cpu | pass |  |
| picorv32_rv32i_uvm_full_seed20261029 | uvm / cpu | pass |  |
| picorv32_rv32i_uvm_full_seed20261029_corners | uvm / cpu | pass |  |

One UVM case includes two positive timing profiles and its corruption control.
Coverage percentages are per-run observations; simulator bins have not been merged.
RTL mutation campaigns were not executed. See summary.json for replay commands and artifacts.

Spike: requested=True; successful executions=4; profile matches=8; comparison corruption controls=4.

Cross-processor trace matches: 4.

Distinct constrained-random instruction corpora: 0.

Live Spike/DPI-C: requested=True; compared retirements=244; detected live controls=12.
