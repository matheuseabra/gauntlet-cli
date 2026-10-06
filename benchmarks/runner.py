"""Run paired, user-supplied local agent commands and evaluate independent behavior."""

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from benchmarks.tasks import TASKS, prepare
from gauntlet.process import run, run_shell

ARM_INSTRUCTIONS = {
    "without": "Read TASK.md, implement the task, and run native tests. Do not invoke Gauntlet.",
    "with": "Read TASK.md, implement the task, and run native tests plus Gauntlet. "
    "Classify survivors as real gap / equivalent / out-of-scope. Preserve specified "
    "behavior; accept equivalents only with a concrete reason. Do not weaken checks.",
}


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def hidden_oracle(root: Path, task: dict, timeout: float) -> dict:
    with tempfile.TemporaryDirectory(prefix="gauntlet-oracle-") as directory:
        path = Path(directory) / "oracle.py"
        path.write_text(task["oracle"])
        result = run(
            [
                sys.executable,
                "-c",
                "import runpy,sys; sys.path.insert(0,sys.argv[1]); "
                "runpy.run_path(sys.argv[2],run_name='__main__')",
                str(root),
                str(path),
            ],
            root,
            timeout,
        )
        return {
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "duration_ms": result.duration_ms,
            "passed": result.exit_code == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }


def gate(root: Path, timeout: float, command: list[str]) -> dict:
    result = run(command, root, timeout)
    try:
        report = json.loads(result.stdout)
        if not isinstance(report, dict):
            raise ValueError("not an object")
    except ValueError:
        report = {}
    passed = (
        not result.timed_out
        and result.exit_code == 0
        and report.get("status") == "passed"
        and report.get("exit_code") == 0
    )
    return {
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "duration_ms": result.duration_ms,
        "passed": passed,
        "report": report,
        "stderr": result.stderr,
    }


def run_case(
    task: dict, arm: str, command: str, repetition: int, timeout: float, gate_command: list[str]
) -> dict:
    with tempfile.TemporaryDirectory(prefix="gauntlet-evaluation-") as directory:
        root = Path(directory)
        prepare(root, task)
        git(root, "init", "-q")
        git(root, "add", ".")
        git(
            root,
            "-c",
            "user.name=Evaluation",
            "-c",
            "user.email=evaluation@example.invalid",
            "commit",
            "-qm",
            "fixed task baseline",
        )
        # Commands see the same task and only the arm instruction differs. No hidden checks
        # are written in their working tree; this is not an adversarial isolation boundary.
        environment = os.environ.copy()
        environment.update(
            GAUNTLET_EVAL_TASK_ID=task["id"],
            GAUNTLET_EVAL_MODE=arm,
            GAUNTLET_EVAL_INSTRUCTIONS=ARM_INSTRUCTIONS[arm],
        )
        started = time.monotonic()
        result = subprocess_subject(command, root, environment, timeout)
        diff = run(["git", "diff", "--stat"], root)
        oracle = hidden_oracle(root, task, timeout)
        evidence = gate(root, timeout, gate_command)
        second = gate(root, timeout, gate_command) if arm == "with" else None
        return {
            "task_id": task["id"],
            "arm": arm,
            "repetition": repetition,
            "subject_exit": result.exit_code,
            "subject_timed_out": result.timed_out,
            "subject_duration_ms": result.duration_ms,
            "subject_stdout": result.stdout,
            "subject_stderr": result.stderr,
            "total_duration_ms": round((time.monotonic() - started) * 1000),
            "diff_stat": diff.stdout,
            "oracle": oracle,
            "gate": evidence,
            "gate_repeat": second,
            "gate_passed_oracle_failed": evidence["passed"] and not oracle["passed"],
            "oracle_passed_gate_blocked": oracle["passed"] and evidence["exit_code"] == 3,
        }


def subprocess_subject(command: str, root: Path, environment: dict, timeout: float):
    # Use the shared process-group cleanup while passing only task-specific environment.
    return run_shell(command, root, timeout, env=environment)


def summarize(records: list[dict]) -> dict:
    return {
        arm: {
            "runs": sum(r["arm"] == arm for r in records),
            "oracle_passes": sum(r["arm"] == arm and r["oracle"]["passed"] for r in records),
            "gate_passed_oracle_failed": sum(
                r["arm"] == arm and r["gate_passed_oracle_failed"] for r in records
            ),
            "oracle_passed_gate_blocked": sum(
                r["arm"] == arm and r["oracle_passed_gate_blocked"] for r in records
            ),
        }
        for arm in ("without", "with")
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--without", required=True, help="Trusted baseline agent shell command")
    parser.add_argument(
        "--with", dest="with_command", required=True, help="Trusted gated agent command"
    )
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--output", required=True)
    parser.add_argument("--subject-kind", choices=["scripted-proxy", "ai-agent"], required=True)
    args = parser.parse_args()
    if args.repetitions < 1 or args.timeout <= 0 or not math.isfinite(args.timeout):
        parser.error("positive repetitions and timeout required")
    records = []
    for repetition in range(args.repetitions):
        for task in TASKS:
            arms = ("without", "with") if repetition % 2 == 0 else ("with", "without")
            for arm in arms:
                command = args.without if arm == "without" else args.with_command
                print(f"{task['id']} {arm} repetition {repetition}", file=sys.stderr, flush=True)
                records.append(
                    run_case(
                        task,
                        arm,
                        command,
                        repetition,
                        args.timeout,
                        [sys.executable, "-m", "gauntlet", "check", "--all", "--json"],
                    )
                )
    output = {
        "version": 1,
        "subject_kind": args.subject_kind,
        "commands": {"without": args.without, "with": args.with_command},
        "tasks_hash": hashlib.sha256(json.dumps(TASKS, sort_keys=True).encode()).hexdigest(),
        "records": records,
        "summary": summarize(records),
        "limitations": [
            "Two diagnostic Python tasks; not a representative benchmark.",
            "No model is invoked by the harness; supplied commands identify the subject.",
            "Gate pass is separate from held-out behavioral correctness.",
            "Hidden oracles are outside the subject tree, not adversarially isolated.",
            "Different commands/repair strategies and shared runtime caches confound causality.",
            "No AI-agent effectiveness claim follows from scripted-proxy results.",
        ],
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
