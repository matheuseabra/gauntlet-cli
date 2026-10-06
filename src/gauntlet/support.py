"""Capability preflight for the reviewed analyzer revisions; no source analysis."""

from pathlib import Path

from gauntlet.config import Config
from gauntlet.discovery import LANGUAGES, SKIP
from gauntlet.errors import GauntletError
from gauntlet.scope import included

# These extensions identify code, not analyzer support. Unknown assets remain outside scope.
UNSUPPORTED = {
    ".swift": "Swift",
    ".c": "C",
    ".h": "C/C++",
    ".cpp": "C++",
    ".cc": "C++",
    ".hpp": "C++",
    ".cs": "C#",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".dart": "Dart",
    ".scala": "Scala",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".sh": "Shell",
    ".bash": "Shell",
    ".sql": "SQL",
    ".cljd": "ClojureDart",
    ".vue": "Vue SFC",
    ".svelte": "Svelte",
    ".m": "Objective-C",
    ".mm": "Objective-C++",
}
SUPPORTED = {
    "crapper": set(LANGUAGES.values()),
    "mutator": set(LANGUAGES.values()),
    "dryer": set(LANGUAGES.values()) - {"javascript"},
}


def candidates(root: Path) -> list[str]:
    import os

    files = []
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        for name in names:
            path = Path(directory) / name
            if path.suffix in UNSUPPORTED or path.suffix in LANGUAGES:
                files.append(path.relative_to(root).as_posix())
    return sorted(files)


def require(root: Path, files: list[str], config: Config, paths: list[str] = ()) -> None:
    limits = [Path(path).resolve() for path in paths]
    failures = []
    for name in files:
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            continue
        if not included(name, config) or (
            limits and not any(path == limit or path.is_relative_to(limit) for limit in limits)
        ):
            continue
        suffix = path.suffix
        if suffix in UNSUPPORTED:
            failures.append(f"{name}: {UNSUPPORTED[suffix]} is unsupported by Gauntlet")
        elif suffix in LANGUAGES:
            language = LANGUAGES[suffix]
            missing = [
                tool
                for tool, supported in SUPPORTED.items()
                if config.tools[tool].enabled and language not in supported
            ]
            if missing:
                failures.append(f"{name}: {language} is unsupported by {', '.join(missing)}")
    if failures:
        raise GauntletError(
            "Unsupported language preflight: "
            + "; ".join(failures)
            + ". See docs/language-support.md; run native validation for these files.",
            4,
            "language-support",
        )
