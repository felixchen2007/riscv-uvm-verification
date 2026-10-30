"""Qualify native virtual sequences, reset epochs, IRQ handling and factory overrides."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

from tool_common import ROOT
sys.path.insert(0, str(ROOT))
from run_uvm_tests import snapshot_hashes
from run_mutation_tests import compare_retirement_prefix
from verification.config import apply_program, load_processor
from verification.mutations import checked_folder
from verification.reference.spike import run_reference, qualify_comparison, verify_spike_build
from verification.traces import normalize_rvfi_csv, compare_traces, write_trace

CASES = [(cpu, scenario) for cpu in ("ibex_smoke", "picorv32_rv32i")
         for scenario in ("reset", "factory")] + [("ibex_smoke", "irq")]


def run_case(cpu, scenario, seed, output):
    folder = output / (cpu + "_" + scenario)
    folder.mkdir()
    sim = folder / "simulation"
    program = "irq" if scenario == "irq" else "corners"
    command = [sys.executable, str(ROOT / "scripts/run_uvm_tests.py"), "--full", "--processor", cpu,
               "--program", program, "--scenario", scenario, "--seed", str(seed), "--output", str(sim)]
    result = {"processor": cpu, "scenario": scenario, "seed": seed, "status": "failed",
              "command": command, "raw_results": str(sim / "results.json"), "spike_executions": 0}
    try:
        proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, errors="replace", timeout=900)
        (folder / "launcher.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
        raw = json.loads((sim / "results.json").read_text())
        if (proc.returncode or raw.get("verification_pass") is not True or raw.get("status") != "pass" or
                raw.get("scenario") != scenario or raw.get("processor_config") != cpu or raw.get("seed") != seed or
                raw.get("corruption_control", {}).get("status") != "detected"):
            raise RuntimeError(raw.get("error", "Advanced native UVM case did not pass"))
        result.update(source_sha256=raw["source_sha256"], profile=raw["profiles"]["stalled"],
                      corruption_control=raw["corruption_control"])
        if scenario == "irq":
            result["irq_audit"] = raw["profiles"]["stalled"]["irq_audit"]
        else:
            cfg = apply_program(load_processor(cpu), program)
            image = sim / "stalled_program.hex"
            trace = normalize_rvfi_csv(sim / "stalled_rvfi_trace.csv", image, cfg)
            write_trace(folder / "retirement-v1.json", trace)
            reference, execution = run_reference(image, cfg, folder / "spike")
            result.update(spike_executions=int(execution["executed"]), spike_comparison=compare_traces(trace, reference))
            control, corrupt = qualify_comparison(trace, reference)
            write_trace(folder / "spike/corrupted-observation.json", corrupt)
            result["comparison_control"] = control
            if scenario == "reset":
                with (sim / "stalled_all_epochs_rvfi_trace.csv").open(newline="") as stream:
                    reader = csv.DictReader(stream); fields = reader.fieldnames; rows = list(reader)
                prefix_path = folder / "aborted-prefix.csv"
                with prefix_path.open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, fields); writer.writeheader()
                    writer.writerows(row for row in rows if int(row["epoch"]) == 0)
                prefix = normalize_rvfi_csv(prefix_path, image, cfg, allow_prefix=True)
                (folder / "aborted-prefix.json").write_text(json.dumps(prefix, indent=2) + "\n")
                result["aborted_prefix_comparison"] = compare_retirement_prefix(prefix, reference)
                if result["aborted_prefix_comparison"]["status"] != "prefix_match":
                    raise RuntimeError("Aborted reset prefix differs from the reference")
        result["status"] = "pass"
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as exc:
        result["error"] = str(exc)
    (folder / "case-result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def run_suite(output, seed=20261029, jobs=2):
    if not 0 < seed <= 0xffffffff or not 1 <= jobs <= 4:
        raise ValueError("Invalid seed or worker count")
    output = checked_folder(output); output.mkdir(parents=True, exist_ok=False)
    hashes = snapshot_hashes(); build = verify_spike_build()[1]
    cases = []
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(run_case, cpu, scenario, seed, output) for cpu, scenario in CASES]
        for future in as_completed(futures):
            case = future.result(); cases.append(case)
            print(f"ADVANCED_CASE {case['processor']} {case['scenario']} {case['status']}", flush=True)
    stable = (snapshot_hashes() == hashes and verify_spike_build()[1] == build and
              all(c.get("source_sha256") == hashes for c in cases))
    summary = {"schema_version": 1, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
               "status": "pass" if stable and len(cases) == len(CASES) and all(c["status"] == "pass" for c in cases) else "failed",
               "source_sha256": hashes, "source_integrity_verified": stable,
               "cases": sorted(cases, key=lambda c: (c["processor"], c["scenario"])),
               "spike_executions": sum(c["spike_executions"] for c in cases),
               "irq_scope": "Ibex external machine interrupt only; native CSR/event checks; no asynchronous Spike comparison"}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261029)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    try:
        raise SystemExit(0 if run_suite(args.output, args.seed, args.jobs)["status"] == "pass" else 1)
    except (OSError, ValueError, RuntimeError) as exc:
        print("ADVANCED_FAILED: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
