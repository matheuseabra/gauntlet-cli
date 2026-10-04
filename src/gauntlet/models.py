from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from gauntlet.config import Config

Severity = Literal["info", "review", "warning", "error"]
MutationState = Literal[
    "killed", "survived", "uncovered", "invalid", "equivalent", "accepted", "timeout"
]
SEVERITY_ORDER = {"error": 0, "warning": 1, "review": 2, "info": 3}


def stable_id(tool: str, *identity: object) -> str:
    payload = json.dumps(identity, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return f"{tool}:{hashlib.sha256(payload.encode()).hexdigest()[:24]}"


@dataclass(frozen=True)
class Location:
    file: str | None = None
    function: str | None = None
    line: int | None = None
    end_line: int | None = None


@dataclass
class Finding:
    id: str
    tool: str
    rule: str
    severity: Severity
    location: Location
    message: str
    metadata: dict = field(default_factory=dict)
    blocking: bool = False
    accepted: bool = False


def finding_key(finding: Finding) -> tuple:
    return (
        SEVERITY_ORDER[finding.severity],
        finding.tool,
        finding.location.file or "",
        finding.location.line or 0,
        finding.id,
    )


@dataclass
class Results:
    repository: dict
    status: str = "passed"
    checks: dict[str, str] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    exit_code: int = 0
    version: int = 1

    def to_dict(self) -> dict:
        data = asdict(self)
        data["findings"] = [asdict(f) for f in sorted(self.findings, key=finding_key)]
        data["summary"] = {
            "blocking": sum(f.blocking for f in self.findings),
            "warnings": sum(f.severity == "warning" for f in self.findings),
            "reviews": sum(f.severity == "review" for f in self.findings),
            "accepted": sum(f.accepted for f in self.findings),
        }
        return data


@dataclass(frozen=True)
class RunContext:
    root: Path
    mode: Literal["changed", "all"]
    changed_files: list[str]
    selected_files: list[str]
    config: Config
    native_changed: bool = False
    scan: bool = False
    quiet: bool = False
    verbose: bool = False
    function_files: list[str] | None = None
