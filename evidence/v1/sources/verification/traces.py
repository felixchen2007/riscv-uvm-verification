"""Common RV32 retirement contract; adapters must preserve architectural meaning."""
import csv
import hashlib
import json
from pathlib import Path
import re


def _integer(value, name, maximum=0xffffffff):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"Invalid {name}: expected unsigned integer <= {maximum}")
    return value


def validate_trace(trace):
    if trace.get("schema_version") != 1 or trace.get("producer") not in ("dut", "spike"):
        raise ValueError("Unsupported trace schema/producer")
    if trace.get("complete") is not True:
        raise ValueError("Incomplete traces cannot be accepted")
    if trace.get("isa") != "rv32i":
        raise ValueError("Initial trace contract supports the RV32I program subset")
    if "program_profile" in trace and (not isinstance(trace["program_profile"], str) or
            not re.fullmatch(r"[a-z][a-z0-9_]*", trace["program_profile"])):
        raise ValueError("Invalid trace program_profile")
    digest = trace.get("program_sha256", "")
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Missing/invalid program image hash")
    rows = trace.get("records")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Empty retirement trace")
    for index, row in enumerate(rows):
        if row.get("order") != index or type(row.get("order")) is not int:
            raise ValueError("Missing, duplicate or reordered retirement")
        if row.get("hart") != 0 or type(row.get("hart")) is not int:
            raise ValueError("Current trace adapters support one hart")
        for name in ("pc", "insn", "rd_data"):
            _integer(row.get(name), name)
        if row["pc"] & 3 or row["insn"] & 3 != 3:
            raise ValueError("Initial program trace requires aligned 32-bit instructions")
        _integer(row.get("rd_address"), "rd_address", 31)
        if row["rd_address"] == 0 and row["rd_data"] != 0:
            raise ValueError("Canonical x0/no-write result must be zero")
        for name in ("trap", "halt", "interrupt"):
            if type(row.get(name)) is not bool:
                raise ValueError(f"Missing architectural {name} observation")
        memory = row.get("memory")
        opcode = row["insn"] & 0x7f
        if opcode in (3, 0x23):
            if not isinstance(memory, dict) or memory.get("kind") != ("load" if opcode == 3 else "store"):
                raise ValueError("Memory instruction lacks its architectural effect")
            _integer(memory.get("address"), "memory address")
            _integer(memory.get("data"), "memory data")
            if _integer(memory.get("mask"), "memory mask", 15) == 0:
                raise ValueError("Memory access has empty mask")
        elif memory is not None:
            raise ValueError("Non-memory instruction contains stale memory fields")
    return trace


def normalize_rvfi_csv(csv_path, program_path, config, *, allow_prefix=False):
    if config.get("retirement_adapter") not in ("ibex_rvfi_csv", "picorv32_rvfi_csv"):
        raise ValueError("No executable retirement adapter for this processor")
    records = []
    required = {"order", "pc", "insn", "rd", "rd_data", "mem_addr", "mem_rmask", "mem_wmask",
                "mem_rdata", "mem_wdata", "trap", "halt", "intr"}
    with Path(csv_path).open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Raw RVFI trace lacks fields; do not infer missing architectural state")
        for raw in reader:
            try:
                insn, rd = int(raw["insn"], 16), int(raw["rd"])
                native = int(raw["order"])
                flags = [int(raw[k]) for k in ("trap", "halt", "intr")]
                if any(v not in (0, 1) for v in flags):
                    raise ValueError("Unknown/non-Boolean retirement flags")
                memory = None
                if insn & 0x7f in (3, 0x23):
                    load = (insn & 0x7f) == 3
                    memory = {"kind": "load" if load else "store", "address": int(raw["mem_addr"], 16),
                              "mask": int(raw["mem_rmask" if load else "mem_wmask"], 16),
                              "data": int(raw["mem_rdata" if load else "mem_wdata"], 16)}
                records.append({"order": native - config["native_order_base"], "native_order": native,
                                "hart": 0, "pc": int(raw["pc"], 16), "insn": insn,
                                "rd_address": rd, "rd_data": int(raw["rd_data"], 16) if rd else 0,
                                "trap": bool(flags[0]), "halt": bool(flags[1]), "interrupt": bool(flags[2]),
                                "memory": memory})
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid/unknown raw RVFI field at record {len(records)}: {exc}") from exc
    if allow_prefix:
        if not records or len(records) > config["expected_retirements"] or records[0]["pc"] != config["entry_pc"]:
            raise ValueError("Invalid bounded retirement prefix")
    elif len(records) != config["expected_retirements"] or records[0]["pc"] != config["entry_pc"]:
        raise ValueError("Trace length/entry does not match the requested smoke configuration")
    if not allow_prefix and "terminal_pc" in config and records[-1]["pc"] != config["terminal_pc"]:
        raise ValueError("Trace terminal PC does not match the program contract")
    last_memory = records[-1]["memory"]
    if not allow_prefix and last_memory != {"kind": "store", "address": config["signature_address"], "mask": 15,
                       "data": config["signature_value"]}:
        raise ValueError("Trace lacks the checked terminal store")
    trace = {"schema_version": 1, "processor_config": config["id"], "producer": "dut",
             "program_profile": config.get("program_profile", "smoke"),
             "isa": config["program_isa"], "complete": True,
             "program_sha256": hashlib.sha256(Path(program_path).read_bytes()).hexdigest(),
             "records": records}
    validate_trace(trace)
    if allow_prefix:
        trace["complete"] = False
    return trace


