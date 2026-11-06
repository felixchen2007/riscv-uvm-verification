# Provides a short command for running the native UVM tests.
# Uses the same arguments and exit code as run_uvm_tests.py.

"""Normal acceptance entry point: the native UVM suite is required."""
from run_uvm_tests import main

if __name__ == "__main__":
    raise SystemExit(main())
