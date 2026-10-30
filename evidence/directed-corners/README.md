# Directed corner milestone evidence

Retained from `build/regressions/directed-corners-milestone`. Original paths and
executor timestamps remain in the manifests. Matching case-relative artifacts
are retained here, including positive XSim coverage databases and individual
native XCRG text/HTML reports for all eight positive corner runs. No runs are
merged. The original smoke images match the earlier Spike evidence byte for byte.

The matrix has eight CPU cases (two programs, two cores, two seeds) and two
component cases. CPU acceptance is native UVM; Spike supplies separate actual
reference execution. Utility fixtures remain distinct from RTL/ISS evidence.
See audit.json for checked counts and docs/directed-corners-results.md for scope.
