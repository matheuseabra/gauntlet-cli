import shlex
import shutil
import sys
from pathlib import Path

from gauntlet import git, support
from gauntlet.adapters.base import resolve
from gauntlet.config import TOOLS, load
from gauntlet.discovery import detect
from gauntlet.errors import GauntletError
from gauntlet.models import Results, RunContext
from gauntlet.pipeline.coverage import artifacts
from gauntlet.pipeline.policy import accepted


def command_executable(command: str, root: Path) -> bool:
    """Check the launch executable only; never execute repository commands in doctor."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    while tokens and "=" in tokens[0] and not tokens[0].startswith("/"):
        tokens.pop(0)
    if not tokens:
        return False
    executable = tokens[0]
    if "/" in executable or "\\" in executable:
        import os

        path = root / executable
        return path.is_file() and os.access(path, os.X_OK)
    return shutil.which(executable) is not None


def python_compatible(version: tuple[int, int]) -> bool:
    return version >= (3, 12)


def _analyze_tools(results: Results, context: RunContext) -> None:
    for name in TOOLS:
        if not context.config.tools[name].enabled:
            results.checks[name] = "disabled"
            continue
        try:
            results.diagnostics.append(f"{name}: {resolve(name, context)}")
            results.checks[name] = "passed"
        except GauntletError as exc:
            results.checks[name] = "missing"
            results.diagnostics.append(str(exc))
            results.exit_code = 5


def _project_checks(results: Results, root: Path, project, config, context) -> None:
    if project.package_manager:
        ready = shutil.which(project.package_manager) is not None
        check_name = (
            "python-package-manager"
            if project.package_manager == "python"
            else project.package_manager
        )
        results.checks[check_name] = "passed" if ready else "missing"
        if not ready:
            results.exit_code = 5
            results.diagnostics.append(
                f"Install project package manager: {project.package_manager}"
            )
    commands = project.commands | config.commands
    for name in ("test", "coverage"):
        if name not in commands:
            results.checks[name] = "unconfigured"
            results.diagnostics.append(f"No inferred commands.{name}; configure it explicitly.")
            continue
        ready = command_executable(commands[name], root)
        results.checks[name] = "available" if ready else "missing"
        if not ready:
            results.exit_code = 5
            results.diagnostics.append(f"Launch executable missing for commands.{name}")
    reports = artifacts(root)
    results.checks["coverage-artifact"] = "present" if reports else "not-generated"
    results.diagnostics.extend(f"Coverage: {p.relative_to(root)}" for p in reports)
    analyzers_enabled = any(config.tools[name].enabled for name in ("crapper", "mutator"))
    if not reports and "coverage" not in commands and analyzers_enabled:
        results.exit_code = 5
        results.diagnostics.append("Generate coverage or configure commands.coverage before check.")


def diagnose(directory: Path) -> Results:
    results = Results({"root": str(directory), "command": "doctor"})
    try:
        root = git.root(directory)
        results.repository["root"] = str(root)
        results.checks["git"] = "passed"
        results.checks["python"] = (
            "passed" if python_compatible(sys.version_info[:2]) else "incompatible"
        )
        results.diagnostics.append(f"Python {sys.version.split()[0]}")
        if results.checks["python"] == "incompatible":
            results.exit_code = 5
            results.diagnostics.append("Gauntlet requires Python 3.12 or newer.")
        config = load(root)
        accepted(root)
        results.checks["configuration"] = "passed"
        support.require(root, git.changed_files(root), config)
        results.checks["language-support"] = "passed"
        project = detect(root)
        context = RunContext(root, "changed", [], [], config)
        _analyze_tools(results, context)
        _project_checks(results, root, project, config, context)
    except GauntletError as exc:
        results.exit_code = exc.code
        results.diagnostics.append(str(exc))
        results.checks[exc.check or "discovery"] = "error"
    except (ValueError, OSError) as exc:
        results.exit_code = 4
        results.diagnostics.append(f"Invalid project metadata: {exc}")
    results.status = "failed" if results.exit_code else "passed"
    if not results.exit_code:
        results.diagnostics.append(
            "Gauntlet is ready. Doctor checks executable presence; it does "
            "not run tests or verify analyzer dependency imports."
        )
    return results
