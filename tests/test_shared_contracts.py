"""Synthetic format/utility tests; these are not RTL or Spike execution evidence."""
import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path
import copy
import csv
import json
from verification.config import load_processor, load_regression
from verification.results import aggregate, classify_failure
from verification.traces import compare_traces, compare_processor_cases, normalize_ibex_csv, normalize_rvfi_csv, validate_trace

def make_trace_files(tmp_path):
    cfg = dict(load_processor('ibex_smoke'), expected_retirements=3)
    columns = 'order pc insn rd rd_data mem_addr mem_rmask mem_wmask mem_rdata mem_wdata trap halt intr'.split()
    rows = [dict(zip(columns, row.split())) for row in ('1 00000080 00100093 1 00000001 deadbeef f 0 00000000 00000000 0 0 0', '2 00000084 00001337 6 00001000 00001000 f 0 00000000 00000000 0 0 0', '3 00000088 00132223 0 00000000 00001004 f f 00000000 00000001 0 0 0')]
    path = tmp_path / 'synthetic.csv'
    image = tmp_path / 'synthetic.hex'
    image.write_text('@20 00100093 00001337 00132223\n')

    def write(data=rows, fields=columns):
        with path.open('w', newline='') as file:
            writer = csv.DictWriter(file, fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(data)
    write()
    return (path, image, cfg, rows, write)

def result_case(name='a', status='pass'):
    return {'schema_version': 1, 'case_id': name, 'layer': 'uvm', 'scope': 'cpu', 'processor_config': 'ibex_smoke', 'seed': 1, 'status': status, 'executed': True, 'artifacts': {}, 'coverage_observations': [{'percent': 50}]}

class AutomationChecks(unittest.TestCase):

    def setUp(self):
        folder = Path(__file__).resolve().parents[1] / 'build/python-tests/unittest-temp'
        folder.mkdir(parents=True, exist_ok=True)
        self.tmp_path = Path(self.enterContext(TemporaryDirectory(dir=folder)))

    def test_trace_normalizes_order_and_discards_stale_memory_fields(self):
        tmp_path = self.tmp_path
        trace_files = make_trace_files(tmp_path)
        path, image, cfg, _, _ = trace_files
        trace = normalize_ibex_csv(path, image, cfg)
        self.assertTrue([r['order'] for r in trace['records']] == [0, 1, 2])
        self.assertTrue([r['native_order'] for r in trace['records']] == [1, 2, 3])
        self.assertTrue(trace['records'][0]['memory'] is None)
        self.assertTrue(trace['records'][-1]['memory'] == {'kind': 'store', 'address': 4100, 'mask': 15, 'data': 1})

    def test_short_trace_requires_explicit_incomplete_prefix_mode(self):
        tmp_path = self.tmp_path
        trace_files = make_trace_files(tmp_path)
        path, image, cfg, rows, write = trace_files
        write(rows[:1])
        with self.assertRaisesRegex(ValueError, 'length/entry'):
            normalize_rvfi_csv(path, image, cfg)
        prefix = normalize_rvfi_csv(path, image, cfg, allow_prefix=True)
        self.assertTrue(prefix['complete'] is False and len(prefix['records']) == 1)
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            compare_traces(prefix, prefix)

    def _check_bad_raw_trace_cannot_pass(self, change):
        tmp_path = self.tmp_path
        trace_files = make_trace_files(tmp_path)
        path, image, cfg, rows, write = trace_files
        if change == 'drop':
            rows.pop()
        elif change == 'duplicate':
            rows[1]['order'] = '1'
        elif change == 'reorder':
            rows[0], rows[1] = (rows[1], rows[0])
        elif change == 'unknown':
            rows[1]['rd_data'] = 'xxxxxxxx'
        elif change == 'bad_terminal':
            rows[-1]['mem_wdata'] = '00000002'
        if change == 'missing_flags':
            write(rows, [f for f in rows[0] if f != 'trap'])
        else:
            write(rows)
        with self.assertRaises(ValueError):
            normalize_ibex_csv(path, image, cfg)

    def test_bad_raw_trace_cannot_pass_00(self):
        self._check_bad_raw_trace_cannot_pass('drop')

    def test_bad_raw_trace_cannot_pass_01(self):
        self._check_bad_raw_trace_cannot_pass('duplicate')

    def test_bad_raw_trace_cannot_pass_02(self):
        self._check_bad_raw_trace_cannot_pass('reorder')

    def test_bad_raw_trace_cannot_pass_03(self):
        self._check_bad_raw_trace_cannot_pass('unknown')

    def test_bad_raw_trace_cannot_pass_04(self):
        self._check_bad_raw_trace_cannot_pass('missing_flags')

    def test_bad_raw_trace_cannot_pass_05(self):
        self._check_bad_raw_trace_cannot_pass('bad_terminal')

    def _check_common_comparator_detects_architectural_differences(self, field):
        tmp_path = self.tmp_path
        trace_files = make_trace_files(tmp_path)
        path, image, cfg, _, _ = trace_files
        actual = normalize_ibex_csv(path, image, cfg)
        reference = copy.deepcopy(actual)
        reference['producer'] = 'spike'
        if field == 'memory':
            reference['records'][-1]['memory']['data'] ^= 1
        elif field == 'length':
            reference['records'].pop()
        elif field == 'program_hash':
            reference['program_sha256'] = 'a' * 64
        elif field == 'trap':
            reference['records'][0]['trap'] = True
        else:
            reference['records'][0][field] ^= 4
        with self.assertRaises(ValueError):
            compare_traces(actual, reference)

    def test_common_comparator_detects_architectural_differences_00(self):
        self._check_common_comparator_detects_architectural_differences('pc')

    def test_common_comparator_detects_architectural_differences_01(self):
        self._check_common_comparator_detects_architectural_differences('insn')

    def test_common_comparator_detects_architectural_differences_02(self):
        self._check_common_comparator_detects_architectural_differences('rd_data')

    def test_common_comparator_detects_architectural_differences_03(self):
        self._check_common_comparator_detects_architectural_differences('trap')

    def test_common_comparator_detects_architectural_differences_04(self):
        self._check_common_comparator_detects_architectural_differences('memory')

    def test_common_comparator_detects_architectural_differences_05(self):
        self._check_common_comparator_detects_architectural_differences('length')

    def test_common_comparator_detects_architectural_differences_06(self):
        self._check_common_comparator_detects_architectural_differences('program_hash')

    def test_incomplete_trace_is_rejected(self):
        tmp_path = self.tmp_path
        trace_files = make_trace_files(tmp_path)
        path, image, cfg, _, _ = trace_files
        trace = normalize_ibex_csv(path, image, cfg)
        trace['complete'] = False
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            validate_trace(trace)

    def test_planned_processor_cannot_execute(self):
        tmp_path = self.tmp_path
        import verification.config as module
        planned_config = dict(load_processor('ibex_smoke'), id='future_smoke', status='planned')
        configs = tmp_path / 'config/processors'
        configs.mkdir(parents=True)
        (configs / 'future_smoke.json').write_text(json.dumps(planned_config))
        self.enterContext(patch.object(module, 'ROOT', tmp_path))
        planned = load_processor('future_smoke', require_implemented=False)
        self.assertTrue(planned['status'] == 'planned')
        with self.assertRaisesRegex(ValueError, 'not executable'):
            load_processor('future_smoke')

    def test_two_implemented_processor_profiles(self):
        self.assertTrue(load_processor('ibex_smoke')['native_order_base'] == 1)
        self.assertTrue(load_processor('picorv32_rv32i')['native_order_base'] == 0)

    def test_pico_native_zero_origin_maps_to_same_architecture(self):
        tmp_path = self.tmp_path
        trace_files = make_trace_files(tmp_path)
        path, image, cfg, rows, write = trace_files
        ibex = normalize_ibex_csv(path, image, cfg)
        for row in rows:
            row['order'] = str(int(row['order']) - 1)
        write()
        pico_cfg = dict(cfg, id='picorv32_rv32i', retirement_adapter='picorv32_rvfi_csv', native_order_base=0)
        pico = normalize_rvfi_csv(path, image, pico_cfg)
        self.assertTrue(compare_traces(ibex, pico)['retirements_compared'] == 3)
        self.assertTrue(pico['records'][0]['native_order'] == 0)
        self.assertTrue(ibex['records'][0]['native_order'] == 1)

    def _check_cross_processor_result_is_checked_not_just_case_passes(self, corrupt):
        tmp_path = self.tmp_path
        trace_files = make_trace_files(tmp_path)
        path, image, cfg, _, _ = trace_files
        trace = normalize_ibex_csv(path, image, cfg)
        cases = []
        for processor in ('ibex_smoke', 'picorv32_rv32i'):
            data = copy.deepcopy(trace)
            data['processor_config'] = processor
            if corrupt and processor.startswith('picorv32'):
                data['records'][0]['rd_data'] ^= 1
            target = tmp_path / (processor + '.json')
            target.write_text(json.dumps(data))
            cases.append({'layer': 'uvm', 'status': 'pass', 'processor_config': processor, 'seed': 1, 'artifacts': {'no_added_delay_trace': str(target), 'stalled_trace': str(target)}})
        if corrupt:
            with self.assertRaisesRegex(ValueError, 'Architectural mismatch'):
                compare_processor_cases(cases, ['ibex_smoke', 'picorv32_rv32i'], [1])
        else:
            self.assertTrue(len(compare_processor_cases(cases, ['ibex_smoke', 'picorv32_rv32i'], [1])) == 2)
            with self.assertRaisesRegex(ValueError, 'Missing passing CPU'):
                compare_processor_cases(cases[:1], ['ibex_smoke', 'picorv32_rv32i'], [1])

    def test_cross_processor_result_is_checked_not_just_case_passes_00(self):
        self._check_cross_processor_result_is_checked_not_just_case_passes(False)

    def test_cross_processor_result_is_checked_not_just_case_passes_01(self):
        self._check_cross_processor_result_is_checked_not_just_case_passes(True)

    def _check_processor_path_is_not_arbitrary(self, name):
        with self.assertRaises(ValueError):
            load_processor(name)

    def test_processor_path_is_not_arbitrary_00(self):
        self._check_processor_path_is_not_arbitrary('../ibex_smoke')

    def test_processor_path_is_not_arbitrary_01(self):
        self._check_processor_path_is_not_arbitrary('ibex_smoke.json')

    def test_processor_path_is_not_arbitrary_02(self):
        self._check_processor_path_is_not_arbitrary('Ibex')

    def test_processor_path_is_not_arbitrary_03(self):
        self._check_processor_path_is_not_arbitrary('')

    def test_processor_path_is_not_arbitrary_04(self):
        self._check_processor_path_is_not_arbitrary(True)

    def _check_invalid_seed_matrix_is_rejected(self, seeds):
        tmp_path = self.tmp_path
        path = tmp_path / 'matrix.json'
        path.write_text(json.dumps({'schema_version': 1, 'processors': ['ibex_smoke'], 'seeds': seeds, 'uvm_mode': 'full', 'jobs': 1}))
        with self.assertRaises(ValueError):
            load_regression(path)

    def test_invalid_seed_matrix_is_rejected_00(self):
        self._check_invalid_seed_matrix_is_rejected([1, 1])

    def test_invalid_seed_matrix_is_rejected_01(self):
        self._check_invalid_seed_matrix_is_rejected([])

    def test_invalid_seed_matrix_is_rejected_02(self):
        self._check_invalid_seed_matrix_is_rejected([0])

    def test_invalid_seed_matrix_is_rejected_03(self):
        self._check_invalid_seed_matrix_is_rejected([True])

    def test_invalid_seed_matrix_is_rejected_04(self):
        self._check_invalid_seed_matrix_is_rejected([-1])

    def test_invalid_seed_matrix_is_rejected_05(self):
        self._check_invalid_seed_matrix_is_rejected([4294967296])

    def test_regression_rejects_missing_and_duplicate_cases(self):
        with self.assertRaises(ValueError):
            aggregate([result_case()], 2)
        with self.assertRaises(ValueError):
            aggregate([result_case(), result_case()], 2)

    def test_regression_never_averages_coverage_or_hides_failures(self):
        result = aggregate([result_case(), result_case('b', 'failed')], 2)
        self.assertTrue(result['status'] == 'failed')
        self.assertTrue(result['failed_cases'] == 1)
        self.assertTrue(result['coverage']['merged_bin_coverage'] is None)
        self.assertTrue(len(result['coverage']['observations']) == 2)

    def test_compile_only_cannot_be_labeled_executed_pass(self):
        case = result_case()
        case['executed'] = False
        with self.assertRaises(ValueError):
            aggregate([case], 1)

    def _check_failure_classification(self, message, category):
        self.assertTrue(classify_failure(message) == category)

    def test_failure_classification_00(self):
        self._check_failure_classification('Unable to checkout svverification license', 'license')

    def test_failure_classification_01(self):
        self._check_failure_classification('Case timed out after 900 seconds', 'timeout')

    def test_failure_classification_02(self):
        self._check_failure_classification('Sources changed during verification', 'source_integrity')

    def test_failure_classification_03(self):
        self._check_failure_classification('RVFI_RD mismatch', 'architectural_mismatch')

    def test_failure_classification_04(self):
        self._check_failure_classification('XSim elaboration failed', 'compile_or_elaboration')

    def test_failure_classification_05(self):
        self._check_failure_classification('processor adapter is not executable', 'unsupported_configuration')

    def test_failure_classification_06(self):
        self._check_failure_classification('DLL could not be loaded', 'infrastructure')
