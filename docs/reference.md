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
test = "python -m pytest"
coverage = "python -m coverage run -m pytest && python -m coverage lcov -o target/coverage/python/lcov.info"

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

Configuration rejects unknown keys, invalid types, and unsupported versions. `tools.crapper.threshold` supplies the default `policy.crap_threshold` unless the policy explicitly overrides it. Project commands run in this order: format, lint, typecheck, test, coverage. Configure only the checks the project uses. They stop the analysis when one fails. Commands are trusted local shell commands from `gauntlet.toml`; do not copy untrusted command strings into the file. Configure a coverage command that writes a format the analyzers support. Gauntlet accepts LCOV, Go `coverage.out`, JaCoCo XML, and Clojure HTML coverage. It does not parse coverage itself. The default Python detection uses the local environment's Python and `coverage.py`; other ecosystems are detected from their project files. Set commands explicitly when detection does not match the project.

Coverage is generated once by the configured coverage command. Crapper and Mutator receive `--use-existing-coverage`. Before running either tool, Gauntlet checks that an artifact exists for each selected language. A missing report fails closed. `scan` does not require coverage.

The upstream Crapper report has no file or line fields. Gauntlet runs Crapper once per selected file to preserve its source association, without guessing a function path. Mutator's function spans refine that location when available. The fallback CRAP policy uses changed files; with Mutator location data it uses changed function spans. It does not compare a historical CRAP baseline. Scores above CRAP 5 are review findings; scores above the configured threshold have warning severity and block by default when policy considers the function changed.

Mutator outcome offsets are UTF-8 byte positions. Gauntlet checks the source bytes before turning an outcome into a finding. A surviving mutant blocks by default. Upstream Mutator currently reports killed and survived outcomes; Gauntlet also reserves state names for uncovered, invalid, equivalent, accepted, and timeout outcomes. A survivor means investigation is required. Preserve specified behavior. Add the smallest meaningful test when a mutant changes that behavior. Do not change production code only to kill a mutant.

On a mutation cache miss, Gauntlet forces upstream `--mutate-all`: a previous
killed result must not hide a gap after tests change. Complete, validated raw
snapshots can be reused through Gauntlet's content cache. Policy, acceptance, and
covering-test context attribution are reapplied on every run. Killed outcomes
are omitted from findings; uncovered-site counts remain nonblocking warnings.

Dryer findings are review suggestions and do not block by default. Upstream changed mode compares selected changed files with each other. It cannot find a duplicate against an unchanged file in the current release. Dryer currently does not analyze JavaScript or JSX files. Preflight fails when selected JavaScript needs enabled Dryer; explicitly disabling that analyzer permits Crapper and Mutator. See the [support matrix](language-support.md).

## Commands

```text
gauntlet check [--changed | --all | --base REF] [--max-mutants N] [--timeout SECONDS] [PATH ...]
gauntlet scan [--changed | --all | --base REF] [PATH ...]
gauntlet doctor [--json]
gauntlet init
gauntlet explain FINDING_ID
```

With selected source files, `check` runs prerequisites, coverage, and enabled analyzers. `scan` inspects complexity, mutation sites, and duplication without executing mutants or test commands. `doctor` checks Git, configuration, installed commands, project tools, and coverage artifacts without executing project commands. `explain` reads `.gauntlet/results.json` and presents one finding; `--input PATH` selects another saved report. Use `--no-crap`, `--no-mutate`, or `--no-dry` to skip an analyzer for a run. You can pass `--output PATH` to write the JSON result elsewhere.

Each tool accepts an installed executable through configuration:

```toml
[tools.crapper]
command = "../crapper/.venv/bin/crapper"

[tools.mutator]
command = "../mutator/.venv/bin/mutator"

[tools.dryer]
command = "../dryer/.venv/bin/dryer"
```

The `checkout` field can point to a sibling checkout with an installed `.venv/bin`
executable. Resolution checks `PATH` first, then `command`, then `checkout`; a
configured path does not override a same-named executable already on `PATH`.
Paths are resolved relative to the repository root, and `command` is an executable
path, not a shell command with arguments. Gauntlet does not invoke upstream
bootstrap scripts. Each tool accepts `enabled` and `timeout` (default 600 seconds).
`gauntlet.timeout` (default 120 seconds) applies to project commands.

### Detected project commands

Explicit `[commands]` entries override detected commands. Detection takes the
first matching root manifest; it does not aggregate every package in a monorepo.
Configure mixed-language projects explicitly.

