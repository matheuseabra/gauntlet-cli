import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gauntlet.config import load
from gauntlet.discovery import Project, detect
from gauntlet.doctor import _project_checks, python_compatible
from gauntlet.errors import GauntletError
from gauntlet.models import Results, RunContext


class ConfigTests(unittest.TestCase):
    def test_doctor_python_compatibility_boundary(self):
        self.assertFalse(python_compatible((3, 11)))
        self.assertTrue(python_compatible((3, 12)))

    def test_doctor_keeps_python_compatibility_separate_from_packaging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = load(root)
            results = Results({"root": str(root)})
            results.checks["python"] = "incompatible"
            with patch("gauntlet.doctor.shutil.which", return_value=True):
                _project_checks(
                    results,
                    root,
                    Project(["python"], "python", "unittest", {}),
                    config,
                    RunContext(root, "changed", [], [], config),
                )
            self.assertEqual(results.checks["python"], "incompatible")
            self.assertEqual(results.checks["python-package-manager"], "passed")

    def test_defaults_are_changed_and_mutation_blocks(self):
        config = load(Path(tempfile.mkdtemp()))
        self.assertEqual(config.mode, "changed")
        self.assertTrue(config.policy.block_surviving_mutants)
        self.assertFalse(config.policy.block_duplicate_candidates)

    def test_validates_version_keys_and_thresholds(self):
        for content in (
            "version = 3",
            "[gauntlet]\nunknown = true",
            "[tools.dryer]\nthreshold = 1.1",
            '[policy]\nblock_surviving_mutants = "yes"',
            '[commands]\nother = "run"',
        ):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                Path(directory, "gauntlet.toml").write_text(content)
                with self.assertRaises(GauntletError) as raised:
                    load(Path(directory))
                self.assertEqual(raised.exception.code, 4)

    def test_malformed_toml_fails_as_configuration_error(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "gauntlet.toml").write_text("[tools\n")
            with self.assertRaises(GauntletError) as raised:
                load(Path(directory))
            self.assertEqual(raised.exception.code, 4)

    def test_accepts_gauntlet_nested_command_table(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "gauntlet.toml").write_text(
                '[gauntlet.commands]\ntest = "python -m unittest"\n'
            )
            self.assertEqual(load(Path(directory)).commands["test"], "python -m unittest")

    def test_invalid_project_pyproject_is_a_configuration_error(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "pyproject.toml").write_text("[project\n")
            with self.assertRaises(GauntletError) as raised:
                detect(Path(directory))
            self.assertEqual(raised.exception.code, 4)


if __name__ == "__main__":
    unittest.main()
