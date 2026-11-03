"""Parser/negative controls are utility checks, separate from native RTL acceptance."""
import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path
import csv
from pathlib import Path
from verification.config import apply_program, load_processor
from verification.coverage import parse_xcrg_report
from verification.scenarios import extract_reset_epoch, audit_irq_trace

def write_csv(path, fields, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)

def irq_fixture(tmp_path):
    pcs = [128, 132, 136, 140, 144, 148, 152, 156, 556, 560, 564, 568, 156, 160, 164]
    rows = [dict(order=i + 1, pc=f'{pc:x}', epoch=0, trap=0, halt=0, intr=int(pc == 556), rd=0, rd_data='0', insn='13', mem_addr='0', mem_wmask='0', mem_wdata='0') for i, pc in enumerate(pcs)]
    rows[8].update(rd=11, rd_data='8000000b')
    rows[9].update(rd=12, rd_data='9c')
    rows[11]['insn'] = '30200073'
    rows[-1].update(mem_addr='1004', mem_wmask='f', mem_wdata='1')
    control = tmp_path / 'control.csv'
    write_csv(control, ['event'], [{'event': e} for e in ('irq_1', 'irq_0')])
    return (rows, control)

class AutomationChecks(unittest.TestCase):

    def setUp(self):
        folder = Path(__file__).resolve().parents[1] / 'build/python-tests/unittest-temp'
        folder.mkdir(parents=True, exist_ok=True)
        self.tmp_path = Path(self.enterContext(TemporaryDirectory(dir=folder)))

    def test_native_report_preserves_open_random_bins(self):
        text = (Path(__file__).parent / 'fixtures/xcrg-directed.txt').read_text()
        groups = parse_xcrg_report(text)
        self.assertTrue(groups['corner_cg']['covered'] == 22)
        self.assertTrue(groups['retire_cg']['covered'] == 15)
        self.assertTrue(groups['random_alu_cg']['covered'] == 0)
        self.assertTrue(groups['random_memory_cg']['expected'] == 8)
        self.assertTrue(not groups['random_memory_cg']['closed'])

    def _check_report_rejects_missing_duplicate_or_contradictory_bins(self, defect):
        text = (Path(__file__).parent / 'fixtures/xcrg-directed.txt').read_text()
        line = next((line for line in text.splitlines() if ',random_memory_cg_' in line))
        if defect == 'missing':
            text = text.replace(line, '')
        elif defect == 'duplicate':
            text += '\n' + line
        else:
            text = text.replace(line, line.replace(',8           ,8           ,0', ',8           ,8           ,1'))
        with self.assertRaises(ValueError):
            parse_xcrg_report(text)

    def test_report_rejects_missing_duplicate_or_contradictory_bins_00(self):
        self._check_report_rejects_missing_duplicate_or_contradictory_bins('missing')

    def test_report_rejects_missing_duplicate_or_contradictory_bins_01(self):
        self._check_report_rejects_missing_duplicate_or_contradictory_bins('duplicate')

    def test_report_rejects_missing_duplicate_or_contradictory_bins_02(self):
        self._check_report_rejects_missing_duplicate_or_contradictory_bins('contradictory')

    def test_reset_split_retains_aborted_evidence_and_only_exports_restart(self):
        tmp_path = self.tmp_path
        path = tmp_path / 'stalled_rvfi_trace.csv'
        write_csv(path, ['epoch', 'order'], [{'epoch': 0, 'order': 1}, {'epoch': 0, 'order': 2}, {'epoch': 1, 'order': 1}])
        result = extract_reset_epoch(path)
        self.assertTrue(result == {'epochs': 2, 'aborted_prefix_retirements': 2, 'final_retirements': 1})
        self.assertTrue(len(list(csv.DictReader(path.read_text().splitlines()))) == 1)
        self.assertTrue(len(list(csv.DictReader((tmp_path / 'stalled_all_epochs_rvfi_trace.csv').read_text().splitlines()))) == 3)

    def _check_reset_requires_exactly_one_observed_restart(self, epochs):
        tmp_path = self.tmp_path
        path = tmp_path / 'trace.csv'
        write_csv(path, ['epoch'], [{'epoch': e} for e in epochs])
        with self.assertRaises(ValueError):
            extract_reset_epoch(path)

    def test_reset_requires_exactly_one_observed_restart_00(self):
        self._check_reset_requires_exactly_one_observed_restart([0, 0])

    def test_reset_requires_exactly_one_observed_restart_01(self):
        self._check_reset_requires_exactly_one_observed_restart([1, 1])

    def test_reset_requires_exactly_one_observed_restart_02(self):
        self._check_reset_requires_exactly_one_observed_restart([0, 1, 0])

    def test_reset_requires_exactly_one_observed_restart_03(self):
        self._check_reset_requires_exactly_one_observed_restart([0, 1, 2])

    def _check_irq_contract_rejects_wrong_event_return_or_completion(self, defect):
        tmp_path = self.tmp_path
        rows, control = irq_fixture(tmp_path)
        if defect == 'mepc':
            rows[9]['rd_data'] = 'a0'
        elif defect == 'mcause':
            rows[8]['rd_data'] = 'b'
        elif defect == 'entry':
            rows[8]['intr'] = 0
        elif defect == 'mret':
            rows[11]['insn'] = '13'
        elif defect == 'signature':
            rows[-1]['mem_wdata'] = '0'
        elif defect == 'order':
            rows[-1]['order'] = 1
        elif defect == 'return_pc':
            rows[12]['pc'] = 'a0'
        elif defect == 'input':
            write_csv(control, ['event'], [{'event': 'irq_1'}])
        path = tmp_path / 'irq.csv'
        write_csv(path, list(rows[0]), rows)
        if defect:
            with self.assertRaises(ValueError):
                audit_irq_trace(path, control)
        else:
            self.assertTrue(audit_irq_trace(path, control)['retirements'] == 15)
            self.assertTrue(audit_irq_trace(path, control)['spike_comparison_executed'] is False)

    def test_irq_contract_rejects_wrong_event_return_or_completion_00(self):
        self._check_irq_contract_rejects_wrong_event_return_or_completion(None)

    def test_irq_contract_rejects_wrong_event_return_or_completion_01(self):
        self._check_irq_contract_rejects_wrong_event_return_or_completion('mepc')

    def test_irq_contract_rejects_wrong_event_return_or_completion_02(self):
        self._check_irq_contract_rejects_wrong_event_return_or_completion('mcause')

    def test_irq_contract_rejects_wrong_event_return_or_completion_03(self):
        self._check_irq_contract_rejects_wrong_event_return_or_completion('entry')

    def test_irq_contract_rejects_wrong_event_return_or_completion_04(self):
        self._check_irq_contract_rejects_wrong_event_return_or_completion('mret')

    def test_irq_contract_rejects_wrong_event_return_or_completion_05(self):
        self._check_irq_contract_rejects_wrong_event_return_or_completion('signature')

    def test_irq_contract_rejects_wrong_event_return_or_completion_06(self):
        self._check_irq_contract_rejects_wrong_event_return_or_completion('order')

    def test_irq_contract_rejects_wrong_event_return_or_completion_07(self):
        self._check_irq_contract_rejects_wrong_event_return_or_completion('return_pc')

    def test_irq_contract_rejects_wrong_event_return_or_completion_08(self):
        self._check_irq_contract_rejects_wrong_event_return_or_completion('input')

    def test_irq_profile_is_explicitly_ibex_only(self):
        self.assertTrue(apply_program(load_processor('ibex_smoke'), 'irq')['program_isa'] == 'rv32i_zicsr_machine')
        with self.assertRaises(ValueError):
            apply_program(load_processor('picorv32_rv32i'), 'irq')
