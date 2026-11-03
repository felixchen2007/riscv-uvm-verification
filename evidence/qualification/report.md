# Live Spike qualification

Status **pass**

| Stage | Result |
| --- | --- |
| spike-build | pass |
| live-spike-build | pass |
| python-checks | pass |
| directed | pass |
| random | pass |
| coverage | pass |

| Measure | Count |
| --- | ---: |
| Python checks passed | 175 |
| CPU, program and seed cases passed | 12 |
| Positive UVM profiles | 24 |
| Live retirement matches | 2020 |
| Spike-only observation controls detected | 36 |
| Combined functional bins hit | 60 |

Live checking covers normal bounded RV32I programs on both CPU adapters.
Reset and interrupt scenarios use the separate native UVM flow.
