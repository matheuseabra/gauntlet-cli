import sys
from dataclasses import replace

from gauntlet import git
from gauntlet.adapters.crapper import CrapperAdapter
from gauntlet.adapters.dryer import DryerAdapter
from gauntlet.adapters.mutator import MutatorAdapter, enrich
from gauntlet.config import COMMANDS
from gauntlet.errors import GauntletError
from gauntlet.models import Results, RunContext
from gauntlet.pipeline import coverage, policy, triage
from gauntlet.pipeline.lock import repository_lock
from gauntlet.process import run_shell

ADAPTERS = (CrapperAdapter, MutatorAdapter, DryerAdapter)


def command(name: str, text: str, context: RunContext, results: Results) -> None:
    if context.verbose:
        print(f"[{name}] {text}", file=sys.stderr)
    result = run_shell(text, context.root, context.config.timeout)
    if context.verbose:
        print(result.stdout, file=sys.stderr, end="")
        print(result.stderr, file=sys.stderr, end="")
    if result.exit_code or result.timed_out:
        detail = "timed out" if result.timed_out else f"exited {result.exit_code}"
        raise GauntletError(
            f"{name} {detail}. Run the configured command directly or use "
            "--verbose for diagnostics.",
            5 if result.exit_code == 127 else 2,
            name,
        )
    results.checks[name] = "passed"


def _prerequisites(context: RunContext, results: Results) -> None:
    needs_coverage = any(context.config.tools[name].enabled for name in ("crapper", "mutator"))
    for name in COMMANDS:
        if name == "coverage":
            if not needs_coverage:
                results.checks[name] = "skipped"
                continue
            if name not in context.config.commands and coverage.artifacts(context.root):
                coverage.require(context)
                results.checks[name] = "reused"
                continue
        if name in context.config.commands:
            command(name, context.config.commands[name], context, results)
        else:
            results.checks[name] = "skipped"
    if needs_coverage:
        coverage.require(context)
        if results.checks["coverage"] == "skipped":
            results.checks["coverage"] = "reused"


def _analyze(context: RunContext, results: Results, accept: dict[str, str]) -> None:
    for adapter_type in ADAPTERS:
        name = adapter_type.name
        if not context.config.tools[name].enabled:
            results.checks[name] = "disabled"
            continue
        adapter = adapter_type()
        try:
            tool_result = adapter.run(context)
        except GauntletError as exc:
            exc.check = exc.check or name
            raise
        results.findings.extend(tool_result.findings)
        results.diagnostics.extend(tool_result.diagnostics)
        results.checks[name] = tool_result.status
        if name == "crapper":
            context = replace(
                context, function_files=sorted({f.location.file for f in tool_result.findings})
            )
        if name == "mutator" and not context.scan:
            enrich(results.findings, adapter.snapshots, context)
    ranges = git.changed_lines(context.root, context.changed_files, context.comparison_base)
    results.diagnostics.extend(
        policy.apply(
            results.findings, context.config, accept, context.changed_files, context.mode, ranges
        )
    )
    results.findings.extend(triage.signals(context, results.findings, accept, ranges))
    for name in (adapter.name for adapter in ADAPTERS):
        findings = [f for f in results.findings if f.tool == name and not f.accepted]
        if any(f.blocking for f in findings):
            results.checks[name] = "failed"
        elif any(f.severity in {"warning", "review"} for f in findings):
            results.checks[name] = "review"
    if any(f.blocking for f in results.findings):
        results.status, results.exit_code = "failed", 3


def run(context: RunContext) -> Results:
    results = Results(
        {
            "root": str(context.root),
            "mode": context.mode,
            "command": "scan" if context.scan else "check",
            "changed_files": context.changed_files,
            "selected_files": context.selected_files,
        }
    )
    try:
        accept = policy.accepted(context.root)
        if not context.selected_files:
            results.diagnostics.extend(
                policy.apply(results.findings, context.config, accept, [], context.mode)
            )
            results.findings.extend(triage.new_tests(context))
            results.diagnostics.append(
                "PASS: no relevant changes"
                if context.mode == "changed"
                else "PASS: no relevant source files"
            )
            return results
        with repository_lock(context.root):
            # Preflight is deliberately before project commands and expensive coverage.
            from gauntlet.adapters.base import resolve

            for adapter in ADAPTERS:
                if context.config.tools[adapter.name].enabled:
                    resolve(adapter.name, context)
            if not context.scan:
                _prerequisites(context, results)
            _analyze(context, results, accept)
    except GauntletError as exc:
        results.status, results.exit_code = "failed", exc.code
        results.diagnostics.append(str(exc))
        if exc.check:
            results.checks[exc.check] = "failed" if exc.code == 2 else "error"
    return results
