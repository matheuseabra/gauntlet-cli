from pathlib import Path

from gauntlet.config import Config, read_toml, table, validate
from gauntlet.errors import GauntletError
from gauntlet.models import Finding


def accepted(root: Path) -> dict[str, str]:
    path = root / ".gauntlet/accept.toml"
    if not path.exists():
        return {}
    data = table(read_toml(path), {"finding"}, "acceptance")
    rows = data.get("finding", [])
    if not isinstance(rows, list):
        raise GauntletError("accept.toml requires [[finding]] entries", 4)
    result = {}
    for row in rows:
        row = table(row, {"id", "reason"}, "accepted finding")
        validate(row.get("id"), str, "finding.id")
        validate(row.get("reason"), str, "finding.reason")
        if row["id"] in result:
            raise GauntletError(f"Duplicate accepted finding: {row['id']}", 4)
        result[row["id"]] = row["reason"]
    return result


def apply(
    findings: list[Finding],
    config: Config,
    accept: dict[str, str],
    changed: list[str],
    mode: str,
    changed_lines: dict | None = None,
) -> list[str]:
    policy = config.policy
    for finding in findings:
        if finding.rule == "crap-score":
            score = finding.metadata["crap"]
            finding.severity = (
                "warning" if score > policy.crap_threshold else "review" if score > 5 else "info"
            )
            touched = finding.location.file in changed
            if changed_lines is not None and finding.location.line is not None:
                start, end = (
                    finding.location.line,
                    finding.location.end_line or finding.location.line,
                )
                touched = any(
                    a <= end and b >= start for a, b in changed_lines.get(finding.location.file, [])
                )
            finding.blocking = bool(
                policy.block_crap_regressions and touched and score > policy.crap_threshold
            )
            finding.metadata["changed"] = touched
        elif finding.rule == "surviving-mutant":
            finding.blocking = policy.block_surviving_mutants
        elif finding.rule == "structural-duplication":
            finding.blocking = policy.block_duplicate_candidates
        if finding.id in accept:
            finding.accepted = True
            finding.blocking = False
            finding.metadata["acceptance_reason"] = accept[finding.id]
    unknown = sorted(set(accept) - {finding.id for finding in findings})
    return [f"Accepted finding was not observed in this run: {identity}" for identity in unknown]
