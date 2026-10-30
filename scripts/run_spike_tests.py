"""Run pinned Spike against an existing shared smoke image, optionally compare RVFI.

This never relabels existing RTL evidence as a newly executed UVM run. Use the
regression runner's --spike option for fresh combined CPU acceptance.
"""
import argparse
import json
from pathlib import Path
import sys
from tool_common import ROOT

sys.path.insert(0, str(ROOT))
from verification.config import load_processor, apply_program
from verification.reference.spike import run_reference, qualify_comparison
from verification.traces import compare_traces, normalize_rvfi_csv, write_trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--program", type=Path, required=True)
    parser.add_argument("--processor", default="ibex_smoke")
    parser.add_argument("--program-profile", choices=("smoke", "corners", "random"), default="smoke")
    parser.add_argument("--rvfi", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cfg = apply_program(load_processor(args.processor), args.program_profile)
    reference, execution = run_reference(args.program, cfg, args.output)
    result = {"status": "pass", "reference_executed": execution["executed"],
              "uvm_executed_by_this_command": False}
    if args.rvfi:
        actual = normalize_rvfi_csv(args.rvfi, args.program, cfg)
        result["comparison"] = compare_traces(actual, reference)
        result["corruption_control"], corrupt = qualify_comparison(actual, reference)
        write_trace(args.output / "dut-retirement-v1.json", actual)
        write_trace(args.output / "corrupted-observation.json", corrupt)
    (args.output / "comparison-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print("SPIKE_PASS: " + str(args.output / "comparison-result.json"))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print("SPIKE_FAILED: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
