# Tests how the tools validate program profiles and identify a saved program.
# Uses sample traces to check taken branches and fallthrough paths.

"""Synthetic program/branch contract tests, separate from real UVM/ISS evidence."""
import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path
import copy
import json
from verification.config import ROOT, apply_program, load_processor, load_program, load_regression
from verification.reference.spike import parse_spike_records
from verification.traces import branch_outcomes, compare_processor_cases, compare_traces, validate_trace

def branch(funct3, offset=8):
    value = offset & 8191
    return 99 | funct3 << 12 | (value >> 12 & 1) << 31 | (value >> 11 & 1) << 7 | (value >> 5 & 63) << 25 | (value >> 1 & 15) << 8

def trace_from(pairs):
    records = [{'order': i, 'hart': 0, 'pc': pc, 'insn': insn, 'rd_address': 0, 'rd_data': 0, 'memory': None, 'trap': False, 'halt': False, 'interrupt': False} for i, (pc, insn) in enumerate(pairs)]
    return {'schema_version': 1, 'processor_config': 'ibex_smoke', 'producer': 'dut', 'isa': 'rv32i', 'complete': True, 'program_sha256': 'a' * 64, 'records': records}

def four_way_trace():
    return trace_from([(128, branch(0)), (136, branch(1)), (140, branch(0)), (144, branch(1)), (152, 19)])

