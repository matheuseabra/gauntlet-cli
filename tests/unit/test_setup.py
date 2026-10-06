import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.python = self.root / "fake-python"
        self.python.write_text(FAKE_PYTHON)
        self.python.chmod(0o755)
        self.log = self.root / "calls.jsonl"
        self.environment = self.root / "tools with spaces"
        self.env = os.environ | {"GAUNTLET_PYTHON": str(self.python), "SETUP_LOG": str(self.log)}

    def setup_tools(self):
        return subprocess.run(
            ["bash", str(PROJECT / "scripts/setup-tools.sh"), str(self.environment)],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
        )

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_installation_is_independent_of_cwd_and_supports_environment_spaces(self):
        result = self.setup_tools()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.environment / "bin/gauntlet").is_file())
        pip = next(call for call in self.calls() if "pip" in call)
        self.assertIn(str(PROJECT / "requirements-tools.txt"), pip)
        self.assertIn(str(PROJECT), pip)

    def test_pip_failure_stops_before_grammar_setup(self):
        self.env["SETUP_PIP_EXIT"] = "7"
        self.assertEqual(self.setup_tools().returncode, 7)
        self.assertFalse(any("prefetch" in " ".join(call) for call in self.calls()))

    def test_incompatible_python_fails_before_creating_environment(self):
        self.env["SETUP_OLD_PYTHON"] = "1"
        self.assertNotEqual(self.setup_tools().returncode, 0)
        self.assertFalse(self.environment.exists())


FAKE_PYTHON = """#!/usr/bin/env python3
import json, os, shutil, sys
from pathlib import Path
with Path(os.environ['SETUP_LOG']).open('a') as log:
    log.write(json.dumps(sys.argv[1:]) + '\\n')
if 'sys.version_info' in ' '.join(sys.argv) and os.environ.get('SETUP_OLD_PYTHON'):
    sys.exit(1)
if sys.argv[1:3] == ['-m', 'venv']:
    bin_dir = Path(sys.argv[3]) / 'bin'
    bin_dir.mkdir(parents=True)
    shutil.copyfile(sys.argv[0], bin_dir / 'python')
    (bin_dir / 'python').chmod(0o755)
    for name in ('gauntlet', 'crapper', 'mutator', 'dryer'):
        path = bin_dir / name
        path.write_text('#!/bin/sh\\nexit 0\\n')
        path.chmod(0o755)
if sys.argv[1:3] == ['-m', 'pip']:
    sys.exit(int(os.environ.get('SETUP_PIP_EXIT', '0')))
"""
