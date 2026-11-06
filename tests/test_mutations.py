# Tests the tools that prepare RTL mutations and classify their outcomes.
# Uses sample results to check which failures count as detecting the mutation.

"""Synthetic qualification of mutation isolation/classification; no RTL kills claimed."""
import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path
import copy
import json
from pathlib import Path
import sys
from verification.config import ROOT
from verification.mutations import DEFINITIONS, prepare_mutant, verify_mutant, transform, classify_observation, checked_folder
from verification.traces import compare_traces
sys.path.insert(0, str(ROOT / 'scripts'))
from run_mutation_tests import compare_retirement_prefix

def observed():
    return {'compiled': True, 'elaborated': True, 'mutation_integrity_verified': True, 'mutation_observation': {'simulated': True, 'returncode': 0, 'simulator_errors': False, 'uvm_counts': {'UVM_ERROR': 1, 'UVM_FATAL': 0}, 'pass_fields': None, 'transcript': 'UVM_ERROR file.sv(10) @ 100: uvm_test_top.env [RVFI_RD] incorrect result\nUVM_ERROR : 1\n'}}

def fixture_trace():
    return {'schema_version': 1, 'producer': 'spike', 'processor_config': 'ibex_smoke', 'isa': 'rv32i', 'program_profile': 'corners', 'program_sha256': 'a' * 64, 'complete': True, 'records': [{'order': 0, 'hart': 0, 'pc': 128, 'insn': 1048723, 'rd_address': 1, 'rd_data': 1, 'memory': None, 'trap': False, 'halt': False, 'interrupt': False}]}