class AutomationChecks(unittest.TestCase):

    def setUp(self):
        folder = Path(__file__).resolve().parents[1] / 'build/python-tests/unittest-temp'
        folder.mkdir(parents=True, exist_ok=True)
        self.tmp_path = Path(self.enterContext(TemporaryDirectory(dir=folder)))

    def test_program_contracts_preserve_cpu_configuration_and_distinct_windows(self):
        cpu = load_processor('ibex_smoke')
        original = copy.deepcopy(cpu)
        corners = apply_program(cpu, 'corners')
        self.assertTrue(cpu == original)
        self.assertTrue(corners['expected_retirements'] == 47 and corners['terminal_pc'] == 316)
        self.assertTrue(corners['retirement_adapter'] == cpu['retirement_adapter'])
        self.assertTrue(apply_program(cpu)['expected_retirements'] == 14)
        self.assertTrue(load_program('corners')['branch_hits'] == {'beq_taken': 1, 'beq_not_taken': 1, 'bne_taken': 2, 'bne_not_taken': 2})

    def _check_invalid_program_identifier_cannot_run(self, name):
        with self.assertRaises(ValueError):
            load_program(name)

    def test_invalid_program_identifier_cannot_run_00(self):
        self._check_invalid_program_identifier_cannot_run('../smoke')

    def test_invalid_program_identifier_cannot_run_01(self):
        self._check_invalid_program_identifier_cannot_run('smoke.json')

    def test_invalid_program_identifier_cannot_run_02(self):
        self._check_invalid_program_identifier_cannot_run('missing')

    def test_invalid_program_identifier_cannot_run_03(self):
        self._check_invalid_program_identifier_cannot_run(True)

    def test_invalid_program_identifier_cannot_run_04(self):
        self._check_invalid_program_identifier_cannot_run('')

    def _check_invalid_program_matrix_is_rejected(self, programs):
        tmp_path = self.tmp_path
        data = json.loads((ROOT / 'config/regressions/corners.json').read_text())
        data['programs'] = programs
        path = tmp_path / 'matrix.json'
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            load_regression(path)

    def test_invalid_program_matrix_is_rejected_00(self):
        self._check_invalid_program_matrix_is_rejected([])

    def test_invalid_program_matrix_is_rejected_01(self):
        self._check_invalid_program_matrix_is_rejected(['smoke', 'smoke'])

    def test_invalid_program_matrix_is_rejected_02(self):
        self._check_invalid_program_matrix_is_rejected(['missing'])

    def test_invalid_program_matrix_is_rejected_03(self):
        self._check_invalid_program_matrix_is_rejected('corners')

    def test_branch_observations_use_actual_successor_pcs(self):
        self.assertTrue(branch_outcomes(four_way_trace()) == dict.fromkeys(('beq_taken', 'beq_not_taken', 'bne_taken', 'bne_not_taken'), 1))

    def test_backward_loop_records_both_directions(self):
        trace = trace_from([(128, 19), (132, branch(1, -4)), (128, 19), (132, branch(1, -4)), (136, 19)])
        self.assertTrue(branch_outcomes(trace) == {'beq_taken': 0, 'beq_not_taken': 0, 'bne_taken': 1, 'bne_not_taken': 1})

    def _check_branch_holes_and_invalid_paths_fail(self, defect):
        trace = four_way_trace()
        expected = None
        if defect == 'successor':
            trace['records'][1]['pc'] = 156
        elif defect == 'missing_successor':
            trace['records'] = trace['records'][:1]
        elif defect == 'ambiguous':
            trace['records'][0]['insn'] = branch(0, 4)
        else:
            expected = load_program('corners')['branch_hits']
        with self.assertRaises(ValueError):
            branch_outcomes(trace, expected)

    def test_branch_holes_and_invalid_paths_fail_00(self):
        self._check_branch_holes_and_invalid_paths_fail('successor')

    def test_branch_holes_and_invalid_paths_fail_01(self):
        self._check_branch_holes_and_invalid_paths_fail('missing_successor')

    def test_branch_holes_and_invalid_paths_fail_02(self):
        self._check_branch_holes_and_invalid_paths_fail('ambiguous')

    def test_branch_holes_and_invalid_paths_fail_03(self):
        self._check_branch_holes_and_invalid_paths_fail('required_bin')

    def test_program_identity_cannot_be_substituted(self):
        actual, reference = (four_way_trace(), four_way_trace())
        reference['program_profile'] = 'corners'
        with self.assertRaisesRegex(ValueError, 'program_profile'):
            compare_traces(actual, reference)

    def _check_invalid_trace_program_identity_is_rejected(self, identity):
        trace = four_way_trace()
        trace['program_profile'] = identity
        with self.assertRaisesRegex(ValueError, 'program_profile'):
            validate_trace(trace)

    def test_invalid_trace_program_identity_is_rejected_00(self):
        self._check_invalid_trace_program_identity_is_rejected(None)

    def test_invalid_trace_program_identity_is_rejected_01(self):
        self._check_invalid_trace_program_identity_is_rejected(True)

    def test_invalid_trace_program_identity_is_rejected_02(self):
        self._check_invalid_trace_program_identity_is_rejected('../corners')

    def test_cross_processor_matrix_keeps_programs_distinct(self):
        tmp_path = self.tmp_path
        cases = []
        for program in ('smoke', 'corners'):
            for processor in ('ibex_smoke', 'picorv32_rv32i'):
                trace = four_way_trace()
                trace['program_profile'] = program
                path = tmp_path / f'{program}-{processor}.json'
                path.write_text(json.dumps(trace))
                cases.append({'layer': 'uvm', 'status': 'pass', 'seed': 1, 'program_profile': program, 'processor_config': processor, 'artifacts': {'no_added_delay_trace': str(path), 'stalled_trace': str(path)}})
        self.assertTrue(len(compare_processor_cases(cases, ['ibex_smoke', 'picorv32_rv32i'], [1], ['smoke', 'corners'])) == 4)
        with self.assertRaisesRegex(ValueError, 'Missing passing CPU'):
            compare_processor_cases(cases[:-1], ['ibex_smoke', 'picorv32_rv32i'], [1], ['smoke', 'corners'])

    def test_reference_terminal_pc_is_checked(self):
        tmp_path = self.tmp_path
        image = tmp_path / 'synthetic.hex'
        image.write_text('@20 00132223\n')
        cfg = dict(load_processor('ibex_smoke'), expected_retirements=1, terminal_pc=132)
        trace = trace_from([(128, 1253923)])
        trace['records'][0]['memory'] = {'kind': 'store', 'address': 4100, 'mask': 15, 'data': 1}
        with self.assertRaisesRegex(ValueError, 'terminal PC'):
            parse_spike_records(json.dumps(trace['records'][0]), image, cfg)
