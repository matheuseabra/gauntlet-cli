"""Unix CLI: stdout is exclusively JSON when --json is requested."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from gauntlet import __version__, git
from gauntlet.config import DEFAULT_CONFIG, TOOLS, load
from gauntlet.discovery import detect, source_files
from gauntlet.doctor import diagnose
from gauntlet.errors import GauntletError
from gauntlet.models import Results, RunContext
from gauntlet.pipeline.runner import run
from gauntlet.reporters import json as json_reporter
from gauntlet.reporters import terminal
from gauntlet.scope import select


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise GauntletError(message, 4)


def parser() -> argparse.ArgumentParser:
    cli = Parser(description="Gauntlet — Make the code prove itself.")
    cli.add_argument("--version", action="version", version=__version__)
    commands = cli.add_subparsers(dest="command")
    for name, help_text in (
        ("check", "Run deterministic quality gates"),
        ("scan", "Inspect complexity, mutation sites, and duplication"),
    ):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("paths", nargs="*", help="Files or directories inside the repository")
        mode = sub.add_mutually_exclusive_group()
        mode.add_argument("--changed", dest="mode", action="store_const", const="changed")
        mode.add_argument("--all", dest="mode", action="store_const", const="all")
        sub.add_argument("--json", action="store_true", help="Emit only JSON to stdout")
        sub.add_argument("--output", help="JSON report path, relative to repository root")
        sub.add_argument("--quiet", action="store_true", help="Suppress terminal output")
        sub.add_argument(
            "--verbose", action="store_true", help="Print command diagnostics to stderr"
        )
        for suffix in ("crap", "mutate", "dry"):
            sub.add_argument(f"--no-{suffix}", action="store_true")
    doctor = commands.add_parser("doctor", help="Check local tool readiness without running checks")
    doctor.add_argument("--json", action="store_true")
    commands.add_parser("init", help="Create configuration without overwriting existing files")
    explain = commands.add_parser("explain", help="Explain one finding from saved results")
    explain.add_argument("finding_id")
    explain.add_argument("--input", default=".gauntlet/results.json")
    return cli


def _check(args: argparse.Namespace) -> Results:
    root = git.root(Path.cwd())
    config = load(root)
    project = detect(root)
    changed = git.changed_files(root)
    mode = args.mode or ("all" if args.paths else config.mode)
    candidates = changed if mode == "changed" else source_files(root)
    selected = select(root, candidates, config, args.paths)
    tools = dict(config.tools)
    for name, disabled in zip(TOOLS, (args.no_crap, args.no_mutate, args.no_dry), strict=True):
        tools[name] = replace(tools[name], enabled=False) if disabled else tools[name]
    config = replace(config, tools=tools, commands=project.commands | config.commands)
    native = mode == "changed" and not args.paths and not config.include and not config.exclude
    context = RunContext(
        root,
        mode,
        changed,
        selected,
        config,
        native,
        args.command == "scan",
        args.quiet,
        args.verbose,
    )
    results = run(context)
    results.repository["project"] = {
        "languages": project.languages,
        "package_manager": project.package_manager,
        "test_framework": project.test_framework,
    }
    try:
        json_reporter.write(results, root / (args.output or config.output))
    except OSError as exc:
        results.exit_code, results.status = 1, "failed"
        results.diagnostics.append(f"Cannot write results: {exc}")
    return results


def _init() -> None:
    try:
        root = git.root(Path.cwd())
    except GauntletError as exc:
        if exc.code != 4:
            raise
        root = Path.cwd()
    path = root / "gauntlet.toml"
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(DEFAULT_CONFIG)
        print(f"Created {path}")
    except FileExistsError:
        print(f"Preserved existing {path}")
    (root / ".gauntlet").mkdir(exist_ok=True)


def _explain(args: argparse.Namespace) -> None:
    root = git.root(Path.cwd())
    try:
        data = json.loads((root / args.input).read_text())
        findings = data["findings"]
        if data.get("version") != 1 or not isinstance(findings, list):
            raise ValueError("unsupported results schema")
        finding = next((f for f in findings if f["id"] == args.finding_id), None)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise GauntletError(f"Cannot read saved findings: {exc}", 4) from exc
    if finding is None:
        raise GauntletError(f"Finding not found: {args.finding_id}", 4)
    print(f"{finding['rule'].upper()}\n")
    print(json.dumps(finding["location"], indent=2))
    print(f"\n{finding['message']}\n")
    for key in ("original", "replacement", "acceptance_reason", "instruction"):
        if key in finding["metadata"]:
            print(f"{key}: {finding['metadata'][key]}")


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] not in {
        "check",
        "scan",
        "doctor",
        "init",
        "explain",
        "-h",
        "--help",
        "--version",
    }:
        arguments.insert(0, "check")
    try:
        args = parser().parse_args(arguments)
        if args.command == "init":
            _init()
            return 0
        if args.command == "explain":
            _explain(args)
            return 0
        results = diagnose(Path.cwd()) if args.command == "doctor" else _check(args)
    except GauntletError as exc:
        results = Results(
            {"root": str(Path.cwd())}, "failed", diagnostics=[str(exc)], exit_code=exc.code
        )
    except (OSError, ValueError, TypeError) as exc:
        results = Results(
            {"root": str(Path.cwd())}, "failed", diagnostics=[f"Gauntlet error: {exc}"], exit_code=1
        )
    except KeyboardInterrupt:
        results = Results(
            {"root": str(Path.cwd())},
            "failed",
            diagnostics=["Gauntlet interrupted; subprocesses were stopped."],
            exit_code=1,
        )
    if "--json" in arguments:
        print(json_reporter.render(results), end="")
    elif "--quiet" not in arguments:
        print(terminal.render(results))
    return results.exit_code
