"""Path policy and transparent CRAP formula guidance, not an effort estimator."""

from gauntlet.config import Config
from gauntlet.models import Finding
from gauntlet.scope import matches

GUIDANCE = (
    "Do not split functions solely to lower the score. Preserve observable behavior; "
    "choose meaningful tests or a cohesive simplification based on the specification."
)


def lever(metadata: dict, threshold: float) -> dict:
    complexity, coverage = metadata.get("cyclomatic_complexity"), metadata.get("coverage_percent")
    if complexity is None or coverage is None:
        return {"recommended_lever": "unverified", "lever_reason": "Metrics unavailable."}
    if complexity > threshold:
        return {
            "recommended_lever": "reduce-complexity",
            "required_coverage_percent": None,
            "lever_reason": "Even 100% coverage leaves CRAP equal to complexity, above threshold.",
        }
    target = max(0.0, min(100.0, 100 * (1 - ((threshold - complexity) / complexity**2) ** (1 / 3))))
    return {
        "recommended_lever": "meaningful-tests" if coverage < target else "none-required",
        "required_coverage_percent": round(target, 2),
        "lever_reason": "Coverage can reach the threshold without structural changes. "
        "This formula estimates score leverage, not engineering effort.",
    }


def apply(finding: Finding, config: Config, changed: list[str], ranges: dict | None) -> None:
    policy = config.policy
    threshold, mode, glob = policy.crap_threshold, "block", None
    for rule in policy.crap_paths:
        if matches(finding.location.file or "", (rule.glob,)):
            threshold, mode, glob = rule.threshold, rule.mode, rule.glob
            break
    score = finding.metadata["crap"]
    touched = finding.location.file in changed
    if ranges is not None and finding.location.line is not None:
        start, end = finding.location.line, finding.location.end_line or finding.location.line
        touched = any(a <= end and b >= start for a, b in ranges.get(finding.location.file, []))
    finding.severity = (
        "review"
        if mode == "review" and score > threshold
        else "warning"
        if score > threshold
        else "review"
        if score > 5
        else "info"
    )
    finding.blocking = bool(
        policy.block_crap_regressions and mode == "block" and touched and score > threshold
    )
    finding.metadata.update(
        changed=touched,
        threshold=threshold,
        policy_mode=mode,
        policy_glob=glob,
        triage_guidance=GUIDANCE,
        **lever(finding.metadata, threshold),
    )
