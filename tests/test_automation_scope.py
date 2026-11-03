"""Retired component requests must fail before any simulator job is launched."""
import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path
import json
import sys
from pathlib import Path
from verification.config import load_regression
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_regression import run_case

class AutomationChecks(unittest.TestCase):

    def setUp(self):
        folder = Path(__file__).resolve().parents[1] / 'build/python-tests/unittest-temp'
        folder.mkdir(parents=True, exist_ok=True)
        self.tmp_path = Path(self.enterContext(TemporaryDirectory(dir=folder)))

    def test_old_component_configuration_is_not_silently_accepted(self):
        tmp_path = self.tmp_path
        path = tmp_path / 'old-matrix.json'
        path.write_text(json.dumps({'schema_version': 1, 'processors': ['ibex_smoke'], 'seeds': [1], 'uvm_mode': 'full', 'jobs': 1, 'include_cocotb': True}))
        with self.assertRaisesRegex(ValueError, 'was removed'):
            load_regression(path)

    def test_component_case_is_rejected_before_output_or_launch(self):
        tmp_path = self.tmp_path
        output = tmp_path / 'not-created'
        with self.assertRaisesRegex(ValueError, 'Only native UVM'):
            run_case('ibex_smoke', 1, 'python', 'full', output)
        self.assertTrue(not output.exists())
