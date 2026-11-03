"""Automation gates for live checking; these synthetic cases do not run Spike."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from verification.config import load_regression
from run_regression import run_case
from run_xsim_tests import run_suite


class LiveReferenceGates(unittest.TestCase):
    def setUp(self):
        folder = ROOT / "build/python-tests/live-gates"
        folder.mkdir(parents=True, exist_ok=True)
        self.temp = Path(self.enterContext(TemporaryDirectory(dir=folder)))

    def test_live_configuration_requires_boolean_and_full_mode(self):
        baseline = json.loads((ROOT / "config/regressions/live-directed.json").read_text())
        for key, value in (("include_live_spike", "true"), ("uvm_mode", "seeded")):
            with self.subTest(field=key):
                data = dict(baseline, **{key: value})
                path = self.temp / "config.json"
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    load_regression(path)

    def test_unsupported_live_scenarios_fail_before_any_output(self):
        for scenario, program in (("reset", "corners"), ("factory", "corners"), ("irq", "irq")):
            with self.subTest(scenario=scenario):
                with self.assertRaisesRegex(ValueError, "Live Spike currently"):
                    run_suite(full=True, live_spike=True, scenario=scenario, program=program, output=self.temp / "not-created")
        self.assertFalse((self.temp / "not-created").exists())

    def test_old_offline_pass_cannot_satisfy_live_request(self):
        def fake_launch(command, **kwargs):
            folder = Path(command[command.index("--output") + 1])
            (folder / "results.json").write_text(json.dumps({"status": "pass", "verification_pass": True,
                "seed": 1, "processor_config": "ibex_smoke", "program_profile": "smoke"}))
            return SimpleNamespace(returncode=0, stdout="synthetic offline pass")
        with patch("run_regression.subprocess.run", side_effect=fake_launch):
            result = run_case("ibex_smoke", 1, "uvm", "full", self.temp, live_spike=True)
        self.assertEqual(result["status"], "failed")
        self.assertIn("live Spike", result["error"])
        self.assertFalse(result["executed"])
