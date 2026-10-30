"""Run every bounded v1 acceptance stage and publish a fail-closed local release manifest."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from tool_common import ROOT, find_questa
sys.path.insert(0, str(ROOT))
from run_uvm_tests import snapshot_hashes, verify_vendor_lock
from run_xsim_tests import find_vivado
from verification.mutations import checked_folder
from verification.reference.spike import verify_spike_build


def totals(baseline, random, advanced, mutations, unit_count):
    cpu_cases = [c for matrix in (baseline, random) for c in matrix["cases"] if c["layer"] == "uvm"]
    component_cases = [c for c in baseline["cases"] if c["layer"] == "python"]
    clean_cases = cpu_cases + [m["baseline"] for m in mutations]
    return {"pytest_passed": unit_count, "cpu_matrix_cases": len(cpu_cases),
        "component_cases": len(component_cases),
        "component_variants": sum(len(c["variants"]) for c in component_cases),
        "advanced_cases": len(advanced["cases"]),
        "positive_uvm_profiles": sum(len(c["profiles"]) for c in clean_cases) + len(advanced["cases"]),
        "uvm_corruption_controls": sum(c["corruption_control"]["status"] == "detected" for c in clean_cases) +
            sum(c["corruption_control"]["status"] == "detected" for c in advanced["cases"]),
        "spike_executions": len(cpu_cases) + sum(m["spike_executions"] for m in mutations) + advanced["spike_executions"],
        "spike_full_trace_matches": sum(len(c["spike"]["profiles"]) for c in clean_cases) +
            sum("spike_comparison" in c for c in advanced["cases"]),
        "spike_comparison_controls": sum(c["spike"]["corruption_control"]["status"] == "detected" for c in clean_cases) +
            sum(c.get("comparison_control", {}).get("status") == "detected" for c in advanced["cases"]),
        "rtl_mutants_killed": sum(m["outcomes"]["killed"] for m in mutations),
        "rtl_mutants_survived": sum(m["outcomes"]["survived"] for m in mutations),
        "rtl_mutants_invalid_or_unqualified": sum(sum(m["outcomes"][k] for k in
            ("compile_invalid", "infrastructure_failed", "unqualified_detection")) for m in mutations)}


def run_release(output):
    output = checked_folder(output); output.mkdir(parents=True, exist_ok=False)
    hashes = snapshot_hashes()
    result = {"schema_version": 1, "release": "v1-bounded-cpu-verification", "status": "failed",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(), "source_sha256": hashes, "stages": [],
        "scope": "two CPU adapters; bounded RV32I subset; two verification layers",
        "limits": ["No full RV32I ISA closure", "No asynchronous interrupt comparison with Spike",
                   "Ibex external IRQ only; PicoRV32 custom IRQ excluded", "No SoC peripherals/RAL or FPGA implementation claimed"]}
    def stage(name, script, arguments, manifest=None, timeout=7200):
        command = [sys.executable, *script, *map(str, arguments)]
        entry = {"name": name, "command": command, "status": "running", "log": str(output / (name + ".log"))}
        result["stages"].append(entry)
        (output / "release.json").write_text(json.dumps(result, indent=2) + "\n")
        print("V1_STAGE_START " + name, flush=True)
        proc = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, errors="replace", timeout=timeout)
        Path(entry["log"]).write_text(proc.stdout, encoding="utf-8")
        entry.update(returncode=proc.returncode, status="failed")
        if proc.returncode:
            raise RuntimeError("Release stage failed: " + name + "; see " + entry["log"])
        data = json.loads(manifest.read_text()) if manifest else None
        if data and data.get("status") not in ("pass", "completed"):
            raise RuntimeError("Release stage manifest failed: " + name)
        if data and data.get("source_sha256") != hashes:
            raise RuntimeError("Stage source identity differs: " + name)
        if snapshot_hashes() != hashes:
            raise RuntimeError("Sources changed during release qualification")
        entry.update(status="pass", manifest=str(manifest) if manifest else None)
        print("V1_STAGE_PASS " + name, flush=True)
        return data
    try:
        result["tools"] = {"vivado_bin": str(find_vivado()), "questa_bin": str(find_questa()),
                           "python": sys.version, "spike_build": verify_spike_build()[1]}
        result["vendor_commits"] = {cpu: verify_vendor_lock(cpu)["commit"] for cpu in ("ibex", "picorv32")}
        stage("python-tests", ["-m", "pytest"], ["-q", "tests", "--basetemp", output / "pytest-temp",
              "--junitxml", output / "pytest.xml"])
        suites = ET.parse(output / "pytest.xml").getroot().findall("testsuite")
        if not suites or any(int(s.attrib[k]) for s in suites for k in ("failures", "errors", "skipped")):
            raise RuntimeError("Python utility test report lacks a clean, unskipped result")
        unit_count = sum(int(s.attrib["tests"]) for s in suites)
        baseline = stage("baseline", [str(ROOT / "scripts/run_regression.py")],
            ["--config", ROOT / "config/regressions/v1-baseline.json", "--output", output / "baseline"], output / "baseline/summary.json")
        random = stage("random", [str(ROOT / "scripts/run_regression.py")],
            ["--config", ROOT / "config/regressions/v1-random.json", "--output", output / "random"], output / "random/summary.json")
        advanced = stage("advanced", [str(ROOT / "scripts/run_advanced_tests.py")],
            ["--output", output / "advanced"], output / "advanced/summary.json")
        mutations = []
        for name in ("ibex", "pico"):
            mutation = stage("mutations-" + name, [str(ROOT / "scripts/run_mutation_tests.py")],
                ["--config", ROOT / ("config/mutations/" + name + "-small.json"), "--output", output / ("mutations-" + name)],
                output / ("mutations-" + name + "/summary.json"))
            if mutation.get("all_targeted_detected") is not True:
                raise RuntimeError("An RTL mutant was not qualified as detected")
            mutations.append(mutation)
        coverage = stage("coverage", [str(ROOT / "scripts/export_coverage.py")],
            ["--regression", output / "random", "--output", output / "coverage"], output / "coverage/summary.json")
        result.update(status="pass", totals=totals(baseline, random, advanced, mutations, unit_count),
                      coverage_groups=coverage["merged"]["groups"], source_integrity_verified=True)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired, ET.ParseError) as exc:
        result["error"] = str(exc)
    (output / "release.json").write_text(json.dumps(result, indent=2) + "\n")
    rows = ["# Verified v1 release", "", "Status: **" + result["status"] + "**.", "",
            "| Stage | Result |", "| --- | --- |"]
    rows += [f"| {s['name']} | {s['status']} |" for s in result["stages"]]
    if "totals" in result:
        rows += ["", "| Executed evidence | Count |", "| --- | --- |"]
        rows += [f"| {k} | {v} |" for k, v in result["totals"].items()]
    rows += ["", "Coverage closure applies only to the declared scoped coverpoints and crosses.",
             "Mutants are eight targeted RTL changes, not a broad mutation score.", "", *result["limits"]]
    if result.get("error"): rows += ["", result["error"]]
    (output / "report.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print("V1_RELEASE_" + result["status"].upper() + " " + str(output / "report.md"), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or ROOT / "build/releases" / datetime.now(timezone.utc).strftime("v1-%Y%m%dT%H%M%S%fZ")
    try:
        raise SystemExit(0 if run_release(output)["status"] == "pass" else 1)
    except (OSError, ValueError, RuntimeError) as exc:
        print("V1_RELEASE_FAILED: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
