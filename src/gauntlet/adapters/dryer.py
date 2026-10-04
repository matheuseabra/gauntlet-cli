from gauntlet.adapters import edn
from gauntlet.adapters.base import Adapter, ToolResult, execute, fresh, selection, signature
from gauntlet.errors import GauntletError
from gauntlet.models import Finding, Location, RunContext, stable_id
from gauntlet.scope import included

INSTRUCTION = (
    "Determine whether this similarity is accidental, intentional, coincidental, or indicates "
    "a missing domain abstraction. Do not refactor merely to remove duplication."
)
SUPPORTED = {
    ".clj",
    ".cljc",
    ".cljs",
    ".bb",
    ".java",
    ".go",
    ".ts",
    ".tsx",
    ".mts",
    ".cts",
    ".rs",
    ".py",
}


class DryerAdapter(Adapter):
    name = "dryer"

    def normalize(self, data: dict, context: RunContext) -> list[Finding]:
        findings = []
        for row in edn.rows(data, "candidates"):
            similarity = edn.number(row.get("score"), "score")
            if similarity > 1:
                raise GauntletError("Dryer similarity exceeds 1", 1)
            locations = []
            for side in ("left", "right"):
                location = row.get(side)
                if not isinstance(location, dict):
                    raise GauntletError(f"Dryer candidate requires {side} location", 1)
                file = edn.relative(location.get("file"), context.root)
                start = edn.integer(location.get("start-line"), "start-line", 1)
                end = edn.integer(location.get("end-line"), "end-line", start)
                locations.append({"file": file, "start_line": start, "end_line": end})
            left, right = sorted(locations, key=lambda loc: (loc["file"], loc["start_line"]))
            if not all(included(loc["file"], context.config) for loc in locations):
                continue
            if not any(loc["file"] in context.selected_files for loc in locations):
                continue
            findings.append(
                Finding(
                    stable_id(self.name, left, right),
                    self.name,
                    "structural-duplication",
                    "review",
                    Location(left["file"], line=left["start_line"], end_line=left["end_line"]),
                    f"{similarity:.2f} similarity: {left['file']}:"
                    f"{left['start_line']}-{left['end_line']} "
                    f"and {right['file']}:{right['start_line']}-{right['end_line']}",
                    {
                        "similarity": similarity,
                        "left": left,
                        "right": right,
                        "language": row.get("language"),
                        "instruction": INSTRUCTION,
                    },
                )
            )
        return findings

    def run(self, context: RunContext) -> ToolResult:
        from pathlib import Path

        if not any(Path(name).suffix in SUPPORTED for name in context.selected_files):
            return ToolResult(
                diagnostics=["Dryer skipped: no selected file uses a supported language."],
                status="skipped",
            )
        config = context.config.tools[self.name]
        path = context.root / ".metrics/dry.edn"
        before = signature(path)
        execute(
            self.name,
            [
                "--edn",
                "--threshold",
                str(config.threshold),
                "--min-lines",
                str(config.min_lines),
                "--min-nodes",
                str(config.min_nodes),
                *selection(context),
            ],
            context,
        )
        fresh(path, before)
        return ToolResult(self.normalize(edn.read(path), context))
