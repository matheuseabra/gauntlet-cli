import sys
import tempfile
import unittest
from pathlib import Path

from gauntlet.config import Config
from gauntlet.errors import GauntletError
from gauntlet.models import Finding, Location, Results
from gauntlet.pipeline.policy import accepted, apply
from gauntlet.process import run
from gauntlet.reporters.json import render


class PolicyProcessTests(unittest.TestCase):
    def finding(self, identity, rule, score=40, line=3):
        return Finding(
            identity,
            "crapper",
            rule,
            "info",
            Location("src/domain.py", "f", line, 4),
            "result",
            {"crap": score},
        )

    def test_crap_blocks_only_changed_function_and_survivor_blocks(self):
        crap = self.finding("crap-id", "crap-score")
        survivor = self.finding("mutator-id", "surviving-mutant")
        apply(
            [crap, survivor],
            Config(),
            {},
            ["src/domain.py"],
            "changed",
            {"src/domain.py": [(10, 12)]},
        )
        self.assertFalse(crap.blocking)
        self.assertTrue(survivor.blocking)
        apply([crap], Config(), {}, ["src/domain.py"], "changed", {"src/domain.py": [(3, 3)]})
        self.assertTrue(crap.blocking)

    def test_moderate_crap_and_acceptance(self):
        crap = self.finding("review-id", "crap-score", 20)
        warning = apply(
            [crap], Config(), {"review-id": "Intended boundary risk."}, ["src/domain.py"], "changed"
        )
        self.assertEqual(crap.severity, "review")
        self.assertTrue(crap.accepted)
        self.assertFalse(crap.blocking)
        self.assertEqual(warning, [])

    def test_accept_requires_reason_and_unique_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, ".gauntlet")
            path.mkdir()
            target = path / "accept.toml"
            for value in (
                '[[finding]]\nid = "x"\nreason = " "\n',
                '[[finding]]\nid = "x"\nreason = "why"\n'
                '[[finding]]\nid = "x"\nreason = "why again"\n',
            ):
                target.write_text(value)
                with self.assertRaises(GauntletError):
                    accepted(Path(directory))

    def test_process_exit_missing_command_and_timeout(self):
        result = run([sys.executable, "-c", "raise SystemExit(7)"], Path.cwd())
        self.assertEqual(result.exit_code, 7)
        with self.assertRaises(GauntletError) as missing:
            run(["gauntlet-definitely-missing"], Path.cwd())
        self.assertEqual(missing.exception.code, 5)
        result = run([sys.executable, "-c", "import time; time.sleep(2)"], Path.cwd(), 0.05)
        self.assertTrue(result.timed_out)

    def test_json_output_is_deterministic_and_schema_versioned(self):
        results = Results({"root": "/repo", "mode": "changed"})
        first = render(results)
        self.assertEqual(first, render(results))
        self.assertEqual(__import__("json").loads(first)["version"], 1)
        self.assertTrue(first.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
