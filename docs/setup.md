# Setup and qualification

## Run the qualification

From the repository root in PowerShell, run:

```powershell
.\scripts\verify.ps1
```

Install Windows Git, Python 3.12 or later, Vivado XSim with UVM 1.2 and
Ubuntu WSL with `python3`, `g++`, `make` and `device-tree-compiler`.
Set `IBEX_PYTHON` to the Python executable if it is outside PATH. Set
`VIVADO_BIN` if the simulator is outside the launcher's discovery paths.
The first run fetches the pinned Spike source from GitHub and compiles it in WSL.

The command builds both Spike adapters, runs the Python automation checks,
qualifies smoke and corners on both CPUs, runs the four-seed live random
regression, and merges native XSim functional coverage. It writes
`release.json`, `report.md` and stage logs to a fresh folder under
`build/releases/`. Use `-Output build/releases/my-run` to name a fresh folder.


See [qualification results](../evidence/qualification/report.md) and the [live Spike guide](spike-dpi.md).
