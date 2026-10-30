"""Synthetic qualification of mutation isolation/classification; no RTL kills claimed."""
import copy
import json
from pathlib import Path
import sys

import pytest

from verification.config import ROOT
from verification.mutations import DEFINITIONS, prepare_mutant, verify_mutant, transform, classify_observation, checked_folder
from verification.traces import compare_traces

sys.path.insert(0, str(ROOT / "scripts"))
from run_mutation_tests import compare_retirement_prefix


@pytest.mark.parametrize("identity", list(DEFINITIONS))
def test_each_mutant_changes_only_an_owned_copy(tmp_path, identity):
    definition = DEFINITIONS[identity]
    original_path = ROOT / "vendor" / definition.get("implementation", "ibex") / definition["file"]
    before = original_path.read_bytes()
    path = prepare_mutant(identity, tmp_path / identity)
    manifest = verify_mutant(path)
    assert original_path.read_bytes() == before
    assert Path(manifest["isolated_source"]).read_bytes() == transform(before, definition)
    assert manifest["original_sha256"] != manifest["mutated_sha256"]
    assert (path.parent / "mutation.patch").read_text().startswith("--- vendor/")


@pytest.mark.parametrize("bad", [b"missing", b"anchor anchor"])
def test_missing_or_ambiguous_anchor_fails(bad):
    with pytest.raises(ValueError, match="anchor"):
        transform(bad, {"old": "anchor", "new": "changed"})


def test_outside_workspace_mutation_is_rejected():
    with pytest.raises(ValueError):
        checked_folder(ROOT.parent / "outside-mutant")


@pytest.mark.parametrize("defect", ["mutant_bytes", "saved_original", "definition", "escape"])
def test_mutation_tampering_cannot_pass(tmp_path, defect):
    path = prepare_mutant("beq_inverted", tmp_path / defect)
    manifest = json.loads(path.read_text())
    if defect == "mutant_bytes":
        Path(manifest["isolated_source"]).write_text("changed")
    elif defect == "saved_original":
        (path.parent / "original.sv").write_text("changed")
    elif defect == "definition":
        manifest["definition"]["error_id"] = "anything"
    else:
        manifest["isolated_source"] = str(ROOT / "vendor/ibex/rtl/ibex_alu.sv")
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        verify_mutant(path)


def observed():
    return {"compiled": True, "elaborated": True, "mutation_integrity_verified": True,
        "mutation_observation": {"simulated": True, "returncode": 0, "simulator_errors": False,
            "uvm_counts": {"UVM_ERROR": 1, "UVM_FATAL": 0}, "pass_fields": None,
            "transcript": "UVM_ERROR file.sv(10) @ 100: uvm_test_top.env [RVFI_RD] incorrect result\nUVM_ERROR : 1\n"}}


def test_only_intended_executed_diagnostic_qualifies_as_kill():
    assert classify_observation(observed(), "RVFI_RD", {"retired": 47}) == "killed"


def test_intended_first_error_allows_fully_recorded_cascades():
    raw = observed()
    raw["mutation_observation"]["uvm_counts"]["UVM_ERROR"] = 3
    raw["mutation_observation"]["transcript"] += (
        "UVM_ERROR file.sv(11) @ 110: env [RVFI_RS1] bad source\n"
        "UVM_ERROR file.sv(12) @ 120: env [RVFI_RD] propagated result\n")
    assert classify_observation(raw, "RVFI_RD", {"retired": 47}) == "killed"
    raw["mutation_observation"]["uvm_counts"]["UVM_ERROR"] = 4
    assert classify_observation(raw, "RVFI_RD", {"retired": 47}) == "unqualified_detection"


@pytest.mark.parametrize(("defect", "expected"), [
    ("compile", "compile_invalid"), ("license", "infrastructure_failed"), ("timeout", "infrastructure_failed"),
    ("wrong_checker", "unqualified_detection"), ("fatal", "unqualified_detection"),
    ("observation_flip", "infrastructure_failed"), ("source_drift", "infrastructure_failed"),
    ("no_execution", "infrastructure_failed"), ("no_marker", "unqualified_detection"),
    ("survived", "survived")])
def test_mutation_taxonomy_rejects_false_kills(defect, expected):
    raw = observed()
    obs = raw["mutation_observation"]
    if defect == "compile":
        raw.update(compiled=False, error="XSim compilation failed VRFC syntax error")
    elif defect == "license":
        raw.update(compiled=False, error="License checkout failed")
    elif defect == "timeout":
        raw["error"] = "xelab timed out"
    elif defect == "wrong_checker":
        obs["transcript"] = obs["transcript"].replace("RVFI_RD", "OTHER")
    elif defect == "fatal":
        obs["uvm_counts"]["UVM_FATAL"] = 1
    elif defect == "observation_flip":
        obs["transcript"] += "[CORRUPTION_INJECTED]"
    elif defect == "source_drift":
        raw["mutation_integrity_verified"] = False
    elif defect == "no_execution":
        obs["simulated"] = False
    else:
        obs["uvm_counts"]["UVM_ERROR"] = 0
        obs["transcript"] = ""
        if defect == "survived":
            obs["pass_fields"] = {"retired": 47}
    assert classify_observation(raw, "RVFI_RD", {"retired": 47}) == expected


def fixture_trace():
    return {"schema_version": 1, "producer": "spike", "processor_config": "ibex_smoke", "isa": "rv32i",
        "program_profile": "corners", "program_sha256": "a" * 64, "complete": True,
        "records": [{"order": 0, "hart": 0, "pc": 128, "insn": 0x00100093, "rd_address": 1,
            "rd_data": 1, "memory": None, "trap": False, "halt": False, "interrupt": False}]}


def test_prefix_match_never_becomes_a_complete_pass():
    reference = fixture_trace()
    prefix = copy.deepcopy(reference)
    prefix.update(producer="dut", complete=False)
    assert compare_retirement_prefix(prefix, reference)["status"] == "prefix_match"
    assert prefix["complete"] is False
    with pytest.raises(ValueError, match="Incomplete"):
        compare_traces(prefix, reference)
    prefix["records"][0]["rd_data"] ^= 1
    assert compare_retirement_prefix(prefix, reference)["status"] == "architectural_mismatch"
