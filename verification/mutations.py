"""Isolated, pinned RTL transformations and conservative outcome qualification."""
import difflib
import hashlib
import json
from pathlib import Path
import re

from verification.config import ROOT

DEFINITIONS = {
    "add_flip_bit0": {"file": "rtl/ibex_alu.sv", "old": "      ALU_ADD,  ALU_SUB,",
        "new": "      ALU_ADD: result_o = adder_result ^ 32'h00000001;\n      ALU_SUB,", "error_id": "RVFI_RD"},
    "beq_inverted": {"file": "rtl/ibex_alu.sv", "old": "ALU_EQ:             cmp_result =  is_equal;",
        "new": "ALU_EQ:             cmp_result = ~is_equal;", "error_id": "RVFI_PC"},
    "sll_flip_bit0": {"file": "rtl/ibex_alu.sv", "old": "      ALU_SLL,  ALU_SRL,",
        "new": "      ALU_SLL: result_o = shift_result ^ 32'h00000001;\n      ALU_SRL,", "error_id": "RVFI_RD"},
    "store_flip_bit0": {"file": "rtl/ibex_load_store_unit.sv", "old": "assign data_wdata_o = data_wdata;",
        "new": "assign data_wdata_o = data_wdata ^ 32'h00000001;", "error_id": "MEM_STORE_DATA", "bus_mutation": True},
    "pico_add_flip_bit0": {"implementation": "picorv32", "file": "picorv32.v",
        "old": "alu_out = alu_add_sub;", "new": "alu_out = instr_add ? (alu_add_sub ^ 32'h00000001) : alu_add_sub;", "error_id": "RVFI_RD"},
    "pico_beq_inverted": {"implementation": "picorv32", "file": "picorv32.v",
        "old": "alu_out_0 = alu_eq;", "new": "alu_out_0 = !alu_eq;", "error_id": "RVFI_PC"},
    "pico_sll_flip_bit0": {"implementation": "picorv32", "file": "picorv32.v",
        "old": "reg_out <= reg_op1;", "new": "reg_out <= (instr_slli || instr_sll) ? (reg_op1 ^ 32'h00000001) : reg_op1;", "error_id": "RVFI_RD"},
    "pico_store_flip_bit0": {"implementation": "picorv32", "file": "picorv32.v",
        "old": "mem_la_wdata = reg_op2;", "new": "mem_la_wdata = reg_op2 ^ 32'h00000001;", "error_id": "MEM_STORE_DATA", "bus_mutation": True},
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def transform(original, definition):
    old, new = definition["old"].encode(), definition["new"].encode()
    if original.count(old) != 1:
        raise ValueError("Mutation anchor is missing or ambiguous")
    return original.replace(old, new, 1)


def checked_folder(path):
    path = Path(path).resolve()
    if not path.is_relative_to((ROOT / "build").resolve()):
        raise ValueError("Mutant artifacts must stay inside the project build folder")
    return path


def prepare_mutant(identity, folder):
    if identity not in DEFINITIONS:
        raise ValueError("Unknown RTL mutation")
    folder = checked_folder(folder)
    folder.mkdir(parents=True, exist_ok=False)
    definition = DEFINITIONS[identity]
    implementation = definition.get("implementation", "ibex")
    original = (ROOT / "vendor" / implementation / definition["file"]).read_bytes()
    lock = json.loads((ROOT / "vendor" / (implementation + ".lock.json")).read_text(encoding="utf-8-sig"))
    if digest(original) != lock["sha256"][definition["file"]]:
        raise ValueError("Original vendor source hash differs from lock")
    mutated = transform(original, definition)
    (folder / "original.sv").write_bytes(original)
    (folder / "mutated.sv").write_bytes(mutated)
    patch = "".join(difflib.unified_diff(original.decode().splitlines(True), mutated.decode().splitlines(True),
        fromfile="vendor/" + implementation + "/" + definition["file"], tofile="isolated/" + definition["file"]))
    (folder / "mutation.patch").write_text(patch, encoding="utf-8")
    manifest = {"schema_version": 1, "id": identity, "definition": definition,
        "original_sha256": digest(original), "mutated_sha256": digest(mutated),
        "implementation": implementation,
        "relative_source": "vendor/" + implementation + "/" + definition["file"], "isolated_source": str(folder / "mutated.sv")}
    path = folder / "mutation.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    verify_mutant(path)
    return path


def verify_mutant(path):
    path = checked_folder(path)
    manifest = json.loads(path.read_text())
    definition = DEFINITIONS.get(manifest.get("id"))
    if manifest.get("schema_version") != 1 or not definition or manifest.get("definition") != definition:
        raise ValueError("Unsupported mutation identity/definition")
    implementation = definition.get("implementation", "ibex")
    if manifest.get("implementation") != implementation:
        raise ValueError("Mutation CPU identity mismatch")
    source = ROOT / "vendor" / implementation / definition["file"]
    original = source.read_bytes()
    lock = json.loads((ROOT / "vendor" / (implementation + ".lock.json")).read_text(encoding="utf-8-sig"))
    if digest(original) != lock["sha256"][definition["file"]] or digest(original) != manifest["original_sha256"]:
        raise ValueError("Pinned original source changed")
    isolated = Path(manifest["isolated_source"]).resolve()
    if isolated != path.parent / "mutated.sv" or manifest["relative_source"] != "vendor/" + implementation + "/" + definition["file"]:
        raise ValueError("Mutation source substitution escaped its isolated folder")
    expected = transform(original, definition)
    if isolated.read_bytes() != expected or digest(expected) != manifest["mutated_sha256"]:
        raise ValueError("Isolated mutant source changed")
    if (path.parent / "original.sv").read_bytes() != original:
        raise ValueError("Saved original differs from pinned RTL")
    return manifest


def classify_observation(raw, expected_error, expected_fields):
    if not raw.get("mutation_integrity_verified"):
        return "infrastructure_failed"
    error = raw.get("error", "").lower()
    if any(word in error for word in ("license", "timed out", "not found", "access denied")):
        return "infrastructure_failed"
    if not raw.get("compiled") or not raw.get("elaborated"):
        return "compile_invalid" if any(w in error for w in ("vrfc", "syntax", "elaboration failed")) else "infrastructure_failed"
    obs = raw.get("mutation_observation", {})
    if not obs.get("simulated") or obs.get("simulator_errors") or obs.get("returncode") != 0:
        return "infrastructure_failed"
    counts, text = obs.get("uvm_counts", {}), obs.get("transcript", "")
    if "[CORRUPTION_INJECTED]" in text or "[WATCHDOG]" in text:
        return "infrastructure_failed"
    ids = re.findall(r"(?m)^UVM_ERROR\s+[^\r\n]*?\[([^\]]+)\]", text)
    if (ids and ids[0] == expected_error and len(ids) == counts.get("UVM_ERROR") and
            counts.get("UVM_FATAL") == 0 and not obs.get("pass_fields")):
        return "killed"
    if counts.get("UVM_ERROR") == counts.get("UVM_FATAL") == 0 and all(
            (obs.get("pass_fields") or {}).get(k) == v for k, v in expected_fields.items()):
        return "survived"
    return "unqualified_detection"