class AutomationChecks(unittest.TestCase):

    def setUp(self):
        folder = Path(__file__).resolve().parents[1] / 'build/python-tests/unittest-temp'
        folder.mkdir(parents=True, exist_ok=True)
        self.tmp_path = Path(self.enterContext(TemporaryDirectory(dir=folder)))

    def _check_each_mutant_changes_only_an_owned_copy(self, identity):
        tmp_path = self.tmp_path
        definition = DEFINITIONS[identity]
        original_path = ROOT / 'vendor' / definition.get('implementation', 'ibex') / definition['file']
        before = original_path.read_bytes()
        path = prepare_mutant(identity, tmp_path / identity)
        manifest = verify_mutant(path)
        self.assertTrue(original_path.read_bytes() == before)
        self.assertTrue(Path(manifest['isolated_source']).read_bytes() == transform(before, definition))
        self.assertTrue(manifest['original_sha256'] != manifest['mutated_sha256'])
        self.assertTrue((path.parent / 'mutation.patch').read_text().startswith('--- vendor/'))

    def test_each_mutant_changes_only_an_owned_copy_00(self):
        self._check_each_mutant_changes_only_an_owned_copy('add_flip_bit0')

    def test_each_mutant_changes_only_an_owned_copy_01(self):
        self._check_each_mutant_changes_only_an_owned_copy('beq_inverted')

    def test_each_mutant_changes_only_an_owned_copy_02(self):
        self._check_each_mutant_changes_only_an_owned_copy('sll_flip_bit0')

    def test_each_mutant_changes_only_an_owned_copy_03(self):
        self._check_each_mutant_changes_only_an_owned_copy('store_flip_bit0')

    def test_each_mutant_changes_only_an_owned_copy_04(self):
        self._check_each_mutant_changes_only_an_owned_copy('pico_add_flip_bit0')

    def test_each_mutant_changes_only_an_owned_copy_05(self):
        self._check_each_mutant_changes_only_an_owned_copy('pico_beq_inverted')

    def test_each_mutant_changes_only_an_owned_copy_06(self):
        self._check_each_mutant_changes_only_an_owned_copy('pico_sll_flip_bit0')

    def test_each_mutant_changes_only_an_owned_copy_07(self):
        self._check_each_mutant_changes_only_an_owned_copy('pico_store_flip_bit0')

    def _check_missing_or_ambiguous_anchor_fails(self, bad):
        with self.assertRaisesRegex(ValueError, 'anchor'):
            transform(bad, {'old': 'anchor', 'new': 'changed'})

    def test_missing_or_ambiguous_anchor_fails_00(self):
        self._check_missing_or_ambiguous_anchor_fails(b'missing')

    def test_missing_or_ambiguous_anchor_fails_01(self):
        self._check_missing_or_ambiguous_anchor_fails(b'anchor anchor')

    def test_outside_workspace_mutation_is_rejected(self):
        with self.assertRaises(ValueError):
            checked_folder(ROOT.parent / 'outside-mutant')

    def _check_mutation_tampering_cannot_pass(self, defect):
        tmp_path = self.tmp_path
        path = prepare_mutant('beq_inverted', tmp_path / defect)
        manifest = json.loads(path.read_text())
        if defect == 'mutant_bytes':
            Path(manifest['isolated_source']).write_text('changed')
        elif defect == 'saved_original':
            (path.parent / 'original.sv').write_text('changed')
        elif defect == 'definition':
            manifest['definition']['error_id'] = 'anything'
        else:
            manifest['isolated_source'] = str(ROOT / 'vendor/ibex/rtl/ibex_alu.sv')
        path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            verify_mutant(path)

    def test_mutation_tampering_cannot_pass_00(self):
        self._check_mutation_tampering_cannot_pass('mutant_bytes')

    def test_mutation_tampering_cannot_pass_01(self):
        self._check_mutation_tampering_cannot_pass('saved_original')

    def test_mutation_tampering_cannot_pass_02(self):
        self._check_mutation_tampering_cannot_pass('definition')

    def test_mutation_tampering_cannot_pass_03(self):
        self._check_mutation_tampering_cannot_pass('escape')

    def test_only_intended_executed_diagnostic_qualifies_as_kill(self):
        self.assertTrue(classify_observation(observed(), 'RVFI_RD', {'retired': 47}) == 'killed')

    def test_intended_first_error_allows_fully_recorded_cascades(self):
        raw = observed()
        raw['mutation_observation']['uvm_counts']['UVM_ERROR'] = 3
        raw['mutation_observation']['transcript'] += 'UVM_ERROR file.sv(11) @ 110: env [RVFI_RS1] bad source\nUVM_ERROR file.sv(12) @ 120: env [RVFI_RD] propagated result\n'
        self.assertTrue(classify_observation(raw, 'RVFI_RD', {'retired': 47}) == 'killed')
        raw['mutation_observation']['uvm_counts']['UVM_ERROR'] = 4
        self.assertTrue(classify_observation(raw, 'RVFI_RD', {'retired': 47}) == 'unqualified_detection')

    def _check_mutation_taxonomy_rejects_false_kills(self, defect, expected):
        raw = observed()
        obs = raw['mutation_observation']
        if defect == 'compile':
            raw.update(compiled=False, error='XSim compilation failed VRFC syntax error')
        elif defect == 'license':
            raw.update(compiled=False, error='License checkout failed')
        elif defect == 'timeout':
            raw['error'] = 'xelab timed out'
        elif defect == 'wrong_checker':
            obs['transcript'] = obs['transcript'].replace('RVFI_RD', 'OTHER')
        elif defect == 'fatal':
            obs['uvm_counts']['UVM_FATAL'] = 1
        elif defect == 'observation_flip':
            obs['transcript'] += '[CORRUPTION_INJECTED]'
        elif defect == 'source_drift':
            raw['mutation_integrity_verified'] = False
        elif defect == 'no_execution':
            obs['simulated'] = False
        else:
            obs['uvm_counts']['UVM_ERROR'] = 0
            obs['transcript'] = ''
            if defect == 'survived':
                obs['pass_fields'] = {'retired': 47}
        self.assertTrue(classify_observation(raw, 'RVFI_RD', {'retired': 47}) == expected)

    def test_mutation_taxonomy_rejects_false_kills_00(self):
        self._check_mutation_taxonomy_rejects_false_kills('compile', 'compile_invalid')

    def test_mutation_taxonomy_rejects_false_kills_01(self):
        self._check_mutation_taxonomy_rejects_false_kills('license', 'infrastructure_failed')

    def test_mutation_taxonomy_rejects_false_kills_02(self):
        self._check_mutation_taxonomy_rejects_false_kills('timeout', 'infrastructure_failed')

    def test_mutation_taxonomy_rejects_false_kills_03(self):
        self._check_mutation_taxonomy_rejects_false_kills('wrong_checker', 'unqualified_detection')

    def test_mutation_taxonomy_rejects_false_kills_04(self):
        self._check_mutation_taxonomy_rejects_false_kills('fatal', 'unqualified_detection')

    def test_mutation_taxonomy_rejects_false_kills_05(self):
        self._check_mutation_taxonomy_rejects_false_kills('observation_flip', 'infrastructure_failed')

    def test_mutation_taxonomy_rejects_false_kills_06(self):
        self._check_mutation_taxonomy_rejects_false_kills('source_drift', 'infrastructure_failed')

    def test_mutation_taxonomy_rejects_false_kills_07(self):
        self._check_mutation_taxonomy_rejects_false_kills('no_execution', 'infrastructure_failed')

    def test_mutation_taxonomy_rejects_false_kills_08(self):
        self._check_mutation_taxonomy_rejects_false_kills('no_marker', 'unqualified_detection')

    def test_mutation_taxonomy_rejects_false_kills_09(self):
        self._check_mutation_taxonomy_rejects_false_kills('survived', 'survived')

    def test_prefix_match_never_becomes_a_complete_pass(self):
        reference = fixture_trace()
        prefix = copy.deepcopy(reference)
        prefix.update(producer='dut', complete=False)
        self.assertTrue(compare_retirement_prefix(prefix, reference)['status'] == 'prefix_match')
        self.assertTrue(prefix['complete'] is False)
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            compare_traces(prefix, reference)
        prefix['records'][0]['rd_data'] ^= 1
        self.assertTrue(compare_retirement_prefix(prefix, reference)['status'] == 'architectural_mismatch')
