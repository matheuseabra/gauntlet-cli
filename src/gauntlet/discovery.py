from __future__ import annotations

import json
import shlex
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from gauntlet.errors import GauntletError

LANGUAGES = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".clj": "clojure",
    ".cljc": "clojure",
    ".cljs": "clojure",
    ".bb": "clojure",
}
SKIP = {
    ".git",
    ".gauntlet",
    ".metrics",
    ".venv",
    ".clj-kondo",
    ".hg",
    ".idea",
    ".svn",
    "venv",
    "node_modules",
    "target",
    "dist",
    "build",
    "vendor",
    "testdata",
    "out",
    "__pycache__",
    "coverage",
    "tests",
    "test",
    "spec",
    "specs",
    "__tests__",
}


@dataclass(frozen=True)
class Project:
    languages: list[str] = field(default_factory=list)
    package_manager: str | None = None
    test_framework: str | None = None
    commands: dict[str, str] = field(default_factory=dict)


def source_file(name: str) -> bool:
    path = Path(name)
    if (
        path.suffix not in LANGUAGES
        or path.name.endswith(".d.ts")
        or any(part in SKIP for part in path.parts)
    ):
        return False
    if path.name == "conftest.py" or path.name.startswith("test_"):
        return False
    return not any(marker in path.name for marker in (".test.", ".spec.", "_test.", "_spec."))


def source_files(root: Path) -> list[str]:
    # Walk prunes dependency/build trees rather than traversing them first.
    import os

    found = []
    for directory, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(d for d in directories if d not in SKIP)
        for name in files:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if source_file(relative) and path.resolve().is_relative_to(root):
                found.append(relative)
    return sorted(found)


def _node(root: Path) -> Project:
    try:
        package = json.loads((root / "package.json").read_text())
        scripts = package.get("scripts", {})
        dependencies = package.get("dependencies", {}) | package.get("devDependencies", {})
        if not isinstance(scripts, dict) or not all(isinstance(v, str) for v in scripts.values()):
            raise ValueError("scripts must contain string commands")
    except (ValueError, TypeError, AttributeError) as exc:
        raise GauntletError(f"Invalid package.json: {exc}", 4) from exc
    manager = "npm"
    for candidate, locks in (
        ("bun", ("bun.lock", "bun.lockb")),
        ("pnpm", ("pnpm-lock.yaml",)),
        ("yarn", ("yarn.lock",)),
    ):
        if any((root / lock).exists() for lock in locks):
            manager = candidate
            break
    declared = package.get("packageManager", "")
    if isinstance(declared, str) and declared.split("@")[0] in {"npm", "bun", "pnpm", "yarn"}:
        manager = declared.split("@")[0]
    framework = next((name for name in ("vitest", "jest", "mocha") if name in dependencies), None)
    commands = {key: f"{manager} run {key}" for key in ("test", "coverage") if key in scripts}
    languages = (
        ["typescript"]
        if "typescript" in dependencies or (root / "tsconfig.json").exists()
        else ["javascript"]
    )
    return Project(languages, manager, framework, commands)


def python_command(root: Path) -> str:
    for path in (
        root / ".venv/bin/python",
        root / "venv/bin/python",
        root / ".venv/Scripts/python.exe",
    ):
        if path.is_file():
            return shlex.quote(str(path))
    return shlex.quote(sys.executable)


def _python(root: Path) -> Project:
    path = root / "pyproject.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (tomllib.TOMLDecodeError, UnicodeError) as exc:
        raise GauntletError(f"Invalid pyproject.toml: {exc}", 4) from exc
    requirements = (
        (root / "requirements.txt").read_text() if (root / "requirements.txt").exists() else ""
    )
    pytest = (
        "pytest" in data.get("tool", {})
        or "pytest" in str(data.get("project", {}))
        or "pytest" in requirements
    )
    framework = "pytest" if pytest else "unittest"
    test = "-m pytest" if pytest else "-m unittest discover -s tests"
    python = python_command(root)
    return Project(
        ["python"],
        "uv" if (root / "uv.lock").exists() else "python",
        framework,
        {
            "test": f"{python} {test}",
            "coverage": f"{python} -m coverage run {test} && {python} -m coverage lcov "
            "-o target/coverage/python/lcov.info",
        },
    )


def detect(root: Path) -> Project:
    if (root / "package.json").exists():
        return _node(root)
    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
        return _python(root)
    if (root / "go.mod").exists():
        return Project(
            ["go"],
            "go",
            "go test",
            {
                "test": "go test ./...",
                "coverage": "go test ./... -coverprofile=coverage.out",
            },
        )
    if (root / "Cargo.toml").exists():
        return Project(
            ["rust"],
            "cargo",
            "cargo test",
            {
                "test": "cargo test",
                "coverage": "cargo llvm-cov --lcov --output-path target/coverage/rust/lcov.info",
            },
        )
    if (root / "pom.xml").exists():
        return Project(["java"], "mvn", "maven", {"test": "mvn -q test"})
    return Project()
