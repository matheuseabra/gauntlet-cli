"""Strict, versioned configuration. Unknown keys are errors, not silent typos."""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from gauntlet.errors import GauntletError

COMMANDS = ("format", "lint", "typecheck", "test", "coverage")
TOOLS = ("crapper", "mutator", "dryer")


@dataclass(frozen=True)
class ToolConfig:
    enabled: bool = True
    command: str | None = None
    checkout: str | None = None
    threshold: float = 30
    max_workers: int = 4
    min_lines: int = 4
    min_nodes: int = 20
    timeout: float = 600


@dataclass(frozen=True)
class Policy:
    crap_threshold: float = 30
    block_crap_regressions: bool = True
    block_surviving_mutants: bool = True
    block_duplicate_candidates: bool = False


@dataclass(frozen=True)
class Config:
    mode: str = "changed"
    output: str = ".gauntlet/results.json"
    timeout: float = 120
    commands: dict[str, str] = field(default_factory=dict)
    tools: dict[str, ToolConfig] = field(
        default_factory=lambda: {
            name: ToolConfig(threshold=0.82 if name == "dryer" else 30) for name in TOOLS
        }
    )
    policy: Policy = field(default_factory=Policy)
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


def read_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeError, OSError) as exc:
        raise GauntletError(f"Cannot read {path.name}: {exc}", 4) from exc


def table(value: object, allowed: set[str], name: str) -> dict:
    if not isinstance(value, dict):
        raise GauntletError(f"{name} must be a TOML table", 4)
    unknown = set(value) - allowed
    if unknown:
        raise GauntletError(f"Unknown keys in {name}: {', '.join(sorted(unknown))}", 4)
    return value


def validate(value: object, kind: type, name: str, minimum: float | None = None) -> None:
    valid = type(value) is kind
    if kind is float:
        valid = type(value) in (float, int) and math.isfinite(value)
    if not valid or (minimum is not None and value < minimum):
        raise GauntletError(
            f"Invalid {name}: expected {kind.__name__}"
            + (f" >= {minimum}" if minimum is not None else ""),
            4,
        )
    if kind is str and not value.strip():
        raise GauntletError(f"{name} must not be empty", 4)


def _tool(name: str, raw: dict) -> ToolConfig:
    fields = {"enabled", "command", "checkout", "timeout"}
    fields |= {
        "crapper": {"threshold"},
        "mutator": {"max_workers"},
        "dryer": {"threshold", "min_lines", "min_nodes"},
    }[name]
    raw = table(raw, fields, f"tools.{name}")
    for key, value in raw.items():
        if key == "enabled":
            validate(value, bool, f"tools.{name}.{key}")
        elif key in {"command", "checkout"}:
            validate(value, str, f"tools.{name}.{key}")
        elif key in {"max_workers", "min_lines", "min_nodes"}:
            validate(value, int, f"tools.{name}.{key}", 1)
        else:
            validate(value, float, f"tools.{name}.{key}", 0.001 if key == "timeout" else 0)
    if name == "dryer" and raw.get("threshold", 0.82) > 1:
        raise GauntletError("tools.dryer.threshold must be between 0 and 1", 4)
    return ToolConfig(**{"threshold": 0.82 if name == "dryer" else 30, **raw})


def _patterns(raw: dict, key: str) -> tuple[str, ...]:
    values = raw.get(key, [])
    if not isinstance(values, list):
        raise GauntletError(f"scope.{key} must be an array of patterns", 4)
    for value in values:
        validate(value, str, f"scope.{key}")
    return tuple(values)


def load(root: Path) -> Config:
    path = root / "gauntlet.toml"
    if not path.exists():
        return Config()
    raw = table(
        read_toml(path),
        {"version", "gauntlet", "commands", "tools", "policy", "scope"},
        "configuration",
    )
    if type(raw.get("version", 1)) is not int or raw.get("version", 1) != 1:
        raise GauntletError("Unsupported configuration version; expected version = 1", 4)
    options = table(raw.get("gauntlet", {}), {"mode", "output", "timeout", "commands"}, "gauntlet")
    for key in ("mode", "output"):
        if key in options:
            validate(options[key], str, f"gauntlet.{key}")
    if options.get("mode", "changed") not in {"changed", "all"}:
        raise GauntletError("gauntlet.mode must be changed or all", 4)
    if "timeout" in options:
        validate(options["timeout"], float, "gauntlet.timeout", 0.001)
    if "commands" in raw and "commands" in options:
        raise GauntletError("Use either [commands] or [gauntlet.commands], not both", 4)
    commands = table(raw.get("commands", options.get("commands", {})), set(COMMANDS), "commands")
    for key, value in commands.items():
        validate(value, str, f"commands.{key}")
    tools = table(raw.get("tools", {}), set(TOOLS), "tools")
    tool_configs = {name: _tool(name, tools.get(name, {})) for name in TOOLS}
    policy = table(raw.get("policy", {}), set(Policy.__dataclass_fields__), "policy")
    for key, value in policy.items():
        validate(
            value,
            float if key == "crap_threshold" else bool,
            f"policy.{key}",
            0 if key == "crap_threshold" else None,
        )
    policy = {"crap_threshold": tool_configs["crapper"].threshold, **policy}
    scope = table(raw.get("scope", {}), {"include", "exclude"}, "scope")
    return Config(
        mode=options.get("mode", "changed"),
        output=options.get("output", ".gauntlet/results.json"),
        timeout=options.get("timeout", 120),
        commands=commands,
        tools=tool_configs,
        policy=Policy(**policy),
        include=_patterns(scope, "include"),
        exclude=_patterns(scope, "exclude"),
    )


DEFAULT_CONFIG = """version = 1

[gauntlet]
mode = "changed"
output = ".gauntlet/results.json"
timeout = 120

# Commands are trusted local shell commands, run in repository root.
# [commands]
# test = "python -m pytest"
# coverage = "python -m coverage run -m pytest && python -m coverage lcov"

[tools.crapper]
enabled = true
threshold = 30

[tools.mutator]
enabled = true
max_workers = 4
timeout = 600

[tools.dryer]
enabled = true
threshold = 0.82
min_lines = 4
min_nodes = 20

[policy]
block_surviving_mutants = true
block_crap_regressions = true
block_duplicate_candidates = false
"""
