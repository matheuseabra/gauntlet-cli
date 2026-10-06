from gauntlet.config import Config
from gauntlet.models import Finding
from gauntlet.pipeline import crap
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
            crap.apply(finding, config, changed, changed_lines)
        elif finding.rule == "surviving-mutant":
            finding.blocking = policy.block_surviving_mutants
        elif finding.rule == "structural-duplication":
            finding.blocking = policy.block_duplicate_candidates
    return apply_acceptances(findings, accept)
