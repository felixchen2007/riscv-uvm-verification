# Bounded CPU v1 evidence

Copied from the completed passing local release `build/releases/v1-verified`.
Original commands and manifests retain their execution paths. `release/` contains
raw/native/reference/coverage/mutation evidence. `sources/` contains the tested
non-vendor verification sources and vendor locks. The repository's unchanged
vendor snapshots are identified by the full source hashes.

`artifact-manifest.json` hashes every archived artifact except itself and this
index. Historical milestones remain separate. Compilation, observation
controls, RTL mutants, native IRQ checks and full Spike matches have distinct
reported scopes; none are substituted for another.
