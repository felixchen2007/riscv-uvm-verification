# Runs the directed RV32I tests on Ibex and PicoRV32.
# Collects the UVM results into a checklist for all 40 base instructions.

"""Run the directed RV32I instruction checklist on Ibex and PicoRV32."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil

from run_xsim_tests import PROFILES, pass_fields, require_ok, run_suite, simulate, simulator_errors, uvm_counts

PROCESSORS = ("ibex_smoke", "picorv32_rv32i")
TRAPS = ("ECALL", "EBREAK")
ORDINARY = frozenset("""
    LUI AUIPC JAL JALR BEQ BNE BLT BGE BLTU BGEU LB LH LW LBU LHU SB SH SW
    ADDI SLTI SLTIU XORI ORI ANDI SLLI SRLI SRAI ADD SUB SLL SLT SLTU XOR SRL SRA OR AND FENCE
""".split())
ALL_INSTRUCTIONS = sorted(ORDINARY | set(TRAPS))


def exercise(bin_dir, snapshot, output, seed, result):
    simulator_files = ["rvfi_trace.csv", "program.hex"]
    for scenario, trap_id in (("ordinary", 0), ("ecall", 1), ("ebreak", 2), ("writeback_control", 0)):
        inject_writeback_error = scenario == "writeback_control"
        timings = PROFILES
        if inject_writeback_error:
            timings = {"stalled": PROFILES["stalled"]}
        for timing, delay in timings.items():
            name = f"{scenario}_{timing}"
            plusargs = ["UVM_TESTNAME=riscv_rv32i_test", "UVM_VERBOSITY=UVM_LOW",
                        "UVM_MAX_QUIT_COUNT=1,YES", f"IBEX_SEED={seed}", f"IBEX_MAX_DELAY={delay}",
                        f"RV32I_TRAP={trap_id}"]
            if inject_writeback_error:
                plusargs.append("IBEX_CORRUPT_RVFI")
            for filename in simulator_files:
                (output / filename).unlink(missing_ok=True)
            proc = simulate(bin_dir, snapshot, output, name, seed, plusargs)
            counts = uvm_counts(proc.stdout)
            fields = pass_fields(proc.stdout)
            artifacts = {}
            artifact_files = simulator_files + [name + "_console.log"]
            for filename in artifact_files:
                source = output / filename
                if not source.is_file():
                    raise RuntimeError(f"{name} did not produce {filename}")
                saved = source
                if filename in simulator_files:
                    saved = output / (name + "_" + filename)
                    shutil.copyfile(source, saved)
                artifacts[saved.name] = hashlib.sha256(saved.read_bytes()).hexdigest()
            if inject_writeback_error:
                simulator_finished = proc.returncode == 0 and not simulator_errors(proc.stdout)
                injection_ran = "[CORRUPTION_INJECTED]" in proc.stdout
                writeback_error_reported = "[RVFI_RD]" in proc.stdout
                exactly_one_error = counts["UVM_ERROR"] == 1 and counts["UVM_FATAL"] == 0
                caught = (simulator_finished and injection_ran and writeback_error_reported
                          and exactly_one_error and fields is None)
                result["corruption_control"] = {"status": "detected" if caught else "failed",
                                                "expected_diagnostic": "RVFI_RD", "uvm_counts": counts,
                                                "artifacts_sha256": artifacts}
                if not caught:
                    raise RuntimeError(f"{name} did not detect the injected writeback")
                continue
            require_ok(proc, name)
            if counts["UVM_ERROR"] != 0 or counts["UVM_FATAL"] != 0 or not fields:
                raise RuntimeError(f"{name} lacks a clean executed UVM pass:\n{proc.stdout[-5000:]}")
            checked = Counter(re.findall(r"\[RV32I_CHECKED\]\s+(\w+) pc=[0-9a-f]+ insn=[0-9a-f]+", proc.stdout))
            expected = ORDINARY
            if trap_id != 0:
                expected = {"ADDI", TRAPS[trap_id - 1]}
                if result["processor_config"] == "ibex_smoke":
                    expected.update(("MCAUSE", "MEPC"))
            if checked.keys() != expected or sum(checked.values()) != fields["retired"]:
                raise RuntimeError(f"{name} has incomplete instruction evidence: {checked}")
            if not trap_id and any(checked[op] != 2 for op in ("BEQ", "BNE", "BLT", "BGE", "BLTU", "BGEU")):
                raise RuntimeError(f"{name} did not verify both outcomes of every branch")
            cpu_id = PROCESSORS.index(result["processor_config"])
            if (fields["seed"], fields["max_delay"], fields["cpu_id"], fields["trap_case"]) != (seed, delay, cpu_id, trap_id):
                raise RuntimeError(f"{name} ran with the wrong configuration")
            if delay and not fields["instr_stalls"] + fields["instr_waits"]:
                raise RuntimeError(f"{name} did not exercise instruction wait cycles")
            if delay and not trap_id and not fields["data_stalls"] + fields["data_waits"]:
                raise RuntimeError(f"{name} did not exercise data wait cycles")
            result["profiles"][name] = {"status": "pass", "checks": dict(sorted(checked.items())),
                                        "uvm_counts": counts, "scenario": fields,
                                        "simulator_errors": False, "artifacts_sha256": artifacts}
            print(f"RV32I_PASS {result['processor_config']} {name} ({fields['retired']} checked steps)", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Fresh output directory")
    parser.add_argument("--vivado-bin")
    parser.add_argument("--seed", type=int, default=20261029)
    args = parser.parse_args()
    if not 0 <= args.seed <= 0xffffffff:
        parser.error("seed must fit unsigned 32 bits")
    args.output.mkdir(parents=True, exist_ok=False)
    results = {}
    for processor in PROCESSORS:
        results[processor] = run_suite(seed=args.seed, vivado_bin=args.vivado_bin,
                                       output=args.output / processor, processor=processor, rv32i=True)
    checklist = {}
    for instruction in ALL_INSTRUCTIONS:
        scenario = "ordinary"
        if instruction in TRAPS:
            scenario = instruction.lower()
        counts_by_processor = {}
        for processor in PROCESSORS:
            profiles = results[processor]["profiles"]
            instruction_count = 0
            for timing in PROFILES:
                profile = profiles[f"{scenario}_{timing}"]
                instruction_count += profile["checks"][instruction]
            counts_by_processor[processor] = instruction_count
        checklist[instruction] = counts_by_processor
    report = {"status": "pass", "instruction_counts": checklist, "processors": results}
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"RV32I_CHECKLIST_PASS {len(checklist)}/40 per core", flush=True)


if __name__ == "__main__":
    main()
