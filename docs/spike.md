# Independent offline Spike reference

Spike belongs to Layer 2. Native UVM remains the CPU acceptance environment;
Python runs the independent reference after successful UVM execution and
compares both timing profiles. `--spike` requires an actual reference execution
for every CPU/seed case. Missing, stale or failed reference builds fail the
requested regression; there is no Python CPU-model fallback.

## Build and run on this Windows PC

The source is the official Spike v1.1.0 release, pinned to
`530af85d83781a3dae31a4ace84a573ec255fefa` in `config/spike.json`.
The native Linux executable runs under the installed Ubuntu WSL distribution.
XSim continues to run natively on Windows. No RISC-V compiler or ELF conversion
is needed for the current shared readmemh smoke image.

The Ubuntu build needs `g++`, `make` and `device-tree-compiler`. This PC also has
the Boost development packages installed, but the optional upstream interactive
socket features are disabled. GCC 15 needs the recorded `-include cstdint`
option for this older source release. No upstream file is patched. The build
exports Linux line endings explicitly and uses an owned Linux cache under
`~/.cache/rvverify-spike/` to avoid spaces in generated Makefile paths.

From the project folder in PowerShell:

```powershell
.\build\python-env\Scripts\python.exe scripts/build_spike.py --jobs 8
.\build\python-env\Scripts\python.exe scripts/run_regression.py --jobs 2 --include-cocotb --spike
# Equivalent checked-in acceptance matrix:
.\build\python-env\Scripts\python.exe scripts/run_regression.py --config config/regressions/spike-smoke.json
```

Use a fresh `--output` folder for each regression. `build/spike/` contains the
upstream source archive, reference executable, official CLI, build logs and
build manifest. Every reference run verifies source/archive/configuration and
executable hashes against that manifest, then checks them again after execution.
Changing the bridge or build configuration requires rebuilding.
The scheduler allows concurrent XSim CPU cases but serializes Questa component
cases because this PC's node-locked Starter license permits only one session.

`scripts/run_spike_tests.py --processor <id> --program <image> --rvfi <csv>
--output <fresh-folder>` can independently replay a recorded image/comparison.
It records that it did not execute a new UVM simulation. The regression runner
is the acceptance entry point for fresh combined UVM/Spike evidence.

## Reference boundary

`verification/reference/spike_bridge.cc` is a thin state-observation adapter
linked to the pinned Spike libraries. `processor_t::step(1)` executes each
instruction inside Spike. The adapter contains no instruction-result model.
Its inputs are the original program image and the declared CPU configuration;
DUT retirement values, the UVM scoreboard and expected signatures calculated
from DUT state are never reference inputs.

| Contract | Current scope |
| --- | --- |
| Program | Exact shared word-address readmemh image; converted only to explicit byte addresses, with overlap/undefined-bit/range rejection |
| Initial state | One RV32 hart, machine privilege, zero registers and 64 KiB of zero RAM before image loading, little endian, PC `0x80` |
| ISA | Ibex reference `rv32ic`, Pico reference `rv32i`; the exercised program contains aligned 32-bit RV32I instructions only |
| Execution window | Selected program contract: 14 successful retirements for smoke, 47 for corners or 111 for random, ending with the signature store of `1` to `0x1004`; PC begins directly at entry, excluding reset-ROM execution |
| Register writes | Spike's actual commit register-write log; architectural x0/no-write canonicalized to zero |
| Memory effects | Spike commit addresses, widths and store values; word-load data read from the independent Spike RAM after the load, valid for this ordinary RAM-only scope |
| Traps / events | Require one increment of Spike's retired-instruction counter per step, machine privilege and no debug mode; no interrupts, debug requests or MMIO are injected; unsupported event/instruction behavior fails |
| Comparison | Original image hash, ISA, record count/order, hart, PC, instruction, destination register/data, load/store effect and trap/halt/interrupt flags |

This adapter deliberately rejects compressed execution, non-word loads/stores,
CSRs and opcodes beyond the bounded smoke families. It does not establish
exception, interrupt, debug, privilege-transition or full-ISA coverage. Ibex's
compressed capability is configured in Spike but is not exercised by this image.

The reference produces raw JSONL records and an upstream commit log. Layer 2
normalizes those records to the same v1 contract as RVFI, rejects missing or
reordered retirements, and compares both positive timing profiles. A per-case
comparison control flips a copy of one DUT writeback result and requires the
specific `rd_data` mismatch. The native UVM corruption control remains separate.
Neither control is an RTL mutation campaign.

The extended [program profiles](programs.md) use this same unchanged bridge and
library build. Pass `--program-profile corners` to standalone reference replay
when selecting a corner image; its strict count and terminal-PC checks use the
corresponding program contract. [Directed results](directed-corners-results.md)
record the expanded matrix separately from the initial Spike milestone.
`--program-profile random` selects the bounded random corpus contract. The same
bridge executes the saved actual instruction image without participating in
generation or reading a DUT result; see [random programs](random-programs.md).

This is an offline integration using the official Spike library. It is separate
from [Ibex's upstream live co-simulation flow](https://ibex-core.readthedocs.io/en/stable/03_reference/cosim.html),
which has its own Spike fork and simulator requirements. The exact pinned
[official source](https://github.com/riscv-software-src/riscv-isa-sim/tree/530af85d83781a3dae31a4ace84a573ec255fefa)
governs this adapter's internal API.
