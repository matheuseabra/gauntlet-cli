"""Review-only correlations and optional test-context evidence, never equivalence proofs."""

import ast
import tomllib
from pathlib import Path

from gauntlet.models import Finding, Location, RunContext, stable_id
from gauntlet.process import run

GUIDANCE = (
    "Classify the survivor as real gap, equivalent, or out-of-scope against the specification. "
    "Find an allowed input for which original and mutant produce different observable behavior. "
    "If no such input is possible, explain the domain constraint and accept the stable ID with "
    "a concrete reason (and expiry when appropriate). Lack of a test is not proof of equivalence. "
    "Do not change production behavior solely to kill a mutant or contort a test "
    "around implementation."
)


def covering_tests(root: Path, file: str, line: int) -> tuple[list[str], str]:
    if not (root / ".coverage").is_file():
        return [], "unavailable: no coverage.py context data"
    try:
        from coverage import CoverageData

        data = CoverageData(basename=str(root / ".coverage"))
        data.read()
        matching = [
            name
            for name in data.measured_files()
            if (root / name).resolve() == (root / file).resolve()
        ]
        contexts = {
            context
            for name in matching
            for context in data.contexts_by_lineno(name).get(line, [])
            if context
        }
        return sorted(contexts), (
            "coverage.py line contexts"
            if contexts
            else "unavailable: coverage has no named test contexts for this line"
        )
    except Exception as exc:
        # Optional attribution cannot turn incomplete or malformed context data into claimed tests.
        return [], f"unavailable: cannot read test contexts ({type(exc).__name__})"


def previous(root: Path, file: str, base: str | None) -> str:
    result = run(["git", "show", f"{base or 'HEAD'}:{file}"], root)
    return result.stdout if result.exit_code == 0 else ""


def review(rule: str, file: str, line: int | None, message: str, **metadata) -> Finding:
    return Finding(
        stable_id("gauntlet", rule, file, line, metadata.get("finding_id")),
        "gauntlet",
        rule,
        "review",
        Location(file, line=line),
        message,
        metadata,
    )


def test_functions(text: str) -> dict[str, ast.AST]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}
    result = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
            "test_"
        ):
            result[node.name] = node
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(
                    child, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and child.name.startswith("test_"):
                    result[f"{node.name}.{child.name}"] = child
    return result


def has_oracle(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            return True
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
            if child.func.attr.startswith("assert") or child.func.attr in {
                "raises",
                "fail",
                "warns",
            }:
                return True
    return False


def new_tests(context: RunContext) -> list[Finding]:
    findings = []
    for file in context.changed_files:
        path = context.root / file
        if path.suffix != ".py" or not path.is_file():
            continue
        current = test_functions(path.read_text(encoding="utf-8"))
        old = test_functions(previous(context.root, file, context.comparison_base))
        for name in sorted(current.keys() - old.keys()):
            node = current[name]
            if not has_oracle(node):
                findings.append(
                    review(
                        "test-without-assertion",
                        file,
                        node.lineno,
                        f"New test {name} has no syntactic assertion or recognized oracle. "
                        "A helper may assert; inspect the behavior before judging test quality.",
                        test=name,
                        evidence="Python AST heuristic; not proof of gaming",
                    )
                )
    return findings


def old_acceptance_ids(context: RunContext) -> set[str]:
    text = previous(context.root, ".gauntlet/accept.toml", context.comparison_base)
    try:
        rows = tomllib.loads(text).get("finding", [])
        return {
            row["id"] for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str)
        }
    except (ValueError, TypeError):
        return set()


def signals(
    context: RunContext, findings: list[Finding], accept: dict, ranges: dict
) -> list[Finding]:
    result = new_tests(context)
    added = set(accept) - old_acceptance_ids(context) if accept else set()
    for finding in findings:
        file, line = finding.location.file, finding.location.line
        if file not in context.changed_files:
            continue
        if finding.rule == "surviving-mutant" and line is not None:
            if any(start <= line <= end for start, end in ranges.get(file, [])):
                result.append(
                    review(
                        "survivor-production-cochange",
                        file,
                        line,
                        "Production code changed at a surviving mutation site in the same diff. "
                        "Verify the specification; this correlation does not prove gaming.",
                        finding_id=finding.id,
                    )
                )
        if finding.id in added:
            result.append(
                review(
                    "acceptance-code-cochange",
                    file,
                    line,
                    "An acceptance was added in the same diff as the code it covers. "
                    "Review the justification independently of the desire for a passing gate.",
                    finding_id=finding.id,
                )
            )
    return result
