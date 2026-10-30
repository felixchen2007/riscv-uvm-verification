"""Run Ibex's native UVM smoke and checker control in Vivado XSim."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from tool_common import ROOT
sys.path.insert(0, str(ROOT))
from verification.config import load_processor, apply_program
from verification.programs import audit_random_program, validate_generation_identity
from verification.mutations import verify_mutant
from verification.scenarios import extract_reset_epoch, audit_irq_trace
from run_uvm_tests import (RTL_SOURCES, TB_SOURCES, PROFILES, verify_vendor_lock,
                           snapshot_hashes, uvm_counts, pass_fields)


def find_vivado(explicit=None):
    candidates = [Path(p) for p in (explicit, os.environ.get("VIVADO_BIN")) if p]
    found = shutil.which("xvlog")
    if found:
        candidates.append(Path(found).parent)
    for location in ("D:/AMDDesignTools", "C:/AMDDesignTools", "C:/Xilinx/Vivado",
                     "D:/Xilinx/Vivado", "C:/AMD/Vivado", "D:/AMD/Vivado"):
        base = Path(location)
        if base.is_dir():
            candidates.extend(sorted(base.glob("*/Vivado/bin"), reverse=True))
            candidates.extend(sorted(base.glob("*/bin"), reverse=True))
    suffix = ".bat" if os.name == "nt" else ""
    for candidate in candidates:
        if all((candidate / (name + suffix)).is_file() for name in ("xvlog", "xelab", "xsim")):
            return candidate.resolve()
    raise RuntimeError("Vivado not found. Set VIVADO_BIN or pass --vivado-bin with its bin folder.")


def call(bin_dir, tool, args, output, log, timeout=300):
    suffix = ".bat" if os.name == "nt" else ""
    # Windows subprocess launches the trusted vendor batch entrypoint; no shell
    # operators or user-authored command strings are constructed here.
    command = [str(bin_dir / (tool + suffix)), *map(str, args)]
    try:
        proc = subprocess.run(command, cwd=output, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        text = exc.stdout or b""
        if isinstance(text, bytes):
            text = text.decode(errors="replace")
        (output / log).write_text(text + "\nPROCESS_TIMEOUT\n", encoding="utf-8")
        raise RuntimeError(f"{tool} timed out; see {output / log}") from exc
    (output / log).write_text(proc.stdout, encoding="utf-8")
    return proc


def simulator_errors(transcript):
    return bool(re.search(r"(?mi)^\s*(?:ERROR:|FATAL:|Error:|Fatal:|\*\* (?:Error|Fatal):)", transcript))


def require_ok(proc, context):
    if proc.returncode or simulator_errors(proc.stdout):
        raise RuntimeError(f"{context} failed (exit {proc.returncode}):\n{proc.stdout[-8000:]}")


def run_suite(seed=20261029, full=False, vivado_bin=None, prepare_only=False, output=None, processor="ibex_smoke", program="smoke", mutation_manifest=None, scenario="normal"):
    cpu = apply_program(load_processor(processor), program)
    contract = cpu["program_contract"]
    if contract.get("requires_full") and not full:
        raise ValueError("Random instructions require --full SV constrained randomization")
    is_pico = cpu["implementation"] == "picorv32"
    scenarios={"normal":0,"reset":1,"factory":2,"irq":3}
    if scenario not in scenarios or (scenario!="normal" and (not full or mutation_manifest)):
        raise ValueError("Unsupported advanced scenario mode")
    if (scenario=="irq")!=(program=="irq") or (scenario=="irq" and is_pico):
        raise ValueError("IRQ scenario requires the Ibex IRQ program")
    if scenario in ("reset","factory") and program!="corners":
        raise ValueError("Reset/factory qualification uses corners")
    if mutation_manifest and (not full or prepare_only or output is None):
        raise ValueError("Mutation observation requires executed full UVM and explicit output")
    default_root = ROOT / "build/xsim" if not is_pico else ROOT / "build/xsim/picorv32"
    if program != "smoke":
        default_root /= program
    if scenario!="normal": default_root /= scenario
    output = Path(output or default_root / ("full" if full else "seeded")).resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = {"status": "incomplete", "verification_pass": False, "simulator": "Vivado XSim",
              "timestamp_utc": datetime.now(timezone.utc).isoformat(), "seed": seed,
              "uvm_version": "1.2", "mode": "sv-constrained-random-instructions-and-memory-timing" if program == "random" else
                  ("sv-constrained-random-timing-and-covergroups" if full else "seeded-procedural-timing"),
              "sv_constrained_randomization_executed": False, "sv_covergroups_executed": False,
              "sv_instruction_randomization_executed": False,
              "spike_comparison_executed": False, "rtl_mutation_campaign_executed": False,
              "profiles": {}, "corruption_control": None,
              "processor_config": processor,
              "program_profile": program, "program_contract": contract,
              "scenario":scenario,
              "configuration": json.loads((ROOT / cpu["parameter_config"]).read_text())}
    result.update(compiled=False, elaborated=False, mutation_integrity_verified=False)
    result_path = output / "results.json"
    if result_path.exists():
        archive = output / "history" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        archive.mkdir(parents=True)
        for previous in output.iterdir():
            if previous.is_file() and previous.suffix in (".log", ".json", ".csv", ".args", ".hex"):
                shutil.copyfile(previous, archive / previous.name)
    result_path.unlink(missing_ok=True)
    try:
        result["vendor_commit_verified"] = verify_vendor_lock(cpu["implementation"])["commit"]
        hashes = snapshot_hashes()
        result["source_sha256"] = hashes
        mutation = verify_mutant(mutation_manifest) if mutation_manifest else None
        if mutation and mutation["implementation"] != cpu["implementation"]:
            raise ValueError("Mutation does not match selected processor")
        if mutation:
            result.update(rtl_mutation_campaign_executed=True, mutation=mutation)
        bin_dir = find_vivado(vivado_bin)
        result["vivado_bin"] = str(bin_dir)
        uvm_dirs = [base / "data/system_verilog/uvm_1.2" for base in (bin_dir.parent, bin_dir.parent.parent)]
        uvm_include = next((p for p in uvm_dirs if (p / "uvm_macros.svh").is_file()), None)
        if uvm_include is None:
            raise RuntimeError("Vivado UVM 1.2 macro directory was not found beside the installation")
        includes = [uvm_include, ROOT / "tb/uvm", ROOT / "vendor/ibex/rtl",
                    ROOT / "vendor/ibex/vendor/lowrisc_ip/ip/prim/rtl",
                    ROOT / "vendor/ibex/vendor/lowrisc_ip/dv/sv/dv_utils"]
        defines = (["RISCV_FORMAL"] if is_pico else ["RVFI", "DV_FCOV_DISABLE"]) + (["IBEX_UVM_FULL"] if full else [])
        compile_args = ["-sv", "-L", "uvm"]
        for include in includes:
            compile_args += ["-i", str(include)]
        for define in defines:
            compile_args += ["-d", define]
        if is_pico:
            sources = ["vendor/picorv32/picorv32.v"] + TB_SOURCES[:-1] + ["tb/uvm/tb_picorv32_uvm.sv"]
        else:
            sources = ["tb/uvm/ibex_xsim_if_stage.sv" if p.endswith("/ibex_if_stage.sv") else p
                       for p in RTL_SOURCES] + TB_SOURCES
        compile_paths = [str(ROOT / p) for p in sources]
        if mutation:
            if sources.count(mutation["relative_source"]) != 1:
                raise ValueError("Mutation must replace exactly one compiled RTL source")
            compile_paths[sources.index(mutation["relative_source"])] = mutation["isolated_source"]
        compile_args += compile_paths
        result["resolved_compile_sources"] = compile_paths
        snapshot = cpu["implementation"] + ("_uvm_full" if full else "_uvm_seeded")
        top = "tb_picorv32_uvm" if is_pico else "tb_ibex_uvm"
        elab_args = ["-L", "uvm", "work." + top, "-s", snapshot, "--timescale", "1ns/1ps"]
        result["compile_defines"] = defines
        result["compile_sources"] = sources
        result["xsim_compatibility"] = "No RTL compatibility wrapper needed" if is_pico else "if_stage only: suppress unused DPI exports; standard RTL SVA macros preloaded and active"
        commands = {"xvlog": compile_args, "xelab": elab_args}
        (output / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        (output / "run.tcl").write_text("run all\nquit\n", encoding="ascii")
        if prepare_only:
            result["status"] = "prepared-only"
            print(f"XSIM_PREPARED_ONLY: {output}; no simulation pass claimed")
            return result
        version = call(bin_dir, "xvlog", ["--version"], output, "version.log")
        require_ok(version, "XSim version check")
        result["tool_version"] = version.stdout.strip()
        require_ok(call(bin_dir, "xvlog", compile_args, output, "compile_console.log"), "XSim compilation")
        result["compiled"] = True
        require_ok(call(bin_dir, "xelab", elab_args, output, "elaborate_console.log"), "XSim elaboration")
        result["elaborated"] = True
        selected_profiles = [("stalled", 3)] if mutation else list(PROFILES.items()) + [("rvfi_corruption_control", 3)]
        if scenario!="normal": selected_profiles=[("stalled",3),("rvfi_corruption_control",3)]
        for profile, delay in selected_profiles:
            plusargs = ["UVM_TESTNAME=" + (cpu["uvm_test"] if scenario=="normal" else "riscv_advanced_test"), "UVM_VERBOSITY=UVM_LOW",
                        "UVM_MAX_QUIT_COUNT=1,YES", f"IBEX_SEED={seed}", f"IBEX_MAX_DELAY={delay}",
                        f"IBEX_PROGRAM={contract['uvm_program_id']}",f"RV_SCENARIO={scenarios[scenario]}"]
            negative = profile == "rvfi_corruption_control"
            if negative:
                plusargs.append("IBEX_CORRUPT_RVFI")
            args = ["-tclbatch", "run.tcl", "-onerror", "quit", "-sv_seed", str(seed),
                    "-log", profile + "_simulation.log"]
            if full:
                args += ["-cov_db_dir", "coverage", "-cov_db_name", profile]
            for value in plusargs:
                args += ["-testplusarg", value]
            # Vivado's Windows batch launcher reparses '=' in unquoted
            # plusargs. XSim's native argument file preserves each full token.
            arg_file = profile + ".args"
            (output / arg_file).write_text("\n".join('"' + str(a).replace('\\', '/') + '"' for a in args) + "\n",
                                           encoding="utf-8")
            proc = call(bin_dir, "xsim", [snapshot, "-f", arg_file], output, profile + "_console.log")
            counts = uvm_counts(proc.stdout)
            fields = pass_fields(proc.stdout)
            for name in ("rvfi_trace.csv", "program.hex", "program-generation.json", "control_trace.csv"):
                if (output / name).is_file():
                    shutil.copyfile(output / name, output / (profile + "_" + name))
            if mutation:
                result["mutation_observation"] = {"simulated": True, "returncode": proc.returncode,
                    "uvm_counts": counts, "pass_fields": fields, "simulator_errors": simulator_errors(proc.stdout),
                    "transcript": proc.stdout, "profile": profile, "max_delay": delay,
                    "observation_corruption_enabled": False}
                if snapshot_hashes() != hashes:
                    raise RuntimeError("Sources changed during mutation observation")
                verify_mutant(mutation_manifest)
                result.update(status="mutation-observed", mutation_integrity_verified=True)
                return result
            if negative:
                caught = (proc.returncode == 0 and not simulator_errors(proc.stdout) and fields is None
                          and "[RVFI_RD]" in proc.stdout and "[CORRUPTION_INJECTED]" in proc.stdout
                          and counts["UVM_ERROR"] == 1 and counts["UVM_FATAL"] == 0)
                result["corruption_control"] = {"status": "detected" if caught else "failed",
                                                "expected_error_id": "RVFI_RD", "uvm_counts": counts,
                                                "injection": "one sampled RVFI rd_data bit; original DUT unchanged"}
                if not caught:
                    raise RuntimeError("Corruption control failed intended diagnostic contract:\n" + proc.stdout[-8000:])
                print("XSIM_EXPECTED_FAILURE_DETECTED: RVFI_RD", flush=True)
                continue
            require_ok(proc, profile)
            advanced=None; epoch_result=None
            if scenario!="normal":
                marker=re.search(r"\[RV_ADVANCED\]\s+([^\r\n]+)",proc.stdout)
                advanced={k:int(v) for k,v in re.findall(r"(\w+)=(\d+)",marker[1])} if marker else {}
                if advanced.get("scenario_id")!=scenarios[scenario] or advanced.get("factory_calls",0)<=0 or advanced.get("virtual_completed")!=1:
                    raise RuntimeError("Virtual sequence/factory override did not execute")
                if scenario=="reset":
                    if any(advanced.get(k)!=v for k,v in {"resets":1,"pending_resets":1,"accepted_resets":int(not is_pico)}.items()):
                        raise RuntimeError("Reset abort/acceptance boundary mismatch")
                    epoch_result=extract_reset_epoch(output/(profile+"_rvfi_trace.csv"))
                if scenario=="irq" and any(advanced.get(k)!=1 for k in ("irq_assertions","irq_deassertions","irq_entries","mret")):
                    raise RuntimeError("Interrupt/return scenario did not complete")
            required = {"retired": contract["expected_retirements"], **contract["expected_counts"],
                        "signature": contract["signature_value"], "seed": seed, "max_delay": delay,
                        "cpu_id": int(is_pico), "program_id": contract["uvm_program_id"]}
            if scenario=="irq": required.pop("retired");required.pop("branches_taken")
            if counts["UVM_ERROR"] != 0 or counts["UVM_FATAL"] != 0 or fields is None:
                raise RuntimeError("Missing clean executed UVM pass:\n" + proc.stdout[-8000:])
            if any(fields.get(k) != v for k, v in required.items()):
                raise RuntimeError(f"Smoke identity/scenario mismatch: {fields}")
            if scenario=="irq" and not (15<=fields.get("retired",0)<=1000 and fields.get("branches_taken",0)>=1):
                raise RuntimeError("IRQ retirement/parking bound failed")
            if delay and (fields.get("instr_stalls", 0) <= 0 or fields.get("data_stalls", 0) <= 0):
                raise RuntimeError("Stalled profile did not exercise both interfaces")
            features = re.search(r"\[IBEX_FULL_FEATURES\] randomize_calls=(\d+) coverage_percent=([0-9.]+)", proc.stdout)
            corner_features = re.search(r"\[RV_CORNER_COVERAGE\] coverage_percent=([0-9.]+)", proc.stdout)
            program_random = re.search(r"\[RV_PROGRAM_RANDOM\] instruction_calls=(\d+) schedule_calls=(\d+) seed=(\d+)", proc.stdout)
            random_coverage = re.search(r"\[RV_RANDOM_COVERAGE\] kind_percent=([0-9.]+) alu_percent=([0-9.]+) memory_percent=([0-9.]+)", proc.stdout)
            expected_calls = (64, 8, seed) if program == "random" else (0, 0, seed)
            if program_random is None or tuple(map(int, program_random.groups())) != expected_calls:
                raise RuntimeError("Program instruction randomization did not execute as requested")
            branch_marker = re.search(r"\[RV_BRANCH_HITS\]\s+([^\r\n]+)", proc.stdout)
            hits = {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", branch_marker[1])} if branch_marker else {}
            expected_hits=contract["branch_hits"] if scenario!="irq" else {"beq_taken":fields["branches_taken"],"beq_not_taken":1,"bne_taken":0,"bne_not_taken":0}
            if hits != expected_hits:
                raise RuntimeError(f"Branch outcome counts differ from program contract: {hits}")
            if full and (features is None or int(features[1]) == 0):
                raise RuntimeError("Full run lacks evidence of successful randomization and covergroup sampling")
            if full and contract["require_smoke_coverage"] is not None and float(features[2]) < contract["require_smoke_coverage"]:
                raise RuntimeError("Required opcode/branch covergroup goals remain open")
            if full and contract["require_corner_coverage"] is not None and (
                    corner_features is None or float(corner_features[1]) < contract["require_corner_coverage"]):
                raise RuntimeError("Required directed corner covergroup goals remain open")
            if program == "random" and (random_coverage is None or float(random_coverage[1]) != 100):
                raise RuntimeError("Random-body instruction-class coverage is incomplete")
            result["profiles"][profile] = {"status": "pass", "scenarios": fields, "uvm_counts": counts,
                                           "assertion_failures": 0, "simulator_exit_code": proc.returncode, "branch_hits": hits}
            if advanced is not None: result["profiles"][profile]["advanced"]=advanced
            if epoch_result: result["profiles"][profile]["reset_epochs"]=epoch_result
            if scenario=="irq":
                result["profiles"][profile]["irq_audit"]=audit_irq_trace(output/(profile+"_rvfi_trace.csv"),output/(profile+"_control_trace.csv"))
            result["profiles"][profile]["program_randomization"] = {
                "instruction_calls": expected_calls[0], "schedule_calls": expected_calls[1], "seed": seed}
            result["profiles"][profile]["generation_metadata"] = validate_generation_identity(
                json.loads((output / (profile + "_program-generation.json")).read_text(encoding="utf-8")), program, seed)
            if program == "random":
                result["profiles"][profile]["random_input_audit"] = audit_random_program(
                    output / (profile + "_program.hex"), output / (profile + "_program-generation.json"), contract, seed)
            if features:
                result["profiles"][profile]["full_features"] = {"randomize_calls": int(features[1]),
                                                               "smoke_covergroup_percent": float(features[2]),
                                                               "corner_covergroup_percent": float(corner_features[1]) if corner_features else None}
                if random_coverage:
                    result["profiles"][profile]["full_features"].update(
                        random_body_kind_percent=float(random_coverage[1]), random_body_alu_percent=float(random_coverage[2]),
                        random_body_memory_percent=float(random_coverage[3]))
            print("XSIM_UVM_PROFILE_PASS " + profile + " " + json.dumps(fields), flush=True)
        if snapshot_hashes() != hashes:
            raise RuntimeError("Sources changed during verification; rerun on stable sources")
        result.update(status="pass", verification_pass=True,
                      sv_instruction_randomization_executed=program == "random",
                      sv_constrained_randomization_executed=full, sv_covergroups_executed=full)
        print(f"XSIM_UVM_REGRESSION_PASS: {result_path}", flush=True)
        return result
    except (OSError, RuntimeError, ValueError) as exc:
        result.update(status="failed", error=str(exc))
        raise
    finally:
        if mutation_manifest:
            try:
                verify_mutant(mutation_manifest)
                result["mutation_integrity_verified"] = True
            except (OSError, ValueError, KeyError) as exc:
                result.update(status="failed", mutation_integrity_verified=False, error=str(exc))
        result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="Execute constrained-random memory timing and covergroups")
    parser.add_argument("--seed", type=int, default=20261029)
    parser.add_argument("--vivado-bin")
    parser.add_argument("--processor", choices=("ibex_smoke", "picorv32_rv32i"), default="ibex_smoke")
    parser.add_argument("--program", choices=("smoke", "corners", "random", "irq"), default="smoke")
    parser.add_argument("--scenario", choices=("normal", "reset", "factory", "irq"), default="normal")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--output", type=Path, help="Isolated directory for this run")
    args = parser.parse_args()
    if not 0 <= args.seed <= 0xffffffff:
        parser.error("seed must fit unsigned 32 bits")
    run_suite(args.seed, args.full, args.vivado_bin, args.prepare_only, args.output, args.processor, args.program, scenario=args.scenario)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"XSIM_UVM_REGRESSION_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