| Root manifest | Defaults |
| --- | --- |
| `package.json` | Declared `test`/`coverage` scripts via npm, Bun, pnpm, or Yarn |
| `pyproject.toml` or `requirements.txt` | Local project Python when available, pytest when detected or unittest discovery, and coverage.py LCOV |
| `go.mod` | `go test ./...` and `-coverprofile=coverage.out` |
| `Cargo.toml` | `cargo test` and `cargo llvm-cov` LCOV; install llvm-cov separately |
| `pom.xml` | `mvn -q test`; configure coverage generation explicitly |

Clojure and projects without a detected manifest need explicit commands or a
supported existing coverage report. Detection does not install dependencies. Mutator runs the test command in isolated
worker directories with private source copies. Use the already-installed project
interpreter/dependencies; an absolute interpreter path is also valid. Avoid
commands that sync, install, or rebuild an environment for every mutant, and check
that the runner imports worker sources rather than the original checkout.

### Selection and output options

| Option | Behavior |
| --- | --- |
| `--changed` | Staged, unstaged, and untracked source files; default unless configured otherwise |
| `--all` | All supported source files under the repository's filters |
| `--base REF` | Existing committed changes from REF's unique merge base to HEAD |
| `PATH ...` | Restrict to existing repository files/directories; without an explicit mode, selects `all` |
| `--json` | JSON-only stdout; also writes the configured report for prepared check/scan runs |
| `--output PATH` | Override the report path (relative paths start at the repository root) |
| `--quiet` | Suppress terminal output; does not suppress requested JSON |
| `--verbose` | Print prerequisite/analyzer command diagnostics to stderr |
| `--no-crap`, `--no-mutate`, `--no-dry` | Disable the corresponding analyzer for this invocation |

`--base`, `--changed`, and `--all` are mutually exclusive. Explicit paths further
restrict the chosen mode. Include/exclude patterns are relative to the repository;
`**` matches zero or more path segments. These filters do not override built-in
source exclusions.

Supported extensions are Python (`.py`), TypeScript (`.ts`, `.tsx`, `.mts`, `.cts`),
JavaScript (`.js`, `.jsx`, `.mjs`, `.cjs`), Go (`.go`), Rust (`.rs`), Java (`.java`),
and Clojure (`.clj`, `.cljc`, `.cljs`, `.bb`). Test/spec filenames and directories,
TypeScript declarations (`.d.ts`), dependencies, build outputs, and Gauntlet state
are excluded; see [`discovery.py`](../src/gauntlet/discovery.py) for the complete
filter list. Recognized unsupported code, including Swift and Shell, fails preflight unless intentionally excluded by scope. Markdown and workflow assets are not analyzed. Unknown code extensions are unverified.

An empty selection passes after language/configuration/acceptance validation, without
checking analyzer executables, running project commands, or requiring coverage.
This includes a test-only change: a pass does not prove those tests ran. Run native
validation separately and include `repository.selected_files` in your handoff.

Doctor inspects executable presence and available coverage paths; it does not run
commands or verify dependency imports. A coverage command may be available before
its artifact exists. Missing coverage is a readiness error when neither a report
nor a coverage command exists and a coverage-dependent analyzer is enabled.

## Findings and policy

The result has schema `version: 1`, stable IDs, sorted findings, checks, and a summary. Every finding has a general severity (`info`, `review`, `warning`, or `error`), a location when the tool can supply one, tool metadata, and a `blocking` decision. Finding IDs and sorting are stable; `timings_ms` and mutation cache/budget metadata vary between runs. Whole reports are not byte-stable.

High CRAP in an unchanged function does not block when Mutator supplies function
spans. Without those spans, CRAP policy uses changed files as an approximation,
so another change in the same file can make a function block. Despite the option
name `block_crap_regressions`, this compares no historical CRAP score. `--all` and
explicit-path runs broaden analysis but still base CRAP blocking on working-tree
changes; `--base` uses committed changed lines instead. Moderate CRAP and Dryer candidates need review. A surviving mutant blocks by default. These rules do not reward 100% coverage, a perfect mutation score, zero duplication, or minimum complexity.

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

Before finishing uncommitted work, run `gauntlet check --changed`.
For committed PR changes, use `gauntlet check --base BASE_SHA` on a clean tracked tree.
Report selected source scope and native validation results.

Do not bypass or weaken Gauntlet checks.

Classify each survivor as real gap / equivalent / out-of-scope against specified
observable behavior. For real gaps, add a meaningful specification-based test.
Record equivalents in accept.toml with a stable ID and concrete reason.
Do not contort tests or modify production behavior solely to kill a mutant.

For CRAP findings, preserve behavior. Simplify excessive branching or improve
meaningful tests when appropriate. Do not split functions solely to lower a score.

For Dryer findings, do not automatically deduplicate. First determine whether
the similarity is accidental, intentional, coincidental, or indicates a
missing domain abstraction.

