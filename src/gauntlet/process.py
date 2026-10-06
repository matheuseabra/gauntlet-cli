"""All subprocess execution, including trusted repository shell commands."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from gauntlet.errors import GauntletError


@dataclass(frozen=True)
class ProcessResult:
    command: list[str]
    cwd: Path
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False


def _stop(process: subprocess.Popen) -> None:
    # Stop the complete tree: a timed-out test must not keep a worker alive.
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        process.kill()


def run(
    command: list[str], cwd: Path, timeout: float = 120, env: dict[str, str] | None = None
) -> ProcessResult:
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=os.name == "posix",
        )
    except (FileNotFoundError, PermissionError) as exc:
        raise GauntletError(f"Executable not found: {command[0]}", 5) from exc
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
        _stop(process)
        stdout, stderr = process.communicate()
        if isinstance(exc, KeyboardInterrupt):
            raise
        timed_out = True
    return ProcessResult(
        command,
        cwd,
        process.returncode,
        stdout,
        stderr,
        round((time.monotonic() - started) * 1000),
        timed_out,
    )


def run_shell(
    command: str, cwd: Path, timeout: float, env: dict[str, str] | None = None
) -> ProcessResult:
    """Only explicitly trusted configured commands use a shell."""
    argv = ["/bin/sh", "-c", command] if os.name == "posix" else ["cmd", "/c", command]
    return run(argv, cwd, timeout, env=env)
