from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from gauntlet.errors import GauntletError
from gauntlet.models import Finding, RunContext
from gauntlet.process import ProcessResult, run


@dataclass
class ToolResult:
    findings: list[Finding] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    status: str = "passed"


class ToolAdapter(Protocol):
    name: str

    def available(self, context: RunContext) -> bool: ...
    def run(self, context: RunContext) -> ToolResult: ...


def resolve(name: str, context: RunContext) -> str:
    executable = shutil.which(name)
    if executable:
        return executable
    config = context.config.tools[name]
    candidates = []
    if config.command:
        candidates.append(context.root / config.command)
    if config.checkout:
        # Use an installed CLI; upstream bootstrap scripts may install dependencies.
        candidates.append(context.root / config.checkout / ".venv" / "bin" / name)
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path.resolve())
    raise GauntletError(
        f"{name} is missing. Install https://github.com/unclebob/{name} into a local "
        f"environment and add its bin directory to PATH, or set tools.{name}.command "
        "to the installed executable. Gauntlet does not install tools.",
        5,
        name,
    )


def selection(context: RunContext) -> list[str]:
    if context.native_changed:
        return ["--changed"]
    # Absolute paths cannot become switches or shell expressions.
    return [str(context.root / name) for name in context.selected_files]


def execute(
    name: str, args: list[str], context: RunContext, allowed: tuple[int, ...] = (0,)
) -> ProcessResult:
    command = [resolve(name, context), "--root", str(context.root), *args]
    result = run(command, context.root, context.config.tools[name].timeout)
    if context.verbose:
        print(f"[{name}] {' '.join(command)}", file=sys.stderr)
        print(result.stdout, file=sys.stderr, end="")
        print(result.stderr, file=sys.stderr, end="")
    if result.timed_out:
        raise GauntletError(f"{name} timed out. Adjust tools.{name}.timeout.", 1, name)
    if result.exit_code not in allowed:
        raise GauntletError(
            f"{name} exited {result.exit_code}; run it directly or use --verbose for diagnostics.",
            1,
            name,
        )
    return result


def signature(path: Path) -> tuple | None:
    if not path.exists():
        return None
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size, stat.st_ino


def fresh(path: Path, before: tuple | None) -> None:
    after = signature(path)
    if after is None or after == before:
        raise GauntletError(f"Tool did not write a fresh report: {path.name}", 1)


class Adapter:
    name: str

    def available(self, context: RunContext) -> bool:
        try:
            resolve(self.name, context)
            return True
        except GauntletError:
            return False
