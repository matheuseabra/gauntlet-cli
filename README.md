<p align="center">
  <img src="docs/assets/gauntlet-logo.png" alt="Gold cosmic gauntlet with six luminous stones" width="240">
</p>

<h1 align="center">Gauntlet</h1>

<p align="center"><strong>Make the code prove itself.</strong></p>

<p align="center">
  <a href="https://github.com/matheuseabra/gauntlet-cli/blob/main/pyproject.toml"><img src="https://img.shields.io/badge/version-0.1.0-4c6ef5?logo=python&logoColor=white" alt="Version 0.1.0"></a>
  <a href="https://github.com/matheuseabra/gauntlet-cli/actions/workflows/ci.yml"><img src="https://github.com/matheuseabra/gauntlet-cli/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI status"></a>
  <a href="https://github.com/matheuseabra/gauntlet-cli/blob/main/LICENSE"><img src="https://img.shields.io/github/license/matheuseabra/gauntlet-cli" alt="MIT License"></a>
</p>

Gauntlet runs local quality checks on **changed code** and turns the results into actionable findings for you, CI, or a coding agent.

It uses three external analyzers:

| Tool | Question it answers |
| --- | --- |
| **Crapper** | Is this code too complex for its test coverage? |
| **Mutator** | Would the tests notice a plausible defect? |
| **Dryer** | Is similar code appearing in multiple places? |

## Acknowledgments

Gauntlet builds on three tools by [Robert C. Martin (Uncle Bob)](https://github.com/unclebob): [Crapper](https://github.com/unclebob/crapper), [Mutator](https://github.com/unclebob/mutator), and [Dryer](https://github.com/unclebob/dryer).

Gauntlet produces evidence. You or your coding agent investigate and repair the findings.

## How it works

`gauntlet check` runs this pipeline. A failed prerequisite stops analysis early. Coverage is generated once or reused. Findings appear in the terminal and in `.gauntlet/results.json`.

## Get started

You need **Python 3.12+**, **Git**, and the [Crapper](https://github.com/unclebob/crapper), [Mutator](https://github.com/unclebob/mutator), and [Dryer](https://github.com/unclebob/dryer) executables on your `PATH`. Install the analyzers separately.

Install Gauntlet from this checkout:

```sh
uv tool install .
# Alternative: pipx install .
```

Then, inside the project you want to check:

```sh
gauntlet init
# Set your test and coverage commands in gauntlet.toml when needed.
gauntlet doctor
gauntlet check
```

Gauntlet detects common project commands. Explicit configuration overrides them. For example, a Python project using pytest and coverage.py can add:

```toml
[commands]
test = "uv run pytest"
coverage = "uv run coverage run -m pytest && uv run coverage lcov -o target/coverage/python/lcov.info"
```

Configure only commands your project uses. `doctor` checks readiness without running tests. Follow the [sample project tutorial](docs/tutorial.md) for a complete walkthrough.

## Everyday commands

| Command | Use it to… |
| --- | --- |
| `gauntlet` or `gauntlet check` | Check staged, unstaged, and untracked source changes |
| `gauntlet check --all` | Check the entire repository |
| `gauntlet check src/domain` | Check a specific file or directory |
| `gauntlet scan` | Inspect hotspots without tests, coverage, or mutation execution |
| `gauntlet check --json` | Get JSON-only output for an agent or CI |
| `gauntlet explain FINDING_ID` | Inspect a finding from the saved report |

An empty source change passes. Use `--verbose` for command diagnostics or `--quiet` to suppress terminal output. Run `gauntlet check --help` for all options.

## Act on findings

| Finding | Default | What to do |
| --- | --- | --- |
| Surviving mutant | Blocks | Determine whether behavior changed. If it did, add the smallest meaningful test. |
| High CRAP on changed code | Blocks | Simplify branching or improve meaningful tests while preserving behavior. |
| Structural duplication | Review | Decide whether the similarity is accidental, intentional, or coincidental before refactoring. |

A survivor requires investigation. Do not change production behavior just to kill a mutant, or deduplicate code just to remove a finding. Known findings can be accepted with an ID and a reason in `.gauntlet/accept.toml`.

A passing check exits with `0`; blocking findings exit with `3`. Review findings alone pass. See the [reference](docs/reference.md#exit-codes) for error exit codes.

## Use with a coding agent or CI

Add this rule to your project's `AGENTS.md`:

```md
Before finishing a coding task, run `gauntlet check`.
Investigate findings, preserve specified behavior, and rerun after repairs.
Do not bypass or weaken the checks.
```

For machine-readable results, run `gauntlet check --json`. It prints only JSON to stdout and also saves `.gauntlet/results.json`. Gauntlet runs locally and makes no LLM calls or source uploads.

## More details

- [Tutorial](docs/tutorial.md): build a sample project and repair a test gap.
- [Reference](docs/reference.md): configuration, coverage, accepted findings, CI, and exit codes.
- [Architecture](docs/architecture.md): modules, adapter boundaries, and execution flow.

## Develop Gauntlet

```sh
uv sync --extra dev
uv run python -m unittest discover -s tests -v
uv run ruff check src tests
uv run ruff format --check src tests
uv run gauntlet --help
```
