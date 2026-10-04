<div align="center">

<img src="docs/assets/gauntlet-logo.png" alt="Gold cosmic gauntlet with six luminous stones" width="220">

# Gauntlet

**Make the code prove itself.**

[![Version 0.1.0](https://img.shields.io/badge/version-0.1.0-4c6ef5?logo=python&logoColor=white)](https://github.com/matheuseabra/gauntlet-cli/blob/main/pyproject.toml)
[![CI status](https://github.com/matheuseabra/gauntlet-cli/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/matheuseabra/gauntlet-cli/actions/workflows/ci.yml)
[![MIT License](https://img.shields.io/github/license/matheuseabra/gauntlet-cli)](https://github.com/matheuseabra/gauntlet-cli/blob/main/LICENSE)

</div>

## The problem

Green tests and high coverage don't mean the code is safe to change.

Coverage tells you a line *ran*, not that a test would *notice* if it broke. Complex code with thin tests is where regressions hide, and copy-pasted logic quietly drifts apart over time. Each of these problems has a good tool, but the tools run separately, report in different shapes, and look at the whole codebase instead of the code you just touched.

Coding agents make this worse. They produce a lot of code and a lot of passing tests very quickly, but nothing checks whether those tests assert anything meaningful. "Tests pass" becomes a weak signal, and human review becomes the bottleneck.

## What Gauntlet does

Gauntlet runs three complementary checks on **only the code you changed** and turns the results into deterministic, actionable findings: in your terminal, in CI, or fed straight back to a coding agent that can fix them.

It's built on three analyzers by Robert C. Martin ([Uncle Bob](https://github.com/unclebob)). Gauntlet orchestrates them, scopes them to your diff, and merges their output into one report:

| Analyzer | Question it answers | Why it matters |
| --- | --- | --- |
| [**Crapper**](https://github.com/unclebob/crapper) | Is this code too complex for its test coverage? | Complexity without tests is where regressions live. |
| [**Mutator**](https://github.com/unclebob/mutator) | Would the tests notice a plausible defect? | Proves tests assert behavior, not just execute lines. |
| [**Dryer**](https://github.com/unclebob/dryer) | Is similar code appearing in multiple places? | Catches duplication before the copies diverge. |

Gauntlet produces evidence. You or your coding agent investigate and repair the findings. It runs entirely on your machine: no LLM calls and no source uploads.

<!--
TODO: add a "What a finding looks like" section here with real output, e.g.

## What a finding looks like

```
<paste real `gauntlet check` output>
```
-->

## How it works

```
git diff ─► coverage (generated or reused) ─► Crapper ─► Mutator ─► Dryer
                                                                      │
                                        terminal findings + .gauntlet/results.json
```

`gauntlet check` runs this pipeline on your changed source files. A failed prerequisite stops analysis early. Coverage is generated once or reused. Findings appear in the terminal and are saved to `.gauntlet/results.json`.

## Get started

You need:

- **Python 3.12+** and **Git**
- The [Crapper](https://github.com/unclebob/crapper), [Mutator](https://github.com/unclebob/mutator), and [Dryer](https://github.com/unclebob/dryer) executables on your `PATH`. Install these separately; `gauntlet doctor` will tell you what's missing.

Install Gauntlet from this checkout:

```bash
uv tool install .
# Alternative: pipx install .
```

Then, inside the project you want to check:

```bash
gauntlet init
# Set your test and coverage commands in gauntlet.toml when needed.
gauntlet doctor
gauntlet check
```

Gauntlet detects common project commands, and explicit configuration overrides them. For example, a Python project using pytest and coverage.py can add:

```toml
[commands]
test = "uv run pytest"
coverage = "uv run coverage run -m pytest && uv run coverage lcov -o target/coverage/python/lcov.info"
```

Configure only the commands your project uses. `doctor` checks readiness without running tests. For a complete walkthrough, follow the [sample project tutorial](https://github.com/matheuseabra/gauntlet-cli/blob/main/docs/tutorial.md).

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

A survivor requires investigation. Don't change production behavior just to kill a mutant, or deduplicate code just to remove a finding. Known findings can be accepted with an ID and a reason in `.gauntlet/accept.toml`.

A passing check exits with `0`; blocking findings exit with `3`. Review findings alone pass. See the [reference](https://github.com/matheuseabra/gauntlet-cli/blob/main/docs/reference.md#exit-codes) for error exit codes.

## Use with a coding agent or CI

Give your agent a gate it can't talk its way past. Add this rule to your project's `AGENTS.md`:

```text
Before finishing a coding task, run `gauntlet check`.
Investigate findings, preserve specified behavior, and rerun after repairs.
Do not bypass or weaken the checks.
```

For machine-readable results, run `gauntlet check --json`. It prints only JSON to stdout and also saves `.gauntlet/results.json`. The same command works in CI, where a non-zero exit code fails the build on blocking findings.

## More details

- [Tutorial](https://github.com/matheuseabra/gauntlet-cli/blob/main/docs/tutorial.md): build a sample project and repair a test gap.
- [Reference](https://github.com/matheuseabra/gauntlet-cli/blob/main/docs/reference.md): configuration, coverage, accepted findings, CI, and exit codes.
- [Architecture](https://github.com/matheuseabra/gauntlet-cli/blob/main/docs/architecture.md): modules, adapter boundaries, and execution flow.

## Contributing

```bash
uv sync --extra dev
uv run python -m unittest discover -s tests -v
uv run ruff check src tests
uv run ruff format --check src tests
uv run gauntlet --help
```

## License

[MIT](https://github.com/matheuseabra/gauntlet-cli/blob/main/LICENSE)
