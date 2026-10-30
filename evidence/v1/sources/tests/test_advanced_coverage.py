"""Parser/negative controls are utility checks, separate from native RTL acceptance."""
import csv
from pathlib import Path

import pytest

from verification.config import apply_program, load_processor
from verification.coverage import parse_xcrg_report
from verification.scenarios import extract_reset_epoch, audit_irq_trace


def test_native_report_preserves_open_random_bins():
    text = (Path(__file__).parent / "fixtures/xcrg-directed.txt").read_text()
    groups = parse_xcrg_report(text)
    assert groups["corner_cg"]["covered"] == 22
    assert groups["retire_cg"]["covered"] == 15
    assert groups["random_alu_cg"]["covered"] == 0
    assert groups["random_memory_cg"]["expected"] == 8
    assert not groups["random_memory_cg"]["closed"]


@pytest.mark.parametrize("defect", ["missing", "duplicate", "contradictory"])
def test_report_rejects_missing_duplicate_or_contradictory_bins(defect):
    text = (Path(__file__).parent / "fixtures/xcrg-directed.txt").read_text()
    line = next(line for line in text.splitlines() if ",random_memory_cg_" in line)
    if defect == "missing": text = text.replace(line, "")
    elif defect == "duplicate": text += "\n" + line
    else: text = text.replace(line, line.replace(",8           ,8           ,0", ",8           ,8           ,1"))
    with pytest.raises(ValueError): parse_xcrg_report(text)


def write_csv(path, fields, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields); writer.writeheader(); writer.writerows(rows)


def test_reset_split_retains_aborted_evidence_and_only_exports_restart(tmp_path):
    path = tmp_path / "stalled_rvfi_trace.csv"
    write_csv(path, ["epoch", "order"], [{"epoch": 0, "order": 1}, {"epoch": 0, "order": 2}, {"epoch": 1, "order": 1}])
    result = extract_reset_epoch(path)
    assert result == {"epochs": 2, "aborted_prefix_retirements": 2, "final_retirements": 1}
    assert len(list(csv.DictReader(path.open()))) == 1
    assert len(list(csv.DictReader((tmp_path / "stalled_all_epochs_rvfi_trace.csv").open()))) == 3


@pytest.mark.parametrize("epochs", [[0, 0], [1, 1], [0, 1, 0], [0, 1, 2]])
def test_reset_requires_exactly_one_observed_restart(tmp_path, epochs):
    path = tmp_path / "trace.csv"
    write_csv(path, ["epoch"], [{"epoch": e} for e in epochs])
    with pytest.raises(ValueError): extract_reset_epoch(path)


def irq_fixture(tmp_path):
    pcs = [0x80, 0x84, 0x88, 0x8c, 0x90, 0x94, 0x98, 0x9c, 0x22c, 0x230, 0x234, 0x238, 0x9c, 0xa0, 0xa4]
    rows = [dict(order=i+1, pc=f"{pc:x}", epoch=0, trap=0, halt=0, intr=int(pc == 0x22c),
                 rd=0, rd_data="0", insn="13", mem_addr="0", mem_wmask="0", mem_wdata="0") for i, pc in enumerate(pcs)]
    rows[8].update(rd=11, rd_data="8000000b")
    rows[9].update(rd=12, rd_data="9c")
    rows[11]["insn"] = "30200073"
    rows[-1].update(mem_addr="1004", mem_wmask="f", mem_wdata="1")
    control = tmp_path / "control.csv"
    write_csv(control, ["event"], [{"event": e} for e in ("irq_1", "irq_0")])
    return rows, control


@pytest.mark.parametrize("defect", [None, "mepc", "mcause", "entry", "mret", "signature", "order", "return_pc", "input"])
def test_irq_contract_rejects_wrong_event_return_or_completion(tmp_path, defect):
    rows, control = irq_fixture(tmp_path)
    if defect == "mepc": rows[9]["rd_data"] = "a0"
    elif defect == "mcause": rows[8]["rd_data"] = "b"
    elif defect == "entry": rows[8]["intr"] = 0
    elif defect == "mret": rows[11]["insn"] = "13"
    elif defect == "signature": rows[-1]["mem_wdata"] = "0"
    elif defect == "order": rows[-1]["order"] = 1
    elif defect == "return_pc": rows[12]["pc"] = "a0"
    elif defect == "input": write_csv(control, ["event"], [{"event": "irq_1"}])
    path = tmp_path / "irq.csv"; write_csv(path, list(rows[0]), rows)
    if defect:
        with pytest.raises(ValueError): audit_irq_trace(path, control)
    else:
        assert audit_irq_trace(path, control)["retirements"] == 15
        assert audit_irq_trace(path, control)["spike_comparison_executed"] is False


def test_irq_profile_is_explicitly_ibex_only():
    assert apply_program(load_processor("ibex_smoke"), "irq")["program_isa"] == "rv32i_zicsr_machine"
    with pytest.raises(ValueError): apply_program(load_processor("picorv32_rv32i"), "irq")