def normalize_ibex_csv(csv_path, program_path, config):
    """Compatibility entry point for existing Ibex integrations."""
    if config.get("retirement_adapter") != "ibex_rvfi_csv":
        raise ValueError("Use the processor-neutral normalizer for other adapters")
    return normalize_rvfi_csv(csv_path, program_path, config)


def compare_traces(actual, reference):
    """Strict common comparator; using it is not evidence that Spike has run."""
    validate_trace(actual)
    validate_trace(reference)
    if actual.get("program_profile", "smoke") != reference.get("program_profile", "smoke"):
        raise ValueError("Reference and DUT differ in program_profile")
    for field in ("isa", "program_sha256"):
        if actual[field] != reference[field]:
            raise ValueError(f"Reference and DUT differ in {field}")
    if len(actual["records"]) != len(reference["records"]):
        raise ValueError("Reference and DUT retirement counts differ")
    fields = ("order", "hart", "pc", "insn", "rd_address", "rd_data", "trap", "halt", "interrupt", "memory")
    for index, (observed, expected) in enumerate(zip(actual["records"], reference["records"])):
        for field in fields:
            if observed[field] != expected[field]:
                raise ValueError(f"Architectural mismatch at record {index}: {field}: {observed[field]} != {expected[field]}")
    return {"status": "match", "retirements_compared": len(actual["records"])}


def write_trace(path, trace):
    validate_trace(trace)
    Path(path).write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")


def branch_outcomes(trace, expected=None):
    """Observe branch direction from successive PCs, separate from ISA prediction."""
    validate_trace(trace)
    hits = dict.fromkeys(("beq_taken", "beq_not_taken", "bne_taken", "bne_not_taken"), 0)
    rows = trace["records"]
    for index, row in enumerate(rows):
        insn, pc = row["insn"], row["pc"]
        if insn & 127 != 0x63:
            continue
        funct3 = (insn >> 12) & 7
        if funct3 not in (0, 1) or index + 1 == len(rows):
            raise ValueError("Unsupported/incomplete branch observation")
        imm = ((insn >> 31) << 12) | (((insn >> 7) & 1) << 11) | (((insn >> 25) & 63) << 5) | (((insn >> 8) & 15) << 1)
        if imm & 4096:
            imm -= 8192
        target, fallthrough = (pc + imm) & 0xffffffff, (pc + 4) & 0xffffffff
        following = rows[index + 1]["pc"]
        if target == fallthrough or following not in (target, fallthrough):
            raise ValueError("Ambiguous/invalid branch successor PC")
        key = ("beq" if funct3 == 0 else "bne") + ("_taken" if following == target else "_not_taken")
        hits[key] += 1
    if expected is not None and hits != expected:
        raise ValueError(f"Branch outcome contract mismatch: {hits} != {expected}")
    return hits


def compare_processor_cases(cases, processors, seeds, programs=None):
    """Cross-DUT comparisons use common architectural fields, not native order."""
    if len(processors) < 2:
        return []
    comparisons = []
    indexed = {}
    for case in cases:
        if case["layer"] != "uvm":
            continue
        key = (case["processor_config"], case["seed"], case.get("program_profile", "smoke"))
        if key in indexed:
            raise ValueError("Duplicate CPU case in cross-processor comparison")
        indexed[key] = case
    for program in programs or ["smoke"]:
        for seed in seeds:
            for processor in processors:
                if indexed.get((processor, seed, program), {}).get("status") != "pass":
                    raise ValueError(f"Missing passing CPU case: {processor} seed={seed} program={program}")
            baseline = indexed[(processors[0], seed, program)]
            for other in processors[1:]:
                candidate = indexed[(other, seed, program)]
                for profile in ("no_added_delay", "stalled"):
                    left = json.loads(Path(baseline["artifacts"][profile + "_trace"]).read_text())
                    right = json.loads(Path(candidate["artifacts"][profile + "_trace"]).read_text())
                    comparison = compare_traces(left, right)
                    comparisons.append({"kind": "cross_processor", "processors": [processors[0], other],
                                        "seed": seed, "profile": profile, "program_profile": program, **comparison})
    return comparisons
