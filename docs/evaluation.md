# Evaluation harness and recorded findings

The harness measures gate outcomes separately from specified behavior. It can run
paired local AI-agent commands, but **no AI-agent effectiveness experiment has been
run here**. The recorded runs use deterministic scripted controls, not a model.

## Run paired commands

From this checkout, with Gauntlet, the pinned analyzers, coverage.py, and project
Python already installed and available on PATH:

```bash
python -m benchmarks.runner \
  --without 'your-agent-command' \
  --with 'your-agent-command' \
  --subject-kind ai-agent --repetitions 10 --timeout 300 \
  --output .gauntlet/evaluation.json
```

Commands are trusted local shell commands; they run in disposable Git fixtures.
The same command should use the supplied `GAUNTLET_EVAL_INSTRUCTIONS` and read
`TASK.md`. The environment also identifies `GAUNTLET_EVAL_TASK_ID` and
`GAUNTLET_EVAL_MODE` (`without` or `with`). Without-arm instructions ask for native
validation only; with-arm instructions add Gauntlet and specification-based triage.
The harness does not enforce compliance or invoke a model itself. Arrange any
agent credentials and data permissions explicitly outside the harness.

Each task/arm/repetition starts with identical source, visible tests, specification,
and Git baseline. Order alternates by repetition. Two deliberately small Python
tasks isolate boundary/mirrored-test behavior and equivalent-mutant acceptance.
After the command finishes, an independent held-out behavioral oracle executes
outside the subject working tree. The harness then records `check --all --json`
for both arms, plus a repeat gate for the with arm. Full selection is intentional
for these tiny fixtures and does not change Gauntlet's changed-only default.

The output includes task-content hash, supplied commands, subject exits/timeouts
and elapsed times, diff statistics, oracle results, gate findings/stage timings,
repeat-cache evidence, and per-arm counts. `gate_passed_oracle_failed` measures an
observed defect the gate missed. `oracle_passed_gate_blocked` identifies a case for
triage; a finite oracle alone does not prove a false block or equivalence. Partial
runs never count as gate passes. Failed subject commands are retained in records
and must be reported separately, even if a later oracle passes.

For diagnostic controls, run the following from the checkout (both commands point
to the same script, which obeys the supplied mode):

```bash
python -m benchmarks.runner \
  --without "python $PWD/benchmarks/proxy.py" \
  --with "python $PWD/benchmarks/proxy.py" \
  --subject-kind scripted-proxy --timeout 120 \
  --output .gauntlet/scripted-controls.json
python -m tests.integration.smoke_cost
```

CI runs these controls with all three analyzers enabled and saves the JSON bound
to the workflow head. It explicitly asserts the negative control: mirrored wrong
behavior can still produce a passing gate. These assertions validate the harness
and known limitations; they do not relax the CLI's existing checks.

## Baseline and phased validation

Before source changes, README, AGENTS, architecture/reference, and the complete
`src/gauntlet` tree were inspected. The pipeline summary was:

1. CLI resolves Git scope, config, and detected commands into a RunContext.
2. Selection defaults to staged, unstaged, and untracked production sources.
3. Committed mode resolves a merge base and requires clean tracked files.
4. The pipeline locks the repository and preflights installed analyzers.
5. Trusted native commands run before coverage and analyzer stages.
6. Crapper, Mutator, and Dryer retain source-analysis ownership via external CLIs.
7. Adapters validate scan/EDN evidence into stable, located findings.
8. Policy and acceptance determine blocking; JSON and terminal share Results.

Baseline was `725402d6200f43676220b06576a4ee377e8cb37c` (current docs on top of
merged implementation `a4b06a5`). `uv sync --extra dev`, all 40 unittest tests,
Ruff lint/format, and wheel/sdist builds passed. Phases were implemented in order:
known-language preflight; survivor/acceptance hygiene; path CRAP policy; budgets,
stage timing, conservative cache; then paired harness controls. Final local validation passed 62 tests, Ruff lint/format, wheel/sdist builds,
workflow lint, and both native smoke checks. New tests retain existing blocking defaults. Optional test attribution uses actual coverage contexts
when available, and reports unavailable data explicitly.

## Recorded scripted controls

Local Linux / Python 3.12, pinned analyzers in `requirements-tools.txt`, one
repetition (four subject runs). All scripted subject commands completed with exit
0. These are designed demonstrations; the with script intentionally follows a
better repair strategy, so the difference cannot be attributed to the gate alone.

| Task | Arm | Held-out behavior | Gate | Finding |
| --- | --- | --- | --- | --- |
| Boundary | Without | Fail at age 18 | Pass | Wrong `>18` implementation plus mirrored tests killed the available mutant |
| Boundary | With | Pass | Pass | Correct `>=18` implementation and independent boundary assertions |
| Allowed domain {17,19} | Without | Pass | Block (3) | `>=18` → `>18` survivor is equivalent because age 18 is rejected first |
| Allowed domain {17,19} | With | Pass | Pass | Same production behavior; stable survivor ID accepted with domain reason |

The without controls passed the oracle in 1/2 tasks, missed one behavioral defect,
and blocked one reasoned equivalent. The with controls passed 2/2; this confirms
the fixture mechanisms, **not an AI-agent improvement rate**. Mutation analysis
cannot establish that an assertion is an independent behavioral oracle. Syntactic
anti-gaming signals are reviews and cannot reliably detect implementation mirroring.
No analyzer threshold, test assertion, or blocking default was weakened.

## Runtime and cache observation

The native cost smoke runs all three pinned analyzers. The first small boundary
run had a 1.546 s Mutator stage; the unchanged repeat took 0.701 s, reused the one
mutation outcome, and scheduled zero new sites. Coverage, Crapper, and Dryer still
ran. Two source files were cached, including an empty package initializer. These
are single noisy observations, not a benchmark distribution or guaranteed speedup.
Fingerprinting itself remains a material part of repeat cost.

Removing the boundary assertion invalidated all hits, reran the site, produced a
survivor, and exited 3. A separate source with three sites on one line and
`--max-mutants 1` scheduled zero sites, reported 0/3 with `partial`, and exited 6;
the pinned upstream can select lines only. A 0.001 s mutation timeout returned
`partial`, unknown inventory/fraction, and exit 6. Source hashes remained unchanged
after both limits. Unit tests also verify test/source/helper/coverage/config/runtime
invalidation, corrupt-cache fallback, count grouping, and partial-plus-blocking
semantics.

## Limits and next experiment

Language capabilities are source-verified at analyzer pins; runtime toolchains
beyond Python remain unverified (see [matrix](language-support.md)). Assertion-free
test detection is currently Python-only. Cache supports transparent local Python
test commands; external-state tests must disable it. Coverage contexts may be
absent; nearest covering test names are not guessed.

These two tasks, finite oracles, scripted repair strategies, and shared runtime
caches do not support a causal claim. The oracles are outside the tree but not
isolated against a hostile command. Model/token cost, human triage effort, repair
iterations, production-scale runtime, and AI success rates are **unmeasured**.

For an AI study, use the same agent/model/version, prompt, budgets, tools, and task
population in both arms; record those settings and exact repository/analyzer
revisions alongside output. Expand tasks/languages and held-out specifications,
run enough paired repetitions to report uncertainty, count subject failures and
partial runs, and collect token/cost/iteration data from the agent provider. Review
acceptance reasons and behavior changes independently. Report both correctness
and runtime/cost, including gate passes that fail held-out behavior and equivalent
survivors that consumed triage time. Do not substitute gate pass rate for quality.
