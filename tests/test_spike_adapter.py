# Tests the Python side of offline Spike verification with sample artifacts.
# Checks how the adapter validates builds, program images, and retirement records.

"""Synthetic adapter qualification only. Real ISS evidence is in regressions."""
import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path
import copy
import json
import subprocess
from types import SimpleNamespace
from verification.config import load_processor, load_regression
from verification.reference.spike import PIN, ROOT, digest, parse_spike_records, qualify_comparison, read_program_image, verify_spike_build
from verification.reference import spike

def make_reference_fixture(tmp_path):
    cfg = dict(load_processor('ibex_smoke'), expected_retirements=2)
    image = tmp_path / 'program.hex'
    image.write_text('@20 00100093 00132223\n')
    rows = [{'order': 0, 'hart': 0, 'pc': 128, 'insn': 1048723, 'rd_address': 1, 'rd_data': 1, 'trap': False, 'halt': False, 'interrupt': False, 'memory': None}, {'order': 1, 'hart': 0, 'pc': 132, 'insn': 1253923, 'rd_address': 0, 'rd_data': 0, 'trap': False, 'halt': False, 'interrupt': False, 'memory': {'kind': 'store', 'address': 4100, 'mask': 15, 'data': 1}}]
    return (cfg, image, rows)

def make_synthetic_build(tmp_path):
    cfg = json.loads((ROOT / 'config/spike.json').read_text())
    config_path = tmp_path / 'config/spike.json'
    config_path.parent.mkdir()
    config_path.write_text(json.dumps(cfg))
    folder = tmp_path / cfg['build_directory']
    folder.mkdir(parents=True)
    fields = {'config_sha256': config_path, 'archive_sha256': folder / 'source.tar', 'bridge_source_sha256': tmp_path / 'verification/reference/spike_bridge.cc', 'bridge_driver_sha256': tmp_path / 'verification/reference/build_spike_linux.py', 'spike_sha256': folder / 'spike', 'bridge_sha256': folder / 'spike_ref'}
    manifest = {'status': 'built', 'upstream': cfg, 'version': f'rvverify-spike-ref api=1 spike=1.1.0 commit={PIN}'}
    for field, path in fields.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(b'synthetic identity fixture only')
        manifest[field] = digest(path)
    (folder / 'build-manifest.json').write_text(json.dumps(manifest))
    return (tmp_path, fields)

