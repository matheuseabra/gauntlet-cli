"""Diagnostic scripted controls. This is not an AI agent and proves no model benefit."""

import json
import os
import subprocess
import sys
from pathlib import Path

STRONG_TESTS = """import unittest
from src.rules import eligible
class RulesTest(unittest.TestCase):
    def test_boundary(self):
        self.assertFalse(eligible(0))
        self.assertFalse(eligible(17))
        self.assertTrue(eligible(18))
        self.assertTrue(eligible(19))
"""
MIRROR_TESTS = """import unittest
from src.rules import eligible
class RulesTest(unittest.TestCase):
    def test_mirrored_implementation(self):
        for age in [0, 17, 18, 19, 100]:
            self.assertEqual(eligible(age), age > 18)
"""


def main():
    gated = os.environ["GAUNTLET_EVAL_MODE"] == "with"
    task = os.environ["GAUNTLET_EVAL_TASK_ID"]
    if task == "eligibility-boundary":
        Path("src/rules.py").write_text(
            "def eligible(age):\n    return age " + (">=" if gated else ">") + " 18\n"
        )
        Path("tests/test_rules.py").write_text(STRONG_TESTS if gated else MIRROR_TESTS)
    if gated:
        result = subprocess.run(
            [sys.executable, "-m", "gauntlet", "check", "--all", "--json"],
            text=True,
            capture_output=True,
        )
        data = json.loads(result.stdout)
        if task == "equivalent-domain" and result.returncode == 3:
            equivalents = [
                f
                for f in data["findings"]
                if f["rule"] == "surviving-mutant"
                and f["metadata"]["original"] == ">="
                and f["metadata"]["replacement"] == ">"
            ]
            Path(".gauntlet/accept.toml").write_text(
                "\n".join(
                    f'[[finding]]\nid="{f["id"]}"\nreason="Allowed ages are only 17 and 19; '
                    '18 is rejected before this comparison, so >=18 and >18 are equivalent."\n'
                    for f in equivalents
                )
            )
            result = subprocess.run(
                [sys.executable, "-m", "gauntlet", "check", "--all", "--json"],
                text=True,
                capture_output=True,
            )
        if result.returncode:
            print(result.stdout)
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
