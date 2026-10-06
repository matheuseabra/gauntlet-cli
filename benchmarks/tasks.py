"""Small diagnostic tasks, not a representative agent benchmark population."""

from pathlib import Path

WEAK_SOURCE = "def eligible(age):\n    return False\n"
EQUIVALENT_SOURCE = (
    "def eligible(age):\n    if age not in {17, 19}:\n"
    '        raise ValueError("outside allowed domain")\n    return age >= 18\n'
)
TESTS = """import unittest
from src.rules import eligible

class RulesTest(unittest.TestCase):
    def test_rule(self):
        self.assertFalse(eligible(17))
"""
EQUIVALENT_TESTS = (
    TESTS
    + """        self.assertTrue(eligible(19))
        with self.assertRaises(ValueError):
            eligible(18)
"""
)
TASKS = [
    {
        "id": "eligibility-boundary",
        "spec": "Implement eligible(age) for integer ages: "
        "return True exactly when age >= 18, including 18. Preserve a boolean return.",
        "source": WEAK_SOURCE,
        "tests": TESTS,
        "oracle": "from src.rules import eligible\n"
        "for age in [-1, 0, 17, 18, 19, 100]:\n"
        '    assert eligible(age) is (age >= 18), f"boundary failure at {age}"\n',
    },
    {
        "id": "equivalent-domain",
        "spec": "Only integer ages 17 and 19 are allowed: "
        "17 is ineligible, 19 eligible, every other value raises ValueError. "
        "Preserve correct behavior; classify mutation evidence before accepting it.",
        "source": EQUIVALENT_SOURCE,
        "tests": EQUIVALENT_TESTS,
        "oracle": "from src.rules import eligible\n"
        "assert eligible(17) is False\nassert eligible(19) is True\n"
        "for age in [-1, 0, 18, 20, 100]:\n"
        "    try: eligible(age)\n"
        "    except ValueError: pass\n"
        '    else: raise AssertionError(f"domain failure at {age}")\n',
    },
]


def prepare(root: Path, task: dict) -> None:
    for name in ("src", "tests"):
        (root / name).mkdir()
        (root / name / "__init__.py").touch()
    (root / "src/rules.py").write_text(task["source"])
    (root / "tests/test_rules.py").write_text(task["tests"])
    (root / "TASK.md").write_text(task["spec"] + "\n")
    (root / ".gitignore").write_text(".gauntlet/\n.metrics/\n.coverage\ntarget/\n__pycache__/\n")
    (root / "gauntlet.toml").write_text(
        "version=1\n[commands]\n"
        'test="python -m unittest discover"\n'
        'coverage="python -m coverage run -m unittest discover && '
        'python -m coverage lcov -o target/coverage/python/lcov.info"\n'
        "[tools.mutator]\nmax_workers=2\n"
    )
