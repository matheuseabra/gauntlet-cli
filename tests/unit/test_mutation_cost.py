import json
import os
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from gauntlet.adapters.mutation_run import plan_sites
from gauntlet.config import Config
from gauntlet.models import Finding, Location, RunContext
from gauntlet.pipeline.cache import MutationCache, repository_hashes
from tests.integration.test_cli import call, git

TOOL = r"""#!/usr/bin/env python3
import json, sys, time
from pathlib import Path
source=Path('code.py').read_bytes()
positions=[i for i in range(len(source)) if source[i:i+2]==b'>=']
if '--scan' in sys.argv:
    print(f'Scan: {len(positions)} mutation sites in code.py')
    for i in positions:
        line=source[:i].count(b'\n')+1
        print(f'  code.py:{line} >= -> >  [defn/f]')
    raise SystemExit(0)
assert '--mutate-all' in sys.argv
if Path('.gauntlet/slow').exists():
    time.sleep(2)
lines=None
if '--lines' in sys.argv:
    lines=set(map(int,sys.argv[sys.argv.index('--lines')+1].split(',')))
keys=[]
for i in positions:
    if lines is None or source[:i].count(b'\n')+1 in lines:
        keys.append(json.dumps(['code.py','code','defn/f',i,i+2,'>=','>']))
survive=Path('.gauntlet/survive').exists()
outcomes=' '.join(json.dumps(key)+(' :survived' if survive else ' :killed') for key in keys)
path=Path('.metrics/mutate/code.edn'); path.parent.mkdir(parents=True,exist_ok=True)
path.write_text('{:version 1 :namespace "code" :source "code.py" :outcomes {'+outcomes+'} '
    ':forms [{:id "defn/f" :file "code.py" :line 1 :end-line 4 :uncovered 0 :sites '
    +str(len(positions))+'}]}')
raise SystemExit(3 if survive else 0)
"""


