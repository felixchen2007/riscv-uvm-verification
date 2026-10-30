"""Synthetic format/utility tests; these are not RTL or Spike execution evidence."""
import copy
import csv
import json

import pytest

from verification.config import load_processor, load_regression
from verification.reference.register_file import RegisterFileModel
from verification.results import aggregate, classify_failure
from verification.traces import compare_traces, compare_processor_cases, normalize_ibex_csv, normalize_rvfi_csv, validate_trace


@pytest.fixture
def trace_files(tmp_path):
    cfg = dict(load_processor("ibex_smoke"), expected_retirements=3)
    columns = "order pc insn rd rd_data mem_addr mem_rmask mem_wmask mem_rdata mem_wdata trap halt intr".split()
    # Non-memory RVFI mask/address values can be stale. They must not become
    # fictitious load effects in the common architectural format.
    rows = [dict(zip(columns, row.split())) for row in (
        "1 00000080 00100093 1 00000001 deadbeef f 0 00000000 00000000 0 0 0",
        "2 00000084 00001337 6 00001000 00001000 f 0 00000000 00000000 0 0 0",
        "3 00000088 00132223 0 00000000 00001004 f f 00000000 00000001 0 0 0")]
    path = tmp_path / "synthetic.csv"
    image = tmp_path / "synthetic.hex"
    image.write_text("@20 00100093 00001337 00132223\n")
    def write(data=rows, fields=columns):
        with path.open("w", newline="") as file:
            writer = csv.DictWriter(file, fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(data)
    write()
    return path, image, cfg, rows, write


def test_trace_normalizes_order_and_discards_stale_memory_fields(trace_files):
    path, image, cfg, _, _ = trace_files
    trace = normalize_ibex_csv(path, image, cfg)
    assert [r["order"] for r in trace["records"]] == [0, 1, 2]
    assert [r["native_order"] for r in trace["records"]] == [1, 2, 3]
    assert trace["records"][0]["memory"] is None
    assert trace["records"][-1]["memory"] == {"kind": "store", "address": 4100, "mask": 15, "data": 1}


def test_short_trace_requires_explicit_incomplete_prefix_mode(trace_files):
    path, image, cfg, rows, write = trace_files
    write(rows[:1])
    with pytest.raises(ValueError, match="length/entry"):
        normalize_rvfi_csv(path, image, cfg)
    prefix = normalize_rvfi_csv(path, image, cfg, allow_prefix=True)
    assert prefix["complete"] is False and len(prefix["records"]) == 1
    with pytest.raises(ValueError, match="Incomplete"):
        compare_traces(prefix, prefix)


@pytest.mark.parametrize("change", ["drop", "duplicate", "reorder", "unknown", "missing_flags", "bad_terminal"])
def test_bad_raw_trace_cannot_pass(trace_files, change):
    path, image, cfg, rows, write = trace_files
    if change == "drop":
        rows.pop()
    elif change == "duplicate":
        rows[1]["order"] = "1"
    elif change == "reorder":
        rows[0], rows[1] = rows[1], rows[0]
    elif change == "unknown":
        rows[1]["rd_data"] = "xxxxxxxx"
    elif change == "bad_terminal":
        rows[-1]["mem_wdata"] = "00000002"
    if change == "missing_flags":
        write(rows, [f for f in rows[0] if f != "trap"])
    else:
        write(rows)
    with pytest.raises(ValueError):
        normalize_ibex_csv(path, image, cfg)


@pytest.mark.parametrize("field", ["pc", "insn", "rd_data", "trap", "memory", "length", "program_hash"])
def test_common_comparator_detects_architectural_differences(trace_files, field):
    path, image, cfg, _, _ = trace_files
    actual = normalize_ibex_csv(path, image, cfg)
    reference = copy.deepcopy(actual)
    reference["producer"] = "spike"  # Synthetic reference fixture only.
    if field == "memory":
        reference["records"][-1]["memory"]["data"] ^= 1
    elif field == "length":
        reference["records"].pop()
    elif field == "program_hash":
        reference["program_sha256"] = "a" * 64
    elif field == "trap":
        reference["records"][0]["trap"] = True
    else:
        reference["records"][0][field] ^= 4
    with pytest.raises(ValueError):
        compare_traces(actual, reference)


def test_incomplete_trace_is_rejected(trace_files):
    path, image, cfg, _, _ = trace_files
    trace = normalize_ibex_csv(path, image, cfg)
    trace["complete"] = False
    with pytest.raises(ValueError, match="Incomplete"):
        validate_trace(trace)


def test_component_model_honors_x0_disable_and_reset():
    model = RegisterFileModel(16)
    model.write(0, 99)
    assert model.read(0) == 0
    model.write(3, -1)
    model.write(3, 0, enable=False)
    assert model.read(3) == 0xffffffff
    model.reset()
    assert model.read(3) == 0
    with pytest.raises(ValueError):
        model.read(16)


def test_planned_processor_cannot_execute(tmp_path, monkeypatch):
    import verification.config as module
    planned_config = dict(load_processor("ibex_smoke"), id="future_smoke", status="planned")
    configs = tmp_path / "config/processors"
    configs.mkdir(parents=True)
    (configs / "future_smoke.json").write_text(json.dumps(planned_config))
    monkeypatch.setattr(module, "ROOT", tmp_path)
    planned = load_processor("future_smoke", require_implemented=False)
    assert planned["status"] == "planned"
    with pytest.raises(ValueError, match="not executable"):
        load_processor("future_smoke")


def test_two_implemented_processor_profiles():
    assert load_processor("ibex_smoke")["native_order_base"] == 1
    assert load_processor("picorv32_rv32i")["native_order_base"] == 0


def test_pico_native_zero_origin_maps_to_same_architecture(trace_files):
    path, image, cfg, rows, write = trace_files
    ibex = normalize_ibex_csv(path, image, cfg)
    for row in rows:
        row["order"] = str(int(row["order"]) - 1)
    write()
    pico_cfg = dict(cfg, id="picorv32_rv32i", retirement_adapter="picorv32_rvfi_csv", native_order_base=0)
    pico = normalize_rvfi_csv(path, image, pico_cfg)
    assert compare_traces(ibex, pico)["retirements_compared"] == 3
    assert pico["records"][0]["native_order"] == 0
    assert ibex["records"][0]["native_order"] == 1


@pytest.mark.parametrize("corrupt", [False, True])
def test_cross_processor_result_is_checked_not_just_case_passes(trace_files, tmp_path, corrupt):
    path, image, cfg, _, _ = trace_files
    trace = normalize_ibex_csv(path, image, cfg)
    cases = []
    for processor in ("ibex_smoke", "picorv32_rv32i"):
        data = copy.deepcopy(trace)
        data["processor_config"] = processor
        if corrupt and processor.startswith("picorv32"):
            data["records"][0]["rd_data"] ^= 1
        target = tmp_path / (processor + ".json")
        target.write_text(json.dumps(data))
        cases.append({"layer": "uvm", "status": "pass", "processor_config": processor, "seed": 1,
                      "artifacts": {"no_added_delay_trace": str(target), "stalled_trace": str(target)}})
    if corrupt:
        with pytest.raises(ValueError, match="Architectural mismatch"):
            compare_processor_cases(cases, ["ibex_smoke", "picorv32_rv32i"], [1])
    else:
        assert len(compare_processor_cases(cases, ["ibex_smoke", "picorv32_rv32i"], [1])) == 2
        with pytest.raises(ValueError, match="Missing passing CPU"):
            compare_processor_cases(cases[:1], ["ibex_smoke", "picorv32_rv32i"], [1])


@pytest.mark.parametrize("name", ["../ibex_smoke", "ibex_smoke.json", "Ibex", "", True])
def test_processor_path_is_not_arbitrary(name):
    with pytest.raises(ValueError):
        load_processor(name)


@pytest.mark.parametrize("seeds", [[1, 1], [], [0], [True], [-1], [0x100000000]])
def test_invalid_seed_matrix_is_rejected(tmp_path, seeds):
    path = tmp_path / "matrix.json"
    path.write_text(json.dumps({"schema_version": 1, "processors": ["ibex_smoke"], "seeds": seeds,
                                "uvm_mode": "full", "jobs": 1, "include_cocotb": False}))
    with pytest.raises(ValueError):
        load_regression(path)


def result_case(name="a", status="pass"):
    return {"schema_version": 1, "case_id": name, "layer": "uvm", "scope": "cpu",
            "processor_config": "ibex_smoke", "seed": 1, "status": status, "executed": True,
            "artifacts": {}, "coverage_observations": [{"percent": 50}]}


def test_regression_rejects_missing_and_duplicate_cases():
    with pytest.raises(ValueError):
        aggregate([result_case()], 2)
    with pytest.raises(ValueError):
        aggregate([result_case(), result_case()], 2)


def test_regression_never_averages_coverage_or_hides_failures():
    result = aggregate([result_case(), result_case("b", "failed")], 2)
    assert result["status"] == "failed"
    assert result["failed_cases"] == 1
    assert result["coverage"]["merged_bin_coverage"] is None
    assert len(result["coverage"]["observations"]) == 2


def test_compile_only_cannot_be_labeled_executed_pass():
    case = result_case()
    case["executed"] = False
    with pytest.raises(ValueError):
        aggregate([case], 1)


@pytest.mark.parametrize(("message", "category"), [
    ("Unable to checkout svverification license", "license"),
    ("Case timed out after 900 seconds", "timeout"),
    ("Sources changed during verification", "source_integrity"),
    ("RVFI_RD mismatch", "architectural_mismatch"),
    ("XSim elaboration failed", "compile_or_elaboration"),
    ("processor adapter is not executable", "unsupported_configuration"),
    ("DLL could not be loaded", "infrastructure")])
def test_failure_classification(message, category):
    assert classify_failure(message) == category
