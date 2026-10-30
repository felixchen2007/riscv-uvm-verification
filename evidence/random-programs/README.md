# Bounded random instruction evidence

Retained from build/regressions/random-program-verified. Original paths and
executor timestamps remain in the manifests. The matrix preserves both directed
baselines and executes the random profile through native UVM and actual Spike.
Generation manifests contain the emitted stimulus and actual randomize counters;
they contain no expected architectural results. Same-seed images replay across
both cores/timing profiles; body-only hashes differ across the two seeds.

Positive coverage databases and eight independent native XCRG reports are kept,
including any uncovered random ALU bins. Directed prologue coverage is separate
from body-only groups. No run merging, random-control-flow coverage, RTL mutant
kills, full-ISA closure or FPGA result is claimed. See audit.json and the project
docs/random-program-results.md for measured counts and scope.