Re-run Gauntlet after making repairs.
```

## Committed comparisons

`--base REF` is mutually exclusive with `--changed` and `--all`. It resolves REF
and checked-out HEAD, requires a clean tracked working tree, and selects existing
files changed since their unique merge base. Untracked files and deletions are
excluded. Paths can further limit this selection. Missing/shallow history,
invalid refs, or ambiguous merge bases fail with exit 4; no fallback full scan is
performed. An empty selection passes without analysis. Changed line ranges come
from the committed comparison, so high CRAP in an unchanged function remains
nonblocking when function spans are available. This is not historical CRAP score
comparison; Mutator still examines selected files rather than changed lines only.

Results add `repository.base_sha`, `head_sha`, and `merge_base_sha` for these runs.
The report schema stays at version 1 with additive repository metadata.

## Explicit tool setup

`bash scripts/setup-tools.sh ENVIRONMENT_PATH` installs this checkout's Gauntlet
and external analyzers from `requirements-tools.txt` in one isolated environment.
Python 3.12+ is required; use `GAUNTLET_PYTHON` to select an interpreter. It also
prefetches supported parser grammars. Setup is network-enabled and separate from
the CLI: checks never invoke it, clone dependencies, or silently install tools.
Activate `ENVIRONMENT_PATH/bin/activate` in each shell that runs checks. The script
selects `GAUNTLET_PYTHON` when set, otherwise `python3.12` when available, then
`python3`, and rejects versions below 3.12. It installs this checkout and the pinned
analyzer/coverage/parser dependencies together so Mutator can import Crapper.
It prefetches Python, TypeScript, TSX, JavaScript, Go, Rust, Java, and Clojure grammars.
The Bash installer targets environments with Unix `bin` directories.

Use the root [`action.yml`](../action.yml) at a reviewed immutable commit for the
same setup in Actions. It adds executables to PATH and exposes a `bin-path` output.
Its `python-version` input defaults to `3.12`; `environment-path` defaults to
`${{ runner.temp }}/gauntlet-tools`. Analyzer pins and Python dependency versions
live in [`requirements-tools.txt`](../requirements-tools.txt); review changes to
that file and the installer when updating your pinned Gauntlet revision.

Project dependencies and commands remain the consumer's responsibility. Bootstrap
each cloud agent inside its own runtime, or use a provisioned environment; setup
on the GitHub runner is insufficient for remote execution.

## CI

Use a secretless `pull_request` job with read-only permissions. Check out the
intended PR head and fetch its base history before running committed comparison.
Replace the setup action placeholder with a reviewed full commit SHA:

```yaml
name: Quality Gate
on: pull_request
permissions:
  contents: read
jobs:
  gauntlet:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          fetch-depth: 0
          persist-credentials: false
      - uses: matheuseabra/gauntlet-cli@<reviewed-commit-sha>
      # Install project runtimes and locked dependencies here.
      # Run native validation separately if empty-source selections must test them.
      - name: Gauntlet
        env:
          BASE_SHA: ${{ github.event.pull_request.base.sha }}
        run: |
          python -c "from pathlib import Path; Path('.gauntlet/results.json').unlink(missing_ok=True)"
          gauntlet check --base "$BASE_SHA" --json
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: gauntlet-pr-${{ github.event.pull_request.number }}-${{ github.event.pull_request.head.sha }}
          path: .gauntlet/results.json
          if-no-files-found: warn
```

Early argument, configuration, path, or Git-context errors print JSON with
`--json` but may occur before the report file is written. Clear old reports first;
a missing or stale report cannot establish a pass. The job exit code remains the
gate. Prepared pipeline failures are saved with their diagnostics. A report-write
failure itself exits 1 and cannot produce a usable report at that path.

Gauntlet does not upload evidence; artifact upload is the workflow's explicit
step. Bind evidence to the repository, PR, and intended head SHA. Reviewers should
treat artifacts as untrusted data and check their selected scope and commit
provenance. Coverage validation checks nonempty artifact presence and its format's
applicability to selected languages, not that it belongs to the current commit.
Generate coverage for the intended head rather than reusing unrelated reports.

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | Passed; review findings can be present |
| `1` | Gauntlet or analyzer error |
| `2` | Prerequisite command or Mutator baseline failed |
| `3` | A blocking finding was reported |
| `4` | Invalid configuration, path, or repository context |
| `5` | Required external tool, command, or coverage artifact is missing |
| `6` | Mutation analysis partial with no blocking finding (never a pass) |

## Mutation triage and acceptance hygiene

Survivors retain their stable ID and source location, plus `mutation_description`,
`triage_guidance`, `covering_tests`, and `covering_tests_provenance`. Named covering
tests come only from coverage.py contexts for the exact mutated line, when present
in `.coverage`. Plain LCOV does not identify tests. An empty list means unavailable,
not that no test covers the line; context evidence must belong to the current run.
`explain` asks for a specification-based real-gap/equivalent/out-of-scope classification.

An acceptance requires `id` and a nonempty `reason`; optional `expires = 2026-12-31`
(or a quoted ISO date) is valid through that UTC date. Expired entries stop
suppressing findings and produce review findings. IDs not observed in the current
scope produce `orphaned-acceptance` review findings; a changed-only selection cannot
prove the ID disappeared from the entire repository. Hygiene also runs on empty
source selections.

Review-only anti-gaming signals report production/survivor location co-changes,
new Python tests without syntactic assertions or recognized oracles, and new
acceptances accompanying changed covered code. These are correlations, not proof
of gaming. Helpers may assert; assertion presence does not prove an independent
behavioral oracle. Other languages' assertion-free tests are currently unverified.

## Path-specific CRAP policy

```toml
[[policy.crap_paths]]
glob = "src/ui/**"
threshold = 50
mode = "review"

