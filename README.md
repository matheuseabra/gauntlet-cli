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

Gauntlet runs three complementary checks on **changed source files by default** and turns the results into deterministic, actionable findings: in your terminal, in CI, or fed straight back to a coding agent that can fix them.

It's built on three analyzers by Robert C. Martin ([Uncle Bob](https://github.com/unclebob)). Gauntlet orchestrates them, scopes them to your diff, and merges their output into one report:

| Analyzer | Question it answers | Why it matters |
| --- | --- | --- |
| [**Crapper**](https://github.com/unclebob/crapper) | Is this code too complex for its test coverage? | Complexity without tests is where regressions live. |
| [**Mutator**](https://github.com/unclebob/mutator) | Would the tests notice a plausible defect? | Finds behavior changes the tests do not distinguish. |
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

`gauntlet check` selects source files, runs configured prerequisites and coverage,
then invokes Crapper, Mutator, and Dryer. A failed prerequisite stops analysis
early. Coverage is generated once or reused. Findings appear in the terminal and
are saved to `.gauntlet/results.json`. Mutator examines functions in selected
files; it is not restricted to changed lines. CRAP blocking uses changed function
spans when available, with a changed-file fallback.

## Get started

You need **Python 3.12+**, **Git**, and network access for explicit tool setup.
From a reviewed checkout of this repository, install Gauntlet and the compatible
pinned analyzers together, then activate the environment:

```bash
bash scripts/setup-tools.sh "$HOME/.local/share/gauntlet/tools"
source "$HOME/.local/share/gauntlet/tools/bin/activate"
```

Set `GAUNTLET_PYTHON` if your compatible interpreter has a different name. This
installer owns analyzer dependencies and parser grammar setup. It does not install
your project's runtime or dependencies, and `check` never invokes it.

If you already manage analyzer executables, `uv tool install .` or `pipx install .`
installs only Gauntlet; make the compatible tools available on `PATH` or configure
their executable paths. See [explicit setup](docs/reference.md#explicit-tool-setup).

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
test = "python -m pytest"
coverage = "python -m coverage run -m pytest && python -m coverage lcov -o target/coverage/python/lcov.info"
```

Run those commands with the project Python and dependencies already available on
PATH. Mutator runs the test command in isolated worker directories; avoid
installing or syncing environments inside each mutant run. Configure only the commands your project uses. `doctor` checks readiness without running tests. For a complete walkthrough, follow the [sample project tutorial](https://github.com/matheuseabra/gauntlet-cli/blob/main/docs/tutorial.md).

## Everyday commands

| Command | Use it to… |
| --- | --- |
| `gauntlet` or `gauntlet check` | Check staged, unstaged, and untracked source changes |
| `gauntlet check --all` | Check the entire repository |
| `gauntlet check --base main` | Check committed changes from the merge base with `main` to the checked-out `HEAD` |
| `gauntlet check src/domain` | Check a specific file or directory |
| `gauntlet scan` | Inspect hotspots without tests, coverage, or mutation execution |
| `gauntlet check --json` | Get JSON-only output for an agent or CI |
| `gauntlet explain FINDING_ID` | Inspect a finding from the saved report |

An empty source selection passes without running project commands or analyzers; it does not verify unsupported source, test-only changes, or product behavior. Use `--verbose` for command diagnostics or `--quiet` to suppress terminal output. Run `gauntlet check --help` for all options.

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
Before finishing uncommitted work, run `gauntlet check --changed`.
For committed PR changes, use `gauntlet check --base BASE_SHA` on a clean tracked tree.
Report the selected scope and native validation alongside the gate result.
Classify each survivor as real gap / equivalent / out-of-scope before acting.
For a real gap, add a meaningful specification-based test.
Record equivalents in accept.toml with a stable ID and concrete reason.
Do not contort tests or change production behavior solely to kill a mutant.
Preserve specified behavior and rerun after repairs.
Do not bypass or weaken the checks.
```

For machine-readable results, run `gauntlet check --json`. It prints only JSON to stdout and also saves `.gauntlet/results.json`. The same command works in CI, where a non-zero exit code fails the build on blocking findings.

On a clean CI checkout, use `gauntlet check --base BASE_SHA --json`; working-tree
`--changed` does not select committed PR changes. Fetch base/head history first.
`--base` requires a clean tracked working tree, excludes untracked/deleted files,
and preserves committed line ranges for CRAP policy. JSON records the resolved
base, head, and merge-base SHAs. It can also be used with `scan` and explicit paths.

For explicit installation of Gauntlet and compatible pinned analyzers, run
`bash scripts/setup-tools.sh /path/to/tool-environment` from this checkout,
then activate that environment. Setup uses the network; analysis does not invoke
setup. The [setup action](action.yml) runs the same installer in GitHub Actions:

```yaml
- uses: actions/checkout@v4
  with:
    ref: ${{ github.event.pull_request.head.sha }}
    fetch-depth: 0
    persist-credentials: false
- uses: matheuseabra/gauntlet-cli@<reviewed-commit-sha>
- run: gauntlet check --base "$BASE_SHA" --json
  env:
    BASE_SHA: ${{ github.event.pull_request.base.sha }}
```

Run this example in a secretless `pull_request` job with read-only permissions.
Install project runtimes and locked dependencies separately. Local/cloud agents
must run setup inside their own environment; GitHub runner installation does
not provision a remote agent.

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
uv build
uv run gauntlet --help
# With the shared tool environment activated:
bash tests/integration/smoke_setup.sh
```

## License

[MIT](https://github.com/matheuseabra/gauntlet-cli/blob/main/LICENSE)
