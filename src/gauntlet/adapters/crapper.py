from gauntlet.adapters import edn
from gauntlet.adapters.base import Adapter, ToolResult, execute, fresh, signature
from gauntlet.models import Finding, Location, RunContext, stable_id

INSTRUCTION = (
    "Investigate whether the changed function should be simplified, decomposed, or better "
    "tested. Preserve behavior."
)


class CrapperAdapter(Adapter):
    name = "crapper"

    def normalize(self, data: dict, file: str, scan: bool = False) -> list[Finding]:
        findings = []
        for row in edn.rows(data, "entries"):
            function = edn.text(row.get("name"), "name")
            namespace = edn.text(row.get("namespace"), "namespace")
            complexity = edn.integer(row.get("complexity"), "complexity", 1)
            coverage = edn.number(row.get("coverage"), "coverage", nullable=scan)
            crap = edn.number(row.get("crap"), "crap", nullable=scan)
            if coverage is not None and coverage > 100:
                from gauntlet.errors import GauntletError

                raise GauntletError("Tool coverage percentage exceeds 100", 1)
            message = f"CC {complexity} · coverage {coverage}% · CRAP {crap}"
            findings.append(
                Finding(
                    stable_id(self.name, file, namespace, function),
                    self.name,
                    "complexity" if scan else "crap-score",
                    "info",
                    Location(file, function),
                    message,
                    {
                        "namespace": namespace,
                        "cyclomatic_complexity": complexity,
                        "coverage_percent": coverage,
                        "crap": crap,
                        "instruction": INSTRUCTION,
                        "location_precision": "file",
                        "policy_basis": "changed-file approximation",
                    },
                )
            )
        return findings

    def run(self, context: RunContext) -> ToolResult:
        findings = []
        path = context.root / ".metrics/crap.edn"
        # The upstream serializer omits paths. Per-file runs preserve exact provenance
        # without guessing namespaces or implementing another source analyzer.
        for file in context.selected_files:
            before = signature(path)
            args = ["--no-coverage" if context.scan else "--use-existing-coverage"]
            args.append(str(context.root / file))
            execute(self.name, args, context)
            fresh(path, before)
            findings.extend(self.normalize(edn.read(path), file, context.scan))
        return ToolResult(findings)