[[policy.crap_paths]]
glob = "src/domain/**"
threshold = 25
mode = "block"
```

The first matching rule wins. Unmatched paths retain global policy; an omitted
rule threshold inherits `policy.crap_threshold`. `mode` is `block` or `review`.
Review rules retain findings rather than excluding code. Rules apply only to selected scope; include UI paths in scope when using the example UI review rule. Block rules still require
changed function spans (or the changed-file fallback) and respect the global
`block_crap_regressions` setting.

CRAP metadata includes complexity, coverage, effective threshold/mode/glob, a
`recommended_lever`, and required coverage when calculable. If complexity itself
exceeds the threshold, coverage alone cannot get below it. Otherwise the CRAP
formula estimates coverage needed without structural changes. This is score
leverage, not a measured cost estimate or proof that tests are meaningful.
`explain` warns against splitting functions solely to lower a score.

## Mutation runtime controls

```toml
[tools.mutator]
max_workers = 4
max_mutants = 100   # omit for unlimited new sites
timeout = 600     # seconds for the entire mutation stage
cache = true       # false for tests depending on external state
```

`check --max-mutants N --timeout SECONDS` overrides these settings for that run.
Both must be positive; timeout may be fractional. These options affect mutation
only, including inventory, cache fingerprinting, and worker execution. They do
not cap coverage, Crapper, or Dryer; configure those command/tool timeouts separately.

Mutator's pinned CLI selects lines, not individual sites. Gauntlet scans the
selected inventory and schedules whole line groups that fit N; a line with more
than N sites may cause zero execution. Counts refer to mutation sites, not test
processes or wall-clock predictions. Valid cache hits do not consume the budget
for **new** sites. The report lists `inventory_sites`, `scheduled_new_sites`,
`completed_sites` (killed + survived), `uncovered_sites`, `reused_sites`, cache hits,
and `reported_fraction` ((completed + uncovered) / inventory). Uncovered sites
were not executed. When inventory itself times out, inventory/fraction are null,
not an invented denominator. A count or timeout truncation sets status `partial`
and `partial_reason`; exit is 6, or 3 when an observed finding blocks. Later tool
errors still fail with their own code. Partial snapshots are never cached.

Cache files under `.gauntlet/mutation-cache/` contain validated raw evidence, not
policy decisions. Keys hash repository files (including tests, helpers, and local
resources), test content separately, coverage artifacts, config, environment,
coordinator code, executable bytes, installed Python distribution contents,
editable dependency sources, and cached Python grammar bytes. Deleting cache is
safe. Test edits invalidate killed evidence and force re-execution. Corrupt or
incomplete cache entries rerun; report/source identities are validated before reuse.

Caching currently supports Python with transparent `python -m pytest` or
`python -m unittest` commands and fingerprintable installed runtimes. Opaque
commands, other languages, external PYTHONPATH, symlinks, oversized repositories,
missing runtime inventories, or uncertain fingerprints rerun conservatively.
Generated state/dependency/build directories are excluded from repository hashing;
installed dependencies are fingerprinted separately. Tests whose outcomes depend
on network services, clock, databases, or other external state must set
`cache = false`; content hashes cannot establish external-state equivalence.
Fingerprinting has measurable overhead and is not a guaranteed speedup.

Results schema v1 adds `timings_ms` for coverage, Crapper, Mutator, and Dryer;
configured native stages also have entries. Values are integer elapsed milliseconds
and include adapter overhead. Zero can mean skipped, disabled, reused coverage,
or too short to round; consult `checks`. Terminal output shows the same timing and
mutation completion summary. No stage timings are promised for errors during CLI
preparation. See [evaluation](evaluation.md) for measured controls and limitations.
