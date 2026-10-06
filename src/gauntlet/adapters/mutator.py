import json
import re
from dataclasses import replace

from gauntlet.adapters import edn
from gauntlet.adapters.base import Adapter, ToolResult, execute, selection, signature
from gauntlet.errors import GauntletError
from gauntlet.models import Finding, Location, RunContext, stable_id
from gauntlet.pipeline.triage import GUIDANCE, covering_tests

INSTRUCTION = (
    "Determine whether this mutation changes specified observable behavior. If yes, add the "
    "smallest meaningful test that distinguishes it. Do not modify production code solely to "
    "kill the mutant. If behavior is equivalent or intentionally accepted, record a reason."
)
STATES = {"killed", "survived", "uncovered", "invalid", "equivalent", "accepted", "timeout"}
SCAN_SITE = re.compile(r"^[ *] (.+):(\d+) (.+)  \[(.+)\]$")


def mutation_identity(identity: str) -> list:
    try:
        parts = json.loads(identity)
        if not isinstance(parts, list) or len(parts) != 7:
            raise ValueError("expected seven mutation identity fields")
        return parts
    except (ValueError, TypeError) as exc:
        raise GauntletError(f"Malformed mutation identity: {exc}", 1) from exc


def locations(data: dict, context: RunContext) -> dict[tuple[str, str, str], Location]:
    namespace = edn.text(data.get("namespace"), "namespace")
    found = {}
    for form in edn.rows(data, "forms"):
        file = edn.relative(form.get("file", data.get("source")), context.root)
        function = edn.text(form.get("id"), "form.id").split("/", 1)[-1]
        start = edn.integer(form.get("line"), "form.line", 1)
        end = edn.integer(form.get("end-line"), "form.end-line", start)
        found[file, namespace, function] = Location(file, function, start, end)
    return found


def enrich(findings: list[Finding], snapshots: list[dict], context: RunContext) -> None:
    mapping = {}
    for snapshot in snapshots:
        mapping.update(locations(snapshot, context))
    for finding in findings:
        if finding.tool != "crapper":
            continue
        key = (finding.location.file, finding.metadata["namespace"], finding.location.function)
        if key in mapping:
            finding.location = mapping[key]
            finding.metadata["location_precision"] = "function"
            finding.metadata["policy_basis"] = "changed-function approximation"


def mutation_message(state: str, original: str, replacement: str) -> str:
    if state != "survived":
        return f"Mutation {original} → {replacement}: {state}."
    if replacement == "":
        description = f"deleting {original!r}"
    elif original == "":
        description = f"inserting {replacement!r}"
    else:
        description = f"replacing {original!r} with {replacement!r}"
    return f"Tests do not distinguish {description} from original behavior."


def mutation_finding(
    tool: str,
    identity: str,
    state: str,
    context: RunContext,
    spans: dict[tuple[str, str, str], Location],
) -> Finding | None:
    if state not in STATES:
        raise GauntletError(f"Unknown mutation state: {state}", 1)
    parts = mutation_identity(identity)
    raw_file, namespace, form, start, end, original, replacement = parts
    file = edn.relative(raw_file, context.root)
    if file not in context.selected_files:
        return None
    namespace = edn.text(namespace, "namespace")
    function = edn.text(form, "form").split("/", 1)[-1]
    start = edn.integer(start, "start byte")
    end = edn.integer(end, "end byte", start)
    if not isinstance(original, str) or not isinstance(replacement, str):
        raise GauntletError("Mutation report requires string operators", 1)
    source = (context.root / file).read_bytes()
    if source[start:end] != original.encode("utf-8"):
        raise GauntletError(f"Mutation report no longer matches source: {file}", 1)
    if state == "killed":
        return None
    span = spans.get((file, namespace, function))
    if span is None:
        raise GauntletError("Mutation outcome refers to an unknown function", 1)
    line = source[:start].count(b"\n") + 1
    tests, attribution = covering_tests(context.root, file, line)
    return Finding(
        stable_id(tool, file, namespace, form, start, end, original, replacement),
        tool,
        "surviving-mutant" if state == "survived" else f"{state}-mutant",
        "error" if state == "survived" else "info",
        replace(span, line=line, end_line=line),
        mutation_message(state, original, replacement),
        {
            "state": state,
            "namespace": namespace,
            "original": original,
            "replacement": replacement,
            "start_byte": start,
            "end_byte": end,
            "instruction": INSTRUCTION,
            "mutation_description": mutation_message(state, original, replacement),
            "covering_tests": tests,
            "covering_tests_provenance": attribution,
            "triage_guidance": GUIDANCE,
        },
    )


