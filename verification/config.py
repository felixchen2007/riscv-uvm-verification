"""Processor contracts are data; planned adapters cannot execute accidentally."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def load_program(name):
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ValueError("Invalid program configuration identifier")
    path = ROOT / "config/programs" / (name + ".json")
    if not path.is_file():
        raise ValueError(f"Unknown program configuration: {name}")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("schema_version") != 1 or cfg.get("id") != name:
        raise ValueError("Unsupported program schema/identity")
    if type(cfg.get("expected_retirements")) is not int or not 1 <= cfg["expected_retirements"] <= 1000:
        raise ValueError("Invalid bounded program retirement count")
    for field in ("entry_pc", "terminal_pc", "signature_address"):
        if type(cfg.get(field)) is not int or not 0 <= cfg[field] < 65536 or cfg[field] % 4:
            raise ValueError("Invalid program address")
    if set(cfg.get("branch_hits", {})) != {"beq_taken", "beq_not_taken", "bne_taken", "bne_not_taken"}:
        raise ValueError("Missing program branch outcome contract")
    if any(type(n) is not int or n < 0 for n in cfg["branch_hits"].values()):
        raise ValueError("Invalid branch outcome counts")
    counts = cfg.get("expected_counts", {})
    if set(counts) != {"loads", "stores", "branches_taken", "branches_not_taken", "jumps"} or any(
            type(n) is not int or n < 0 for n in counts.values()):
        raise ValueError("Invalid program scenario contract")
    if (counts["branches_taken"] != cfg["branch_hits"]["beq_taken"] + cfg["branch_hits"]["bne_taken"] or
            counts["branches_not_taken"] != cfg["branch_hits"]["beq_not_taken"] + cfg["branch_hits"]["bne_not_taken"]):
        raise ValueError("Program branch counts contradict outcome bins")
    if type(cfg.get("uvm_program_id")) is not int or cfg["uvm_program_id"] not in (0, 1, 2, 3) or cfg.get("signature_value") != 1:
        raise ValueError("Unsupported UVM program/signature policy")
    for field in ("require_smoke_coverage", "require_corner_coverage"):
        value = cfg.get(field)
        if value is not None and (type(value) not in (int, float) or not 0 <= value <= 100):
            raise ValueError("Invalid program coverage goal")
    return cfg


def apply_program(processor, name="smoke"):
    program = load_program(name)
    if processor["id"] not in program.get("supported_processors", [processor["id"]]):
        raise ValueError("Program is unsupported on this processor adapter")
    result = dict(processor, program_profile=name, program_contract=program)
    for field in ("entry_pc", "terminal_pc", "signature_address", "signature_value", "expected_retirements"):
        result[field] = program[field]
    if "program_isa" in program:
        result["program_isa"] = program["program_isa"]
    return result


def load_processor(name, *, require_implemented=True):
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ValueError("Invalid processor configuration identifier")
    path = ROOT / "config/processors" / (name + ".json")
    if not path.is_file():
        raise ValueError(f"Unknown processor configuration: {name}")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("schema_version") != 1 or cfg.get("id") != name:
        raise ValueError("Unsupported processor configuration schema/identity")
    if cfg.get("hart_count") != 1 or cfg.get("xlen") != 32:
        raise ValueError("Current adapters support one RV32 hart only")
    if cfg.get("program_isa") != "rv32i":
        raise ValueError("Current shared smoke image supports RV32I only")
    if require_implemented and cfg.get("status") != "implemented":
        raise ValueError(f"Processor {name} is {cfg.get('status')}; its adapter is not executable")
    return cfg


def load_regression(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported regression schema")
    processors, seeds = data.get("processors"), data.get("seeds")
    if not isinstance(processors, list) or not processors or len(set(processors)) != len(processors):
        raise ValueError("Regression requires unique processor identifiers")
    for name in processors:
        load_processor(name)
    if not isinstance(seeds, list) or not seeds or any(type(s) is not int or not 0 < s <= 0xffffffff for s in seeds):
        raise ValueError("Regression requires unsigned, nonzero 32-bit seeds")
    if len(set(seeds)) != len(seeds):
        raise ValueError("Duplicate seeds would inflate regression counts")
    if data.get("uvm_mode") not in ("seeded", "full"):
        raise ValueError("uvm_mode must be seeded or full")
    if type(data.get("jobs")) is not int or not 1 <= data["jobs"] <= 8:
        raise ValueError("jobs must be in 1..8")
    if type(data.get("include_cocotb")) is not bool:
        raise ValueError("include_cocotb must be a Boolean")
    if type(data.setdefault("include_spike", False)) is not bool:
        raise ValueError("include_spike must be a Boolean")
    programs = data.setdefault("programs", ["smoke"])
    if not isinstance(programs, list) or not programs or len(set(programs)) != len(programs):
        raise ValueError("Regression requires unique program identifiers")
    for name in programs:
        program = load_program(name)
        if program.get("requires_full") and data["uvm_mode"] != "full":
            raise ValueError("Random instruction generation requires full SV constrained-random mode")
    return data
