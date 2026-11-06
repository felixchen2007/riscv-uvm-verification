# Turns a test matrix into UVM runs by CPU, program, and seed.
# Collects the results and checks that repeated inputs match.

"""Automate native UVM CPU verification in isolated, reproducible case folders."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

from tool_common import ROOT
sys.path.insert(0, str(ROOT))
from verification.config import load_processor, load_regression, apply_program
from verification.results import aggregate, classify_failure
from verification.traces import compare_traces, compare_processor_cases, normalize_rvfi_csv, write_trace, branch_outcomes
from verification.reference.spike import compare_case_with_spike, verify_spike_build
from verification.programs import summarize_random_corpora
from run_uvm_tests import snapshot_hashes

def run_case(processor, seed, layer, mode, output, include_spike=False, program="smoke", live_spike=False):
    if layer != "uvm":
        raise ValueError("Only native UVM CPU cases are supported")
    cfg = apply_program(load_processor(processor), program)
    case_id = f"{processor}_{layer}_{mode}_seed{seed}"
    if layer == "uvm" and program != "smoke":
        case_id += "_" + program
    folder = output / "cases" / case_id
    folder.mkdir(parents=True)
    script = "run_uvm_tests.py"
    command = [sys.executable, str(ROOT / "scripts" / script), "--seed", str(seed), "--output", str(folder)]
    if layer == "uvm":
        command += ["--sim", "xsim", "--processor", processor, "--program", program]
        if mode == "full":
            command.append("--full")
        if live_spike:
            command.append("--spike-live")
    result = {"schema_version": 1, "case_id": case_id, "layer": layer,
              "scope": "cpu", "processor_config": processor,
              "program_profile": program,
              "seed": seed, "status": "failed", "executed": False, "failure_category": None,
              "artifacts": {"raw_results": str(folder / "results.json"), "console": str(folder / "launcher.log")},
              "replay_command": [*command[:command.index("--output") + 1], str(folder / "replay"),
                                 *command[command.index("--output") + 2:]],
              "coverage_observations": [], "spike_comparison_executed": False}
    result["sv_instruction_randomization_executed"] = False
    try:
        proc = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, errors="replace", timeout=900)
        (folder / "launcher.log").write_text(proc.stdout, encoding="utf-8")
        raw = json.loads((folder / "results.json").read_text(encoding="utf-8"))
        if proc.returncode or raw.get("status") != "pass" or raw.get("verification_pass") is not True:
            raise RuntimeError(raw.get("error", raw.get("failure", proc.stdout[-6000:])))
        if raw.get("seed") != seed:
            raise RuntimeError("Run manifest does not match the requested seed")
        if layer == "uvm" and raw.get("processor_config") != processor:
            raise RuntimeError("Run manifest does not match requested CPU implementation")
        if layer == "uvm" and raw.get("program_profile") != program:
            raise RuntimeError("Run manifest does not match requested program")
        if live_spike:
            controls = raw.get("live_spike_controls", {})
            if (raw.get("live_spike_requested") is not True or raw.get("spike_comparison_executed") is not True or
                    set(controls) != {"spike_rd_control", "spike_pc_control", "spike_store_control"} or
                    any(c.get("status") != "detected" for c in controls.values())):
                raise RuntimeError("Requested live Spike checking or controls did not execute")
            if (set(raw.get("profiles", {})) != {"no_added_delay", "stalled"} or
                    any(p.get("live_spike_compared") != cfg["expected_retirements"] for p in raw["profiles"].values())):
                raise RuntimeError("Incomplete live Spike comparison counts")
            result["live_spike"] = {"profiles": {name: p["live_spike_compared"] for name, p in raw["profiles"].items()},
                                    "controls": controls, "build": raw["live_spike_build"]}
        result["source_sha256"] = raw["source_sha256"]
        if layer == "uvm":
            if raw.get("sv_instruction_randomization_executed") is not (program == "random"):
                raise RuntimeError("Requested instruction generation mode was not executed")
            result["sv_instruction_randomization_executed"] = raw["sv_instruction_randomization_executed"]
            if raw.get("sv_constrained_randomization_executed") is not (mode == "full"):
                raise RuntimeError("Requested UVM execution mode was not executed")
            if raw.get("corruption_control", {}).get("status") != "detected":
                raise RuntimeError("Missing intended scoreboard corruption diagnostic")
            traces = {}
            program_hashes = []
            result["profiles"] = raw["profiles"]
            result["corruption_control"] = raw["corruption_control"]
            result["branch_observations"] = {}
            for profile in ("no_added_delay", "stalled"):
                trace = normalize_rvfi_csv(folder / (profile + "_rvfi_trace.csv"),
                                           folder / (profile + "_program.hex"), cfg)
                trace_path = folder / (profile + "_retirement-v1.json")
                write_trace(trace_path, trace)
                result["artifacts"][profile + "_trace"] = str(trace_path)
                traces[profile] = trace
                observed_branches = branch_outcomes(trace, cfg["program_contract"]["branch_hits"])
                if observed_branches != raw["profiles"][profile]["branch_hits"]:
                    raise ValueError("SV branch counters differ from successive observed retirement PCs")
                result["branch_observations"][profile] = observed_branches
                program_hashes.append(trace["program_sha256"])
                features = raw["profiles"][profile].get("full_features")
                if features:
                    result["coverage_observations"].append({"case_id": case_id, "profile": profile,
                       "seed": seed, "covergroup": "riscv_scoreboard.retire_cg",
                       "percent": features["smoke_covergroup_percent"],
                       "database": str(folder / "coverage/xsim.covdb" / profile)})
                    result["coverage_observations"].append({"case_id": case_id, "profile": profile,
                       "seed": seed, "covergroup": "riscv_scoreboard.corner_cg",
                       "percent": features["corner_covergroup_percent"],
                       "database": str(folder / "coverage/xsim.covdb" / profile)})
                    if program == "random":
                        for group, field in (("random_kind_cg", "random_body_kind_percent"), ("random_alu_cg", "random_body_alu_percent"), ("random_memory_cg", "random_body_memory_percent")):
                            result["coverage_observations"].append({"case_id": case_id, "profile": profile,
                                "seed": seed, "covergroup": "riscv_scoreboard." + group, "percent": features[field],
                                "database": str(folder / "coverage/xsim.covdb" / profile)})
            result["timing_invariance"] = compare_traces(*traces.values())
            if include_spike:
                result["spike"] = compare_case_with_spike(folder, cfg, traces)
                result["spike_comparison_executed"] = True
                result["artifacts"]["spike_comparison"] = str(folder / "spike/comparison-result.json")
                result["reference_replay_command"] = [sys.executable, str(ROOT / "scripts/run_spike_tests.py"),
                    "--processor", processor, "--program", str(folder / "no_added_delay_program.hex"),
                    "--program-profile", program,
                    "--rvfi", str(folder / "no_added_delay_rvfi_trace.csv"), "--output", str(folder / "spike-replay")]
            result["program_sha256"] = program_hashes[0]
            (folder / "program-manifest.json").write_text(json.dumps({"schema_version": 1,
                "format": "verilog-readmemh-word-addresses", "isa": cfg["program_isa"],
                "entry_pc": cfg["entry_pc"], "seed": seed, "sha256": program_hashes[0],
                "program_profile": program, "contract": cfg["program_contract"],
                "sv_instruction_randomization_executed": program == "random",
                "generator": "SystemVerilog constrained-random body with directed prologue" if program == "random" else
                    "SystemVerilog ibex_program directed skeleton with seed-derived operand"}, indent=2) + "\n")
        result.update(status="pass", executed=True)
    except subprocess.TimeoutExpired as exc:
        console = exc.stdout or b""
        if isinstance(console, bytes):
            console = console.decode(errors="replace")
        (folder / "launcher.log").write_text(console + "\nPROCESS_TIMEOUT\n", encoding="utf-8")
        result.update(error="Case timed out after 900 seconds", failure_category="timeout")
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        result.update(error=str(exc), failure_category=classify_failure(str(exc)))
    (folder / "case-result-v1.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def run_regression(config, output, jobs=None, include_spike=None):
    matrix = load_regression(config)
    if jobs is not None:
        if not 1 <= jobs <= 8:
            raise ValueError("jobs must be in 1..8")
        matrix["jobs"] = jobs
    if include_spike is not None:
        matrix["include_spike"] = include_spike
    if matrix["include_spike"]:
        verify_spike_build()  # Fail before launching expensive RTL runs if unavailable.
    if matrix["include_live_spike"]:
        from build_spike_live import verify_live_build
        verify_live_build()
    # Do not overwrite old failures or share simulation work libraries.
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Regression output already exists; choose a fresh directory")
    output.mkdir(parents=True)
    hashes = snapshot_hashes()
    tasks = [(p, s, "uvm", program) for p in matrix["processors"]
             for program in matrix["programs"] for s in matrix["seeds"]]
    cases = []
    with ThreadPoolExecutor(max_workers=matrix["jobs"]) as pool:
        futures = [pool.submit(run_case, p, s, layer, matrix["uvm_mode"], output,
                               matrix["include_spike"], program, matrix["include_live_spike"]) for p, s, layer, program in tasks]
        for future in as_completed(futures):
            case = future.result()
            cases.append(case)
            print(f"REGRESSION_CASE {case['case_id']} {case['status']}", flush=True)
    cases.sort(key=lambda c: c["case_id"])
    summary = aggregate(cases, len(tasks))
    try:
        summary["processor_comparisons"] = compare_processor_cases(cases, matrix["processors"], matrix["seeds"], matrix["programs"])
        summary["random_corpora"] = summarize_random_corpora(cases)
    except ValueError as exc:
        summary.update(status="failed", processor_comparison_error=str(exc))
    if snapshot_hashes() != hashes or any(c.get("source_sha256", hashes) != hashes for c in cases):
        summary.update(status="failed", source_integrity_error="Sources changed during the matrix")
    summary.update(schema_version=1, timestamp_utc=datetime.now(timezone.utc).isoformat(),
                   matrix=matrix, source_sha256=hashes, cases=cases,
                   resource_policy={"worker_limit": matrix["jobs"]},
                   spike_comparison_executed=matrix["include_spike"] and all(
                       c["spike_comparison_executed"] for c in cases if c["layer"] == "uvm"),
                   rtl_mutation_campaign_executed=False)
    summary["live_spike_comparison_executed"] = matrix["include_live_spike"] and all("live_spike" in c for c in cases)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    rows = ["# Regression report", "", f"Status: **{summary['status']}**. {summary['passed_cases']}/{len(tasks)} cases passed.",
            "", "| Case | Layer / scope | Result | Failure class |", "| --- | --- | --- | --- |"]
    for case in cases:
        rows.append(f"| {case['case_id']} | {case['layer']} / {case['scope']} | {case['status']} | {case['failure_category'] or ''} |")
    rows += ["", "One UVM case includes two positive timing profiles and its corruption control.",
             "Coverage percentages are per-run observations; simulator bins have not been merged.",
             "RTL mutation campaigns were not executed. See summary.json for replay commands and artifacts."]
    spike_cases = [c["spike"] for c in cases if "spike" in c]
    rows += ["", f"Spike: requested={matrix['include_spike']}; successful executions={len(spike_cases)}; "
             f"profile matches={sum(len(c['profiles']) for c in spike_cases)}; "
             f"comparison corruption controls={sum(c['corruption_control']['status'] == 'detected' for c in spike_cases)}."]
    rows += ["", f"Cross-processor trace matches: {len(summary.get('processor_comparisons', []))}."]
    rows += ["", f"Distinct constrained-random instruction corpora: {len(summary.get('random_corpora', []))}."]
    rows += ["", f"Live Spike/DPI-C: requested={matrix['include_live_spike']}; "
             f"compared retirements={sum(sum(c.get('live_spike', {}).get('profiles', {}).values()) for c in cases)}; "
             f"detected live controls={sum(len(c.get('live_spike', {}).get('controls', {})) for c in cases)}."]
    if summary.get("processor_comparison_error"):
        rows += ["", "Cross-processor check failed: " + summary["processor_comparison_error"]]
    (output / "report.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"REGRESSION_{summary['status'].upper()}: {output / 'report.md'}", flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/regressions/smoke.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--jobs", type=int)
    parser.add_argument("--spike", action="store_true", default=None,
                        help="Require independent pinned Spike execution/comparison for each CPU case")
    args = parser.parse_args()
    output = args.output or ROOT / "build/regressions" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    summary = run_regression(args.config, output, args.jobs, args.spike)
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"REGRESSION_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
