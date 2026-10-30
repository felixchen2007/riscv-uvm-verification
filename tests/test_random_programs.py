"""Synthetic legality/replay controls. These tests never execute a CPU model."""
import copy
import json
import subprocess
import sys

import pytest

from verification.config import ROOT, load_program, load_regression
from verification.programs import validate_random_body, summarize_random_corpora, validate_generation_identity


@pytest.fixture
def body_fixture():
    contract = load_program("random")
    seed = 20261029
    words, items, previous = {}, [], 0
    for index, kind in enumerate([0, 1, 0, 2, 0, 3, 0, 4] * 8):
        rs1, rs2, rd = (6 if kind in (3, 4) else 2), 3, 1
        if kind == 0:
            insn = (rs2 << 20) | (rs1 << 15) | (rd << 7) | 0x33
        elif kind == 1:
            insn = (1 << 20) | (rs1 << 15) | (rd << 7) | 0x13
        elif kind == 2:
            insn = 0x12345000 | (rd << 7) | 0x37
        elif kind == 3:
            insn = (32 << 20) | (6 << 15) | (2 << 12) | (rd << 7) | 3
        else:
            insn = (1 << 25) | (rs2 << 20) | (6 << 15) | (2 << 12) | 0x23
        pc = contract["random_body_start"] + index * 4
        words[pc] = insn
        items.append({"pc": pc, "insn": insn, "kind": kind, "rd": rd,
                      "rs1": rs1, "rs2": rs2, "dependency": 0, "previous_rd": previous})
        previous = rd if kind != 4 else 0
    manifest = {"schema_version": 1, "program_profile": "random", "seed": seed,
        "instruction_calls": 64, "schedule_calls": 8, "body_start": 316, "body_end": 572, "items": items}
    return words, manifest, contract, seed


def test_legality_audit_counts_classes_without_predicting_results(body_fixture):
    result = validate_random_body(*body_fixture)
    assert result["status"] == "legal" and result["random_instructions"] == 64
    assert result["kind_counts"] == {0: 32, 1: 8, 2: 8, 3: 8, 4: 8}
    assert result["scratch_word_slots"] == [8]
    assert "no architectural results" in result["scope"]


@pytest.mark.parametrize("defect", ["opcode", "reserved_rd", "memory_signature", "misaligned", "wrong_base",
    "wrong_manifest", "missing", "pc_order", "class_quota", "previous_rd", "dependency", "noninteger", "calls", "seed"])
def test_illegal_or_misreported_generated_body_is_rejected(body_fixture, defect):
    words, manifest, contract, seed = body_fixture
    row = manifest["items"][0]
    target = 0
    if defect == "opcode":
        row["insn"] = 0x73
    elif defect == "reserved_rd":
        row["insn"] = (row["insn"] & ~(31 << 7)) | (6 << 7)
        row["rd"] = 6
    elif defect in ("memory_signature", "misaligned", "wrong_base"):
        target = 5
        row = manifest["items"][target]
        offset = 4 if defect == "memory_signature" else 34 if defect == "misaligned" else 32
        base = 5 if defect == "wrong_base" else 6
        row["insn"] = (offset << 20) | (base << 15) | (2 << 12) | (1 << 7) | 3
        row["rs1"] = base
    elif defect == "wrong_manifest":
        row["insn"] ^= 1 << 20
    elif defect == "missing":
        manifest["items"].pop()
    elif defect == "pc_order":
        row["pc"] += 4
    elif defect == "class_quota":
        row["kind"] = 1
        row["insn"] = (1 << 20) | (2 << 15) | (1 << 7) | 0x13
    elif defect == "previous_rd":
        row["previous_rd"] = 1
    elif defect == "dependency":
        row["dependency"] = 1
    elif defect == "noninteger":
        row["rd"] = True
    elif defect == "calls":
        manifest["instruction_calls"] = 63
    elif defect == "seed":
        manifest["seed"] += 1
    if defect != "wrong_manifest":
        words[contract["random_body_start"] + target * 4] = row["insn"]
    with pytest.raises(ValueError):
        validate_random_body(words, manifest, contract, seed)


def test_random_profile_cannot_silently_use_procedural_mode(tmp_path):
    matrix = json.loads((ROOT / "config/regressions/random.json").read_text())
    matrix["uvm_mode"] = "seeded"
    path = tmp_path / "seeded.json"
    path.write_text(json.dumps(matrix))
    with pytest.raises(ValueError, match="requires full"):
        load_regression(path)
    proc = subprocess.run([sys.executable, str(ROOT / "scripts/run_uvm_tests.py"), "--program", "random"],
                          capture_output=True, text=True, timeout=15)
    assert proc.returncode == 2 and "no procedural fallback" in proc.stderr


def test_directed_generation_metadata_has_exact_identity_and_zero_calls():
    data = {"schema_version": 1, "program_profile": "smoke", "seed": 1,
            "instruction_calls": 0, "schedule_calls": 0, "items": []}
    assert validate_generation_identity(data, "smoke", 1)["instruction_calls"] == 0


@pytest.mark.parametrize("defect", ["padded_profile", "bool_seed", "calls", "items"])
def test_generation_metadata_format_or_execution_mismatch_is_rejected(defect):
    data = {"schema_version": 1, "program_profile": "smoke", "seed": 1,
            "instruction_calls": 0, "schedule_calls": 0, "items": []}
    if defect == "padded_profile":
        data["program_profile"] = "  smoke"
    elif defect == "bool_seed":
        data["seed"] = True
    elif defect == "calls":
        data["instruction_calls"] = 64
    else:
        data["items"] = [{}]
    with pytest.raises(ValueError):
        validate_generation_identity(data, "smoke", 1)


def corpus_case(seed=1):
    audit = {"body_sha256": "a" * 64, "image_sha256": "b" * 64, "kind_counts": {"0": 32}, "alu_counts": {"add": 32}}
    return {"program_profile": "random", "layer": "uvm", "status": "pass", "seed": seed,
        "sv_instruction_randomization_executed": True,
        "profiles": {name: {"random_input_audit": copy.deepcopy(audit)} for name in ("no_added_delay", "stalled")}}


def test_corpus_replay_accepts_same_seed_across_cases_and_timing():
    assert len(summarize_random_corpora([corpus_case(), corpus_case()])) == 1


@pytest.mark.parametrize("defect", ["timing_replay", "core_replay", "seed_diversity", "not_executed"])
def test_replay_or_diversity_failures_cannot_pass(defect):
    cases = [corpus_case(), corpus_case()]
    if defect == "timing_replay":
        cases[1]["profiles"]["stalled"]["random_input_audit"]["body_sha256"] = "c" * 64
    elif defect == "core_replay":
        for profile in cases[1]["profiles"].values():
            profile["random_input_audit"]["image_sha256"] = "c" * 64
    elif defect == "seed_diversity":
        cases[1]["seed"] = 2  # Same body, even if a prologue operand had changed.
    else:
        cases[1]["sv_instruction_randomization_executed"] = False
    with pytest.raises(ValueError):
        summarize_random_corpora(cases)
