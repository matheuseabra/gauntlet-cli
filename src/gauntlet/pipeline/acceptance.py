"""Reasoned, time-bounded exceptions; hygiene findings never suppress evidence."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from gauntlet.config import read_toml, table, validate
from gauntlet.errors import GauntletError
from gauntlet.models import Finding, Location, stable_id


@dataclass(frozen=True)
class Acceptance:
    reason: str
    expires: date | None = None


def accepted(root: Path) -> dict[str, Acceptance]:
    path = root / ".gauntlet/accept.toml"
    if not path.exists():
        return {}
    data = table(read_toml(path), {"finding"}, "acceptance")
    rows = data.get("finding", [])
    if not isinstance(rows, list):
        raise GauntletError("accept.toml requires [[finding]] entries", 4)
    result = {}
    for raw in rows:
        row = table(raw, {"id", "reason", "expires"}, "accepted finding")
        validate(row.get("id"), str, "finding.id")
        validate(row.get("reason"), str, "finding.reason")
        if row["id"] in result:
            raise GauntletError(f"Duplicate accepted finding: {row['id']}", 4)
        result[row["id"]] = Acceptance(row["reason"], expiry(row.get("expires")))
    return result


def expiry(value: object) -> date | None:
    if value is None:
        return None
    if type(value) is date:
        return value
    try:
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError("expected YYYY-MM-DD")
        return date.fromisoformat(value)
    except ValueError as exc:
        raise GauntletError("finding.expires must be a date in YYYY-MM-DD format", 4) from exc


def apply_acceptances(
    findings: list[Finding], accept: dict, today: date | None = None
) -> list[str]:
    today = today or datetime.now(UTC).date()
    observed = {finding.id for finding in findings}
    reviews = []
    diagnostics = []
    for identity, raw in sorted(accept.items()):
        entry = Acceptance(raw) if isinstance(raw, str) else raw
        expired = entry.expires is not None and entry.expires < today
        if expired or identity not in observed:
            rule = "expired-acceptance" if expired else "orphaned-acceptance"
            message = (
                f"Acceptance {identity} expired on {entry.expires}; "
                "it no longer suppresses findings."
                if expired
                else f"Acceptance {identity} was not observed in this scope; "
                "review whether it is orphaned or the source was not selected."
            )
            reviews.append(
                Finding(
                    stable_id("gauntlet", rule, identity),
                    "gauntlet",
                    rule,
                    "review",
                    Location(".gauntlet/accept.toml"),
                    message,
                    {
                        "finding_id": identity,
                        "reason": entry.reason,
                        "expires": str(entry.expires) if entry.expires else None,
                        "observed_in_scope": identity in observed,
                    },
                )
            )
            diagnostics.append(message)
        if not expired:
            for finding in findings:
                if finding.id == identity:
                    finding.accepted, finding.blocking = True, False
                    finding.metadata["acceptance_reason"] = entry.reason
                    finding.metadata["acceptance_expires"] = (
                        str(entry.expires) if entry.expires else None
                    )
    findings.extend(reviews)
    return diagnostics
