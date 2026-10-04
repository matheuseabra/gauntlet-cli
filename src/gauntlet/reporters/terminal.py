from gauntlet.models import Results, finding_key


def render(results: Results) -> str:
    lines = ["GAUNTLET", ""]
    for name, status in results.checks.items():
        marker = {"passed": "✓", "failed": "✗", "error": "✗", "review": "•"}.get(status, "–")
        lines.append(f"{marker} {name}: {status}")
    for finding in sorted(results.findings, key=finding_key):
        if finding.severity == "info":
            continue
        loc = finding.location
        label = loc.file or finding.metadata.get("namespace", "unknown location")
        if loc.line:
            label += f":{loc.line}"
        if loc.function:
            label += f"::{loc.function}"
        accepted = " [accepted]" if finding.accepted else ""
        lines.extend(["", f"{finding.tool.upper()} {label}{accepted}", f"  {finding.message}"])
    lines.extend(f"\n{message}" for message in results.diagnostics)
    summary = results.to_dict()["summary"]
    lines.extend(
        [
            "",
            f"{summary['blocking']} blocking · {summary['warnings']} warnings · "
            f"{summary['reviews']} reviews",
        ]
    )
    label = "GAUNTLET FAILED" if results.exit_code else "GAUNTLET PASSED"
    if not results.exit_code and summary["reviews"]:
        label += " WITH REVIEW FINDINGS"
    lines.append(label)
    return "\n".join(lines)
