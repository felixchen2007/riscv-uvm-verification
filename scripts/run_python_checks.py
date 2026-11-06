# Runs the Python tests for the verification tools.
# Saves the test transcript and result for the qualification report.

"""Run standard-library automation checks and write a fail-closed result manifest."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest

from tool_common import ROOT
sys.path.insert(0, str(ROOT))
from run_uvm_tests import snapshot_hashes


def run_checks(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    hashes = snapshot_hashes()
    result = {"schema_version": 1, "status": "failed", "framework": "stdlib unittest",
              "timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "automation and checking utilities; not RTL simulation",
              "source_sha256": hashes}
    try:
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
        with (output / "checks.log").open("w", encoding="utf-8") as log:
            ran = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        result.update(tests_run=ran.testsRun, failures=len(ran.failures),
                      errors=len(ran.errors), skipped=len(ran.skipped),
                      unexpected_successes=len(ran.unexpectedSuccesses))
        if (ran.testsRun > 0 and ran.wasSuccessful() and not ran.skipped
                and snapshot_hashes() == hashes):
            result["status"] = "pass"
    except Exception as exc:
        result["error"] = str(exc)
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"PYTHON_CHECKS_{result['status'].upper()}: {output / 'results.json'}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or ROOT / "build/python-tests" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    sys.exit(0 if run_checks(output)["status"] == "pass" else 1)
