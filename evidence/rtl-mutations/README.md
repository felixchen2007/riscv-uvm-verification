# Actual Ibex RTL mutation evidence

Retained from build/mutations/ibex-verified. The pinned originals remain unchanged;
each mutant's effective compiled source differs in exactly one owned RTL copy.
Original/modified files, patches, hashes, actual compiler lists, UVM logs and
retirement observations are retained. A matching stopped prefix is never a full
pass. One real clean Spike reference is reused for identical input images.

The initial qualification attempt rejected cascaded errors under a single-error
rule. Its original summary/report remain separate. The final campaign was rerun
with an expected-first-error policy, complete counts and independent reference
divergence checks. These are actual DUT-source mutations, separate from the two
clean-baseline observation/comparator controls. Only four Ibex mutants at one
program/seed are qualified; no broad score or PicoRV32 coverage is claimed.
