# Configuration and behavior reference

Detailed settings, analyzer behavior, policies, and exit codes. Start with the [README](../README.md) or follow the [sample project tutorial](tutorial.md).

## Configuration

`gauntlet init` creates `gauntlet.toml` and `.gauntlet/` without replacing an existing configuration.

```toml
version = 1

[gauntlet]
mode = "changed"
output = ".gauntlet/results.json"
timeout = 120

[commands]
format = "uv run ruff format --check ."
lint = "uv run ruff check ."
typecheck = "uv run mypy src"
test = "uv run pytest"
coverage = "uv run coverage run -m pytest && uv run coverage lcov -o target/coverage/python/lcov.info"

[tools.crapper]
enabled = true
threshold = 30

[tools.mutator]
enabled = true
max_workers = 4
timeout = 600

[tools.dryer]
enabled = true
threshold = 0.82
min_lines = 4
min_nodes = 20

[policy]
crap_threshold = 30
block_crap_regressions = true
block_surviving_mutants = true
block_duplicate_candidates = false

[scope]
include = ["src/domain/**", "src/services/**"]
exclude = ["**/*.generated.*", "**/migrations/**", "**/fixtures/**", "**/ui/**"]
```

Project commands run in this order: format, lint, typecheck, test, coverage. Configure only the checks the project uses. They stop the analysis when one fails. Commands are trusted local shell commands from `gauntlet.toml`; do not copy untrusted command strings into the file. Configure a coverage command that writes a format the analyzers support. Gauntlet accepts LCOV, Go `coverage.out`, JaCoCo XML, and Clojure HTML coverage. It does not parse coverage itself. The default Python detection uses the local environment's Python and `coverage.py`; other ecosystems are detected from their project files. Set commands explicitly when detection does not match the project.

Coverage is generated once by the configured coverage command. Crapper and Mutator receive `--use-existing-coverage`. Before running either tool, Gauntlet checks that an artifact exists for each selected language. A missing report fails closed. `scan` does not require coverage.

The upstream Crapper report has no file or line fields. Gauntlet runs Crapper once per selected file to preserve its source association, without guessing a function path. Mutator's function spans refine that location when available. The fallback CRAP policy uses changed files; with Mutator location data it uses changed function spans. It does not compare a historical CRAP baseline. Functions above CRAP 5 are review findings. A changed function above the configured threshold blocks by default.

Mutator outcome offsets are UTF-8 byte positions. Gauntlet checks the source bytes before turning an outcome into a finding. A surviving mutant blocks by default. Upstream Mutator currently reports killed and survived outcomes; Gauntlet also reserves state names for uncovered, invalid, equivalent, accepted, and timeout outcomes. A survivor means investigation is required. Preserve specified behavior. Add the smallest meaningful test when a mutant changes that behavior. Do not change production code only to kill a mutant.

Dryer findings are review suggestions and do not block by default. Upstream changed mode compares selected changed files with each other. It cannot find a duplicate against an unchanged file in the current release. Dryer currently does not analyze JavaScript or JSX files. Gauntlet marks Dryer as skipped when the selection contains no language Dryer supports.

## Commands

```text
gauntlet check [--changed | --all] [PATH ...]
gauntlet scan [--changed | --all] [PATH ...]
gauntlet doctor
gauntlet init
gauntlet explain FINDING_ID
```

`check` runs prerequisites, coverage, and enabled analyzers. `scan` inspects complexity, mutation sites, and duplication without executing mutants or test commands. `doctor` checks Git, configuration, installed commands, project tools, and coverage artifacts without executing project commands. `explain` reads `.gauntlet/results.json` and presents one finding. Use `--no-crap`, `--no-mutate`, or `--no-dry` to skip an analyzer for a run. You can pass `--output PATH` to write the JSON result elsewhere.

Each tool accepts an installed executable through configuration:

```toml
[tools.crapper]
command = "../crapper/.venv/bin/crapper"

[tools.mutator]
command = "../mutator/.venv/bin/mutator"

[tools.dryer]
command = "../dryer/.venv/bin/dryer"
```

The `checkout` field can point to a sibling checkout with an installed `.venv/bin` executable. Gauntlet does not invoke upstream bootstrap scripts.

## Findings and policy

The result has schema `version: 1`, stable IDs, sorted findings, checks, and a summary. Every finding has a general severity (`info`, `review`, `warning`, or `error`), a location when the tool can supply one, tool metadata, and a `blocking` decision. Reports contain no timestamps or durations, so equivalent repository and analyzer state produces stable JSON.

High CRAP in an unchanged function does not block. CRAP regression checks use changed function spans when Mutator supplies them; without those spans, the initial policy uses changed files as an approximation. Moderate CRAP and Dryer candidates need review. A surviving mutant blocks by default. These rules do not reward 100% coverage, a perfect mutation score, zero duplication, or minimum complexity.

To accept a known finding, add an ID and a reason to `.gauntlet/accept.toml`:

```toml
[[finding]]
id = "mutator:0123456789abcdef01234567"
reason = "Equivalent for the validated integer-only input domain."
```

Accepted findings remain in JSON and no longer block. Gauntlet reports acceptance entries that were not observed in the current run; this can happen when a changed-only run does not include the finding.

## Agent instructions

Add a project-specific definition of done to `AGENTS.md`:

```md
## Definition of Done

Before considering a coding task complete, run `gauntlet check`.

Do not bypass or weaken Gauntlet checks.

For surviving mutants, determine whether the mutant changes specified
observable behavior. If it does, add or improve the smallest meaningful test.
Do not modify production code solely to kill a mutant.

For CRAP findings, preserve behavior. Simplify excessive branching or improve
meaningful tests when appropriate.

For Dryer findings, do not automatically deduplicate. First determine whether
the similarity is accidental, intentional, coincidental, or indicates a
missing domain abstraction.

Re-run Gauntlet after making repairs.
```

CI can run the same local command without a Gauntlet server or provider API:

```yaml
- name: Gauntlet
  run: gauntlet check --changed --json
```

Archive `.gauntlet/results.json` as a CI artifact if useful. Gauntlet does not upload source or findings.

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | Passed; review findings can be present |
| `1` | Gauntlet or analyzer error |
| `2` | Prerequisite command or Mutator baseline failed |
| `3` | A blocking finding was reported |
| `4` | Invalid configuration, path, or repository context |
| `5` | Required external tool, command, or coverage artifact is missing |
