#!/usr/bin/env bash
# Exercise the installed CLI and real pinned analyzers in an isolated repository.
set -euo pipefail
fixture="$(mktemp -d)"
trap 'rm -rf "$fixture"' EXIT
cd "$fixture"
git init -q
git config user.name Fixture
git config user.email fixture@example.invalid
mkdir -p src tests
touch src/__init__.py tests/__init__.py
cat > .gitignore <<'EOF'
.gauntlet/
.metrics/
.coverage
target/
__pycache__/
EOF
cat > src/rules.py <<'EOF'
def eligible(age):
    return age >= 17
EOF
cat > tests/test_rules.py <<'EOF'
import unittest
from src.rules import eligible

class RulesTest(unittest.TestCase):
    def test_eligibility(self):
        self.assertFalse(eligible(16))
        self.assertTrue(eligible(19))
EOF
cat > gauntlet.toml <<'EOF'
version = 1
[commands]
test = "python -m unittest discover"
coverage = "python -m coverage run -m unittest discover && python -m coverage lcov -o target/coverage/python/lcov.info"
[tools.mutator]
max_workers = 2
EOF
git add .
git commit -qm baseline
base="$(git rev-parse HEAD)"
gauntlet check --base "$base" --json > empty.json
python -c 'import json; assert json.load(open("empty.json"))["repository"]["selected_files"] == []'
cat > src/rules.py <<'EOF'
def eligible(age):
    return age >= 18
EOF
git add src/rules.py
git commit -qm 'change threshold without boundary assertion'
status=0
gauntlet check --base "$base" --json > weak.json || status=$?
test "$status" -eq 3
python - <<'PY'
import json
data = json.load(open("weak.json"))
assert data["repository"]["selected_files"] == ["src/rules.py"]
assert any(f["blocking"] and f["rule"] == "surviving-mutant"
           and f["metadata"]["original"] == ">=" and f["metadata"]["replacement"] == ">"
           for f in data["findings"])
PY
cat > tests/test_rules.py <<'EOF'
import unittest
from src.rules import eligible

class RulesTest(unittest.TestCase):
    def test_eligibility(self):
        self.assertFalse(eligible(17))
        self.assertTrue(eligible(18))
        self.assertTrue(eligible(19))
EOF
git add tests/test_rules.py
git commit -qm 'specify exact boundary behavior'
gauntlet check --base "$base" --json > strong.json
python - <<'PY'
import json
data = json.load(open("strong.json"))
assert data["summary"]["blocking"] == 0
assert all(data["checks"][tool] == "passed" for tool in ("crapper", "mutator", "dryer"))
assert data["repository"]["base_sha"] == data["repository"]["merge_base_sha"]
PY
printf 'Real tool setup, committed survivor, and boundary repair passed.\n'
