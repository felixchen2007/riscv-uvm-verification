"""Synthetic adapter qualification only. Real ISS evidence is in regressions."""
import copy
import json
import subprocess
from types import SimpleNamespace

import pytest

from verification.config import load_processor, load_regression
from verification.reference.spike import (PIN, ROOT, digest, parse_spike_records,
    qualify_comparison, read_program_image, verify_spike_build)
from verification.reference import spike


def test_word_addresses_are_converted_without_changing_little_endian_words(tmp_path):
    path = tmp_path / "program.hex"
    path.write_text("// exact readmemh words\n@20 00100093 ffd00113 /* comment */\n@400 deadbeef\n")
    assert read_program_image(path) == {128: 0x00100093, 132: 0xffd00113, 4096: 0xdeadbeef}


@pytest.mark.parametrize("content", ["", "00100093", "@20 xxxxxxxx", "@20 100000000",
    "@20 1234 @20 5678", "@4000 00100093", "@100000020 00100093", "@zz 00100093"])
def test_invalid_image_is_rejected(tmp_path, content):
    path = tmp_path / "bad.hex"
    path.write_text(content)
    with pytest.raises(ValueError):
        read_program_image(path)


@pytest.fixture
def reference_fixture(tmp_path):
    cfg = dict(load_processor("ibex_smoke"), expected_retirements=2)
    image = tmp_path / "program.hex"
    image.write_text("@20 00100093 00132223\n")
    rows = [
        {"order": 0, "hart": 0, "pc": 128, "insn": 0x00100093, "rd_address": 1,
         "rd_data": 1, "trap": False, "halt": False, "interrupt": False, "memory": None},
        {"order": 1, "hart": 0, "pc": 132, "insn": 0x00132223, "rd_address": 0,
         "rd_data": 0, "trap": False, "halt": False, "interrupt": False,
         "memory": {"kind": "store", "address": 4100, "mask": 15, "data": 1}},
    ]
    return cfg, image, rows


def test_synthetic_reference_records_and_intended_corruption(reference_fixture):
    cfg, image, rows = reference_fixture
    reference = parse_spike_records("\n".join(map(json.dumps, rows)), image, cfg)
    actual = copy.deepcopy(reference)
    actual["producer"] = "dut"
    result, corrupt = qualify_comparison(actual, reference)
    assert result["status"] == "detected" and result["field"] == "rd_data"
    assert corrupt["records"][0]["rd_data"] == 0
    assert actual["records"][0]["rd_data"] == 1


@pytest.mark.parametrize("defect", ["empty", "json", "drop", "duplicate", "reorder", "terminal", "trap", "missing_memory"])
def test_partial_or_invalid_reference_cannot_pass(reference_fixture, defect):
    cfg, image, rows = reference_fixture
    if defect == "drop":
        rows.pop()
    elif defect == "duplicate":
        rows[1]["order"] = 0
    elif defect == "reorder":
        rows.reverse()
    elif defect == "terminal":
        rows[-1]["memory"]["data"] = 2
    elif defect == "trap":
        rows[0]["trap"] = True
    elif defect == "missing_memory":
        rows[-1]["memory"] = None
    text = "\n".join(map(json.dumps, rows))
    if defect == "empty":
        text = ""
    elif defect == "json":
        text = "not JSON"
    with pytest.raises(ValueError):
        parse_spike_records(text, image, cfg)


@pytest.fixture
def synthetic_build(tmp_path):
    # Synthetic files qualify integrity gates, never an executable fallback.
    cfg = json.loads((ROOT / "config/spike.json").read_text())
    config_path = tmp_path / "config/spike.json"
    config_path.parent.mkdir()
    config_path.write_text(json.dumps(cfg))
    folder = tmp_path / cfg["build_directory"]
    folder.mkdir(parents=True)
    fields = {"config_sha256": config_path, "archive_sha256": folder / "source.tar",
        "bridge_source_sha256": tmp_path / "verification/reference/spike_bridge.cc",
        "bridge_driver_sha256": tmp_path / "verification/reference/build_spike_linux.py",
        "spike_sha256": folder / "spike", "bridge_sha256": folder / "spike_ref"}
    manifest = {"status": "built", "upstream": cfg,
        "version": f"rvverify-spike-ref api=1 spike=1.1.0 commit={PIN}"}
    for field, path in fields.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(b"synthetic identity fixture only")
        manifest[field] = digest(path)
    (folder / "build-manifest.json").write_text(json.dumps(manifest))
    return tmp_path, fields


def test_build_identity_fixture_passes_integrity_gates(synthetic_build):
    root, _ = synthetic_build
    assert verify_spike_build(root)[1]["status"] == "built"


@pytest.mark.parametrize("field", ["archive_sha256", "bridge_source_sha256", "bridge_driver_sha256", "spike_sha256", "bridge_sha256"])
def test_stale_reference_artifact_fails_closed(synthetic_build, field):
    root, fields = synthetic_build
    fields[field].write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="hash changed"):
        verify_spike_build(root)


def test_missing_build_fails_closed(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/spike.json").write_bytes((ROOT / "config/spike.json").read_bytes())
    with pytest.raises(RuntimeError, match="build missing"):
        verify_spike_build(tmp_path)


def test_spike_matrix_requires_boolean(tmp_path):
    matrix = json.loads((ROOT / "config/regressions/smoke.json").read_text())
    matrix["include_spike"] = "true"
    path = tmp_path / "matrix.json"
    path.write_text(json.dumps(matrix))
    with pytest.raises(ValueError, match="include_spike"):
        load_regression(path)


@pytest.mark.parametrize("defect", [None, "returncode", "missing_marker", "wrong_marker", "short_trace", "source_change", "timeout"])
def test_mocked_execution_completion_and_integrity_gates(reference_fixture, tmp_path, monkeypatch, defect):
    # All external execution is mocked: this test proves gates, not an ISS run.
    cfg, image, rows = reference_fixture
    config = json.loads((ROOT / "config/spike.json").read_text())
    monkeypatch.setattr(spike, "verify_spike_build", lambda: (config, {"synthetic": True}))
    monkeypatch.setattr(spike, "wsl_path", lambda p: "/synthetic/" + p.name)
    def fake_run(command, **kwargs):
        assert command[0] == "wsl" and cfg["spike_isa"] in command
        if defect == "timeout":
            raise subprocess.TimeoutExpired(command, 180)
        if defect == "source_change":
            image.write_text(image.read_text() + "// changed during execution\n")
        marker = "SPIKE_REFERENCE_PASS retired=2 next_pc=136 signature=1\n"
        if defect == "missing_marker":
            marker = ""
        elif defect == "wrong_marker":
            marker = marker.replace("136", "140")
        output = rows[:-1] if defect == "short_trace" else rows
        return SimpleNamespace(returncode=1 if defect == "returncode" else 0,
            stdout="\n".join(map(json.dumps, output)), stderr=marker)
    monkeypatch.setattr(spike.subprocess, "run", fake_run)
    output = tmp_path / "mock-execution"
    if defect:
        with pytest.raises((RuntimeError, ValueError, subprocess.TimeoutExpired)):
            spike.run_reference(image, cfg, output)
        assert json.loads((output / "reference-result.json").read_text())["status"] == "failed"
    else:
        trace, result = spike.run_reference(image, cfg, output)
        assert result["status"] == "pass" and len(trace["records"]) == 2
