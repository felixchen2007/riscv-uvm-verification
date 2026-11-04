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
    for scenario, trap_id in (("ordinary", 0), ("ecall", 1), ("ebreak", 2), ("writeback_control", 0)):
        negative = scenario == "writeback_control"
        for timing, delay in ([("stalled", 3)] if negative else PROFILES.items()):
            name = f"{scenario}_{timing}"
            plusargs = ["UVM_TESTNAME=riscv_rv32i_test", "UVM_VERBOSITY=UVM_LOW",
                        "UVM_MAX_QUIT_COUNT=1,YES", f"IBEX_SEED={seed}", f"IBEX_MAX_DELAY={delay}",
                        f"RV32I_TRAP={trap_id}"]
            if negative:
                plusargs.append("IBEX_CORRUPT_RVFI")
            for filename in ("rvfi_trace.csv", "program.hex"):
                (output / filename).unlink(missing_ok=True)
            proc = simulate(bin_dir, snapshot, output, name, seed, plusargs)
            counts = uvm_counts(proc.stdout)
            fields = pass_fields(proc.stdout)
            artifacts = {}
            for filename in ("rvfi_trace.csv", "program.hex", name + "_console.log"):
                source = output / filename
                if not source.is_file():
                    raise RuntimeError(f"{name} did not produce {filename}")
                saved = output / (name + "_" + filename) if not filename.startswith(name) else source
                if saved != source:
                    shutil.copyfile(source, saved)
                artifacts[saved.name] = hashlib.sha256(saved.read_bytes()).hexdigest()
            if negative:
                caught = (proc.returncode == 0 and not simulator_errors(proc.stdout) and fields is None
                          and "[CORRUPTION_INJECTED]" in proc.stdout and "[RVFI_RD]" in proc.stdout
                          and counts["UVM_ERROR"] == 1 and counts["UVM_FATAL"] == 0)
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
            expected = ORDINARY if trap_id == 0 else {"ADDI", TRAPS[trap_id - 1]}
            if trap_id and result["processor_config"] == "ibex_smoke":
                expected |= {"MCAUSE", "MEPC"}
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
        scenario = instruction.lower() if instruction in TRAPS else "ordinary"
        checklist[instruction] = {
            processor: sum(results[processor]["profiles"][f"{scenario}_{timing}"]["checks"][instruction]
                           for timing in PROFILES)
            for processor in PROCESSORS
        }
    report = {"status": "pass", "instruction_counts": checklist, "processors": results}
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"RV32I_CHECKLIST_PASS {len(checklist)}/40 per core", flush=True)


if __name__ == "__main__":
    main()
