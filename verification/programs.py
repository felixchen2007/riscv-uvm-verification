"""Audit generated input legality, never predict instruction results or DUT state."""
from collections import Counter
import hashlib
import json
from pathlib import Path

from verification.reference.spike import read_program_image

ALU_KEYS = {0: "add", 256: "sub", 1: "sll", 2: "slt", 3: "sltu",
            4: "xor", 5: "srl", 261: "sra", 6: "or", 7: "and"}


def validate_generation_identity(manifest, program, seed):
    calls, schedules = (64, 8) if program == "random" else (0, 0)
    expected = {"schema_version": 1, "program_profile": program, "seed": seed,
                "instruction_calls": calls, "schedule_calls": schedules}
    if not isinstance(manifest, dict) or any(type(manifest.get(k)) is not type(v) or manifest[k] != v
                                             for k, v in expected.items()):
        raise ValueError("Generation metadata identity/count mismatch")
    if not isinstance(manifest.get("items"), list) or len(manifest["items"]) != calls:
        raise ValueError("Generation metadata item count mismatch")
    return expected


def validate_random_body(words, manifest, contract, seed):
    validate_generation_identity(manifest, "random", seed)
    start, end = contract["random_body_start"], contract["random_body_end"]
    if (manifest.get("schema_version") != 1 or manifest.get("program_profile") != "random" or
            manifest.get("seed") != seed or manifest.get("instruction_calls") != 64 or
            manifest.get("schedule_calls") != 8 or manifest.get("body_start") != start or
            manifest.get("body_end") != end):
        raise ValueError("Random generation manifest identity/count mismatch")
    items = manifest.get("items")
    if not isinstance(items, list) or len(items) != 64 or end - start != 64 * 4:
        raise ValueError("Incomplete bounded random instruction body")
    kinds, alus, registers, slots = Counter(), Counter(), set(), set()
    previous_rd, forced_dependencies = 0, 0
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError("Invalid random instruction manifest item")
        if any(type(item.get(field)) is not int for field in
               ("pc", "insn", "kind", "rd", "rs1", "rs2", "dependency", "previous_rd")):
            raise ValueError("Missing/noninteger random generation field")
        pc = start + index * 4
        if item.get("pc") != pc or pc not in words:
            raise ValueError("Missing/reordered random body instruction")
        insn = words[pc]
        opcode, rd, rs1, rs2 = insn & 127, (insn >> 7) & 31, (insn >> 15) & 31, (insn >> 20) & 31
        funct3, key = (insn >> 12) & 7, ((insn >> 25) << 3) | ((insn >> 12) & 7)
        if insn & 3 != 3 or opcode not in (0x33, 0x13, 0x37, 3, 0x23):
            raise ValueError("Instruction outside legal random body scope")
        kind = {0x33: 0, 0x13: 1, 0x37: 2, 3: 3, 0x23: 4}[opcode]
        if item.get("insn") != insn or item.get("kind") != kind or item.get("previous_rd") != previous_rd:
            raise ValueError("Emitted instruction differs from generation manifest")
        if kind != 4 and (rd in (6, 27) or item.get("rd") != rd):
            raise ValueError("Random instruction clobbers a reserved register or misreports destination")
        if kind == 0:
            if key not in ALU_KEYS or item.get("rs1") != rs1 or item.get("rs2") != rs2:
                raise ValueError("Unsupported/misreported random register ALU")
            alus[ALU_KEYS[key]] += 1
        elif kind == 1:
            if funct3 != 0 or item.get("rs1") != rs1:
                raise ValueError("Random immediate instruction must be ADDI")
        elif kind in (3, 4):
            offset = (insn >> 20) if kind == 3 else (((insn >> 25) << 5) | ((insn >> 7) & 31))
            if funct3 != 2 or rs1 != 6 or item["rs1"] != 6 or offset not in range(32, 64, 4):
                raise ValueError("Random memory instruction escaped aligned scratch RAM")
            if kind == 4 and item.get("rs2") != rs2:
                raise ValueError("Misreported random store source")
            slots.add(offset // 4)
        dependency = item.get("dependency")
        if type(dependency) is not int or dependency not in (0, 1, 2):
            raise ValueError("Invalid constrained dependency mode")
        if dependency:
            if previous_rd == 0 or kind not in (0, 1) or (dependency == 2 and kind != 0):
                raise ValueError("Illegal forced dependency mode")
            if (rs1 if dependency == 1 else rs2) != previous_rd:
                raise ValueError("Requested random dependency was not encoded")
            forced_dependencies += 1
        kinds[kind] += 1
        registers.update((rd,) if kind != 4 else ())
        previous_rd = rd if kind != 4 else 0
        if index % 8 == 7:
            block = Counter(entry["kind"] for entry in items[index - 7:index + 1])
            if block != {0: 4, 1: 1, 2: 1, 3: 1, 4: 1}:
                raise ValueError("Random block violates shuffled instruction-class quota")
    if kinds != {0: 32, 1: 8, 2: 8, 3: 8, 4: 8}:
        raise ValueError("Random body does not satisfy bounded class counts")
    return {"status": "legal", "random_instructions": 64, "kind_counts": dict(kinds),
            "alu_counts": dict(alus), "destination_registers": sorted(registers),
            "scratch_word_slots": sorted(slots), "forced_dependencies": forced_dependencies,
            "scope": "input legality/distribution only; no architectural results predicted"}


def audit_random_program(image_path, manifest_path, contract, seed):
    words = read_program_image(image_path)
    result = validate_random_body(words,
        json.loads(Path(manifest_path).read_text(encoding="utf-8")), contract, seed)
    result["body_sha256"] = hashlib.sha256(b"".join(words[pc].to_bytes(4, "little")
        for pc in range(contract["random_body_start"], contract["random_body_end"], 4))).hexdigest()
    result["image_sha256"] = hashlib.sha256(Path(image_path).read_bytes()).hexdigest()
    result["generation_manifest_sha256"] = hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest()
    return result


def summarize_random_corpora(cases):
    """Require replay across timing/core adapters and real body diversity by seed."""
    seeds = {}
    for case in cases:
        if case.get("program_profile") != "random" or case["layer"] != "uvm":
            continue
        if case["status"] != "pass" or not case.get("sv_instruction_randomization_executed"):
            raise ValueError("Missing executed constrained-random instruction case")
        for profile in case["profiles"].values():
            audit = profile["random_input_audit"]
            identity = {key: audit[key] for key in ("body_sha256", "image_sha256", "kind_counts", "alu_counts")}
            if case["seed"] in seeds and seeds[case["seed"]] != identity:
                raise ValueError("Random program replay differs across timing profiles or processors")
            seeds[case["seed"]] = identity
    if len({s["body_sha256"] for s in seeds.values()}) != len(seeds):
        raise ValueError("Random instruction bodies did not vary across distinct seeds")
    return [{"seed": seed, **identity} for seed, identity in sorted(seeds.items())]
