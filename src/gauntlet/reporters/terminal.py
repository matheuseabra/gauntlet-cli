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
    if results.timings_ms:
        lines.append(
            "Timing: "
            + " · ".join(
                f"{stage} {duration / 1000:.3f}s" for stage, duration in results.timings_ms.items()
            )
        )
    if results.mutation:
        lines.append(
            "Mutation: " + f"{results.mutation.get('completed_sites', 0)} completed / "
            f"{results.mutation.get('inventory_sites')} inventoried; "
            f"{results.mutation.get('cache_hits', 0)} cached files"
        )
    if results.status == "partial":
        lines.append("GAUNTLET PARTIAL — analysis incomplete; not a pass")
        return "\n".join(lines)
    label = "GAUNTLET FAILED" if results.exit_code else "GAUNTLET PASSED"
    if not results.exit_code and summary["reviews"]:
        label += " WITH REVIEW FINDINGS"
    lines.append(label)
    return "\n".join(lines)