class AutomationChecks(unittest.TestCase):

    def setUp(self):
        folder = Path(__file__).resolve().parents[1] / 'build/python-tests/unittest-temp'
        folder.mkdir(parents=True, exist_ok=True)
        self.tmp_path = Path(self.enterContext(TemporaryDirectory(dir=folder)))

    def test_word_addresses_are_converted_without_changing_little_endian_words(self):
        tmp_path = self.tmp_path
        path = tmp_path / 'program.hex'
        path.write_text('// exact readmemh words\n@20 00100093 ffd00113 /* comment */\n@400 deadbeef\n')
        self.assertTrue(read_program_image(path) == {128: 1048723, 132: 4291821843, 4096: 3735928559})

    def _check_invalid_image_is_rejected(self, content):
        tmp_path = self.tmp_path
        path = tmp_path / 'bad.hex'
        path.write_text(content)
        with self.assertRaises(ValueError):
            read_program_image(path)

    def test_invalid_image_is_rejected_00(self):
        self._check_invalid_image_is_rejected('')

    def test_invalid_image_is_rejected_01(self):
        self._check_invalid_image_is_rejected('00100093')

    def test_invalid_image_is_rejected_02(self):
        self._check_invalid_image_is_rejected('@20 xxxxxxxx')

    def test_invalid_image_is_rejected_03(self):
        self._check_invalid_image_is_rejected('@20 100000000')

    def test_invalid_image_is_rejected_04(self):
        self._check_invalid_image_is_rejected('@20 1234 @20 5678')

    def test_invalid_image_is_rejected_05(self):
        self._check_invalid_image_is_rejected('@4000 00100093')

    def test_invalid_image_is_rejected_06(self):
        self._check_invalid_image_is_rejected('@100000020 00100093')

    def test_invalid_image_is_rejected_07(self):
        self._check_invalid_image_is_rejected('@zz 00100093')

    def test_synthetic_reference_records_and_intended_corruption(self):
        tmp_path = self.tmp_path
        reference_fixture = make_reference_fixture(tmp_path)
        cfg, image, rows = reference_fixture
        reference = parse_spike_records('\n'.join(map(json.dumps, rows)), image, cfg)
        actual = copy.deepcopy(reference)
        actual['producer'] = 'dut'
        result, corrupt = qualify_comparison(actual, reference)
        self.assertTrue(result['status'] == 'detected' and result['field'] == 'rd_data')
        self.assertTrue(corrupt['records'][0]['rd_data'] == 0)
        self.assertTrue(actual['records'][0]['rd_data'] == 1)

    def _check_partial_or_invalid_reference_cannot_pass(self, defect):
        tmp_path = self.tmp_path
        reference_fixture = make_reference_fixture(tmp_path)
        cfg, image, rows = reference_fixture
        if defect == 'drop':
            rows.pop()
        elif defect == 'duplicate':
            rows[1]['order'] = 0
        elif defect == 'reorder':
            rows.reverse()
        elif defect == 'terminal':
            rows[-1]['memory']['data'] = 2
        elif defect == 'trap':
            rows[0]['trap'] = True
        elif defect == 'missing_memory':
            rows[-1]['memory'] = None
        text = '\n'.join(map(json.dumps, rows))
        if defect == 'empty':
            text = ''
        elif defect == 'json':
            text = 'not JSON'
        with self.assertRaises(ValueError):
            parse_spike_records(text, image, cfg)

    def test_partial_or_invalid_reference_cannot_pass_00(self):
        self._check_partial_or_invalid_reference_cannot_pass('empty')

    def test_partial_or_invalid_reference_cannot_pass_01(self):
        self._check_partial_or_invalid_reference_cannot_pass('json')

    def test_partial_or_invalid_reference_cannot_pass_02(self):
        self._check_partial_or_invalid_reference_cannot_pass('drop')

    def test_partial_or_invalid_reference_cannot_pass_03(self):
        self._check_partial_or_invalid_reference_cannot_pass('duplicate')

    def test_partial_or_invalid_reference_cannot_pass_04(self):
        self._check_partial_or_invalid_reference_cannot_pass('reorder')

    def test_partial_or_invalid_reference_cannot_pass_05(self):
        self._check_partial_or_invalid_reference_cannot_pass('terminal')

    def test_partial_or_invalid_reference_cannot_pass_06(self):
        self._check_partial_or_invalid_reference_cannot_pass('trap')

    def test_partial_or_invalid_reference_cannot_pass_07(self):
        self._check_partial_or_invalid_reference_cannot_pass('missing_memory')

    def test_build_identity_fixture_passes_integrity_gates(self):
        tmp_path = self.tmp_path
        synthetic_build = make_synthetic_build(tmp_path)
        root, _ = synthetic_build
        self.assertTrue(verify_spike_build(root)[1]['status'] == 'built')

    def _check_stale_reference_artifact_fails_closed(self, field):
        tmp_path = self.tmp_path
        synthetic_build = make_synthetic_build(tmp_path)
        root, fields = synthetic_build
        fields[field].write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError, 'hash changed'):
            verify_spike_build(root)

    def test_stale_reference_artifact_fails_closed_00(self):
        self._check_stale_reference_artifact_fails_closed('archive_sha256')

    def test_stale_reference_artifact_fails_closed_01(self):
        self._check_stale_reference_artifact_fails_closed('bridge_source_sha256')

    def test_stale_reference_artifact_fails_closed_02(self):
        self._check_stale_reference_artifact_fails_closed('bridge_driver_sha256')

    def test_stale_reference_artifact_fails_closed_03(self):
        self._check_stale_reference_artifact_fails_closed('spike_sha256')

    def test_stale_reference_artifact_fails_closed_04(self):
        self._check_stale_reference_artifact_fails_closed('bridge_sha256')

    def test_missing_build_fails_closed(self):
        tmp_path = self.tmp_path
        (tmp_path / 'config').mkdir()
        (tmp_path / 'config/spike.json').write_bytes((ROOT / 'config/spike.json').read_bytes())
        with self.assertRaisesRegex(RuntimeError, 'build missing'):
            verify_spike_build(tmp_path)

    def test_spike_matrix_requires_boolean(self):
        tmp_path = self.tmp_path
        matrix = json.loads((ROOT / 'config/regressions/smoke.json').read_text())
        matrix['include_spike'] = 'true'
        path = tmp_path / 'matrix.json'
        path.write_text(json.dumps(matrix))
        with self.assertRaisesRegex(ValueError, 'include_spike'):
            load_regression(path)

    def _check_mocked_execution_completion_and_integrity_gates(self, defect):
        tmp_path = self.tmp_path
        reference_fixture = make_reference_fixture(tmp_path)
        cfg, image, rows = reference_fixture
        config = json.loads((ROOT / 'config/spike.json').read_text())
        self.enterContext(patch.object(spike, 'verify_spike_build', lambda: (config, {'synthetic': True})))
        self.enterContext(patch.object(spike, 'wsl_path', lambda p: '/synthetic/' + p.name))

        def fake_run(command, **kwargs):
            self.assertTrue(command[0] == 'wsl' and cfg['spike_isa'] in command)
            if defect == 'timeout':
                raise subprocess.TimeoutExpired(command, 180)
            if defect == 'source_change':
                image.write_text(image.read_text() + '// changed during execution\n')
            marker = 'SPIKE_REFERENCE_PASS retired=2 next_pc=136 signature=1\n'
            if defect == 'missing_marker':
                marker = ''
            elif defect == 'wrong_marker':
                marker = marker.replace('136', '140')
            output = rows[:-1] if defect == 'short_trace' else rows
            return SimpleNamespace(returncode=1 if defect == 'returncode' else 0, stdout='\n'.join(map(json.dumps, output)), stderr=marker)
        self.enterContext(patch.object(spike.subprocess, 'run', fake_run))
        output = tmp_path / 'mock-execution'
        if defect:
            with self.assertRaises((RuntimeError, ValueError, subprocess.TimeoutExpired)):
                spike.run_reference(image, cfg, output)
            self.assertTrue(json.loads((output / 'reference-result.json').read_text())['status'] == 'failed')
        else:
            trace, result = spike.run_reference(image, cfg, output)
            self.assertTrue(result['status'] == 'pass' and len(trace['records']) == 2)

    def test_mocked_execution_completion_and_integrity_gates_00(self):
        self._check_mocked_execution_completion_and_integrity_gates(None)

    def test_mocked_execution_completion_and_integrity_gates_01(self):
        self._check_mocked_execution_completion_and_integrity_gates('returncode')

    def test_mocked_execution_completion_and_integrity_gates_02(self):
        self._check_mocked_execution_completion_and_integrity_gates('missing_marker')

    def test_mocked_execution_completion_and_integrity_gates_03(self):
        self._check_mocked_execution_completion_and_integrity_gates('wrong_marker')

    def test_mocked_execution_completion_and_integrity_gates_04(self):
        self._check_mocked_execution_completion_and_integrity_gates('short_trace')

    def test_mocked_execution_completion_and_integrity_gates_05(self):
        self._check_mocked_execution_completion_and_integrity_gates('source_change')

    def test_mocked_execution_completion_and_integrity_gates_06(self):
        self._check_mocked_execution_completion_and_integrity_gates('timeout')
