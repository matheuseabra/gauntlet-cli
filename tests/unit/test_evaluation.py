import json
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

from benchmarks.runner import gate, hidden_oracle, run_case, summarize
from benchmarks.tasks import TASKS, prepare


class EvaluationTests(unittest.TestCase):
    def test_held_out_boundary_rejects_mirrored_wrong_behavior(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepare(root, TASKS[0])
            (root / "src/rules.py").write_text("def eligible(age): return age > 18\n")
            self.assertFalse(hidden_oracle(root, TASKS[0], 5)["passed"])
            (root / "src/rules.py").write_text("def eligible(age): return age >= 18\n")
            self.assertTrue(hidden_oracle(root, TASKS[0], 5)["passed"])
            self.assertFalse((root / "oracle.py").exists())

    def test_gate_and_oracle_are_separate_and_partial_never_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = {"status": "partial", "exit_code": 6}
            command = [sys.executable, "-c", f"print({json.dumps(report)!r})"]
            self.assertFalse(gate(root, 5, command)["passed"])
        records = [
            dict(
                arm="without",
                oracle={"passed": False},
                gate_passed_oracle_failed=True,
                oracle_passed_gate_blocked=False,
            )
        ]
        self.assertEqual(summarize(records)["without"]["gate_passed_oracle_failed"], 1)
        self.assertEqual(summarize(records)["without"]["oracle_passes"], 0)

    def test_subject_environment_is_isolated_and_same_baseline_is_reset(self):
        script = (
            "import os; from pathlib import Path; "
            'assert Path("src/rules.py").read_text().endswith("return False\\n"); '
            'assert os.environ["GAUNTLET_EVAL_MODE"] == "without"; '
            'Path("src/rules.py").write_text("def eligible(age): return age >= 18\\n")'
        )
        command = shlex.join([sys.executable, "-c", script])
        fake_gate = [sys.executable, "-c", 'print(\'{"status":"passed","exit_code":0}\')']
        for repetition in range(2):
            data = run_case(TASKS[0], "without", command, repetition, 5, fake_gate)
            self.assertEqual(data["subject_exit"], 0, data["subject_stderr"])
            self.assertTrue(data["oracle"]["passed"], data["oracle"])
            self.assertTrue(data["gate"]["passed"])
