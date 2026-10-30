"""Compile pinned Ibex and run native UVM smoke profiles plus corruption control."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

from tool_common import ROOT, call_tool, find_questa, require_success, uvm_paths

VENDOR = "vendor/ibex/"
RTL_NAMES = ["ibex_pkg", "ibex_alu", "ibex_branch_predict", "ibex_compressed_decoder",
             "ibex_controller", "ibex_cs_registers", "ibex_csr", "ibex_counter", "ibex_decoder",
             "ibex_ex_block", "ibex_fetch_fifo", "ibex_id_stage", "ibex_if_stage",
             "ibex_load_store_unit", "ibex_multdiv_fast", "ibex_multdiv_slow",
             "ibex_prefetch_buffer", "ibex_pmp", "ibex_wb_stage", "ibex_dummy_instr",
             "ibex_icache", "ibex_register_file_ff", "ibex_core"]
RTL_SOURCES = [VENDOR + "rtl/" + name + ".sv" for name in RTL_NAMES]
TB_SOURCES = ["tb/uvm/riscv_control_if.sv", "tb/uvm/ibex_mem_if.sv", "tb/uvm/ibex_rvfi_if.sv", "tb/uvm/picorv32_mem_if.sv", "tb/uvm/ibex_uvm_pkg.sv",
              "tb/uvm/tb_ibex_uvm.sv"]
PROFILES = {"no_added_delay": 0, "stalled": 3}


def verify_vendor_lock(implementation="ibex"):
    pins = {"ibex": "38c070939183cc10940b66c8e9e04eeca6b65470",
            "picorv32": "ef203c2b0a3fb793280f5114941416c425c5b461"}
    if implementation not in pins:
        raise ValueError("Unknown vendor source lock")
    path = ROOT / "vendor" / (implementation + ".lock.json")
    lock = json.loads(path.read_text(encoding="utf-8-sig"))
    if lock["commit"] != pins[implementation]:
        raise RuntimeError(f"Unexpected {implementation} vendor commit in lock file")
    for name, expected in lock["sha256"].items():
        actual = hashlib.sha256((ROOT / "vendor" / implementation / name).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"Vendor snapshot differs from pinned source: {name}")
    return lock


def snapshot_hashes():
    paths = set(ROOT / source for source in RTL_SOURCES + TB_SOURCES)
    paths.add(ROOT / "vendor/ibex.lock.json")
    paths.add(ROOT / "requirements-verification.txt")
    for folder in ("vendor", "tb", "scripts", "config", "verification", "schemas", "tests", ".github"):
        for path in (ROOT / folder).rglob("*"):
            if path.is_file() and path.suffix in (".v", ".sv", ".svh", ".cc", ".h", ".py", ".ps1", ".json", ".txt", ".yml", ".yaml") and "__pycache__" not in path.parts:
                paths.add(path)
    return {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)}


def uvm_counts(transcript):
    counts = {}
    for severity in ("UVM_INFO", "UVM_WARNING", "UVM_ERROR", "UVM_FATAL"):
        matches = re.findall(rf"\b{severity}\s*:\s*(\d+)", transcript)
        counts[severity] = int(matches[-1]) if matches else None
    return counts


def pass_fields(transcript):
    for match in re.finditer(r"\[(?:IBEX|RV)_UVM_PASS\]\s+([^\r\n]+)", transcript):
        fields = {}
        for key, value in re.findall(r"(\w+)=([^\s]+)", match.group(1)):
            try:
                fields[key] = int(value, 0)
            except ValueError:
                try:
                    fields[key] = int(value, 16) if key == "signature" else int(value)
                except ValueError:
                    fields[key] = value
        if fields:
            return fields
    return None


def run_suite(seed=20261029, full=False, profiles=None, output=None, compile_only=False):
    output = (output or ROOT / "build/uvm" / ("full" if full else "starter")).resolve()
    output.mkdir(parents=True, exist_ok=True)
    result_path = output / "results.json"
    result_path.unlink(missing_ok=True)
    configuration = json.loads((ROOT / "config/smoke.json").read_text(encoding="utf-8"))
    result = {"status": "incomplete", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "native UVM 1.2 simulation of pinned Ibex; no FPGA or JTAG access",
              "configuration": configuration, "seed": seed,
              "mode": "licensed-sv-constrained-random-and-covergroups" if full else "starter-seeded-procedural-stimulus",
              "sv_constrained_randomization_executed": False, "sv_covergroups_executed": False,
              "spike_comparison_executed": False, "profiles": {}, "corruption_control": None}
    try:
        result["vendor_lock_verified"] = verify_vendor_lock()["commit"]
        hashes = snapshot_hashes()
        result["source_sha256"] = hashes
        tool_dir = find_questa()
        uvm_source, dpi = uvm_paths(tool_dir)
        result["questa_bin"] = str(tool_dir)
        result["uvm_package_sha256"] = hashlib.sha256((uvm_source / "uvm_pkg.sv").read_bytes()).hexdigest()
        result["tool_versions"] = {}
        for tool in ("vlog", "vsim"):
            run = call_tool(tool_dir, tool, ["-version"], output, tool + "_version.log")
            require_success(run, tool + " version")
            result["tool_versions"][tool] = run.stdout.strip()
        for library in ("work", "uvm12"):
            if not (output / library).exists():
                require_success(call_tool(tool_dir, "vlib", [library], output, library + "_library.log"), "library creation")
        require_success(call_tool(tool_dir, "vlog", ["-sv", "-work", "uvm12", "+incdir+" + str(uvm_source),
                                                    uvm_source / "uvm_pkg.sv"], output, "uvm_compile.log"), "UVM package compilation")
        incdirs = [uvm_source, ROOT / "tb/uvm", ROOT / VENDOR / "rtl",
                   ROOT / VENDOR / "vendor/lowrisc_ip/ip/prim/rtl",
                   ROOT / VENDOR / "vendor/lowrisc_ip/dv/sv/dv_utils"]
        args = ["-sv", "-L", "uvm12", "+define+RVFI", "+define+DV_FCOV_DISABLE"]
        args += ["+incdir+" + str(path) for path in incdirs]
        if full:
            args.append("+define+IBEX_UVM_FULL")
        args += [str(ROOT / source) for source in RTL_SOURCES + TB_SOURCES]
        result["compile_defines"] = ["RVFI", "DV_FCOV_DISABLE"] + (["IBEX_UVM_FULL"] if full else [])
        result["compile_sources"] = RTL_SOURCES + TB_SOURCES
        require_success(call_tool(tool_dir, "vlog", args, output, "project_compile.log"), "Ibex UVM compilation")
        if compile_only:
            result["status"] = "compiled-only"
            result["verification_pass"] = False
            print("IBEX_UVM_COMPILE_ONLY: no simulation or verification pass claimed", flush=True)
            return result
        (output / "run.do").write_text("onerror {quit -code 1}\nrun -all\nquit -code 0\n", encoding="ascii")
        selected = list(profiles) if profiles else list(PROFILES)
        for profile in selected + ["rvfi_corruption_control"]:
            corrupt = profile == "rvfi_corruption_control"
            delay = 3 if corrupt else PROFILES[profile]
            args = ["-c", "-onfinish", "stop", "-L", "uvm12", "-sv_lib", str(dpi), "-sv_seed", str(seed),
                    "-l", profile + "_transcript.log", "work.tb_ibex_uvm", "+UVM_TESTNAME=ibex_smoke_test",
                    "+UVM_VERBOSITY=UVM_LOW", "+UVM_MAX_QUIT_COUNT=1,YES", f"+IBEX_SEED={seed}",
                    f"+IBEX_MAX_DELAY={delay}", "-do", "do run.do"]
            if full:
                args.insert(1, "-coverage")
            if corrupt:
                args.append("+IBEX_CORRUPT_RVFI")
            run = call_tool(tool_dir, "vsim", args, output, profile + "_console.log", timeout=180)
            transcript = run.stdout
            counts = uvm_counts(transcript)
            fields = pass_fields(transcript)
            license_denied = bool(re.search(r"Unable to checkout verification license|Failed to checkout.*license|License checkout failed", transcript, re.I))
            if license_denied:
                raise RuntimeError(f"Simulator license denied {profile}; see {output / (profile + '_console.log')}")
            if corrupt:
                caught = (run.returncode == 0 and "[RVFI_RD]" in transcript and counts["UVM_ERROR"] == 1
                          and counts["UVM_FATAL"] == 0
                          and fields is None and "** Error:" not in transcript and "** Fatal:" not in transcript)
                result["corruption_control"] = {"status": "detected" if caught else "failed",
                                                "injection": "corrupt observed RVFI register result; DUT RTL unchanged",
                                                "expected_error_id": "RVFI_RD", "uvm_counts": counts,
                                                "simulator_exit_code": run.returncode}
                if not caught:
                    raise RuntimeError("RVFI corruption control was not detected as expected:\n" + transcript[-7000:])
                print("IBEX_UVM_EXPECTED_FAILURE_DETECTED rvfi_corruption_control RVFI_RD", flush=True)
                continue
            require_success(run, "UVM profile " + profile)
            if fields is None or counts["UVM_ERROR"] != 0 or counts["UVM_FATAL"] != 0:
                raise RuntimeError(f"UVM profile {profile} lacks a clean executed pass:\n{transcript[-7000:]}")
            required = ("retired", "loads", "stores", "branches_taken", "branches_not_taken", "jumps", "signature")
            if any(not isinstance(fields.get(key), int) or fields[key] <= 0 for key in required):
                raise RuntimeError(f"UVM profile {profile} did not exercise required smoke scenarios: {fields}")
            for key, expected in (("seed", seed), ("max_delay", delay)):
                if key in fields and fields[key] != expected:
                    raise RuntimeError(f"UVM profile {profile} reports wrong {key}: {fields[key]} != {expected}")
            if delay and ("instr_stalls" in fields or "data_stalls" in fields):
                if fields.get("instr_stalls", 0) <= 0 or fields.get("data_stalls", 0) <= 0:
                    raise RuntimeError("Stalled profile did not exercise both instruction and data backpressure")
            result["profiles"][profile] = {"status": "pass", "max_delay": delay, "scenarios": fields,
                                           "uvm_counts": counts, "simulator_exit_code": run.returncode}
            print("IBEX_UVM_PROFILE_PASS " + profile + " " + json.dumps(fields, sort_keys=True), flush=True)
        if snapshot_hashes() != hashes:
            raise RuntimeError("Project sources changed during verification; rerun on a stable source snapshot")
        result["status"] = "pass"
        result["verification_pass"] = True
        result["sv_constrained_randomization_executed"] = full
        result["sv_covergroups_executed"] = full
        print("IBEX_UVM_REGRESSION_PASS: " + str(result_path), flush=True)
        return result
    except (OSError, RuntimeError, ValueError) as exc:
        result["status"] = "failed"
        result["verification_pass"] = False
        result["failure"] = str(exc)
        raise
    finally:
        result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sim", choices=("xsim", "questa"), default="xsim",
                        help="Host simulator (default: user-selected Vivado XSim)")
    parser.add_argument("--vivado-bin", help="Override Vivado's bin folder")
    parser.add_argument("--processor", choices=("ibex_smoke", "picorv32_rv32i"), default="ibex_smoke")
    parser.add_argument("--program", choices=("smoke", "corners", "random", "irq"), default="smoke")
    parser.add_argument("--scenario", choices=("normal", "reset", "factory", "irq"), default="normal")
    parser.add_argument("--seed", type=int, default=20261029)
    parser.add_argument("--profile", action="append", choices=PROFILES)
    parser.add_argument("--full", action="store_true", help="Execute SV randomize and covergroups; requires suitable license")
    parser.add_argument("--compile-only", action="store_true", help="Compile without claiming a verification pass")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--rtl-mutation", type=Path, help="Owned isolated RTL manifest; campaign observation mode")
    args = parser.parse_args()
    if args.scenario != "normal" and (args.sim != "xsim" or not args.full or args.rtl_mutation):
        parser.error("Advanced scenarios require XSim --full and pristine RTL")
    if (args.scenario == "irq") != (args.program == "irq") or (args.scenario == "irq" and args.processor != "ibex_smoke"):
        parser.error("IRQ scenario requires --program irq and the Ibex adapter")
    if args.rtl_mutation and (args.sim != "xsim" or not args.full or args.output is None):
        parser.error("RTL mutation observations require XSim, --full and an isolated --output")
    if args.program == "random" and not args.full:
        parser.error("--program random requires --full; instruction randomization has no procedural fallback")
    if not 0 < args.seed <= 0xFFFFFFFF:
        parser.error("seed must be between 1 and 4294967295")
    if args.sim == "xsim":
        if args.profile or args.compile_only:
            parser.error("--profile and --compile-only apply to --sim questa; XSim runs both smoke profiles")
        from run_xsim_tests import run_suite as run_xsim_suite
        run_xsim_suite(args.seed, args.full, args.vivado_bin, output=args.output, processor=args.processor, program=args.program,
                       mutation_manifest=args.rtl_mutation, scenario=args.scenario)
    else:
        if args.program != "smoke":
            parser.error("The extended program acceptance flow uses XSim; Questa retains its original smoke")
        if args.processor != "ibex_smoke":
            parser.error("The PicoRV32 acceptance flow uses XSim; no Questa PicoRV32 run is claimed")
        run_suite(args.seed, args.full, args.profile, args.output, args.compile_only)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print("IBEX_UVM_REGRESSION_FAILED: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
