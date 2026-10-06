"""Exercise budget and cache correctness with installed, pinned analyzer CLIs."""

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from benchmarks.tasks import TASKS, prepare

STRONG = """import unittest
from src.rules import eligible
class RulesTest(unittest.TestCase):
    def test_boundary(self):
        self.assertFalse(eligible(17))
        self.assertTrue(eligible(18))
        self.assertTrue(eligible(19))
"""


def check(root, *options):
    result = subprocess.run(
        ["gauntlet", "check", "--all", "--json", *options],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=120,
    )
    data = json.loads(result.stdout)
    assert result.returncode == data["exit_code"], (result, data)
    return data


def main():
    with tempfile.TemporaryDirectory(prefix="gauntlet-cost-") as directory:
        root = Path(directory)
        prepare(root, TASKS[0])
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        source = root / "src/rules.py"
        source.write_text("def eligible(age):\n    return age >= 18\n")
        original = hashlib.sha256(source.read_bytes()).hexdigest()
        tests = root / "tests/test_rules.py"
        tests.write_text(STRONG)
        first = check(root)
        assert first["exit_code"] == 0, first
        repeat = check(root)
        assert repeat["exit_code"] == 0, repeat
        assert repeat["mutation"]["cache_hits"] >= 1, repeat
        tests.write_text(STRONG.replace("        self.assertTrue(eligible(18))\n", ""))
        changed = check(root)
        assert changed["exit_code"] == 3, changed
        assert changed["mutation"]["cache_hits"] == 0, changed
        assert any(f["rule"] == "surviving-mutant" for f in changed["findings"]), changed
        # Upstream selects whole source lines, so two sites on one line cannot fit N=1.
        source.write_text("def eligible(age):\n    return age >= 18 and age <= 100\n")
        original = hashlib.sha256(source.read_bytes()).hexdigest()
        tests.write_text(STRONG)
        limited = check(root, "--max-mutants", "1")
        assert limited["status"] == "partial" and limited["exit_code"] == 6, limited
        assert limited["mutation"]["scheduled_new_sites"] <= 1, limited
        timeout = check(root, "--timeout", "0.001")
        assert timeout["status"] == "partial" and timeout["exit_code"] == 6, timeout
        assert hashlib.sha256(source.read_bytes()).hexdigest() == original
        print(
            json.dumps(
                {
                    name: {
                        "timings_ms": data["timings_ms"],
                        "mutation": data["mutation"],
                        "exit_code": data["exit_code"],
                        "status": data["status"],
                    }
                    for name, data in [
                        ("first", first),
                        ("repeat", repeat),
                        ("test_change", changed),
                        ("count_limit", limited),
                        ("timeout", timeout),
                    ]
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
