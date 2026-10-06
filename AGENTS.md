# Repository Guidelines

## Project Structure

- `src/gauntlet/` contains the CLI package. Keep analyzer integrations in `adapters/`, orchestration and policy in `pipeline/`, and output formatting in `reporters/`.
- `tests/unit/` covers focused behavior; `tests/integration/` exercises the CLI. `tests/fixtures/` holds sample repositories and source files.
- `README.md` documents user-facing behavior and configuration. `pyproject.toml` defines package metadata and tool settings; `uv.lock` pins development dependencies.

## Build, Test, and Development

Use Python 3.12 or newer. Run `uv sync --extra dev` to install the package and development tools.

- `uv run python -m unittest discover -s tests -v` runs unit and CLI integration tests.
- `uv run ruff check src tests` runs lint checks.
- `uv run ruff format --check src tests` verifies formatting.
- `uv build` builds the distributable package.
- `uv run python -m gauntlet --help` runs the CLI from the checkout.

## Coding Style

Use four spaces for indentation, type hints for public functions, and descriptive `snake_case` names. Follow Ruff's 100-character line limit and configured rules (`E`, `F`, `I`, `B`, `UP`, `C90`); keep function complexity at or below 12. Keep CLI JSON output stable and send diagnostics to standard error when `--json` is active.

## Tests and Quality Checks

Name test modules `test_*.py` and test methods `test_<behavior>`. Add focused unit coverage for domain and policy changes, plus CLI integration coverage when commands, exit codes, or output change. Before finishing code changes, run the relevant tests and Ruff checks. Run `gauntlet check` when the repository's configuration and analyzer tools are available; do not weaken checks to clear a finding.

## Commits and Pull Requests

Use scoped imperative messages such as `fix(cli): keep JSON output clean` or `feature(policy): report accepted findings`. A pull request should explain the behavior change, list checks run, and link a related issue when one exists. For CLI changes, include a short command example and describe any output or exit-code changes.

## Configuration and Safety

Gauntlet runs configured project commands from `gauntlet.toml` in a local shell. Treat these commands as trusted code: review them before running, and do not copy untrusted command strings into configuration. Keep analyzer integrations as external CLI calls; do not add hidden downloads or network uploads.
