"""Budget external mutation execution without reimplementing mutation analysis."""

import copy
import re
import time
from collections import Counter
from dataclasses import replace

from gauntlet.adapters import edn
from gauntlet.adapters.base import ToolResult, execute, resolve, signature
from gauntlet.errors import GauntletError
from gauntlet.models import RunContext
from gauntlet.pipeline.cache import MutationCache

HEADER = re.compile(r"^Scan: (\d+) mutation sites in (.+)$", re.M)


def remaining(deadline: float) -> float:
    return max(0.001, deadline - time.monotonic())


def inventory(adapter, context: RunContext, files: list[str], deadline: float):
    limited = replace(context, selected_files=files, native_changed=False)
    result = execute(
        "mutator",
        ["--scan", "--no-coverage", *(str(context.root / f) for f in files)],
        limited,
        timeout=remaining(deadline),
        allow_timeout=True,
    )
    if result.timed_out:
        return None
    sites = adapter.scan(result.stdout, limited)
    counts = {
        edn.relative(file, context.root): int(count)
        for count, file in HEADER.findall(result.stdout)
    }
    grouped = {file: [site for site in sites if site.location.file == file] for file in files}
    if set(counts) != set(files) or any(len(grouped[f]) != counts[f] for f in files):
        raise GauntletError(
            "Mutator scan inventory is incomplete or unrecognized; "
            "cannot enforce an honest mutation budget.",
            1,
            "mutator",
        )
    return grouped


def plan_sites(grouped: dict, maximum: int | None) -> dict[str, list[int] | None]:
    if maximum is None:
        return dict.fromkeys(grouped)
    plans = {}
    for file, sites in grouped.items():
        lines = Counter(site.location.line for site in sites)
        chosen = []
        for line, count in sorted(lines.items()):
            if count <= maximum:
                chosen.append(line)
                maximum -= count
        if chosen or not sites:
            plans[file] = None if len(chosen) == len(lines) else chosen
    return plans


def report_files(data: dict, context: RunContext) -> set[str]:
    return {
        edn.relative(form.get("file", data.get("source")), context.root)
        for form in edn.rows(data, "forms")
    }


def restricted(data: dict, context: RunContext, plans: dict) -> dict:
    from gauntlet.adapters.mutator import mutation_identity

    data = copy.deepcopy(data)
    outcomes = {}
    for identity, state in data.get("outcomes", {}).items():
        parts = mutation_identity(identity)
        file = edn.relative(parts[0], context.root)
        if file not in plans:
            continue
        selected_lines = plans[file]
        line = (context.root / file).read_bytes()[: edn.integer(parts[3], "start byte")].count(
            b"\n"
        ) + 1
        if selected_lines is None or line in selected_lines:
            outcomes[identity] = state
    data["outcomes"] = outcomes
    # Line-limited snapshots contain historical outcomes for other lines. Never present
    # their aggregate counts as current execution or cache these partial snapshots.
    if any(lines is not None for lines in plans.values()):
        for form in data["forms"]:
            form["uncovered"] = sum(
                state == "uncovered" and mutation_identity(identity)[2] == form["id"]
                for identity, state in outcomes.items()
            )
    return data


def collect(adapter, context: RunContext, before: dict, files: set[str], plans: dict) -> list[dict]:
    snapshots = []
    for path in sorted((context.root / ".metrics/mutate").rglob("*.edn")):
        if signature(path) == before.get(path):
            continue
        data = edn.read(path)
        if report_files(data, context) & files:
            adapter.normalize(data, context)
            snapshots.append(restricted(data, context, plans))
    return snapshots


def invoke(context: RunContext, files: list[str], lines: list[int] | None, deadline: float):
    args = [
        "--use-existing-coverage",
        "--mutate-all",
        "--max-workers",
        str(context.config.tools["mutator"].max_workers),
    ]
    if "test" in context.config.commands:
        args += ["--test-command", context.config.commands["test"]]
    if lines is not None:
        args += ["--lines", ",".join(map(str, lines))]
    return execute(
        "mutator",
        [*args, *(str(context.root / f) for f in files)],
        context,
        allowed=(0, 2, 3),
        timeout=remaining(deadline),
        allow_timeout=True,
    )


def counts(snapshots: list[dict]) -> dict:
    states = Counter(state for data in snapshots for state in data["outcomes"].values())
    return {
        "completed_sites": states["killed"] + states["survived"],
        "killed": states["killed"],
        "survived": states["survived"],
        "uncovered_sites": states["uncovered"],
    }


