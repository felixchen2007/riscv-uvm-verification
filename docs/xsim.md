# Vivado XSim host simulation

The runner supports `--processor ibex_smoke` (default) and
`--processor picorv32_rv32i`. Both use the same UVM predictor, program and
coverage model, with different physical memory agents. Pico enables RVFI with
`RISCV_FORMAL`, requires no RTL compatibility wrapper and does not enable
`FORMAL` or TESTBUG macros. The compatibility section below applies to Ibex.

The user-selected simulator is Vivado XSim, installed here at
`D:/AMDDesignTools/2025.2/Vivado/bin`. The DE10-Lite stays the optional FPGA
target and uses Quartus for implementation. These host simulations contain no
AMD device primitives and do not require an AMD FPGA.

The runner uses the installation's precompiled UVM 1.2 library: `-L uvm` is
passed to both `xvlog` and `xelab`. `--full` defines `IBEX_UVM_FULL`, enabling
successful `randomize()` calls for bounded grant/response delays and explicit
covergroup sampling. Default mode uses an explicit seeded xorshift PRNG and
procedural counters. There is no fallback between simulators or modes.

Runtime options are written to XSim argument files because the Windows vendor
batch launcher reparses unquoted `=` characters in UVM plusargs. Each profile
retains its argument file for replay. Compilation, elaboration and simulation
have separate logs, and simulator errors are checked in addition to UVM counts.

## Pinned-source compatibility

Ibex v2.1.0 exports two dummy scrambling DPI functions inside the no-cache
generate block of `ibex_if_stage`. XSim 2025.2 generated invalid C++ identifiers
containing that generate scope's dot, and elaboration failed. The environment
does not call those functions.

`tb/uvm/ibex_xsim_if_stage.sv` first loads the standard upstream assertion
macros, then temporarily defines `SYNTHESIS` only while including the unmodified
`ibex_if_stage.sv`. This suppresses the unused DPI exports and V2S coverage
signals (already excluded with `DV_FCOV_DISABLE`), while preserving the standard
RTL assertion macros. It then undefines `SYNTHESIS`; the other DUT files and the
UVM environment compile normally. The source lock remains unchanged. The full
compile file list and this compatibility selection are recorded in the manifest.

The wrapper uses no `--ignore_assertions` or `--ignore_coverage` flags.
Independent memory/RVFI interface assertions and the watchdog remain enabled.
No Spike DPI library is linked in this milestone. The precompiled AMD UVM
library reports `UVM_NO_DPI`; factory, phases, sequences and monitors execute,
but DPI-based component-name checks are unavailable in that library.

## Reproduce

```powershell
.\scripts\run.ps1 --full
```

For another installation, pass `--vivado-bin` or set `VIVADO_BIN`. An explicitly
requested XSim run fails if the tools are missing. `scripts/run_xsim_tests.py
--prepare-only` writes compile commands without claiming an execution pass.

The initial full-mode coverage scope is seven opcode families, branch direction,
BEQ/BNE kind and their cross. The smoke includes taken BEQ and untaken BNE;
untaken BEQ and taken BNE remain coverage holes for the next program milestone.
This deliberately small covergroup is not a project or ISA coverage-closure claim.

References: [AMD UVM support](https://docs.amd.com/r/en-US/ug900-vivado-logic-simulation/Universal-Verification-Methodology-UVM-Support),
[XSim command options](https://docs.amd.com/r/2025.2-English/ug900-vivado-logic-simulation/xelab-xvhdl-and-xvlog-xsim-Command-Options).