class MutationCostTests(unittest.TestCase):
    def fixture(self, root):
        git(root, "init", "-q")
        (root / "code.py").write_text(
            "def f(x):\n    a = x >= 1\n    b = x >= 2\n    return x >= 3\n"
        )
        tool = root / "mutator"
        tool.write_text(TOOL)
        tool.chmod(0o755)
        (root / "coverage").mkdir()
        (root / "coverage/lcov.info").write_text("TN:\nSF:code.py\nDA:2,1\nend_of_record\n")
        (root / "gauntlet.toml").write_text(
            'version=1\n[commands]\ntest="true"\n'
            "[tools.crapper]\nenabled=false\n[tools.dryer]\nenabled=false\n"
            f"[tools.mutator]\ncommand={str(tool)!r}\n"
        )

    def test_line_groups_enforce_count_without_claiming_single_site_execution(self):
        sites = [
            Finding(str(i), "mutator", "mutation-site", "info", Location("code.py", line=line), "")
            for i, line in enumerate([2, 2, 3])
        ]
        self.assertEqual(plan_sites({"code.py": sites}, 1), {"code.py": [3]})
        self.assertEqual(plan_sites({"code.py": sites}, 3), {"code.py": None})

    def test_count_limit_is_nonzero_partial_with_coverage_counts_and_no_cached_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            result = call(root, "check", "--max-mutants", "1", "--json")
            data = json.loads(result.stdout)
            self.assertEqual(result.returncode, 6, result.stdout)
            self.assertEqual(data["status"], "partial")
            self.assertEqual(data["mutation"]["inventory_sites"], 3)
            self.assertEqual(data["mutation"]["scheduled_new_sites"], 1)
            self.assertEqual(data["mutation"]["completed_sites"], 1)
            self.assertAlmostEqual(data["mutation"]["reported_fraction"], 1 / 3)
            self.assertFalse((root / ".gauntlet/mutation-cache").exists())
            full = call(root, "check", "--json")
            self.assertEqual(full.returncode, 0, full.stdout)
            full_data = json.loads(full.stdout)
            self.assertEqual(full_data["mutation"]["completed_sites"], 3)
            self.assertTrue(
                all(type(value) is int and value >= 0 for value in full_data["timings_ms"].values())
            )
            terminal = call(root, "check", "--max-mutants", "1")
            self.assertIn("GAUNTLET PARTIAL", terminal.stdout)
            self.assertIn("Timing:", terminal.stdout)

    def test_timeout_is_partial_and_production_source_remains_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / ".gauntlet").mkdir()
            (root / ".gauntlet/slow").touch()
            original = (root / "code.py").read_bytes()
            result = call(root, "check", "--timeout", "0.15", "--json")
            data = json.loads(result.stdout)
            self.assertEqual(result.returncode, 6, result.stdout)
            self.assertEqual(data["status"], "partial")
            self.assertIn("timeout", data["mutation"]["partial_reason"])
            self.assertEqual(data["mutation"]["completed_sites"], 0)
            self.assertEqual((root / "code.py").read_bytes(), original)
            for args in [("--timeout", "-1"), ("--max-mutants", "0")]:
                self.assertEqual(call(root, "check", *args, "--json").returncode, 4)

    def test_partial_run_keeps_survivors_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / ".gauntlet").mkdir()
            (root / ".gauntlet/survive").touch()
            result = call(root, "check", "--max-mutants", "1", "--json")
            data = json.loads(result.stdout)
            self.assertEqual(result.returncode, 3, result.stdout)
            self.assertEqual(data["status"], "partial")
            self.assertEqual(data["checks"]["mutator"], "failed")
            self.assertEqual(data["mutation"]["partial_reason"], "max-mutants")
            self.assertTrue(any(f["blocking"] for f in data["findings"]))

    def test_cache_invalidates_tests_source_helpers_coverage_runtime_and_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            test = root / "test_rules.py"
            test.write_text("def test_rule(): assert True\n")
            config = replace(Config(), commands={"test": f"{sys.executable} -m unittest discover"})
            context = RunContext(root, "changed", ["code.py"], ["code.py"], config)
            with (
                patch("gauntlet.pipeline.cache.runtime_hash", return_value="a" * 64),
                patch.dict(os.environ, {"PYTHONPATH": ""}),
            ):
                cache = MutationCache(context, str(root / "mutator"))
                self.assertIsNotNone(cache.namespace)
                cache.put("code.py", 0, [])
                self.assertIsNotNone(MutationCache(context, str(root / "mutator")).get("code.py"))
                for file in [
                    test,
                    root / "code.py",
                    root / "helper.py",
                    root / "coverage/lcov.info",
                ]:
                    original = file.read_bytes() if file.exists() else None
                    file.write_text((original.decode() if original else "") + "\n# change\n")
                    self.assertIsNone(MutationCache(context, str(root / "mutator")).get("code.py"))
                    if original is not None:
                        file.write_bytes(original)
                    else:
                        file.unlink()
                with patch("gauntlet.pipeline.cache.runtime_hash", return_value="b" * 64):
                    self.assertIsNone(MutationCache(context, str(root / "mutator")).get("code.py"))
                new_config = replace(config, commands={"test": f"{sys.executable} -m unittest -v"})
                changed = replace(context, config=new_config)
                self.assertIsNone(MutationCache(changed, str(root / "mutator")).get("code.py"))
                cache.path("code.py").write_text("corrupt")
                self.assertIsNone(cache.get("code.py"))

    def test_uncertain_cache_inputs_rerun_and_test_hash_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            context = RunContext(
                root,
                "changed",
                ["code.py"],
                ["code.py"],
                replace(Config(), commands={"test": "custom-runner"}),
            )
            self.assertIsNone(MutationCache(context, str(root / "mutator")).namespace)
            before = repository_hashes(root)
            (root / "test_new.py").write_text("def test_f(): assert True\n")
            after = repository_hashes(root)
            self.assertNotEqual(before[1], after[1])
            (root / "external").symlink_to("/tmp", target_is_directory=True)
            self.assertIsNone(repository_hashes(root))