def uncovered_findings(
    tool: str,
    data: dict,
    context: RunContext,
    spans: dict[tuple[str, str, str], Location],
) -> list[Finding]:
    findings = []
    for form in edn.rows(data, "forms"):
        file = edn.relative(form.get("file", data.get("source")), context.root)
        count = edn.integer(form.get("uncovered", 0), "uncovered")
        if count and file in context.selected_files:
            function = form["id"].split("/", 1)[-1]
            findings.append(
                Finding(
                    stable_id(tool, file, data["namespace"], form["id"], "uncovered"),
                    tool,
                    "uncovered-mutants",
                    "warning",
                    spans[file, data["namespace"], function],
                    f"{count} mutation sites were not executed because their lines lack coverage.",
                    {
                        "state": "uncovered",
                        "count": count,
                        "instruction": "Investigate meaningful tests for specified behavior "
                        "on these lines.",
                    },
                )
            )
    return findings


class MutatorAdapter(Adapter):
    name = "mutator"

    def normalize(self, data: dict, context: RunContext) -> list[Finding]:
        if data.get("version") != 1:
            raise GauntletError("Unsupported Mutator snapshot version", 1)
        spans = locations(data, context)
        outcomes = data.get("outcomes")
        if not isinstance(outcomes, dict):
            raise GauntletError("Mutator report requires an outcomes map", 1)
        findings = []
        for identity, state in outcomes.items():
            finding = mutation_finding(self.name, identity, state, context, spans)
            if finding is not None:
                findings.append(finding)
        findings.extend(uncovered_findings(self.name, data, context, spans))
        return findings

    def scan(self, stdout: str, context: RunContext) -> list[Finding]:
        findings = []
        for row in stdout.splitlines():
            match = SCAN_SITE.match(row)
            if not match:
                continue
            file, line, description, form = match.groups()
            if description.startswith("delete "):
                original, replacement = description.removeprefix("delete "), ""
            elif " -> " in description:
                original, replacement = description.split(" -> ", 1)
            else:
                continue
            file = edn.relative(file, context.root)
            if file not in context.selected_files:
                continue
            findings.append(
                Finding(
                    stable_id(self.name, "scan", file, int(line), form, original, replacement),
                    self.name,
                    "mutation-site",
                    "info",
                    Location(file, form.split("/", 1)[-1], int(line)),
                    f"Potential mutation: {description}; tests were not executed.",
                    {"original": original, "replacement": replacement, "instruction": INSTRUCTION},
                )
            )
        return findings

    def run(self, context: RunContext) -> ToolResult:
        args = (
            ["--scan", "--no-coverage"]
            if context.scan
            else [
                "--use-existing-coverage",
                "--max-workers",
                str(context.config.tools[self.name].max_workers),
            ]
        )
        if not context.scan and "test" in context.config.commands:
            args.extend(["--test-command", context.config.commands["test"]])
        metrics = context.root / ".metrics/mutate"
        before = {path: signature(path) for path in metrics.rglob("*.edn")}
        result = execute(self.name, [*args, *selection(context)], context, allowed=(0, 2, 3))
        if result.exit_code == 2:
            raise GauntletError(
                "Mutator baseline failed (or its Crapper dependency is missing). "
                "Run mutator directly to diagnose the prerequisite.",
                2,
                "mutator",
            )
        if context.scan:
            return ToolResult(
                self.scan(result.stdout, context),
                ["Mutation scan inventories sites; no tests or mutants were run."],
            )
        snapshots = [
            edn.read(path)
            for path in sorted(metrics.rglob("*.edn"))
            if signature(path) != before.get(path)
        ]
        reported = {loc.file for data in snapshots for loc in locations(data, context).values()}
        expected = (
            context.function_files if context.function_files is not None else context.selected_files
        )
        if set(expected) - reported:
            raise GauntletError(
                "Mutator did not write fresh function reports for selected sources", 1
            )
        findings = [finding for data in snapshots for finding in self.normalize(data, context)]
        if result.exit_code == 3 and not any(f.rule == "surviving-mutant" for f in findings):
            raise GauntletError(
                "Mutator reported survivors but supplied no matching survivor evidence", 1
            )
        self.snapshots = snapshots
        return ToolResult(findings)
