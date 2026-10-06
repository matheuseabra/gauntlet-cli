# Tutorial: Build a Small Project with Gauntlet

This walkthrough builds a date-based trial policy, adds tests, runs Gauntlet, and repairs a test gap. It shows the workflow around your code; Gauntlet does not write or change the project for you.

You need Python 3.12+, Git, and `uv`. From a reviewed Gauntlet checkout, explicitly
install the CLI, pinned analyzers, and parser grammars into one environment:

```sh
bash scripts/setup-tools.sh "$HOME/.local/share/gauntlet/tools"
. "$HOME/.local/share/gauntlet/tools/bin/activate"
```

Keep that tool environment active while following the tutorial. Project
dependencies are installed separately below. `check` does not install tools or
run the setup script. See [explicit setup](reference.md#explicit-tool-setup) for
interpreter selection and the reusable GitHub action.

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
test = "python -m pytest"
coverage = "python -m coverage run -m pytest && python -m coverage lcov -o target/coverage/python/lcov.info"
```

The coverage command writes LCOV to a path Gauntlet and the upstream analyzers can read. After installing the sample dependencies, run `gauntlet doctor` to check the
project commands and analyzer executables. Doctor checks executable presence;
it does not run tests, generate coverage, or verify analyzer dependency imports.
`coverage-artifact: not-generated` is expected before the first full check when a
coverage command is configured.

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
export PATH="$(pwd)/.venv/bin:$PATH"
```

This exposes the installed project Python while keeping the Gauntlet tool
environment on PATH. Configured test commands use `python -m pytest` so mutation
workers run the installed dependencies directly, without creating or syncing a
new environment for every mutant. Mutator executes the test command from each
worker directory, where the source file is a private mutated copy.

Run the tests directly first:

```sh
uv run pytest
```

This first set leaves out the exact expiry boundary: day 14. That is an intentional gap in the example, not a recommended testing habit. Mutation analysis looks for behavior changes the tests do not distinguish. A passing gate can still miss defects outside an analyzer's mutation inventory.

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

With the pinned analyzers, the expiry comparison can survive a change from `< TRIAL_DAYS` to `<= TRIAL_DAYS`. The current tests check day 13 and day 15, but they do not say what should happen on day 14. Inspect the finding in `.gauntlet/results.json`, or use its ID with:

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

If your source change is still in Git's changed set, `--changed` will analyze it.
Tests are excluded from source selection, so changing only a test after committing
the source does not select that source again. Select it explicitly or use `--all`
to rerun its analysis:

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

Repeat the test and check steps until the changed behavior has evidence you trust.
For an agent working on uncommitted code, use `gauntlet check --changed --json`.
Gauntlet prints the structured result and saves `.gauntlet/results.json`.

## 7. Check committed changes

A clean checkout has no working-tree source changes. To inspect this example's
committed source, use a baseline that precedes it. After the repaired check passes,
you can create an empty baseline and commit the sample:

```sh
git -c user.name=Tutorial -c user.email=tutorial@example.invalid commit --allow-empty -m baseline
BASE_SHA="$(git rev-parse HEAD)"
git add .
git -c user.name=Tutorial -c user.email=tutorial@example.invalid commit -m 'implement trial policy and boundary tests'
gauntlet check --base "$BASE_SHA" --json
```

`--base` compares the unique merge base with the checked-out `HEAD`. It requires a
clean tracked working tree and includes committed changed-line ranges for CRAP
policy. Untracked files and deleted files are excluded. The report records
`repository.base_sha`, `head_sha`, and `merge_base_sha`.

In a PR job, check out the intended head, fetch complete history, and use the PR
base SHA. Install tools and project dependencies in that job's runtime; a runner's
setup does not provision a remote agent. See the [CI example](reference.md#ci).
An empty selected-source pass skips native commands and analyzers; always report
scope and run the project's native validation separately when needed.

For configuration options, exit codes, and policy details, see the [reference](reference.md).
