"""Build and qualify the bounded live Spike CPU verification workflow."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

from tool_common import ROOT

sys.path.insert(0, str(ROOT))
from run_uvm_tests import snapshot_hashes


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def run_release(output):
    output = output.resolve()
    if not output.is_relative_to((ROOT / "build").resolve()):
        raise ValueError("Release output must be inside the project build directory")
    output.mkdir(parents=True, exist_ok=False)
    hashes = snapshot_hashes()
    manifest = output / "release.json"
    result = {
        "schema_version": 1,
        "release": "live-spike",
        "status": "failed",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "normal bounded RV32I programs on Ibex and PicoRV32",
        "source_sha256": hashes,
        "stages": [],
    }

    def stage(name, script, *args, evidence=None):
        command = [sys.executable, "-S", str(ROOT / "scripts" / script), *map(str, args)]
        log = output / (name + ".log")
        entry = {"name": name, "status": "running", "command": command, "log": str(log)}
        result["stages"].append(entry)
        write_json(manifest, result)
        print(f"VERIFY_STAGE_START {name}", flush=True)
        try:
            with log.open("w", encoding="utf-8") as stream:
                entry["returncode"] = subprocess.run(
                    command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=7200
                ).returncode
            if entry["returncode"]:
                raise RuntimeError(f"{name} failed. See {log}")
            data = json.loads(evidence.read_text(encoding="utf-8")) if evidence else None
            if data is not None:
                if data.get("status") != "pass" or data.get("source_sha256") != hashes:
                    raise RuntimeError(f"{name} did not produce passing evidence for the tested sources")
                entry["manifest"] = str(evidence)
            if snapshot_hashes() != hashes:
                raise RuntimeError("Source files changed during qualification")
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
            entry["status"] = "failed"
            raise
        entry["status"] = "pass"
        write_json(manifest, result)
        print(f"VERIFY_STAGE_PASS {name}", flush=True)
        return data

    try:
        stage("spike-build", "build_spike.py")
        stage("live-spike-build", "build_spike_live.py")
        checks = stage("python-checks", "run_python_checks.py", "--output", output / "python",
                       evidence=output / "python/results.json")
        matrices = {
            "directed": json.loads((ROOT / "config/regressions/live-directed.json").read_text()),
            "random": json.loads((ROOT / "config/regressions/live-random.json").read_text()),
        }
        cases = []
        for name, matrix in matrices.items():
            config = output / f"{name}-matrix.json"
            write_json(config, matrix)
            regression = stage(name, "run_regression.py", "--config", config,
                               "--output", output / name, evidence=output / name / "summary.json")
            if not regression["live_spike_comparison_executed"] or not regression["spike_comparison_executed"]:
                raise RuntimeError(f"{name} requires executed live and offline Spike comparisons")
            cases.extend(regression["cases"])
        coverage = stage("coverage", "export_coverage.py", "--regression", output / "random",
                         "--output", output / "coverage", evidence=output / "coverage/summary.json")
        result["totals"] = {
            "Python checks passed": checks["tests_run"],
            "CPU, program and seed cases passed": len(cases),
            "Positive UVM profiles": sum(len(case["profiles"]) for case in cases),
            "Live retirement matches": sum(sum(case["live_spike"]["profiles"].values()) for case in cases),
            "Spike-only observation controls detected": sum(len(case["live_spike"]["controls"]) for case in cases),
            "Combined functional bins hit": sum(group["covered"] for group in coverage["merged"]["groups"].values()),
        }
        result["status"] = "pass"
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as exc:
        result["error"] = str(exc)

    write_json(manifest, result)
    rows = ["# Live Spike qualification", "", f"Status **{result['status']}**", "",
            "| Stage | Result |", "| --- | --- |"]
    rows.extend(f"| {entry['name']} | {entry['status']} |" for entry in result["stages"])
    if "totals" in result:
        rows.extend(["", "| Measure | Count |", "| --- | ---: |"])
        rows.extend(f"| {name} | {value} |" for name, value in result["totals"].items())
    if "error" in result:
        rows.extend(["", result["error"]])
    rows.extend(["", "Live checking covers normal bounded RV32I programs on both CPU adapters.",
                 "Reset and interrupt scenarios use the separate native UVM flow."])
    report = output / "report.md"
    report.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"VERIFY_RELEASE_{result['status'].upper()} {report}", flush=True)
    return result["status"] == "pass"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    default = ROOT / "build/releases" / datetime.now(timezone.utc).strftime("verify-%Y%m%dT%H%M%S%fZ")
    try:
        if sys.version_info < (3, 12):
            raise RuntimeError("Python 3.12 or later is required")
        raise SystemExit(0 if run_release(args.output or default) else 1)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"VERIFY_RELEASE_FAILED {exc}", file=sys.stderr)
        raise SystemExit(1)
