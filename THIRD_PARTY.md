# Third-party source

The independent reference build uses unmodified
[Spike v1.1.0](https://github.com/riscv-software-src/riscv-isa-sim/tree/530af85d83781a3dae31a4ace84a573ec255fefa),
commit `530af85d83781a3dae31a4ace84a573ec255fefa`, under its BSD-style license.
`config/spike.json` pins the source and build options. The ignored source
checkout/archive retain the original `LICENSE` and individual component notices,
including those in SoftFloat and libfdt. Binaries are built locally in `build/`
and are not redistributed. The project-owned bridge observes state through the
pinned C++ API without patching the upstream implementation. Build manifests
record archive, executable, adapter and configuration hashes.

`vendor/picorv32/` contains the unmodified `picorv32.v`, `COPYING` and `README.md`
from [YosysHQ PicoRV32](https://github.com/YosysHQ/picorv32/tree/ef203c2b0a3fb793280f5114941416c425c5b461),
commit `ef203c2b0a3fb793280f5114941416c425c5b461`, under the ISC license.
The source copyright/permission notice and COPYING are retained.
`vendor/picorv32.lock.json` records the revision and per-file hashes; the runner
checks them before compilation. No local RTL patch or upstream TESTBUG macro is used.

`vendor/ibex/` is a selected, unmodified snapshot of
[lowRISC Ibex v2.1.0](https://github.com/lowRISC/ibex/tree/38c070939183cc10940b66c8e9e04eeca6b65470),
commit `38c070939183cc10940b66c8e9e04eeca6b65470`, under Apache-2.0.
The original LICENSE, NOTICE and CREDITS.md are retained. The lowRISC primitive
sources and DV coverage macros are taken from that same snapshot; their original
copyright and SPDX headers are retained. Individual file hashes are recorded in
`vendor/ibex.lock.json` and verified before compilation.

The project uses the simulator's installed UVM 1.2 library. UVM and simulator
binaries are not redistributed here. `build/ibex-upstream` is only a temporary
upstream checkout used to create the snapshot and is excluded from source control.

The complementary Python environment installs cocotb and pytest from PyPI into
the ignored build folder, using the versions in `requirements-verification.txt`.
Those packages and their binaries are not vendored; their license metadata
remains in the installed distributions. The cocotb component harness compiles
the same locked upstream RTL used by the UVM project.
