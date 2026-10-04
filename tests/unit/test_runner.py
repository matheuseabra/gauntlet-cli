import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from gauntlet.config import Config
from gauntlet.models import Results, RunContext
from gauntlet.pipeline.runner import _prerequisites


class RunnerTests(unittest.TestCase):
    def context(self, root: Path, config: Config) -> RunContext:
        return RunContext(root, "changed", ["src/main.py"], ["src/main.py"], config)

    def test_runs_configured_coverage_to_refresh_existing_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "coverage/lcov.info"
            artifact.parent.mkdir()
            artifact.write_text("TN:\n")
            config = replace(Config(), commands={"coverage": "python -m coverage"})
            context = self.context(root, config)
            results = Results({"root": str(root)})
            with patch("gauntlet.pipeline.runner.run_shell") as run_shell:
                run_shell.return_value.exit_code = 0
                run_shell.return_value.timed_out = False
                _prerequisites(context, results)
            run_shell.assert_called_once_with("python -m coverage", root, config.timeout)
            self.assertEqual(results.checks["coverage"], "passed")

    def test_reuses_existing_coverage_when_no_command_is_configured(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "coverage/lcov.info"
            artifact.parent.mkdir()
            artifact.write_text("TN:\n")
            context = self.context(root, Config())
            results = Results({"root": str(root)})
            with patch("gauntlet.pipeline.runner.run_shell") as run_shell:
                _prerequisites(context, results)
            run_shell.assert_not_called()
            self.assertEqual(results.checks["coverage"], "reused")


if __name__ == "__main__":
    unittest.main()
