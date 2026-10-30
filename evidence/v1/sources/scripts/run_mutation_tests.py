"""Run a clean native UVM/Spike baseline, then isolated RTL mutation observations."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

from tool_common import ROOT
sys.path.insert(0, str(ROOT))
from run_regression import run_case
from run_uvm_tests import snapshot_hashes, verify_vendor_lock
from verification.config import apply_program, load_processor
from verification.mutations import DEFINITIONS, checked_folder, prepare_mutant, verify_mutant, classify_observation
from verification.reference.spike import verify_spike_build
from verification.traces import compare_traces, normalize_rvfi_csv


def compare_retirement_prefix(prefix, reference):
    if prefix.get("complete") is not False or reference.get("complete") is not True:
        raise ValueError("Mutation diagnostics require an explicit incomplete prefix and complete reference")
    if not 0 < len(prefix["records"]) <= len(reference["records"]):
        raise ValueError("Invalid bounded mutation trace prefix")
    actual, expected = copy.deepcopy(prefix), copy.deepcopy(reference)
    actual["complete"] = True  # Structural validation only; original stays incomplete.
    expected["records"] = expected["records"][:len(actual["records"])]
    try:
        result = compare_traces(actual, expected)
        return {"status": "prefix_match", "retirements_compared": result["retirements_compared"],
                "note": "No observed architectural divergence in this prefix; this is not a full pass"}
    except ValueError as exc:
        if not str(exc).startswith("Architectural mismatch at record "):
            raise
        return {"status": "architectural_mismatch", "diagnostic": str(exc),
                "observed_retirements": len(prefix["records"])}


def run_mutant(identity, config, output, reference, baseline_image_hash):
    folder = output / "mutants" / identity
    manifest_path = prepare_mutant(identity, folder / "rtl")
    sim = folder / "simulation"
    command = [sys.executable, str(ROOT / "scripts/run_uvm_tests.py"), "--full", "--processor", config["processor"],
        "--program", config["program"], "--seed", str(config["seed"]), "--output", str(sim),
        "--rtl-mutation", str(manifest_path)]
    record = {"id": identity, "outcome": "infrastructure_failed", "expected_error_id": DEFINITIONS[identity]["error_id"],
        "command": command, "rtl_manifest": str(manifest_path), "simulation_result": str(sim / "results.json"),
        "spike_reference_reused": True, "rtl_mutant": True, "observation_corruption_enabled": False}
    try:
        proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, errors="replace", timeout=900)
        (folder / "launcher.log").write_text(proc.stdout + proc.stderr)
        raw = json.loads((sim / "results.json").read_text())
        errors = re.findall(r"(?m)^UVM_ERROR\s+[^\r\n]*?\[([^\]]+)\]", raw.get("mutation_observation", {}).get("transcript", ""))
        record.update(first_error_id=errors[0] if errors else None, error_ids=errors)
        cfg = apply_program(load_processor(config["processor"]), config["program"])
        expected = {"retired": cfg["expected_retirements"], **cfg["program_contract"]["expected_counts"],
            "seed": config["seed"], "signature": 1, "cpu_id": int(config["processor"] == "picorv32_rv32i"), "program_id": cfg["program_contract"]["uvm_program_id"], "max_delay": 3}
        record.update(outcome=classify_observation(raw, record["expected_error_id"], expected),
            launcher_returncode=proc.returncode, compiled=raw.get("compiled"), elaborated=raw.get("elaborated"),
            source_sha256=raw.get("source_sha256"), uvm_counts=raw.get("mutation_observation", {}).get("uvm_counts"),
            mutation=verify_mutant(manifest_path))
        if proc.returncode and record["outcome"] in ("killed", "survived"):
            record.update(outcome="infrastructure_failed", error="Launcher failed despite an apparent observation")
        trace_path = sim / "stalled_rvfi_trace.csv"
        if raw.get("mutation_observation", {}).get("simulated") and trace_path.is_file():
            prefix = normalize_rvfi_csv(trace_path, sim / "stalled_program.hex", cfg, allow_prefix=True)
            if prefix["program_sha256"] != baseline_image_hash:
                raise ValueError("Mutant input image differs from clean baseline")
            (folder / "retirement-prefix.json").write_text(json.dumps(prefix, indent=2) + "\n")
            record["spike_comparison"] = compare_retirement_prefix(prefix, reference)
            if (record["outcome"] == "killed" and not DEFINITIONS[identity].get("bus_mutation") and
                    record["spike_comparison"]["status"] != "architectural_mismatch"):
                record.update(outcome="unqualified_detection", error="Architectural mutant lacks independent retirement divergence")
            if record["outcome"] == "survived" and (len(prefix["records"]) != cfg["expected_retirements"] or
                    record["spike_comparison"]["status"] != "prefix_match"):
                record.update(outcome="unqualified_detection", error="Clean UVM marker contradicted the independent reference")
        elif record["outcome"] in ("killed", "survived"):
            raise ValueError("Executed outcome lacks a usable observed retirement trace")
        verify_mutant(manifest_path)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as exc:
        record.update(outcome="infrastructure_failed", error=str(exc))
    (folder / "mutation-result.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def run_campaign(config_path, output):
    config = json.loads(Path(config_path).read_text())
    identities = config.get("mutations", [])
    if (config.get("schema_version") != 1 or config.get("processor") not in ("ibex_smoke", "picorv32_rv32i") or
            config.get("program") != "corners" or type(config.get("seed")) is not int or not 0 < config["seed"] <= 0xffffffff or
            not identities or len(set(identities)) != len(identities) or any(i not in DEFINITIONS for i in identities) or
            type(config.get("jobs")) is not int or not 1 <= config["jobs"] <= 4):
        raise ValueError("Unsupported bounded mutation campaign configuration")
    implementation = load_processor(config["processor"])["implementation"]
    if any(DEFINITIONS[i].get("implementation", "ibex") != implementation for i in identities):
        raise ValueError("Mutation definitions do not match campaign CPU")
    output = checked_folder(output)
    output.mkdir(parents=True, exist_ok=False)
    hashes = snapshot_hashes()
    verify_vendor_lock("ibex"); verify_vendor_lock("picorv32")
    build = verify_spike_build()[1]
    summary = {"schema_version": 1, "status": "failed", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "configuration": config, "source_sha256": hashes, "mutants": [], "spike_executions": 0,
        "rtl_mutation_campaign_executed": True, "all_targeted_detected": False}
    try:
        baseline = run_case(config["processor"], config["seed"], "uvm", "full", output / "baseline", True, config["program"])
        summary["baseline"] = baseline
        if baseline["status"] != "pass":
            raise RuntimeError("Clean native UVM/Spike baseline failed; no mutants launched")
        base_folder = Path(baseline["artifacts"]["raw_results"]).parent
        reference = json.loads((base_folder / "spike/retirement-v1.json").read_text())
        summary.update(spike_executions=1, reference_manifest=str(base_folder / "spike/reference-result.json"))
        with ThreadPoolExecutor(max_workers=config["jobs"]) as pool:
            futures = [pool.submit(run_mutant, i, config, output, reference, baseline["program_sha256"]) for i in identities]
            for future in as_completed(futures):
                mutant = future.result()
                summary["mutants"].append(mutant)
                print(f"RTL_MUTATION {mutant['id']} {mutant['outcome']}", flush=True)
        summary["mutants"].sort(key=lambda m: m["id"])
        if snapshot_hashes() != hashes or baseline["source_sha256"] != hashes or any(
                m.get("source_sha256") != hashes for m in summary["mutants"]):
            raise RuntimeError("Sources changed or a mutant lacks the campaign source identity")
        if verify_spike_build()[1] != build:
            raise RuntimeError("Reference build identity changed during campaign")
        verify_vendor_lock("ibex"); verify_vendor_lock("picorv32")
        counts = {name: sum(m["outcome"] == name for m in summary["mutants"]) for name in
            ("killed", "survived", "compile_invalid", "infrastructure_failed", "unqualified_detection")}
        denominator = counts["killed"] + counts["survived"]
        summary.update(status="completed", outcomes=counts, valid_executed_mutants=denominator,
            detected_fraction=counts["killed"] / denominator if denominator else None,
            all_targeted_detected=counts["killed"] == len(identities), vendor_sources_preserved=True)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        summary["error"] = str(exc)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    rows = ["# RTL mutation report", "", f"Status: {summary['status']}; all targeted detected: {summary['all_targeted_detected']}.",
        "", "| Mutant | Outcome | Intended UVM checker | Spike prefix observation |", "| --- | --- | --- | --- |"]
    for m in summary["mutants"]:
        rows.append(f"| {m['id']} | {m['outcome']} | {m['expected_error_id']} | {m.get('spike_comparison', {}).get('status', 'not available')} |")
    rows += ["", "Compile-invalid and infrastructure failures are excluded from the detection denominator.",
        "A matching stopped prefix is not a full architectural pass. One actual clean Spike execution is reused only for identical input images.",
        "This targeted campaign does not establish a broad mutation score."]
    (output / "report.md").write_text("\n".join(rows) + "\n")
    print("RTL_MUTATION_REPORT " + str(output / "report.md"), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/mutations/ibex-small.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = run_campaign(args.config, args.output)
        raise SystemExit(0 if summary["all_targeted_detected"] else 1)
    except (OSError, ValueError, RuntimeError) as exc:
        print("MUTATION_CAMPAIGN_FAILED: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
