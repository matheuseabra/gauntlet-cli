from gauntlet.config import Config
from gauntlet.models import Finding
from gauntlet.pipeline.acceptance import accepted as accepted
from gauntlet.pipeline.acceptance import apply_acceptances


def apply(
    findings: list[Finding],
    config: Config,
    accept: dict,
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
    return apply_acceptances(findings, accept)
