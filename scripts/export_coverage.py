"""Export per-run coverage and merge actual XSim databases using XCRG."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

from tool_common import ROOT
sys.path.insert(0, str(ROOT))
from run_uvm_tests import snapshot_hashes
from run_xsim_tests import find_vivado, call, require_ok
from verification.coverage import parse_xcrg_report
from verification.mutations import checked_folder


def db_hashes(folder):
    return {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


def export_report(bin_dir, inputs, output):
    output.mkdir(parents=True, exist_ok=False)
    args = []
    before = {}
    for folder, profile in inputs:
        database = folder / "coverage/xsim.covdb" / profile
        if not (database / "xsim.covinfo").is_file():
            raise ValueError("Required native coverage database is missing")
        before.update(db_hashes(database))
        args += ["-cov_db_dir", str(folder / "coverage"), "-cov_db_name", profile]
    args += ["-report_dir", "report", "-report_format", "all", "-log", "xcrg.log"]
    (output / "command.json").write_text(json.dumps([str(bin_dir / "xcrg.bat"), *args], indent=2) + "\n")
    proc = call(bin_dir, "xcrg", args, output, "console.log")
    require_ok(proc, "Native coverage export/merge")
    restores = re.findall(r"(?m)^\s*\d+\s+.*xsim\.covinfo\s*$", proc.stdout)
    if len(restores) != len(inputs):
        raise RuntimeError("Coverage tool did not restore every requested database")
    after = {}
    for folder, profile in inputs:
        after.update(db_hashes(folder / "coverage/xsim.covdb" / profile))
    if before != after:
        raise RuntimeError("Coverage reporting changed an input database")
    report = output / "report/functionalCoverageReport/xcrg_func_cov_report.txt"
    groups = parse_xcrg_report(report.read_text())
    result = {"input_databases": len(inputs), "input_sha256": before, "groups": groups,
              "report": str(report), "native_merge": len(inputs) > 1}
    (output / "bin-summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def export_campaign(regression, output):
    regression = Path(regression).resolve()
    source = json.loads((regression / "summary.json").read_text())
    cases = source.get("cases", [])
    hashes = snapshot_hashes()
    if (source.get("status") != "pass" or source.get("source_sha256") != hashes or not cases or
            any(c.get("layer") != "uvm" or c.get("program_profile") != "random" or c.get("status") != "pass" for c in cases)):
        raise ValueError("Coverage campaign requires a passing, current-source random regression")
    output = checked_folder(output); output.mkdir(parents=True, exist_ok=False)
    bin_dir = find_vivado()
    result = {"schema_version": 1, "status": "failed", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "source_sha256": hashes, "regression": str(regression), "individual": []}
    try:
        merged_inputs = []
        for case in cases:
            folder = Path(case["artifacts"]["raw_results"]).parent
            merged_inputs.append((folder, "stalled"))
            for profile in ("no_added_delay", "stalled"):
                report = export_report(bin_dir, [(folder, profile)], output / case["case_id"] / profile)
                if any(not report["groups"][g]["closed"] for g in ("retire_cg", "corner_cg", "random_kind_cg")):
                    raise RuntimeError("An individual run lost a mandatory directed or instruction-family bin")
                result["individual"].append({"case_id": case["case_id"], "processor": case["processor_config"],
                                             "seed": case["seed"], "profile": profile, **report})
        # Preserve per-processor closure as well as the combined native merge.
        result["per_processor"] = {}
        for cpu in sorted({c["processor_config"] for c in cases}):
            selected = [(Path(c["artifacts"]["raw_results"]).parent, "stalled")
                        for c in cases if c["processor_config"] == cpu]
            report = export_report(bin_dir, selected, output / ("merged_" + cpu))
            result["per_processor"][cpu] = report
            if not all(g["closed"] for g in report["groups"].values()):
                raise RuntimeError("Per-processor native merged coverage has open scoped bins: " + cpu)
        result["merged"] = export_report(bin_dir, merged_inputs, output / "merged_all")
        if not all(g["closed"] for g in result["merged"]["groups"].values()) or snapshot_hashes() != hashes:
            raise RuntimeError("Native merged scoped bins remain open or sources changed")
        result["status"] = "pass"
    except (OSError, ValueError, RuntimeError) as exc:
        result["error"] = str(exc)
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regression", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        raise SystemExit(0 if export_campaign(args.regression, args.output)["status"] == "pass" else 1)
    except (OSError, ValueError, RuntimeError) as exc:
        print("COVERAGE_FAILED: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
