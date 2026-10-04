# Tutorial: Build a Small Project with Gauntlet

This walkthrough builds a date-based trial policy, adds tests, runs Gauntlet, and repairs a test gap. It shows the workflow around your code; Gauntlet does not write or change the project for you.

You need Python 3.12+, Git, `uv`, the `gauntlet` command, and the upstream `crapper`, `mutator`, and `dryer` commands. Gauntlet does not install the analyzer tools. Follow their setup instructions in the [Crapper](https://github.com/unclebob/crapper), [Mutator](https://github.com/unclebob/mutator), and [Dryer](https://github.com/unclebob/dryer) repositories, then check them with `gauntlet doctor`.

## 1. Create the project

Start a Git repository, initialize Gauntlet, and create the source and test directories:

```sh
mkdir trial-policy
cd trial-policy
git init
gauntlet init
mkdir -p src/trial_policy tests
```

Create `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "trial-policy"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[project.optional-dependencies]
dev = ["coverage>=7,<8", "pytest>=8,<10"]

[tool.pytest.ini_options]
pythonpath = ["src"]
```

Add Python build and coverage outputs to `.gitignore`:

```gitignore
.venv/
__pycache__/
.pytest_cache/
.coverage
coverage/
target/
.metrics/
.gauntlet/results.json
.gauntlet/run.lock
```

Append these commands to the generated `gauntlet.toml`:

```toml
[commands]
test = "uv run pytest"
coverage = "uv run coverage run -m pytest && uv run coverage lcov -o target/coverage/python/lcov.info"
```

The coverage command writes LCOV to a path Gauntlet and the upstream analyzers can read. Run `gauntlet doctor` to check the project commands and analyzer executables. Doctor does not run tests or generate coverage.

## 2. Write the behavior and its first tests

The sample rule says a trial is active from its start date through day 13. A trial that starts in the future is not active.

Create `src/trial_policy/__init__.py`:

```python
from datetime import date

TRIAL_DAYS = 14


def is_trial_active(started_on: date, today: date) -> bool:
    elapsed_days = (today - started_on).days
    return 0 <= elapsed_days < TRIAL_DAYS
```

Create `tests/test_trial_policy.py`:

```python
from datetime import date, timedelta

from trial_policy import is_trial_active

START = date(2026, 1, 1)


def test_trial_is_active_on_its_start_day():
    assert is_trial_active(START, START)


def test_trial_is_active_on_day_thirteen():
    assert is_trial_active(START, START + timedelta(days=13))


def test_trial_is_inactive_after_day_fourteen():
    assert not is_trial_active(START, START + timedelta(days=15))


def test_future_trial_is_inactive():
    assert not is_trial_active(START + timedelta(days=1), START)
```

Install the sample package and its development tools:

```sh
uv sync --extra dev
```

Run the tests directly first:

```sh
uv run pytest
```

This first set leaves out the exact expiry boundary: day 14. That is an intentional gap in the example, not a recommended testing habit. Mutation analysis will look for behavior changes that these tests do not distinguish.

## 3. Inspect the changed code

Run the cheap scan before the full check:

```sh
gauntlet scan --changed
```

Scan asks Crapper for complexity, asks Mutator to list possible mutation sites without running them, and asks Dryer to look for structural duplication. It does not run your test or coverage commands. The first run should not have a coverage artifact yet.

## 4. Run the full check

Run:

```sh
gauntlet check --changed
```

Gauntlet runs the configured test and coverage commands, then passes the existing coverage artifact to Crapper and Mutator. It also runs Dryer. The exact mutation candidates depend on the analyzer versions and source language.

One possible survivor is a change from `< TRIAL_DAYS` to `<= TRIAL_DAYS`. The current tests check day 13 and day 15, but they do not say what should happen on day 14. Inspect the finding in `.gauntlet/results.json`, or use its ID with:

```sh
gauntlet explain FINDING_ID
```

Treat the survivor as a question about the specified behavior. Do not change production code just to make the mutation disappear.

## 5. Repair the test gap

Add the missing boundary test:

```python
def test_trial_expires_on_day_fourteen():
    assert not is_trial_active(START, START + timedelta(days=14))
```

Run the tests, then run Gauntlet again:

```sh
uv run pytest
gauntlet check --changed
```

If your source change is still in Git's changed set, `--changed` will analyze it. If you changed only the test file after committing the source, select the source explicitly or use `--all` so Gauntlet reruns the relevant analysis:

```sh
gauntlet check src/trial_policy/__init__.py
# or
gauntlet check --all
```

The boundary test should kill a comparison mutant at the trial expiry. If another mutant survives, decide whether it changes specified behavior and add a test only when that behavior matters.

## 6. Handle the other findings

- A high CRAP score on changed code is a reason to inspect complexity and meaningful test coverage. Preserve behavior while you improve the code or tests. Do not chase a target score.
- A Dryer match is a review item. Decide whether it is accidental, coincidental, or intentional before refactoring. Do not deduplicate only to remove the finding.
- If a finding is understood and intentionally accepted, add its stable ID and a non-empty reason to `.gauntlet/accept.toml`. The finding remains visible in JSON but no longer blocks.

Repeat the test and check steps until the changed behavior has evidence you trust. For an agent or CI job, use `gauntlet check --changed --json`; Gauntlet prints the structured result to standard output and saves `.gauntlet/results.json`.

For configuration options, exit codes, and policy details, see the [reference](reference.md).
