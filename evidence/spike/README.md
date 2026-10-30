# Spike milestone evidence

These are retained copies from `build/regressions/spike-milestone-verified`.
The original manifests retain their original paths and executor timestamps.
Use the matching `cases/<case-id>/` path here to inspect copied artifacts.

The accepted matrix has four CPU UVM cases and two component cases. Each CPU
case has two positive UVM profiles, one native UVM corruption control, one real
Spike execution, two reference comparisons and one comparison corruption control.
The raw UVM-only results correctly retain `spike_comparison_executed: false`;
the case envelope and Spike artifacts record the separately executed reference.

`audit.json` summarizes checked counts and source identity. `pytest.xml` records
75 utility tests, which are separate from RTL and ISS execution. Raw Spike
JSONL, commit logs, images, normalized traces, UVM logs and comparison controls
are retained. Coverage databases and built executables remain under `build/`;
their identities and original locations are recorded in the manifests.

The earlier `build/regressions/spike-milestone` attempt remains a failed 5/6 run
because concurrent Questa component sessions exceeded its one-session license.
Its CPU/Spike checks passed, but it is not the accepted full matrix. The accepted
run uses the scheduler's single Questa component slot. No RTL mutation campaign,
ISA coverage closure, live DPI comparison or FPGA result is claimed.
