import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from gauntlet.config import Config
from gauntlet.doctor import diagnose
from gauntlet.errors import GauntletError
from gauntlet.support import require
from tests.integration.test_cli import call, git


class SupportTests(unittest.TestCase):
    def test_mixed_swift_changes_fail_before_commands_for_check_scan_and_doctor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git(root, "init", "-q")
            (root / "logic.swift").write_text("func value() -> Int { 1 }")
            (root / "logic.py").write_text("def value(): return 1")
            for command in ("check", "scan", "doctor"):
                result = call(root, command, "--json")
                self.assertEqual(result.returncode, 4, result.stdout)
                self.assertIn("Swift", result.stdout)
                self.assertIn("unsupported", result.stdout)
            with patch("gauntlet.doctor._analyze_tools") as tools:
                self.assertEqual(diagnose(root).exit_code, 4)
                tools.assert_not_called()

    def test_enabled_analyzer_support_and_intentional_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "logic.js").write_text("function value() { return 1; }")
            with self.assertRaisesRegex(GauntletError, "dryer"):
                require(root, ["logic.js"], Config())
            config = Config()
            tools = config.tools | {"dryer": replace(config.tools["dryer"], enabled=False)}
            require(root, ["logic.js"], replace(config, tools=tools))
            require(root, ["logic.js"], replace(config, exclude=("*.js",)))
            (root / "README.md").write_text("Documentation")
            require(root, ["README.md"], config)