def execute_plans(
    adapter, context: RunContext, plans: dict, deadline: float
) -> tuple[list[dict], bool]:
    snapshots = []
    batches = (
        [(list(plans), None)]
        if all(v is None for v in plans.values())
        else [([file], lines) for file, lines in plans.items()]
    )
    for files, lines in batches:
        if not files or time.monotonic() >= deadline:
            return snapshots, bool(files)
        before = {
            path: signature(path) for path in (context.root / ".metrics/mutate").rglob("*.edn")
        }
        result = invoke(context, files, lines, deadline)
        if not result.timed_out and result.exit_code == 2:
            raise GauntletError(
                "Mutator baseline failed; run the project tests directly.", 2, "mutator"
            )
        fresh = collect(adapter, context, before, set(files), {f: plans[f] for f in files})
        if (
            not result.timed_out
            and result.exit_code == 3
            and not any(
                state == "survived" for data in fresh for state in data["outcomes"].values()
            )
        ):
            raise GauntletError(
                "Mutator reported survivors without matching selected evidence.", 1, "mutator"
            )
        snapshots.extend(fresh)
        if result.timed_out:
            return snapshots, True
    return snapshots, False


def cached_snapshots(adapter, context: RunContext, cache: MutationCache):
    hits, snapshots, misses = {}, [], []
    for file in context.selected_files:
        data = cache.get(file)
        if data is not None:
            try:
                for snapshot in data["snapshots"]:
                    if report_files(snapshot, context) != {file}:
                        raise ValueError("wrong cache source")
                    adapter.normalize(snapshot, context)
                if sum(len(s["outcomes"]) for s in data["snapshots"]) != data["inventory"]:
                    raise ValueError("incomplete cache evidence")
                hits[file] = data["inventory"]
                snapshots.extend(data["snapshots"])
            except (GauntletError, ValueError, TypeError, KeyError):
                misses.append(file)
        else:
            misses.append(file)
    return hits, snapshots, misses


def finish(adapter, context, cache, hits, snapshots, grouped, plans, timed_out):
    total = sum(hits.values()) + sum(len(sites) for sites in grouped.values())
    scheduled_new = sum(
        len(grouped[f])
        if lines is None
        else sum(site.location.line in lines for site in grouped[f])
        for f, lines in plans.items()
    )
    details = counts(snapshots) | {
        "inventory_sites": total,
        "scheduled_new_sites": scheduled_new,
        "reused_sites": sum(hits.values()),
        "cache_hits": len(hits),
        "cache_misses": len(grouped),
        "cache_status": cache.reason,
        "max_mutants": context.config.tools["mutator"].max_mutants,
        "timeout_seconds": context.config.tools["mutator"].timeout,
    }
    covered = details["completed_sites"] + details["uncovered_sites"]
    partial = timed_out or scheduled_new < sum(len(s) for s in grouped.values())
    if not partial and covered != total:
        raise GauntletError(
            "Mutator did not supply complete fresh outcomes for its inventory.", 1, "mutator"
        )
    details["partial_reason"] = "timeout" if timed_out else "max-mutants" if partial else None
    details["reported_fraction"] = covered / total if total else 1.0
    findings = [finding for data in snapshots for finding in adapter.normalize(data, context)]
    adapter.snapshots = snapshots
    if not partial:
        for file in grouped:
            own = [s for s in snapshots if report_files(s, context) == {file}]
            cache.put(file, len(grouped[file]), own)
    return ToolResult(findings, status="partial" if partial else "passed", details=details)


def run(adapter, context: RunContext) -> ToolResult:
    deadline = time.monotonic() + context.config.tools["mutator"].timeout
    cache = MutationCache(context, resolve("mutator", context), deadline)
    hits, snapshots, misses = cached_snapshots(adapter, context, cache)
    grouped = (
        inventory(adapter, context, misses, deadline)
        if misses and time.monotonic() < deadline
        else {}
    )
    if grouped is None or (misses and not grouped):
        adapter.snapshots = snapshots
        return ToolResult(
            [f for s in snapshots for f in adapter.normalize(s, context)],
            status="partial",
            details=counts(snapshots)
            | {
                "inventory_sites": None,
                "scheduled_new_sites": 0,
                "reused_sites": sum(hits.values()),
                "cache_hits": len(hits),
                "cache_misses": len(misses),
                "cache_status": cache.reason,
                "max_mutants": context.config.tools["mutator"].max_mutants,
                "timeout_seconds": context.config.tools["mutator"].timeout,
                "partial_reason": "timeout during inventory or fingerprint",
                "reported_fraction": None,
            },
        )
    plans = plan_sites(grouped, context.config.tools["mutator"].max_mutants)
    fresh, timed_out = execute_plans(adapter, context, plans, deadline)
    snapshots.extend(fresh)
    return finish(adapter, context, cache, hits, snapshots, grouped, plans, timed_out)
