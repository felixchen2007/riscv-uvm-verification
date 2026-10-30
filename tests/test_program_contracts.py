"""Synthetic program/branch contract tests, separate from real UVM/ISS evidence."""
import copy
import json

import pytest

from verification.config import ROOT, apply_program, load_processor, load_program, load_regression
from verification.reference.spike import parse_spike_records
from verification.traces import branch_outcomes, compare_processor_cases, compare_traces, validate_trace


def test_program_contracts_preserve_cpu_configuration_and_distinct_windows():
    cpu = load_processor("ibex_smoke")
    original = copy.deepcopy(cpu)
    corners = apply_program(cpu, "corners")
    assert cpu == original
    assert corners["expected_retirements"] == 47 and corners["terminal_pc"] == 0x13c
    assert corners["retirement_adapter"] == cpu["retirement_adapter"]
    assert apply_program(cpu)["expected_retirements"] == 14
    assert load_program("corners")["branch_hits"] == {
        "beq_taken": 1, "beq_not_taken": 1, "bne_taken": 2, "bne_not_taken": 2}


@pytest.mark.parametrize("name", ["../smoke", "smoke.json", "missing", True, ""])
def test_invalid_program_identifier_cannot_run(name):
    with pytest.raises(ValueError):
        load_program(name)


@pytest.mark.parametrize("programs", [[], ["smoke", "smoke"], ["missing"], "corners"])
def test_invalid_program_matrix_is_rejected(tmp_path, programs):
    data = json.loads((ROOT / "config/regressions/corners.json").read_text())
    data["programs"] = programs
    path = tmp_path / "matrix.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_regression(path)


def branch(funct3, offset=8):
    value = offset & 0x1fff
    return (0x63 | (funct3 << 12) | (((value >> 12) & 1) << 31) |
        (((value >> 11) & 1) << 7) | (((value >> 5) & 63) << 25) | (((value >> 1) & 15) << 8))


def trace_from(pairs):
    records = [{"order": i, "hart": 0, "pc": pc, "insn": insn, "rd_address": 0,
        "rd_data": 0, "memory": None, "trap": False, "halt": False, "interrupt": False}
        for i, (pc, insn) in enumerate(pairs)]
    return {"schema_version": 1, "processor_config": "ibex_smoke", "producer": "dut",
        "isa": "rv32i", "complete": True, "program_sha256": "a" * 64, "records": records}


def four_way_trace():
    return trace_from([(0x80, branch(0)), (0x88, branch(1)), (0x8c, branch(0)),
                       (0x90, branch(1)), (0x98, 0x13)])


def test_branch_observations_use_actual_successor_pcs():
    assert branch_outcomes(four_way_trace()) == dict.fromkeys(
        ("beq_taken", "beq_not_taken", "bne_taken", "bne_not_taken"), 1)


def test_backward_loop_records_both_directions():
    trace = trace_from([(0x80, 0x13), (0x84, branch(1, -4)), (0x80, 0x13),
                        (0x84, branch(1, -4)), (0x88, 0x13)])
    assert branch_outcomes(trace) == {"beq_taken": 0, "beq_not_taken": 0, "bne_taken": 1, "bne_not_taken": 1}


@pytest.mark.parametrize("defect", ["successor", "missing_successor", "ambiguous", "required_bin"])
def test_branch_holes_and_invalid_paths_fail(defect):
    trace = four_way_trace()
    expected = None
    if defect == "successor":
        trace["records"][1]["pc"] = 0x9c
    elif defect == "missing_successor":
        trace["records"] = trace["records"][:1]
    elif defect == "ambiguous":
        trace["records"][0]["insn"] = branch(0, 4)
    else:
        expected = load_program("corners")["branch_hits"]
    with pytest.raises(ValueError):
        branch_outcomes(trace, expected)


def test_program_identity_cannot_be_substituted():
    actual, reference = four_way_trace(), four_way_trace()
    reference["program_profile"] = "corners"
    with pytest.raises(ValueError, match="program_profile"):
        compare_traces(actual, reference)


@pytest.mark.parametrize("identity", [None, True, "../corners"])
def test_invalid_trace_program_identity_is_rejected(identity):
    trace = four_way_trace()
    trace["program_profile"] = identity
    with pytest.raises(ValueError, match="program_profile"):
        validate_trace(trace)


def test_cross_processor_matrix_keeps_programs_distinct(tmp_path):
    cases = []
    for program in ("smoke", "corners"):
        for processor in ("ibex_smoke", "picorv32_rv32i"):
            trace = four_way_trace()
            trace["program_profile"] = program
            path = tmp_path / f"{program}-{processor}.json"
            path.write_text(json.dumps(trace))
            cases.append({"layer": "uvm", "status": "pass", "seed": 1, "program_profile": program,
                "processor_config": processor, "artifacts": {"no_added_delay_trace": str(path), "stalled_trace": str(path)}})
    assert len(compare_processor_cases(cases, ["ibex_smoke", "picorv32_rv32i"], [1], ["smoke", "corners"])) == 4
    with pytest.raises(ValueError, match="Missing passing CPU"):
        compare_processor_cases(cases[:-1], ["ibex_smoke", "picorv32_rv32i"], [1], ["smoke", "corners"])


def test_reference_terminal_pc_is_checked(tmp_path):
    image = tmp_path / "synthetic.hex"
    image.write_text("@20 00132223\n")
    cfg = dict(load_processor("ibex_smoke"), expected_retirements=1, terminal_pc=0x84)
    trace = trace_from([(0x80, 0x00132223)])
    trace["records"][0]["memory"] = {"kind": "store", "address": 4100, "mask": 15, "data": 1}
    with pytest.raises(ValueError, match="terminal PC"):
        parse_spike_records(json.dumps(trace["records"][0]), image, cfg)
