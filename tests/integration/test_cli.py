import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = [sys.executable, "-m", "gauntlet"]
PROJECT = Path(__file__).resolve().parents[2]


def call(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        CLI + list(args),
        cwd=cwd,
        text=True,
        capture_output=True,
        env={**__import__("os").environ, "PYTHONPATH": str(PROJECT / "src")},
    )


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class CliIntegrationTests(unittest.TestCase):
    def test_init_preserves_configuration_and_creates_state_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = call(root, "init")
            self.assertEqual(result.returncode, 0)
            config = root / "gauntlet.toml"
            original = config.read_bytes()
            self.assertEqual(call(root, "init").returncode, 0)
            self.assertEqual(config.read_bytes(), original)
            self.assertTrue((root / ".gauntlet").is_dir())

    def test_empty_changed_set_is_a_machine_readable_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git(root, "init", "-q")
            (root / "gauntlet.toml").write_text(
                "version = 1\n[tools.crapper]\nenabled = false\n"
                "[tools.mutator]\nenabled = false\n[tools.dryer]\nenabled = false\n"
            )
            git(root, "add", "gauntlet.toml")
            git(
                root,
                "-c",
                "user.email=test@example.invalid",
                "-c",
                "user.name=Test",
                "commit",
                "-m",
                "configuration",
                "-q",
            )
            result = call(root, "check", "--json")
            data = json.loads(result.stdout)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(data["status"], "passed")
            self.assertEqual(data["findings"], [])
            self.assertEqual(json.loads((root / ".gauntlet/results.json").read_text()), data)
            self.assertEqual(result.stderr, "")

    def test_invalid_configuration_has_json_only_stdout_and_exit_four(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git(root, "init", "-q")
            (root / "gauntlet.toml").write_text("version = 99\n")
            result = call(root, "check", "--json")
            self.assertEqual(result.returncode, 4)
            self.assertEqual(result.stderr, "")
            data = json.loads(result.stdout)
            self.assertEqual(data["exit_code"], 4)

    def test_full_pipeline_normalizes_survivor_crap_duplicate_and_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src/retry.py"
            source.parent.mkdir()
            source.write_text("def allowed(attempts, limit):\n    return attempts > limit\n")
            (root / "src/other.py").write_text(
                "def other(attempts, limit):\n    return attempts >= limit\n"
            )
            bin_dir = root / "bin"
            bin_dir.mkdir()
            crapper, mutator, dryer, coverage = [
                bin_dir / name for name in ("crapper", "mutator", "dryer", "coverage.py")
            ]
            crapper.write_text(CRAPPER_TOOL)
            mutator.write_text(MUTATOR_TOOL)
            dryer.write_text(DRYER_TOOL)
            coverage.write_text(COVERAGE_TOOL)
            for tool in (crapper, mutator, dryer, coverage):
                tool.chmod(0o755)
            (root / "gauntlet.toml").write_text(
                "version = 1\n"
                f'[commands]\ntest = "true"\ncoverage = {shlex.quote(str(coverage))!r}\n'
                f"[tools.crapper]\ncommand = {str(crapper)!r}\nthreshold = 30\n"
                f"[tools.mutator]\ncommand = {str(mutator)!r}\n"
                f"[tools.dryer]\ncommand = {str(dryer)!r}\n"
                "[policy]\nblock_surviving_mutants = true\nblock_crap_regressions = true\n"
                "block_duplicate_candidates = false\n"
            )
            git(root, "init", "-q")
            git(root, "config", "user.email", "tests@example.invalid")
            git(root, "config", "user.name", "Tests")
            git(root, "add", ".")
            git(root, "commit", "-m", "baseline", "-q")
            source.write_text("def allowed(attempts, limit):\n    return attempts >= limit\n")

            result = call(root, "check", "--json")
            data = json.loads(result.stdout)
            rules = {finding["rule"] for finding in data["findings"]}
            self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
            self.assertTrue({"crap-score", "surviving-mutant", "structural-duplication"} <= rules)
            survivor = next(f for f in data["findings"] if f["rule"] == "surviving-mutant")
            self.assertEqual(survivor["location"]["line"], 2)
            crap = next(f for f in data["findings"] if f["rule"] == "crap-score")
            duplicate = next(f for f in data["findings"] if f["rule"] == "structural-duplication")
            self.assertTrue(crap["blocking"])
            self.assertFalse(duplicate["blocking"])
            self.assertTrue((root / ".gauntlet/results.json").is_file())

            accepted_ids = [f["id"] for f in data["findings"]]
            rows = "\n".join(
                f'[[finding]]\nid = "{identity}"\nreason = "Reviewed fixture."'
                for identity in accepted_ids
            )
            accept_path = root / ".gauntlet/accept.toml"
            accept_path.parent.mkdir(exist_ok=True)
            accept_path.write_text(rows + "\n")
            accepted = call(root, "check", "--json")
            accepted_data = json.loads(accepted.stdout)
            self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
            self.assertTrue(
                all(
                    f["accepted"] and not f["blocking"]
                    for f in accepted_data["findings"]
                    if f["tool"] != "gauntlet"
                )
            )

            # A clean committed head must retain the changed lines for CRAP
            # policy, not fall back to the now-empty working-tree diff.
            accept_path.unlink()
            git(root, "add", "src/retry.py")
            git(root, "commit", "-qm", "committed change")
            committed = call(root, "check", "--base", "HEAD~1", "--json")
            committed_data = json.loads(committed.stdout)
            self.assertEqual(committed.returncode, 3, committed.stdout + committed.stderr)
            committed_crap = next(
                f for f in committed_data["findings"] if f["rule"] == "crap-score"
            )
            self.assertTrue(committed_crap["blocking"])
            self.assertTrue(committed_crap["metadata"]["changed"])
            self.assertEqual(committed_data["repository"]["selected_files"], ["src/retry.py"])
            self.assertEqual(len(committed_data["repository"]["head_sha"]), 40)

            # A later edit outside the unchanged complex function must not
            # block its existing CRAP finding. Only accept the fixture survivor.
            accept_path.write_text(
                f'[[finding]]\nid = "{survivor["id"]}"\nreason = "Reviewed fixture."\n'
            )
            source.write_text(source.read_text() + "\n# documentation outside the function\n")
            git(root, "add", "src/retry.py")
            git(root, "commit", "-qm", "comment only")
            outside = call(root, "check", "--base", "HEAD~1", "--json")
            outside_data = json.loads(outside.stdout)
            self.assertEqual(outside.returncode, 0, outside.stdout + outside.stderr)
            outside_crap = next(f for f in outside_data["findings"] if f["rule"] == "crap-score")
            self.assertFalse(outside_crap["blocking"])
            self.assertFalse(outside_crap["metadata"]["changed"])

    def test_base_empty_scope_stays_empty_and_conflicting_flags_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git(root, "init", "-q")
            git(root, "config", "user.email", "tests@example.invalid")
            git(root, "config", "user.name", "Tests")
            (root / "existing.py").write_text("def value(): return 1\n")
            git(root, "add", ".")
            git(root, "commit", "-qm", "baseline")
            result = call(root, "check", "--base", "HEAD", "--json")
            data = json.loads(result.stdout)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(data["repository"]["selected_files"], [])
            self.assertEqual(data["checks"], {})
            self.assertEqual(data, json.loads((root / ".gauntlet/results.json").read_text()))
            for flag in ("--changed", "--all"):
                self.assertEqual(
                    call(root, "check", "--base", "HEAD", flag, "--json").returncode, 4
                )
            self.assertEqual(call(root, "scan", "--base", "HEAD", "--json").returncode, 0)
            self.assertEqual(call(root, "check", "--base", "not-a-ref", "--json").returncode, 4)
            self.assertEqual(call(root, "check", "--base", "", "--json").returncode, 4)


CRAPPER_TOOL = """#!/usr/bin/env python3
from pathlib import Path
(Path.cwd() / ".metrics").mkdir(exist_ok=True)
(Path.cwd() / ".metrics/crap.edn").write_text(
    '{:entries [{:name "allowed" :namespace "retry" :complexity 8 '
    ':coverage 40.0 :crap 40.0}]}')
"""

MUTATOR_TOOL = """#!/usr/bin/env python3
import json
from pathlib import Path
source = Path("src/retry.py").read_bytes()
start = source.index(b">=")
key = json.dumps(["src/retry.py", "retry", "defn/allowed", start, start+2, ">=", ">"])
path = Path(".metrics/mutate/retry.edn")
path.parent.mkdir(parents=True, exist_ok=True)
escaped = json.dumps(key)[1:-1]
path.write_text('{:version 1 :namespace "retry" :source "src/retry.py" '
    ':tested-at "variable" :outcomes {"' + escaped + '" :survived} '
    ':forms [{:id "defn/allowed" :file "src/retry.py" :line 1 :end-line 2 '
    ':killed 0 :survived 1 :uncovered 0 :sites 1}]}')
"""

DRYER_TOOL = """#!/usr/bin/env python3
from pathlib import Path
Path(".metrics").mkdir(exist_ok=True)
Path(".metrics/dry.edn").write_text('{:candidates [{:score 0.91 :language "python" '
    ':left {:file "src/retry.py" :start-line 1 :end-line 2} '
    ':right {:file "src/other.py" :start-line 1 :end-line 2} '
    ':left-nodes 24 :right-nodes 26}]}')
"""

COVERAGE_TOOL = """#!/usr/bin/env python3
from pathlib import Path
path = Path("coverage/lcov.info")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text("TN:\\nSF:src/retry.py\\nDA:1,1\\nDA:2,1\\nend_of_record\\n")
"""


if __name__ == "__main__":
    unittest.main()
